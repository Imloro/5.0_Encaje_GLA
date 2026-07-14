"""
Lector de GML catastral (formato INSPIRE de la Direccion General del
Catastro). Produce un ModeloTerritorial con la parcela principal y sus
linderos segmentados.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET

from ...core.modelos import Parcela
from ...domain.modelo_territorial import ModeloTerritorial, FuenteDatos
from ...geometry.linderos import segmentar_linderos

_NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "cp": "http://inspire.ec.europa.eu/schemas/cp/4.0",
}


def _limpiar_cierre(vertices):
    if len(vertices) > 1 and vertices[-1] == vertices[0]:
        return vertices[:-1]
    return vertices


def leer(path: str) -> ModeloTerritorial:
    with open(path, "r", encoding="utf-8") as f:
        contenido = f.read()

    epsg = 25830
    m = re.search(r"EPSG/0/(\d+)", contenido)
    if m:
        epsg = int(m.group(1))

    try:
        root = ET.fromstring(contenido)
    except ET.ParseError as e:
        raise ValueError(f"GML mal formado: {e}")

    ref_el = root.find(".//cp:nationalCadastralReference", _NS)
    referencia = ref_el.text if ref_el is not None else "desconocida"

    area_el = root.find(".//cp:areaValue", _NS)
    area_declarada = float(area_el.text) if area_el is not None else 0.0

    pos_el = root.find(".//gml:posList", _NS)
    if pos_el is None:
        raise ValueError("No se encontro gml:posList en el GML.")
    nums = [float(x) for x in pos_el.text.split()]
    vertices = _limpiar_cierre(
        [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)])

    parcela = Parcela(referencia=referencia, vertices=vertices,
                      area_declarada=area_declarada, epsg=epsg)
    linderos = segmentar_linderos(parcela)

    return ModeloTerritorial(
        parcela=parcela,
        linderos=linderos,
        colindantes=[],
        fuentes=[FuenteDatos(tipo="gml", path=path)])
