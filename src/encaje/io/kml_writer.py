"""
Escritor de KML para Google Earth. Convierte el Resultado (coordenadas
UTM del catastro) a WGS84 y genera un KML con capas: parcela, colindantes,
poligono edificable y huella(s).
"""
from __future__ import annotations
from ..core.modelos import Resultado
from ..geometry.crs import utm_a_wgs84

_ESTILOS = """
  <Style id="parcela"><LineStyle><color>ffaa6614</color><width>2.5</width></LineStyle>
    <PolyStyle><color>1414a0eb</color></PolyStyle></Style>
  <Style id="colindante"><LineStyle><color>ff888888</color><width>1</width></LineStyle>
    <PolyStyle><color>11888888</color></PolyStyle></Style>
  <Style id="edificable"><LineStyle><color>ff0099ff</color><width>2</width></LineStyle>
    <PolyStyle><color>220099ff</color></PolyStyle></Style>
  <Style id="huella"><LineStyle><color>ffcc3300</color><width>3</width></LineStyle>
    <PolyStyle><color>990044cc</color></PolyStyle></Style>
  <Style id="huella2"><LineStyle><color>ff00aa00</color><width>3</width></LineStyle>
    <PolyStyle><color>6600aa00</color></PolyStyle></Style>
  <Style id="playa"><LineStyle><color>ff22bbdd</color><width>2</width></LineStyle>
    <PolyStyle><color>5522bbdd</color></PolyStyle></Style>
  <Style id="oficina"><LineStyle><color>ff0066cc</color><width>2</width></LineStyle>
    <PolyStyle><color>770066cc</color></PolyStyle></Style>
"""


def _coords(vertices, epsg):
    pts = list(vertices)
    if pts and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    out = []
    for x, y in pts:
        lon, lat = utm_a_wgs84(x, y, epsg)
        out.append(f"{lon:.8f},{lat:.8f},0")
    return "\n            ".join(out)


def _placemark(nombre, estilo, vertices, epsg, descripcion=""):
    desc = f"<description><![CDATA[{descripcion}]]></description>" if descripcion else ""
    return f"""    <Placemark>
      <name>{nombre}</name>{desc}
      <styleUrl>#{estilo}</styleUrl>
      <Polygon><altitudeMode>clampToGround</altitudeMode>
        <outerBoundaryIs><LinearRing><coordinates>
            {_coords(vertices, epsg)}
        </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>"""


def escribir_kml(resultado: Resultado, path: str) -> None:
    p = resultado.parcela
    epsg = p.epsg
    estado = resultado.estado.value
    partes = []

    # Colindantes primero (al fondo)
    for c in resultado.colindantes:
        if len(c.vertices) >= 3:
            info = f"<b>Ref:</b> {c.referencia}<br/>"
            if c.uso:
                info += f"<b>Uso:</b> {c.uso}<br/>"
            if c.tiene_edificacion:
                info += f"<b>Edificacion:</b> {c.datos_brutos.get('edificacion_m2',0):.0f} m2<br/>"
            partes.append(_placemark(
                f"Colindante {c.referencia}", "colindante", c.vertices, epsg, info))

    partes.append(_placemark(
        f"Parcela {p.referencia} ({p.area_calculada:,.0f} m2)",
        "parcela", p.vertices, epsg,
        f"<b>Ref:</b> {p.referencia}<br/><b>Area:</b> {p.area_calculada:,.0f} m2"))

    if resultado.poligono_edificable:
        partes.append(_placemark(
            f"Poligono edificable ({resultado.area_edificable:,.0f} m2)",
            "edificable", resultado.poligono_edificable, epsg,
            f"<b>Retranqueo:</b> {resultado.parametros.retranqueo_efectivo} m<br/>"
            f"<b>Area edificable:</b> {resultado.area_edificable:,.0f} m2"))

    for i, hu in enumerate(resultado.huellas):
        estilo = "huella" if i == 0 else "huella2"
        alcanza = "" if hu.alcanza_objetivo else " (no alcanza objetivo)"
        dims = f"{hu.dims[0]:.0f}x{hu.dims[1]:.0f}m" if hu.dims else ""
        partes.append(_placemark(
            f"GLA {hu.tipo} {hu.area:,.0f} m2{alcanza}",
            estilo, hu.poligono, epsg,
            f"<b>Tipo:</b> {hu.tipo}<br/><b>Area:</b> {hu.area:,.0f} m2<br/>"
            f"<b>Dims:</b> {dims}<br/><b>Estado:</b> {estado}"))

    # Playa de maniobra y oficinas (si hay implantacion)
    if resultado.implantacion:
        imp = resultado.implantacion
        for playa in imp.playas:
            if playa.poligono and len(playa.poligono) >= 3:
                partes.append(_placemark(
                    f"Playa {playa.tipo} ({playa.profundidad_real:.0f}m, "
                    f"{playa.area:,.0f} m2)",
                    "playa", playa.poligono, epsg,
                    f"<b>Playa de maniobra</b><br/>"
                    f"<b>Tipo:</b> {playa.tipo}<br/>"
                    f"<b>Profundidad:</b> {playa.profundidad_real:.1f} m<br/>"
                    f"<b>Area:</b> {playa.area:,.0f} m2"))
        for ofi in imp.oficinas:
            if ofi.poligono and len(ofi.poligono) >= 3:
                partes.append(_placemark(
                    f"Oficinas {ofi.tipo} ({ofi.area:,.0f} m2)",
                    "oficina", ofi.poligono, epsg,
                    f"<b>Oficinas</b><br/>"
                    f"<b>Tipo:</b> {ofi.tipo}<br/>"
                    f"<b>Area:</b> {ofi.area:,.0f} m2<br/>"
                    f"<b>Posicion:</b> {ofi.posicion}"))

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Encaje Catastral - {p.referencia}</name>
  <description>GLA {resultado.gla_objetivo:,.0f} m2 | Estado: {estado}</description>
{_ESTILOS}
  <Folder>
    <name>{p.referencia}</name>
    <open>1</open>
{chr(10).join(partes)}
  </Folder>
</Document>
</kml>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(kml)
