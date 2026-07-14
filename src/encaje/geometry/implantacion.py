"""
Optimizador de implantacion logistica.

Prioridades (en orden):
  1. Cumplir normativa urbanistica (retranqueos, ocupacion)
  2. Maximizar GLA
  3. Maximizar numero de muelles (docks)
  4. Playa de maniobra ~35m
  5. Acceso adecuado desde el vial
  6. Oficinas: minimo espacio, maxima visibilidad sin penalizar muelles

Las oficinas son SUBORDINADAS a la implantacion logistica.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from ..domain.lindero import Lindero, TipoLindero
from ..domain.implantacion import (ParametrosLogisticos, Playa, Oficina,
                                    ImplantacionLogistica, TipoOficina)
from . import _backend as g
from . import huella as h


@dataclass
class PesosOptimizacion:
    gla: float = 0.35
    muelles: float = 0.25
    calidad_playa: float = 0.15
    accesibilidad: float = 0.10
    oficinas: float = 0.05
    ampliaciones: float = 0.10


def lindero_acceso_principal(linderos):
    for tipo in [TipoLindero.ACCESO_PRINCIPAL, TipoLindero.VIAL,
                 TipoLindero.ACCESO_SECUNDARIO]:
        cands = [l for l in linderos if l.tipo == tipo]
        if cands: return max(cands, key=lambda l: l.longitud)
    return None


def _rotar(pts, ang, cx, cy):
    c, s = math.cos(ang), math.sin(ang)
    return [((p[0]-cx)*c-(p[1]-cy)*s+cx, (p[0]-cx)*s+(p[1]-cy)*c+cy) for p in pts]


def _recortar_y(poly, yc, bajo=True):
    res = []; n = len(poly)
    for i in range(n):
        p1, p2 = poly[i], poly[(i+1)%n]
        d1 = (p1[1] <= yc) if bajo else (p1[1] >= yc)
        d2 = (p2[1] <= yc) if bajo else (p2[1] >= yc)
        if d1: res.append(p1)
        dy = p2[1] - p1[1]
        if abs(dy) > 1e-9 and d1 != d2:
            t = (yc - p1[1]) / dy
            res.append((p1[0] + t*(p2[0]-p1[0]), yc))
    return res


def _reservar_playa(pol_edif, acceso, prof):
    ang = math.atan2(acceso.punto_fin[1]-acceso.punto_inicio[1],
                     acceso.punto_fin[0]-acceso.punto_inicio[0])
    cx, cy = g.centroide(pol_edif)
    rot = _rotar(pol_edif, -ang, cx, cy)
    acc_rot = _rotar([acceso.punto_inicio], -ang, cx, cy)[0]
    ys = [p[1] for p in rot]; y_min, y_max = min(ys), max(ys)
    prof_real = min(prof, (y_max - y_min) * 0.7)
    if acc_rot[1] < (y_min+y_max)/2:
        yc = y_min + prof_real
        pl, nv = _recortar_y(rot, yc, True), _recortar_y(rot, yc, False)
    else:
        yc = y_max - prof_real
        pl, nv = _recortar_y(rot, yc, False), _recortar_y(rot, yc, True)
    return (_rotar(pl, ang, cx, cy) if len(pl)>=3 else [],
            _rotar(nv, ang, cx, cy) if len(nv)>=3 else [], prof_real)


# ── Muelles ──────────────────────────────────────────────────────

def _fachada_muelles(nave_pts, acceso):
    """La fachada de muelles es la arista de la nave MAS CERCANA al acceso
    (la que mira hacia la playa donde operan los camiones)."""
    acc_mid = acceso.punto_medio
    n = len(nave_pts)
    mejor = (float('inf'), 0, 1)
    for i in range(n):
        j = (i+1) % n
        mx = (nave_pts[i][0]+nave_pts[j][0])/2
        my = (nave_pts[i][1]+nave_pts[j][1])/2
        d = math.hypot(mx-acc_mid[0], my-acc_mid[1])
        if d < mejor[0]: mejor = (d, i, j)
    return mejor[1], mejor[2]


def _calcular_muelles(nave_pts, acceso, ofi_longitud, modulo):
    """Calcula la longitud util de fachada y el numero de muelles."""
    i, j = _fachada_muelles(nave_pts, acceso)
    lon_fachada = math.hypot(nave_pts[j][0]-nave_pts[i][0],
                             nave_pts[j][1]-nave_pts[i][1])
    lon_util = lon_fachada - ofi_longitud  # descontar oficinas
    n_muelles = int(lon_util / modulo) if modulo > 0 and lon_util > 0 else 0
    return lon_fachada, lon_util, n_muelles


# ── Oficinas (en esquina, minimo footprint) ──────────────────────

def _normal_ext(p1, p2, centro):
    dx, dy = p2[0]-p1[0], p2[1]-p1[1]
    d = math.hypot(dx, dy)
    if d < 1e-9: return (0, 0)
    n1, n2 = (dy/d, -dx/d), (-dy/d, dx/d)
    mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
    return n1 if (math.hypot(mid[0]+n1[0]-centro[0], mid[1]+n1[1]-centro[1]) >
                  math.hypot(mid[0]+n2[0]-centro[0], mid[1]+n2[1]-centro[1])) else n2


def _colocar_oficinas(nave_pts, area_total, acceso, tipo_ofi, params):
    """
    Oficinas subordinadas a la logistica:
    - Reducir huella con n_plantas (default 2)
    - En ESQUINA de la fachada, no a lo ancho completo
    - Profundidad estandar (15m) para luz natural
    - Minimizar ocupacion de fachada de muelles
    """
    if area_total <= 0 or len(nave_pts) < 3:
        return None, 0.0

    area_planta = area_total / max(params.n_plantas_oficinas, 1)
    prof = params.profundidad_oficina_m  # 15m estandar
    longitud_ofi = area_planta / prof    # longitud que ocupa en fachada

    # Fachada hacia el acceso (= fachada de muelles)
    i, j = _fachada_muelles(nave_pts, acceso)
    p_ini, p_fin = nave_pts[i], nave_pts[j]
    lon_fachada = math.hypot(p_fin[0]-p_ini[0], p_fin[1]-p_ini[1])

    if longitud_ofi > lon_fachada * 0.3:
        longitud_ofi = lon_fachada * 0.3  # nunca mas del 30% de la fachada
        area_planta = longitud_ofi * prof
        area_total = area_planta * params.n_plantas_oficinas

    # Direccion a lo largo de la fachada (unitaria)
    dx = (p_fin[0]-p_ini[0]) / max(lon_fachada, 1e-9)
    dy = (p_fin[1]-p_ini[1]) / max(lon_fachada, 1e-9)
    centro = g.centroide(nave_pts)
    nx, ny = _normal_ext(p_ini, p_fin, centro)

    # Posicionar en la ESQUINA de la fachada (no centrado)
    # La oficina ocupa solo longitud_ofi desde p_ini
    p_a = p_ini
    p_b = (p_ini[0] + dx*longitud_ofi, p_ini[1] + dy*longitud_ofi)

    if tipo_ofi == TipoOficina.INTEGRADA:
        ofi_pts = [p_a, p_b,
                   (p_b[0]-nx*prof, p_b[1]-ny*prof),
                   (p_a[0]-nx*prof, p_a[1]-ny*prof)]
        pos = f"Integrada, esquina fachada vial, {params.n_plantas_oficinas}pl"
    else:
        ofi_pts = [p_a, p_b,
                   (p_b[0]+nx*prof, p_b[1]+ny*prof),
                   (p_a[0]+nx*prof, p_a[1]+ny*prof)]
        pos = f"Exenta adosada, esquina fachada vial, {params.n_plantas_oficinas}pl"

    return (Oficina(tipo=tipo_ofi.value, poligono=ofi_pts,
                    area=area_total, posicion=pos),
            longitud_ofi)


# ── Evaluacion de candidata ─────────────────────────────────────

def _evaluar(pol_edif, acceso, ang, gla_obj, params):
    # 1. Playa PRIMERO (restriccion, no consecuencia)
    pl_pol, nv_sp, prof = _reservar_playa(pol_edif, acceso, params.playa_principal_m)
    if not nv_sp or len(nv_sp) < 3:
        pl_pol, nv_sp, prof = _reservar_playa(pol_edif, acceso, params.playa_minima_m)
    if not nv_sp or len(nv_sp) < 3:
        return None

    # 2. Nave
    res = h.inscribir_rectangulo(nv_sp, gla_obj, ang)
    if res["area"] < 100:
        return None
    nave_gla = res["area"]

    # 3. Oficinas en esquina (subordinadas)
    oficinas = []; ofi_area = 0.0; ofi_lon = 0.0
    if params.oficinas_pct > 0:
        ofi_area = nave_gla * params.oficinas_pct
        ofi, ofi_lon = _colocar_oficinas(
            res["poligono"], ofi_area, acceso, params.tipo_oficina, params)
        if ofi:
            oficinas.append(ofi)
            ofi_area = ofi.area

    # 4. Muelles (descontando oficinas)
    lon_fach, lon_util, n_muelles = _calcular_muelles(
        res["poligono"], acceso, ofi_lon, params.modulo_muelle_m)

    return {
        "nave": res, "nave_gla": nave_gla, "angulo": ang,
        "playa_pol": pl_pol, "playa_prof": prof,
        "playa_area": g.area(pl_pol) if len(pl_pol)>=3 else 0,
        "oficinas": oficinas, "ofi_area": ofi_area, "ofi_lon": ofi_lon,
        "lon_fachada": lon_fach, "lon_muelles": lon_util,
        "n_muelles": n_muelles,
        "nave_space_area": g.area(nv_sp),
    }


# ── Funcion objetivo ────────────────────────────────────────────

def _puntuar(c, gla_obj, params, pesos=None):
    if pesos is None: pesos = PesosOptimizacion()

    s_gla = min(c["nave_gla"] / max(gla_obj, 1), 1.0)

    # Muelles: normalizar por el maximo teorico
    max_muelles_teorico = c["lon_fachada"] / max(params.modulo_muelle_m, 1)
    s_muelles = c["n_muelles"] / max(max_muelles_teorico, 1) if max_muelles_teorico > 0 else 0

    prof = c["playa_prof"]
    if prof >= params.playa_principal_m: s_playa = 1.0
    elif prof >= params.playa_minima_m:
        s_playa = 0.5 + 0.5 * (prof - params.playa_minima_m) / max(
            params.playa_principal_m - params.playa_minima_m, 1)
    else: s_playa = 0.0

    s_acc = 1.0 if c["oficinas"] else 0.7

    # Oficinas: premiamos que ocupen POCO frente (subordinadas)
    if c["lon_fachada"] > 0 and c["ofi_lon"] > 0:
        ratio_ocupado = c["ofi_lon"] / c["lon_fachada"]
        s_ofi = 1.0 - ratio_ocupado  # menos frente ocupado = mejor
    else:
        s_ofi = 1.0

    sobrante = c["nave_space_area"] - c["nave_gla"]
    s_amp = min(sobrante / max(c["nave_space_area"], 1), 0.5) * 2

    score = (pesos.gla * s_gla + pesos.muelles * s_muelles +
             pesos.calidad_playa * s_playa + pesos.accesibilidad * s_acc +
             pesos.oficinas * s_ofi + pesos.ampliaciones * s_amp)
    return score


# ── Generador principal ─────────────────────────────────────────

def generar_implantacion(pol_edif, linderos, gla_obj,
                         params_log, n_alternativas=3):
    acceso = lindero_acceso_principal(linderos)
    if acceso is None:
        ang = h.angulo_optimo(pol_edif)
        res = h.inscribir_rectangulo(pol_edif, gla_obj, ang)
        return ImplantacionLogistica(
            nave_poligono=res["poligono"], nave_gla=res["area"],
            nave_dims=res["dims"], nave_angulo=res["angulo"],
            descripcion="Sin acceso definido — GLA maxima sin playa")

    # Barrido completo: 0 a 178 cada 2 grados
    candidatas = []
    for deg in range(0, 180, 2):
        c = _evaluar(pol_edif, acceso, float(deg), gla_obj, params_log)
        if c is not None:
            score = _puntuar(c, gla_obj, params_log)
            candidatas.append((score, c, deg))

    if not candidatas:
        return ImplantacionLogistica(
            nave_poligono=[], nave_gla=0,
            descripcion="No se encontro implantacion viable")

    candidatas.sort(reverse=True, key=lambda x: x[0])

    def _build(score, c, deg):
        return ImplantacionLogistica(
            nave_poligono=c["nave"]["poligono"],
            nave_gla=c["nave_gla"],
            nave_dims=c["nave"]["dims"],
            nave_angulo=float(deg),
            playas=[Playa("principal", c["playa_pol"], c["playa_prof"],
                          [acceso.indice], c["playa_area"])],
            oficinas=c["oficinas"],
            oficinas_area=c["ofi_area"],
            n_muelles=c["n_muelles"],
            longitud_muelles=c["lon_muelles"],
            puntuacion=score,
            descripcion=(f"ang={deg}deg, GLA={c['nave_gla']:,.0f}m2, "
                         f"{c['n_muelles']} muelles ({c['lon_muelles']:.0f}m util), "
                         f"playa {c['playa_prof']:.0f}m, "
                         f"score={score:.3f}"))

    mejor = candidatas[0]
    alts = [_build(s, c, d) for s, c, d in candidatas[1:n_alternativas]]

    impl = _build(*mejor)
    impl.alternativas = alts
    impl.descripcion = (f"Mejor de {len(candidatas)} orientaciones. "
                        f"Acceso L{acceso.indice} "
                        f"({acceso.orientacion_cardinal}, {acceso.longitud:.0f}m). "
                        + impl.descripcion)
    return impl
