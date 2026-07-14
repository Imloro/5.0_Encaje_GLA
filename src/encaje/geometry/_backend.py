"""
Backend geometrico. Usa Shapely si esta disponible (rapido, robusto,
probado por millones de usuarios). Si no, cae a implementacion pura en
Python (mas lenta pero identica en resultado para los casos de encaje).

El resto del motor SOLO habla con las funciones de este modulo, nunca
con Shapely directamente. Asi el motor es agnostico del backend.
"""
from __future__ import annotations

try:
    from shapely.geometry import Polygon as _ShapelyPolygon
    from shapely import __version__ as _shapely_version
    _HAS_SHAPELY = True
except ImportError:
    _HAS_SHAPELY = False
    _shapely_version = None


def backend_info() -> str:
    return f"shapely {_shapely_version}" if _HAS_SHAPELY else "python-puro (fallback)"


# --------------------------------------------------------------------------
# Funciones geometricas fundamentales (puras, sin dependencias)
# --------------------------------------------------------------------------

def area_con_signo(pts: list[tuple[float, float]]) -> float:
    """Area con signo (shoelace). Positiva si CCW, negativa si CW."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return a / 2.0


def area(pts: list[tuple[float, float]]) -> float:
    """Area absoluta del poligono."""
    return abs(area_con_signo(pts))


def perimetro(pts: list[tuple[float, float]]) -> float:
    import math
    n = len(pts)
    return sum(
        math.hypot(pts[(i + 1) % n][0] - pts[i][0],
                   pts[(i + 1) % n][1] - pts[i][1])
        for i in range(n)
    )


def punto_en_poligono(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting. True si (x, y) esta dentro del poligono."""
    n = len(poly)
    dentro = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro


def centroide(pts: list[tuple[float, float]]) -> tuple[float, float]:
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return cx, cy


def bbox(pts: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------
# Offset (retranqueo) — con Shapely si esta, si no fallback por segmento
# --------------------------------------------------------------------------

def offset_interior(pts: list[tuple[float, float]], r: float) -> list[tuple[float, float]]:
    """
    Desplaza el poligono r metros hacia el interior (buffer negativo).
    Devuelve la lista de vertices del poligono resultante.

    REGLA ROBUSTA: el offset interior SIEMPRE reduce el area. Si el
    resultado tuviera area mayor que el original, el sentido es erroneo.
    """
    if r <= 0:
        return list(pts)

    if _HAS_SHAPELY:
        poly = _ShapelyPolygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        result = poly.buffer(-r, join_style=2)  # 2 = mitre (conserva angulos)
        if result.is_empty:
            return []
        # Si el buffer produce multipoligono, tomar el mayor
        if result.geom_type == "MultiPolygon":
            result = max(result.geoms, key=lambda g: g.area)
        return list(result.exterior.coords)[:-1]

    # ---- Fallback puro: offset por segmento + interseccion ----
    return _offset_por_segmento(pts, r)


def _offset_por_segmento(pts: list[tuple[float, float]], r: float) -> list[tuple[float, float]]:
    import math

    def desplaza(p1, p2, sign):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        d = math.hypot(dx, dy)
        if d < 1e-9:
            return p1, p2
        nx = sign * dy / d
        ny = sign * (-dx / d)
        return (p1[0] + nx * r, p1[1] + ny * r), (p2[0] + nx * r, p2[1] + ny * r)

    def interseccion(p1, p2, p3, p4):
        dx1, dy1 = p2[0] - p1[0], p2[1] - p1[1]
        dx2, dy2 = p4[0] - p3[0], p4[1] - p3[1]
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 1e-9:
            return p3
        t = ((p3[0] - p1[0]) * dy2 - (p3[1] - p1[1]) * dx2) / den
        return (p1[0] + t * dx1, p1[1] + t * dy1)

    def construir(sign):
        n = len(pts)
        segs = [desplaza(pts[i], pts[(i + 1) % n], sign) for i in range(n)]
        out = []
        for i in range(n):
            prev = (i - 1) % n
            out.append(interseccion(segs[prev][0], segs[prev][1],
                                    segs[i][0], segs[i][1]))
        return out

    area_orig = area(pts)
    cand_pos = construir(+1)
    cand_neg = construir(-1)
    area_pos = area(cand_pos)
    area_neg = area(cand_neg)

    # Regla robusta: el offset interior reduce el area.
    # Elegir el candidato con area < original y mayor de los dos validos.
    validos = [(a, c) for a, c in [(area_pos, cand_pos), (area_neg, cand_neg)]
               if a < area_orig]
    if not validos:
        return []
    return max(validos, key=lambda x: x[0])[1]


# --------------------------------------------------------------------------
# Rectangulo minimo rotado — orientacion real de la parcela
# --------------------------------------------------------------------------

def rectangulo_minimo_rotado(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """
    Devuelve (area_minima, angulo_grados) del rectangulo de area minima
    que contiene el poligono. El angulo da la orientacion real.
    """
    import math

    if _HAS_SHAPELY:
        poly = _ShapelyPolygon(pts)
        mrr = poly.minimum_rotated_rectangle
        coords = list(mrr.exterior.coords)
        # Angulo del lado mas largo
        best_len = 0
        best_ang = 0
        for i in range(len(coords) - 1):
            dx = coords[i + 1][0] - coords[i][0]
            dy = coords[i + 1][1] - coords[i][1]
            length = math.hypot(dx, dy)
            if length > best_len:
                best_len = length
                best_ang = math.degrees(math.atan2(dy, dx))
        return mrr.area, best_ang % 180

    # Fallback: rotating calipers simplificado
    best = None
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        ang = math.atan2(pts[j][1] - pts[i][1], pts[j][0] - pts[i][0])
        c, s = math.cos(-ang), math.sin(-ang)
        rot = [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in pts]
        xs = [p[0] for p in rot]
        ys = [p[1] for p in rot]
        a = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if best is None or a < best[0]:
            best = (a, math.degrees(ang) % 180)
    return best
