"""
Motor de calculo. Pipeline determinista:
  ModeloTerritorial + ParametrosUrbanisticos  ->  Resultado (con Validacion)

No sabe que existe Claude, ni la CLI, ni la web, ni el formato de origen.
Solo geometria.
"""
from __future__ import annotations
import math
from ..geometry import _backend as g
from ..geometry import huella as h
from ..geometry import linderos as lind
from ..geometry import implantacion as impl
from ..domain.modelo_territorial import ModeloTerritorial
from ..domain.implantacion import ParametrosLogisticos
from .modelos import (Parcela, ParametrosUrbanisticos,
                      Resultado, Huella, ModoHuella, EntradaParcela)
from .validacion import Validacion, Incidencia, Gravedad


def _distancia_max_fuera(poligono, contenedor):
    """Distancia maxima de un vertice de 'poligono' al exterior de
    'contenedor'. 0 si todos estan dentro."""
    cx, cy = g.centroide(poligono)
    max_d = 0.0
    for (px, py) in poligono:
        tx = px + (cx - px) * 0.001
        ty = py + (cy - py) * 0.001
        if not g.punto_en_poligono(tx, ty, contenedor):
            d = min(math.hypot(px - qx, py - qy) for qx, qy in contenedor)
            max_d = max(max_d, d)
    return max_d


def _asegurar_modelo_territorial(entrada) -> ModeloTerritorial:
    """
    Convierte EntradaParcela a ModeloTerritorial si es necesario.
    Permite la migracion progresiva: el motor acepta ambos tipos.
    """
    if isinstance(entrada, ModeloTerritorial):
        return entrada
    if isinstance(entrada, EntradaParcela):
        linderos = lind.segmentar_linderos(entrada.parcela)
        return ModeloTerritorial(
            parcela=entrada.parcela,
            linderos=linderos,
            colindantes=entrada.colindantes)
    raise TypeError(f"El motor espera ModeloTerritorial o EntradaParcela, "
                    f"recibido {type(entrada)}")


