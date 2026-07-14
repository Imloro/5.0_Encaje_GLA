"""
Lector de "Parcela y colindantes en formato FXCC" (ZIP del Catastro).

Estructura del ZIP:
  <ref_parcela>/<ref_parcela>.dxf   geometria de la parcela
  <ref_parcela>/<ref_parcela>.asc   datos alfanumericos de la parcela
  <ref_colindante>/...              una carpeta por cada colindante

DXF: capas catastrales (PG-LP limite parcela, PG-AA area construida...).
ASC: registro alfanumerico de ancho fijo del catastro.

Produce una EntradaParcela con la parcela principal y todos los colindantes,
cada uno con su geometria y datos alfanumericos.
"""
from __future__ import annotations
import os
import re
import zipfile
import tempfile

from ...core.modelos import Parcela, Colindante
from ...domain.modelo_territorial import ModeloTerritorial, FuenteDatos
from ...geometry.linderos import segmentar_linderos
from ...geometry import _backend as g


def _parse_dxf_capas(texto: str) -> dict[str, list[list[tuple[float, float]]]]:
    """Extrae, por capa, una LISTA de polilineas (cada POLYLINE/LWPOLYLINE
    es un anillo independiente). El DXF del catastro puede tener varias
    entidades en la misma capa; no deben concatenarse."""
    tokens = [t.strip() for t in texto.replace("\r\n", "\n").split("\n") if t.strip()]
    capas: dict[str, list[list[tuple[float, float]]]] = {}
    i = 0
    n = len(tokens)

    while i < n - 1:
        if tokens[i] == "0" and tokens[i + 1] in ("POLYLINE", "LWPOLYLINE"):
            # Leer la capa de esta entidad y sus vertices hasta SEQEND/siguiente 0
            capa = "0"
            verts: list[tuple[float, float]] = []
            j = i + 2
            px = None
            while j < n - 1:
                code = tokens[j]
                val = tokens[j + 1]
                if code == "0" and val in ("VERTEX",):
                    px = None  # nuevo vertice
                elif code == "0" and val in ("SEQEND", "POLYLINE", "LWPOLYLINE",
                                             "LINE", "ENDSEC"):
                    if val in ("POLYLINE", "LWPOLYLINE", "LINE", "ENDSEC"):
                        j -= 2  # dejar que el bucle externo lo procese
                    break
                elif code == "8":
                    capa = val
                elif code == "10":
                    try:
                        px = float(val)
                    except ValueError:
                        px = None
                elif code == "20" and px is not None:
                    try:
                        verts.append((px, float(val)))
                    except ValueError:
                        pass
                    px = None
                j += 2
            if len(verts) >= 3:
                capas.setdefault(capa, []).append(verts)
            i = j
        else:
            i += 2
    return capas


def _parse_dxf_lineas(texto: str) -> dict[str, list[tuple]]:
    """Extrae segmentos LINE por capa: cada uno es ((x1,y1),(x2,y2))."""
    tokens = [t.strip() for t in texto.replace("\r\n", "\n").split("\n") if t.strip()]
    capas: dict[str, list] = {}
    i = 0
    n = len(tokens)
    while i < n - 1:
        if tokens[i] == "0" and tokens[i + 1] == "LINE":
            capa = "0"
            x1 = y1 = x2 = y2 = None
            j = i + 2
            while j < n - 1:
                code, val = tokens[j], tokens[j + 1]
                if code == "0":
                    break
                elif code == "8":
                    capa = val
                elif code == "10":
                    x1 = float(val)
                elif code == "20":
                    y1 = float(val)
                elif code == "11":
                    x2 = float(val)
                elif code == "21":
                    y2 = float(val)
                j += 2
            if None not in (x1, y1, x2, y2):
                capas.setdefault(capa, []).append(((x1, y1), (x2, y2)))
            i = j
        else:
            i += 2
    return capas


