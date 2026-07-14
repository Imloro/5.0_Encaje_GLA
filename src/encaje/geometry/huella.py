"""
Orientacion de la nave e inscripcion de la huella dentro del poligono
edificable. Todo determinista.
"""
from __future__ import annotations
import math
from . import _backend as g


def angulo_optimo(pol_edificable: list[tuple[float, float]],
                  paso: int = 5, afinar: bool = True) -> float:
    """
    Barrido de orientaciones. Devuelve el angulo (grados) que maximiza
    el area del mayor rectangulo inscrito. La nave debe orientarse con
    la parcela, no con el Norte.
    """
    mejor_ang = 0.0
    mejor_area = 0.0
    for deg in range(0, 180, paso):
        _, a = _mayor_rectangulo_en_angulo(pol_edificable, math.radians(deg))
        if a > mejor_area:
            mejor_area = a
            mejor_ang = deg

    if afinar:
        for deg in range(int(mejor_ang) - paso + 1, int(mejor_ang) + paso):
            _, a = _mayor_rectangulo_en_angulo(pol_edificable, math.radians(deg))
            if a > mejor_area:
                mejor_area = a
                mejor_ang = deg

    return float(mejor_ang)


def _mayor_rectangulo_en_angulo(pol: list[tuple[float, float]], ang: float,
                                grid: float = 2.0):
    """Mayor rectangulo inscrito alineado al angulo dado. Devuelve
    (esquinas_en_coords_originales, area)."""
    c, s = math.cos(-ang), math.sin(-ang)
    rot = [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in pol]
    xs = [p[0] for p in rot]
    ys = [p[1] for p in rot]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    nx = int((xmax - xmin) / grid) + 1
    ny = int((ymax - ymin) / grid) + 1

    grid_bool = [[False] * ny for _ in range(nx)]
    for ix in range(nx):
        for iy in range(ny):
            x0 = xmin + ix * grid
            y0 = ymin + iy * grid
            x1 = x0 + grid
            y1 = y0 + grid
            # Una celda cuenta como interior solo si sus CUATRO esquinas
            # estan dentro del poligono. Asi el rectangulo inscrito nunca
            # sobresale (evita el error de borde del rasterizado por centro).
            if (g.punto_en_poligono(x0, y0, rot) and
                    g.punto_en_poligono(x1, y0, rot) and
                    g.punto_en_poligono(x1, y1, rot) and
                    g.punto_en_poligono(x0, y1, rot)):
                grid_bool[ix][iy] = True

    area_c, x0i, y0i, x1i, y1i = _mayor_rect_binario(grid_bool, nx, ny)
    rx0 = xmin + x0i * grid
    ry0 = ymin + y0i * grid
    rx1 = xmin + (x1i + 1) * grid
    ry1 = ymin + (y1i + 1) * grid
    corners_rot = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
    cc, ss = math.cos(ang), math.sin(ang)
    corners = [(p[0] * cc - p[1] * ss, p[0] * ss + p[1] * cc) for p in corners_rot]
    return corners, (rx1 - rx0) * (ry1 - ry0)


def _mayor_rect_binario(grid, nx, ny):
    """Mayor rectangulo de True en matriz binaria (metodo histograma)."""
    heights = [0] * ny
    best = (0, 0, 0, 0, 0)
    for ix in range(nx):
        for iy in range(ny):
            heights[iy] = heights[iy] + 1 if grid[ix][iy] else 0
        stack = []
        for iy in range(ny + 1):
            h = heights[iy] if iy < ny else 0
            start = iy
            while stack and stack[-1][1] > h:
                s_iy, s_h = stack.pop()
                a = s_h * (iy - s_iy)
                if a > best[0]:
                    best = (a, ix - s_h + 1, s_iy, ix, iy - 1)
                start = s_iy
            stack.append((start, h))
    return best