def calcular(entrada, params: ParametrosUrbanisticos,
             params_log: ParametrosLogisticos | None = None) -> Resultado:
    modelo = _asegurar_modelo_territorial(entrada)
    parcela = modelo.parcela
    val = Validacion()
    U = params.umbrales

    # --- 1. Segmentar linderos si no estan ---
    if not modelo.tiene_linderos:
        modelo.linderos = lind.segmentar_linderos(parcela)

    # --- 2. Clasificar linderos por colindantes (si los hay) ---
    if modelo.tiene_colindantes:
        lind.clasificar_por_colindantes(modelo.linderos, modelo.colindantes)

    # --- 3. Asignar retranqueos a cada lindero ---
    lind.asignar_retranqueos(
        modelo.linderos, params.retranqueo_vial, params.retranqueo_lindero)

    n_vial = len(modelo.linderos_vial)
    n_priv = len(modelo.linderos_privados)
    n_desc = len(modelo.linderos_desconocidos)
    if n_vial > 0 or n_priv > 0:
        val.anadir(Incidencia(
            tipo="linderos_clasificados", gravedad=Gravedad.INFO,
            mensaje=f"Linderos: {n_vial} a vial, {n_priv} privados, "
                    f"{n_desc} sin determinar"))

    # --- 4. Discrepancia de superficie ---
    disc = parcela.discrepancia_pct
    if disc > U.tolerancia_area_pct:
        val.anadir(Incidencia(
            tipo="discrepancia_superficie", gravedad=Gravedad.MENOR,
            mensaje="La superficie calculada difiere de la declarada en catastro",
            magnitud=disc, unidad="%", umbral=U.tolerancia_area_pct))

    # --- 5. Poligono edificable (con retranqueo por lindero) ---
    r = params.retranqueo_efectivo
    if r > 0:
        pol_edif = g.offset_interior(parcela.vertices, r)
        if not pol_edif:
            val.anadir(Incidencia(
                tipo="sin_edificable", gravedad=Gravedad.GRAVE,
                mensaje="El retranqueo consume toda la parcela: sin area edificable",
                magnitud=r, unidad="m"))
            return Resultado(parcela=parcela, parametros=params,
                             poligono_edificable=[], area_edificable=0.0,
                             gla_objetivo=0.0, colindantes=modelo.colindantes,
                             validacion=val)
        area_edif = g.area(pol_edif)
        exceso = area_edif - parcela.area_calculada
        if exceso > U.tolerancia_edificable_m2:
            val.anadir(Incidencia(
                tipo="edificable_mayor_que_parcela", gravedad=Gravedad.GRAVE,
                mensaje="El poligono edificable resulto mayor que la parcela "
                        "(error de offset)",
                magnitud=exceso, unidad="m2", umbral=U.tolerancia_edificable_m2))
    else:
        pol_edif = list(parcela.vertices)
        area_edif = parcela.area_calculada
        val.anadir(Incidencia(
            tipo="sin_retranqueos", gravedad=Gravedad.INFO,
            mensaje="Sin retranqueos: GLA calculada sobre parcela bruta"))

    # --- 6. Orientacion y compacidad ---
    area_min_rect, ang_parcela = g.rectangulo_minimo_rotado(parcela.vertices)
    compacidad = parcela.area_calculada / area_min_rect if area_min_rect else 0.0
    if compacidad < 0.85:
        val.anadir(Incidencia(
            tipo="parcela_irregular", gravedad=Gravedad.INFO,
            mensaje="Parcela irregular: se recomienda revisar la huella en L",
            magnitud=compacidad * 100, unidad="%", umbral=85.0))

    # --- 7. GLA objetivo (sobre PARCELA, limitado por edificable y edif.) ---
    gla_objetivo = parcela.area_calculada * params.ocupacion
    if gla_objetivo > area_edif:
        val.anadir(Incidencia(
            tipo="gla_limitada_por_edificable", gravedad=Gravedad.MENOR,
            mensaje="La GLA objetivo supera el area edificable; se limita a esta",
            magnitud=gla_objetivo - area_edif, unidad="m2"))
        gla_objetivo = area_edif

    if params.edificabilidad is not None:
        techo = parcela.area_calculada * params.edificabilidad
        if gla_objetivo > techo:
            val.anadir(Incidencia(
                tipo="gla_limitada_por_edificabilidad", gravedad=Gravedad.MENOR,
                mensaje="La GLA supera el techo de edificabilidad; se limita",
                magnitud=gla_objetivo - techo, unidad="m2"))
            gla_objetivo = techo

    # --- 8. Inscribir huella(s) ---
    # Si hay accesos definidos Y parametros logisticos: implantacion completa
    # Si no: comportamiento original (solo GLA maxima)
    huellas: list[Huella] = []
    implantacion_obj = None

    accesos = [l for l in modelo.linderos if l.es_acceso]
    usar_implantacion = len(accesos) > 0 and params_log is not None

    if usar_implantacion:
        # IMPLANTACION LOGISTICA: playa + nave orientada + oficinas
        implantacion_obj = impl.generar_implantacion(
            pol_edif, modelo.linderos, gla_objetivo, params_log)

        if implantacion_obj.nave_gla > 0:
            huellas.append(Huella(
                tipo="nave_logistica",
                poligono=implantacion_obj.nave_poligono,
                area=implantacion_obj.nave_gla,
                dims=implantacion_obj.nave_dims,
                angulo=implantacion_obj.nave_angulo,
                alcanza_objetivo=implantacion_obj.nave_gla >= gla_objetivo * 0.95))

            val.anadir(Incidencia(
                tipo="implantacion_generada", gravedad=Gravedad.INFO,
                mensaje=f"Implantacion logistica: {implantacion_obj.descripcion}"))

            # Validar playa
            for playa in implantacion_obj.playas:
                if playa.profundidad_real < params_log.playa_minima_m:
                    val.anadir(Incidencia(
                        tipo="playa_insuficiente", gravedad=Gravedad.MENOR,
                        mensaje=f"Playa {playa.tipo}: profundidad {playa.profundidad_real:.1f}m "
                                f"< minimo {params_log.playa_minima_m:.0f}m",
                        magnitud=playa.profundidad_real, unidad="m",
                        umbral=params_log.playa_minima_m))
                else:
                    val.anadir(Incidencia(
                        tipo="playa_correcta", gravedad=Gravedad.INFO,
                        mensaje=f"Playa {playa.tipo}: {playa.profundidad_real:.1f}m "
                                f"(objetivo {params_log.playa_principal_m:.0f}m, "
                                f"area {playa.area:,.0f} m2)"))

            # Validar oficinas
            if implantacion_obj.oficinas:
                for ofi in implantacion_obj.oficinas:
                    val.anadir(Incidencia(
                        tipo="oficinas_ubicadas", gravedad=Gravedad.INFO,
                        mensaje=f"Oficinas {ofi.tipo}: {ofi.area:,.0f} m2 — {ofi.posicion}"))

            # Validar muelles
            if implantacion_obj.n_muelles > 0:
                val.anadir(Incidencia(
                    tipo="muelles_estimados", gravedad=Gravedad.INFO,
                    mensaje=f"Muelles estimados: {implantacion_obj.n_muelles} posiciones "
                            f"({implantacion_obj.longitud_muelles:.0f}m util de fachada)"))
        else:
            val.anadir(Incidencia(
                tipo="implantacion_fallida", gravedad=Gravedad.GRAVE,
                mensaje="No se pudo generar la implantacion: "
                        + implantacion_obj.descripcion))
    else:
        # COMPORTAMIENTO ORIGINAL: GLA maxima sin implantacion logistica
        ang_opt = h.angulo_optimo(pol_edif)

        def add_rectangulo():
            res = h.inscribir_rectangulo(pol_edif, gla_objetivo, ang_opt)
            huellas.append(Huella(
                tipo="rectangulo", poligono=res["poligono"], area=res["area"],
                dims=res["dims"], angulo=res["angulo"],
                alcanza_objetivo=res["alcanza"]))
            return res["alcanza"]

        def add_huella_L():
            res = h.inscribir_huella_L(pol_edif, gla_objetivo)
            huellas.append(Huella(
                tipo="huella_L", poligono=res["poligono"], area=res["area"],
                alcanza_objetivo=True))

        modo = params.modo_huella
        if modo == ModoHuella.RECTANGULO:
            if not add_rectangulo():
                val.anadir(Incidencia(
                    tipo="rectangulo_no_alcanza", gravedad=Gravedad.INFO,
                    mensaje="El rectangulo unico no alcanza la ocupacion objetivo; "
                            "considere huella en L o multinave"))
        elif modo == ModoHuella.HUELLA_L:
            add_huella_L()
        elif modo == ModoHuella.AMBAS:
            add_rectangulo()
            add_huella_L()
        else:  # AUTO
            if not add_rectangulo():
                val.anadir(Incidencia(
                    tipo="rectangulo_no_alcanza", gravedad=Gravedad.INFO,
                    mensaje="El rectangulo unico no alcanza la ocupacion; "
                            "se anade huella en L que si la alcanza"))
                add_huella_L()

        if not accesos:
            val.anadir(Incidencia(
                tipo="sin_accesos", gravedad=Gravedad.INFO,
                mensaje="Sin accesos definidos: calculo de GLA maxima sin playa "
                        "ni implantacion logistica. Clasifica los linderos de "
                        "acceso para obtener una implantacion completa."))

    # --- 9. Validacion geometrica de cada huella ---
    for hu in huellas:
        d_fuera = _distancia_max_fuera(hu.poligono, pol_edif)
        if d_fuera > 0:
            grav = (Gravedad.MENOR if d_fuera <= U.tolerancia_vertice_m
                    else Gravedad.GRAVE)
            val.anadir(Incidencia(
                tipo="huella_fuera_edificable", gravedad=grav,
                mensaje=f"La huella '{hu.tipo}' sobresale del poligono edificable",
                magnitud=d_fuera, unidad="m", umbral=U.tolerancia_vertice_m))

    return Resultado(
        parcela=parcela, parametros=params,
        poligono_edificable=pol_edif, area_edificable=area_edif,
        gla_objetivo=gla_objetivo, huellas=huellas,
        colindantes=modelo.colindantes,
        implantacion=implantacion_obj,
        angulo_parcela=ang_parcela, compacidad=compacidad,
        validacion=val)