def _reconstruir_anillo(segmentos: list[tuple], tol: float = 0.01) -> list:
    """Une segmentos LINE en un anillo cerrado siguiendo extremos contiguos."""
    if not segmentos:
        return []
    segs = list(segmentos)
    anillo = list(segs.pop(0))
    cambiado = True
    while segs and cambiado:
        cambiado = False
        fin = anillo[-1]
        for k, (a, b) in enumerate(segs):
            if (abs(a[0] - fin[0]) < tol and abs(a[1] - fin[1]) < tol):
                anillo.append(b); segs.pop(k); cambiado = True; break
            if (abs(b[0] - fin[0]) < tol and abs(b[1] - fin[1]) < tol):
                anillo.append(a); segs.pop(k); cambiado = True; break
    # quitar cierre duplicado
    if len(anillo) > 1 and abs(anillo[0][0] - anillo[-1][0]) < tol \
            and abs(anillo[0][1] - anillo[-1][1]) < tol:
        anillo = anillo[:-1]
    return anillo


def _geometria_desde_dxf(texto: str) -> tuple[list, float]:
    """
    Devuelve (vertices_parcela, area_edificacion).
    La parcela (PG-LP) puede venir como POLYLINE o como segmentos LINE
    sueltos. Se toma la mejor reconstruccion (mayor area cerrada valida).
    La edificacion en PG-AA.
    """
    capas_poly = _parse_dxf_capas(texto)
    capas_line = _parse_dxf_lineas(texto)

    candidatos = []
    # Opcion 1: la mayor POLYLINE de PG-LP
    for poly in capas_poly.get("PG-LP", []):
        v = poly[:-1] if len(poly) > 1 and poly[-1] == poly[0] else poly
        if len(v) >= 3:
            candidatos.append(v)
    # Opcion 2: reconstruir desde los segmentos LINE de PG-LP
    anillo = _reconstruir_anillo(capas_line.get("PG-LP", []))
    if len(anillo) >= 3:
        candidatos.append(anillo)

    if not candidatos:
        return [], 0.0
    # El anillo valido de mayor area es la parcela
    parcela = max(candidatos, key=lambda v: g.area(v))

    # Edificacion PG-AA (poly + lineas)
    area_edif = sum(g.area(v) for v in capas_poly.get("PG-AA", []) if len(v) >= 3)
    anillo_aa = _reconstruir_anillo(capas_line.get("PG-AA", []))
    if len(anillo_aa) >= 3:
        area_edif = max(area_edif, g.area(anillo_aa))

    return parcela, area_edif


def _parse_asc(texto: str) -> dict:
    """Extrae datos alfanumericos basicos del ASC. El formato del catastro
    es de registros de ancho fijo; extraemos lo reconocible sin asumir
    posiciones exactas (varian por tipo de registro)."""
    datos = {}
    # Buscar una superficie (numero seguido de patrones tipicos)
    m = re.search(r"\b(\d{2,7})\b", texto)
    if m:
        datos["superficie_asc"] = int(m.group(1))
    # Uso: buscar palabras clave habituales
    for uso in ["INDUSTRIAL", "RESIDENCIAL", "ALMACEN", "AGRARIO",
                "COMERCIAL", "SUELO", "VIAL"]:
        if uso in texto.upper():
            datos["uso"] = uso.capitalize()
            break
    datos["asc_bruto"] = texto[:500]  # muestra para inspeccion
    return datos


def _epsg_desde_dxf(texto: str) -> int:
    # El DXF del catastro no siempre lleva CRS; por defecto 25830.
    # Se puede afinar por rango de coordenadas si hiciera falta.
    return 25830


def leer(path: str) -> ModeloTerritorial:
    """
    Lee un ZIP FXCC. Extrae la parcela principal y los colindantes.

    NOTA: la geometria de la parcela principal en el DXF del catastro
    puede venir fragmentada (segmentos LINE dispersos), por lo que su
    reconstruccion no siempre es fiable. Para la geometria de la parcela
    se recomienda usar el GML (leer_entrada con .gml) y, si se desea,
    enriquecer con colindantes via `enriquecer_con_fxcc`. Cuando solo se
    dispone del FXCC, se usa la mejor reconstruccion posible y la
    validacion avisara si la superficie no cuadra con el ASC.
    """
    return _leer_fxcc(path)