def inscribir_rectangulo(pol_edificable: list[tuple[float, float]],
                         area_objetivo: float,
                         ang: float | None = None) -> dict:
    """
    Inscribe un rectangulo de area = area_objetivo en el poligono
    edificable, orientado al angulo optimo (o al dado).
    Si el mayor rectangulo posible es menor que el objetivo, devuelve
    el mayor posible y marca alcanza=False.
    """
    if ang is None:
        ang = angulo_optimo(pol_edificable)

    corners_max, area_max = _mayor_rectangulo_en_angulo(
        pol_edificable, math.radians(ang), grid=2.0)

    alcanza = area_max >= area_objetivo

    if alcanza:
        # Recortar el rectangulo maximo al area objetivo
        c, s = math.cos(-math.radians(ang)), math.sin(-math.radians(ang))
        rot = [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in corners_max]
        xs = [p[0] for p in rot]
        ys = [p[1] for p in rot]
        rx0, rx1 = min(xs), max(xs)
        ry0, ry1 = min(ys), max(ys)
        lx, ly = rx1 - rx0, ry1 - ry0
        escala = area_objetivo / (lx * ly)
        if lx >= ly:
            rot_rect = [(rx0, ry0), (rx0 + lx * escala, ry0),
                        (rx0 + lx * escala, ry1), (rx0, ry1)]
            dims = (lx * escala, ly)
        else:
            rot_rect = [(rx0, ry0), (rx1, ry0),
                        (rx1, ry0 + ly * escala), (rx0, ry0 + ly * escala)]
            dims = (lx, ly * escala)
        cc, ss = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        corners = [(p[0] * cc - p[1] * ss, p[0] * ss + p[1] * cc) for p in rot_rect]
        return {"poligono": corners, "area": area_objetivo, "dims": dims,
                "angulo": ang, "alcanza": True}
    else:
        # Devolver el mayor rectangulo posible
        c, s = math.cos(-math.radians(ang)), math.sin(-math.radians(ang))
        rot = [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in corners_max]
        xs = [p[0] for p in rot]
        ys = [p[1] for p in rot]
        dims = (max(xs) - min(xs), max(ys) - min(ys))
        return {"poligono": corners_max, "area": area_max, "dims": dims,
                "angulo": ang, "alcanza": False}


def inscribir_huella_L(pol_edificable: list[tuple[float, float]],
                       area_objetivo: float) -> dict:
    """
    Huella ortogonal que sigue la forma del poligono edificable,
    recortada hasta alcanzar el area objetivo. Prueba corte en las
    4 direcciones y devuelve la que mejor se ajusta.
    """
    xmin, ymin, xmax, ymax = g.bbox(pol_edificable)

    def recortar_y(poly, yc, menor):
        res = []
        n = len(poly)
        for i in range(n):
            p1, p2 = poly[i], poly[(i + 1) % n]
            c1 = (p1[1] <= yc) if menor else (p1[1] >= yc)
            c2 = (p2[1] <= yc) if menor else (p2[1] >= yc)
            if c1:
                res.append(p1)
            if c1 != c2:
                t = (yc - p1[1]) / (p2[1] - p1[1])
                res.append((p1[0] + t * (p2[0] - p1[0]), yc))
        return res

    def recortar_x(poly, xc, menor):
        res = []
        n = len(poly)
        for i in range(n):
            p1, p2 = poly[i], poly[(i + 1) % n]
            c1 = (p1[0] <= xc) if menor else (p1[0] >= xc)
            c2 = (p2[0] <= xc) if menor else (p2[0] >= xc)
            if c1:
                res.append(p1)
            if c1 != c2:
                t = (xc - p1[0]) / (p2[0] - p1[0])
                res.append((xc, p1[1] + t * (p2[1] - p1[1])))
        return res

    def area_recorte(recorte_fn, corte, menor):
        h = recorte_fn(pol_edificable, corte, menor)
        return g.area(h) if len(h) >= 3 else 0

    def buscar(recorte_fn, lo, hi, menor):
        for _ in range(30):
            mid = (lo + hi) / 2
            a = area_recorte(recorte_fn, mid, menor)
            if menor:
                if a < area_objetivo:
                    lo = mid
                else:
                    hi = mid
            else:
                if a > area_objetivo:
                    lo = mid
                else:
                    hi = mid
        return (lo + hi) / 2

    opciones = []
    for fn, lo, hi, menor, etiqueta in [
        (recortar_y, ymin, ymax, True, "Y<="),
        (recortar_y, ymin, ymax, False, "Y>="),
        (recortar_x, xmin, xmax, True, "X<="),
        (recortar_x, xmin, xmax, False, "X>="),
    ]:
        corte = buscar(fn, lo, hi, menor)
        h = fn(pol_edificable, corte, menor)
        if len(h) >= 3:
            opciones.append((abs(g.area(h) - area_objetivo), etiqueta, h, g.area(h)))

    if not opciones:
        return {"poligono": pol_edificable, "area": g.area(pol_edificable),
                "corte": None}
    opciones.sort(key=lambda o: o[0])
    _, etiqueta, huella, area_real = opciones[0]
    return {"poligono": huella, "area": area_real, "corte": etiqueta}
