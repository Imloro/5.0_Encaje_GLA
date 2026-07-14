"""
Conversion de coordenadas. Usa pyproj si esta disponible (exacto para
cualquier CRS). Si no, fallback UTM->WGS84 para husos 28-31 (peninsula
+ Canarias), suficiente para catastro espanol.
"""
from __future__ import annotations
import math

try:
    from pyproj import Transformer
    _HAS_PYPROJ = True
except ImportError:
    _HAS_PYPROJ = False


def crs_info() -> str:
    return "pyproj" if _HAS_PYPROJ else "conversion-utm-interna (fallback)"


def huso_desde_epsg(epsg: int) -> int:
    """25828->28, 25829->29, 25830->30, 25831->31."""
    if 25828 <= epsg <= 25831:
        return epsg - 25800
    return 30  # por defecto peninsula


def utm_a_wgs84(easting: float, northing: float, epsg: int = 25830) -> tuple[float, float]:
    """
    Convierte (easting, northing) en el CRS dado a (lon, lat) WGS84.
    Devuelve (longitud, latitud) en grados decimales.
    """
    if _HAS_PYPROJ:
        transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326",
                                          always_xy=True)
        lon, lat = transformer.transform(easting, northing)
        return lon, lat

    # ---- Fallback: formula UTM inversa (ETRS89/GRS80 ~ WGS84) ----
    huso = huso_desde_epsg(epsg)
    a = 6378137.0
    f = 1 / 298.257222101
    b = a * (1 - f)
    e2 = 1 - (b / a) ** 2
    k0 = 0.9996
    E0 = 500000.0
    lon0 = math.radians(-183.0 + huso * 6)  # meridiano central del huso

    x = easting - E0
    y = northing
    M = y / k0
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    N1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    T1 = math.tan(phi1) ** 2
    C1 = e2 * math.cos(phi1) ** 2 / (1 - e2)
    R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    D = x / (N1 * k0)
    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * e2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * e2 - 3 * C1 ** 2)
        * D ** 6 / 720)
    lon = lon0 + (D
                  - (1 + 2 * T1 + C1) * D ** 3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * e2 + 24 * T1 ** 2)
                  * D ** 5 / 120) / math.cos(phi1)
    return math.degrees(lon), math.degrees(lat)
