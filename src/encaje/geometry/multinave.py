"""
Empaquetado MULTINAVE.

Coloca N naves rectangulares (ortogonales) dentro del poligono edificable
(ya retranqueado), de forma DETERMINISTA:

  - Cada nave elige su PROPIO angulo optimo (barrido sobre las direcciones
    reales de las aristas de la parcela + barrido grueso). Asi las naves
    siguen los "dientes" de una parcela irregular en vez de forzar una
    unica orientacion.
  - Estrategia voraz "pocas naves grandes": en cada paso se coloca el mayor
    rectangulo libre posible; se descartan las que no llegan a un tamano
    minimo (evita astillas).
  - Cada nave reserva su PLAYA de maniobra y estima sus MUELLES y oficinas.
  - Separacion configurable de X metros entre naves (borde libre alrededor
    de cada implantacion; garantiza que no se toquen).

Reutiliza el rasterizado y el "mayor rectangulo en matriz binaria" de
huella.py. No depende de Shapely ni de numpy: mismo input -> mismo output.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

from . import _backend as g
from . import huella as h
from ..domain.implantacion import (ParametrosLogisticos, Playa, Oficina,
                                    ImplantacionLogistica, TipoOficina)


# --------------------------------------------------------------------------
# Parametros del empaquetado (los urbanisticos y logisticos van aparte)
# --------------------------------------------------------------------------

@dataclass
class ParametrosMultinave:
    """Parametros que controlan el empaquetado de varias naves."""
    separacion_naves_m: float = 12.0     # X: borde libre entre naves
    max_naves: int = 8                   # tope de naves a colocar
    min_area_nave_m2: float = 2000.0     # por debajo -> no se coloca (astilla)
    min_lado_nave_m: float = 40.0        # lado corto minimo de la nave
    min_fondo_nave_m: float = 24.0       # fondo minimo tras reservar playa
    grid_m: float = 2.0                  # resolucion del rasterizado
    paso_angulo: int = 10                # barrido grueso adicional (grados)
    con_playa: bool = True               # reservar playa de maniobra por nave
    con_oficinas: bool = True            # colocar oficinas por nave
    # Modulo estructural para ajustar dimensiones de nave (0 = sin ajuste)
    modulo_luz_m: float = 12.0
    modulo_crujia_m: float = 24.0


@dataclass
class ResultadoMultinave:
    """Salida del empaquetado: lista de implantaciones + agregados."""
    naves: list[ImplantacionLogistica]
    gla_total: float
    area_ocupada_total: float            # naves + playas + oficinas
    n_naves: int
    descripcion: str = ""


# --------------------------------------------------------------------------
# Utilidades geometricas locales
# --------------------------------------------------------------------------

def _rot(pts, ang):
    """Rota los puntos 'ang' radianes alrededor del origen."""
    c, s = math.cos(ang), math.sin(ang)
    return [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in pts]


def _azimuts_candidatos(pol, paso):
    """Direcciones a probar: las de las aristas de la parcela (mod 90)
    mas un barrido grueso. Aristas -> las naves siguen los dientes."""
    angs = set()
    n = len(pol)
    for i in range(n):
        a, b = pol[i], pol[(i + 1) % n]
        deg = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0
        angs.add(round(deg, 1))
    for d in range(0, 90, max(paso, 1)):
        angs.add(float(d))
    return sorted(angs)


def _rect_a_poligono(x0, y0, x1, y1, ang):
    """Convierte un rectangulo axis-aligned del marco rotado a coords
    originales aplicando +ang."""
    esquinas = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return _rot(esquinas, ang)


def _dilatar_rect(corners, m):
    """Devuelve el rectangulo (en su propio marco) crecido 'm' metros en
    todas direcciones, como poligono en coords originales. Sirve para
    marcar la zona ocupada + separacion."""
    if m <= 0:
        return list(corners)
    cx, cy = g.centroide(corners)
    out = []
    for (px, py) in corners:
        vx, vy = px - cx, py - cy
        d = math.hypot(vx, vy) or 1.0
        # crecer empujando cada esquina hacia afuera en diagonal ~ m*sqrt(2)
        out.append((px + vx / d * m * 1.4142, py + vy / d * m * 1.4142))
    return out


# --------------------------------------------------------------------------
# Mayor rectangulo LIBRE en un angulo, respetando exclusiones (naves ya
# colocadas + su separacion). Extiende huella._mayor_rectangulo_en_angulo
# con una lista de poligonos a excluir.
# --------------------------------------------------------------------------

def _mayor_rect_libre_en_angulo(pol, excluir, ang, grid):
    rot_pol = _rot(pol, -ang)
    rot_exc = [_rot(e, -ang) for e in excluir]

    xs = [p[0] for p in rot_pol]
    ys = [p[1] for p in rot_pol]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    nx = int((xmax - xmin) / grid) + 1
    ny = int((ymax - ymin) / grid) + 1
    if nx < 1 or ny < 1:
        return None

    grid_bool = [[False] * ny for _ in range(nx)]
    for ix in range(nx):
        x0 = xmin + ix * grid
        x1 = x0 + grid
        for iy in range(ny):
            y0 = ymin + iy * grid
            y1 = y0 + grid
            # Interior de la parcela: las 4 esquinas dentro (evita rebasar).
            if not (g.punto_en_poligono(x0, y0, rot_pol) and
                    g.punto_en_poligono(x1, y0, rot_pol) and
                    g.punto_en_poligono(x1, y1, rot_pol) and
                    g.punto_en_poligono(x0, y1, rot_pol)):
                continue
            # Libre: el centro no cae en ninguna zona excluida.
            xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
            if any(g.punto_en_poligono(xc, yc, e) for e in rot_exc):
                continue
            grid_bool[ix][iy] = True

    area_c, x0i, y0i, x1i, y1i = h._mayor_rect_binario(grid_bool, nx, ny)
    if area_c <= 0:
        return None

    rx0 = xmin + x0i * grid
    ry0 = ymin + y0i * grid
    rx1 = xmin + (x1i + 1) * grid
    ry1 = ymin + (y1i + 1) * grid
    ancho = rx1 - rx0            # eje x del marco rotado
    fondo = ry1 - ry0           # eje y del marco rotado
    return {
        "local": (rx0, ry0, rx1, ry1),
        "ang": ang,
        "ancho": ancho,
        "fondo": fondo,
        "area": ancho * fondo,
        "poligono": _rect_a_poligono(rx0, ry0, rx1, ry1, ang),
    }


# --------------------------------------------------------------------------
# Componer una nave (playa + nave + muelles + oficinas) a partir del
# rectangulo-envolvente que devuelve el empaquetador.
# --------------------------------------------------------------------------

def _snap(v, modulo):
    if modulo and modulo > 0:
        return math.floor(v / modulo) * modulo
    return v


def _componer_nave(rect, params_log, mn, ref_pt, indice):
    """A partir del rectangulo-envolvente (nave + playa), reserva la playa
    en el lado corto orientado hacia 'ref_pt' (acceso), deja la nave y
    calcula muelles y oficinas. Devuelve una ImplantacionLogistica."""
    rx0, ry0, rx1, ry1 = rect["local"]
    ang = rect["ang"]
    L = rx1 - rx0               # dimension en x (marco rotado)
    W = ry1 - ry0               # dimension en y (marco rotado)

    # El lado LARGO sera la fachada de muelles; la playa se resta del corto.
    # Trabajamos con "largo" a lo ancho (x) y "fondo" en (y). Si W>L, el eje
    # corto es x: reorientamos sumando 90 grados para que el largo sea x.
    if W > L:
        ang = ang + math.radians(90.0)
        L, W = W, L
        # recomputar rectangulo local en el nuevo marco
        rx0, ry0, rx1, ry1 = 0.0, 0.0, L, W
        base = _rot(rect["poligono"], -ang)
        bx = [p[0] for p in base]; by = [p[1] for p in base]
        rx0, ry0, rx1, ry1 = min(bx), min(by), max(bx), max(by)
        L, W = rx1 - rx0, ry1 - ry0

    # --- Playa: profundidad objetivo, limitada por dejar fondo minimo ---
    playa_prof = 0.0
    if mn.con_playa:
        objetivo = params_log.playa_principal_m
        prof = min(objetivo, W - mn.min_fondo_nave_m)
        if prof >= params_log.playa_minima_m:
            playa_prof = prof
        elif (W - mn.min_fondo_nave_m) >= params_log.playa_secundaria_m:
            playa_prof = params_log.playa_secundaria_m

    fondo_nave = W - playa_prof

    # --- Elegir el lado corto (y0 o y1) que aloja la playa: el mas cercano
    #     al punto de referencia de acceso (si se conoce) ---
    lado_y0 = True
    if ref_pt is not None:
        mid_y0 = _rot([((rx0 + rx1) / 2, ry0)], ang)[0]
        mid_y1 = _rot([((rx0 + rx1) / 2, ry1)], ang)[0]
        d0 = math.hypot(mid_y0[0] - ref_pt[0], mid_y0[1] - ref_pt[1])
        d1 = math.hypot(mid_y1[0] - ref_pt[0], mid_y1[1] - ref_pt[1])
        lado_y0 = d0 <= d1

    # Ajuste a modulo estructural (encoge, nunca crece)
    L_nave = _snap(L, mn.modulo_luz_m) or L
    fondo_nave = _snap(fondo_nave, mn.modulo_crujia_m) or fondo_nave
    if L_nave <= 0 or fondo_nave <= 0:
        L_nave, fondo_nave = L, W - playa_prof

    # Coordenadas (marco rotado) de nave y playa
    nx0 = rx0
    nx1 = rx0 + L_nave
    if lado_y0:
        py0, py1 = ry0, ry0 + playa_prof
        ny0, ny1 = ry0 + playa_prof, ry0 + playa_prof + fondo_nave
        fachada_y = ny0            # fachada de muelles mira a la playa (y menor)
    else:
        py0, py1 = ry1 - playa_prof, ry1
        ny0, ny1 = ry1 - playa_prof - fondo_nave, ry1 - playa_prof
        fachada_y = ny1

    nave_pol = _rect_a_poligono(nx0, ny0, nx1, ny1, ang)
    gla = L_nave * fondo_nave

    playa_obj = None
    if playa_prof > 0:
        playa_pol = _rect_a_poligono(nx0, py0, nx1, py1, ang)
        playa_obj = Playa(tipo="principal", poligono=playa_pol,
                          profundidad_real=playa_prof,
                          lindero_indices=[], area=g.area(playa_pol))

    # --- Oficinas: bloque en esquina de la fachada de muelles ---
    oficinas = []
    ofi_area = 0.0
    ofi_lon = 0.0
    if mn.con_oficinas and params_log.oficinas_pct > 0 and gla > 0:
        ofi_area = gla * params_log.oficinas_pct
        prof_ofi = params_log.profundidad_oficina_m
        area_planta = ofi_area / max(params_log.n_plantas_oficinas, 1)
        ofi_lon = area_planta / prof_ofi
        if ofi_lon > L_nave * 0.30:
            ofi_lon = L_nave * 0.30
            area_planta = ofi_lon * prof_ofi
            ofi_area = area_planta * params_log.n_plantas_oficinas
        # esquina junto a la fachada de muelles, dentro de la nave
        oy0 = fachada_y if lado_y0 else fachada_y - prof_ofi
        oy1 = oy0 + prof_ofi
        ofi_pol = _rect_a_poligono(nx0, oy0, nx0 + ofi_lon, oy1, ang)
        oficinas.append(Oficina(tipo=params_log.tipo_oficina.value,
                                poligono=ofi_pol, area=ofi_area,
                                posicion=f"Esquina fachada muelles, nave {indice}"))

    # --- Muelles: sobre la fachada larga, descontando oficinas ---
    lon_util = L_nave - ofi_lon
    n_muelles = int(lon_util / params_log.modulo_muelle_m) if lon_util > 0 else 0

    ang_deg = math.degrees(ang) % 180
    impl = ImplantacionLogistica(
        nave_poligono=nave_pol,
        nave_gla=gla,
        nave_dims=(L_nave, fondo_nave),
        nave_angulo=ang_deg,
        playas=[playa_obj] if playa_obj else [],
        oficinas=oficinas,
        oficinas_area=ofi_area,
        n_muelles=n_muelles,
        longitud_muelles=lon_util,
        descripcion=(f"Nave {indice}: {L_nave:.0f}x{fondo_nave:.0f}m, "
                     f"GLA {gla:,.0f} m2, {n_muelles} muelles, "
                     f"playa {playa_prof:.0f}m, ang {ang_deg:.0f}deg"))
    return impl


# --------------------------------------------------------------------------
# Empaquetador principal
# --------------------------------------------------------------------------

def empaquetar_multinave(pol_edif, params_log=None, mn=None,
                         acceso_mid=None) -> ResultadoMultinave:
    """
    Coloca varias naves dentro de 'pol_edif'. Determinista.

    pol_edif   : poligono edificable (ya retranqueado).
    params_log : ParametrosLogisticos (playa, muelles, oficinas).
    mn         : ParametrosMultinave (separacion, tamanos minimos, ...).
    acceso_mid : (x, y) del acceso principal, si se conoce, para orientar
                 las playas de las naves hacia el vial.
    """
    if params_log is None:
        params_log = ParametrosLogisticos()
    if mn is None:
        mn = ParametrosMultinave()

    naves: list[ImplantacionLogistica] = []
    excluir = []                       # poligonos ya ocupados (+ separacion)
    angulos = _azimuts_candidatos(pol_edif, mn.paso_angulo)

    for k in range(mn.max_naves):
        mejor = None
        for a_deg in angulos:
            r = _mayor_rect_libre_en_angulo(
                pol_edif, excluir, math.radians(a_deg), mn.grid_m)
            if r and (mejor is None or r["area"] > mejor["area"]):
                mejor = r

        if mejor is None:
            break
        lado_corto = min(mejor["ancho"], mejor["fondo"])
        if mejor["area"] < mn.min_area_nave_m2 or lado_corto < mn.min_lado_nave_m:
            break

        impl = _componer_nave(mejor, params_log, mn, acceso_mid, indice=k + 1)
        if impl.nave_gla < mn.min_area_nave_m2:
            # tras restar playa la nave no llega al minimo -> paramos
            # (por ser voraz, las siguientes serian aun menores)
            break
        naves.append(impl)

        # Marcar la envolvente + separacion como ocupada para la siguiente
        excluir.append(_dilatar_rect(mejor["poligono"], mn.separacion_naves_m))

    gla_total = sum(n.nave_gla for n in naves)
    area_ocupada = sum(n.area_total_ocupada for n in naves)
    return ResultadoMultinave(
        naves=naves,
        gla_total=gla_total,
        area_ocupada_total=area_ocupada,
        n_naves=len(naves),
        descripcion=(f"{len(naves)} naves, GLA total {gla_total:,.0f} m2, "
                     f"separacion {mn.separacion_naves_m:.0f}m entre naves"))
