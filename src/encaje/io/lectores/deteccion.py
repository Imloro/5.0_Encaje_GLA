"""
Deteccion automatica del formato de entrada y despacho al lector correcto.
Anadir un formato nuevo (GeoJSON, SHP...) = anadir un lector y una regla
aqui. El motor no cambia.
"""
from __future__ import annotations
import os
import zipfile

from ...domain.modelo_territorial import ModeloTerritorial
from . import gml as lector_gml
from . import fxcc as lector_fxcc


def leer_entrada(path: str, fxcc: str | None = None) -> ModeloTerritorial:
    """
    Detecta el formato por extension/contenido y devuelve ModeloTerritorial.

    Si se pasa `fxcc` (ruta a un ZIP FXCC) junto a un GML, la geometria de
    la parcela se toma del GML (fiable) y los colindantes del FXCC.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el archivo: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext == ".gml":
        modelo = lector_gml.leer(path)
        if fxcc and os.path.exists(fxcc):
            modelo = lector_fxcc.enriquecer_con_fxcc(modelo, fxcc)
        return modelo
    if ext == ".zip" or zipfile.is_zipfile(path):
        return lector_fxcc.leer(path)

    raise ValueError(
        f"Formato no soportado: {ext}. Formatos actuales: .gml, .zip (FXCC).")