def enriquecer_con_fxcc(entrada: ModeloTerritorial, path_zip: str) -> ModeloTerritorial:
    """
    Toma un ModeloTerritorial (tipicamente de un GML, con geometria fiable)
    y le anade los colindantes extraidos del ZIP FXCC. La geometria de la
    parcela principal NO se toca: sigue siendo la del GML.
    """
    fxcc = _leer_fxcc(path_zip)
    ref_principal = entrada.parcela.referencia
    colindantes = [c for c in _todos_los_recintos(fxcc)
                   if c.referencia != ref_principal]
    entrada.colindantes = colindantes
    entrada.fuentes.append(FuenteDatos(tipo="fxcc", path=path_zip))
    return entrada


def _todos_los_recintos(fxcc: ModeloTerritorial) -> list[Colindante]:
    """Devuelve parcela principal (como colindante) + colindantes del FXCC,
    para poder filtrar por referencia al enriquecer."""
    recintos = list(fxcc.colindantes)
    p = fxcc.parcela
    recintos.append(Colindante(
        referencia=p.referencia, vertices=p.vertices, epsg=p.epsg))
    return recintos


def _leer_fxcc(path: str) -> ModeloTerritorial:
    if not zipfile.is_zipfile(path):
        raise ValueError("El archivo no es un ZIP FXCC valido.")

    parcela_obj = None
    colindantes: list[Colindante] = []

    with zipfile.ZipFile(path) as z:
        # Agrupar archivos por carpeta (= referencia catastral)
        carpetas: dict[str, dict] = {}
        for nombre in z.namelist():
            if nombre.endswith("/"):
                continue
            partes = nombre.split("/")
            if len(partes) < 2:
                continue
            ref = partes[-2]
            ext = os.path.splitext(nombre)[1].lower()
            carpetas.setdefault(ref, {})[ext] = nombre

        # La parcela principal: normalmente la primera carpeta o la que
        # coincide con el nombre del ZIP. Heuristica: la de mayor area.
        candidatos = []
        for ref, archivos in carpetas.items():
            if ".dxf" not in archivos:
                continue
            dxf_txt = z.read(archivos[".dxf"]).decode("utf-8", "ignore")
            vertices, area_edif = _geometria_desde_dxf(dxf_txt)
            if len(vertices) < 3:
                continue
            datos = {}
            if ".asc" in archivos:
                asc_txt = z.read(archivos[".asc"]).decode("latin-1", "ignore")
                datos = _parse_asc(asc_txt)
            datos["edificacion_m2"] = area_edif
            candidatos.append({
                "ref": ref, "vertices": vertices,
                "area": g.area(vertices), "datos": datos,
                "epsg": _epsg_desde_dxf(dxf_txt)})

        if not candidatos:
            raise ValueError("El ZIP FXCC no contiene geometrias validas (PG-LP).")

        # La parcela principal = la de referencia que coincide con el nombre
        # del ZIP, si existe; si no, la mayor.
        nombre_zip = os.path.splitext(os.path.basename(path))[0]
        principal = next((c for c in candidatos if c["ref"] == nombre_zip), None)
        if principal is None:
            principal = max(candidatos, key=lambda c: c["area"])

        parcela_obj = Parcela(
            referencia=principal["ref"], vertices=principal["vertices"],
            area_declarada=principal["datos"].get("superficie_asc",
                                                  principal["area"]),
            epsg=principal["epsg"])

        for c in candidatos:
            if c["ref"] == principal["ref"]:
                continue
            colindantes.append(Colindante(
                referencia=c["ref"], vertices=c["vertices"], epsg=c["epsg"],
                uso=c["datos"].get("uso"),
                superficie=c["datos"].get("superficie_asc"),
                datos_brutos=c["datos"]))

    linderos = segmentar_linderos(parcela_obj)
    return ModeloTerritorial(
        parcela=parcela_obj, linderos=linderos,
        colindantes=colindantes,
        fuentes=[FuenteDatos(tipo="fxcc", path=path)])
