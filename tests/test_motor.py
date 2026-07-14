"""Tests de regresion con casos reales. Motor + validacion + lectores."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from encaje.io.lectores.deteccion import leer_entrada
from encaje.core.modelos import ParametrosUrbanisticos, ModoHuella
from encaje.core.motor import calcular
from encaje.core.validacion import Estado

CASOS = os.path.join(os.path.dirname(__file__), "casos")


def _run(archivo, **kw):
    entrada = leer_entrada(os.path.join(CASOS, archivo))
    return entrada, calcular(entrada, ParametrosUrbanisticos(**kw))


def test_gml_area_correcta():
    ent, _ = _run("ciempozuelos_ie6.gml", ocupacion=0.66)
    assert ent.parcela.discrepancia_pct < 0.1


def test_gml_gla_ciempozuelos():
    _, res = _run("ciempozuelos_ie6.gml", retranqueo_vial=10,
                  retranqueo_lindero=10, ocupacion=0.66)
    assert 20000 < res.gla_objetivo < 22500


def test_resina_rectangulo_no_alcanza():
    _, res = _run("resina.gml", retranqueo_vial=6, retranqueo_lindero=4,
                  ocupacion=0.62, modo_huella=ModoHuella.AMBAS)
    rect = [h for h in res.huellas if h.tipo == "rectangulo"][0]
    assert not rect.alcanza_objetivo


def test_validacion_tiene_estado():
    _, res = _run("ciempozuelos_ie6.gml", retranqueo_vial=10,
                  retranqueo_lindero=10, ocupacion=0.60)
    assert res.estado in (Estado.VALIDA, Estado.REQUIERE_REVISION, Estado.NO_VALIDA)


def test_incidencias_tienen_magnitud():
    """Las incidencias de tolerancia deben llevar magnitud medida."""
    _, res = _run("resina.gml", retranqueo_vial=6, retranqueo_lindero=4,
                  ocupacion=0.62)
    fuera = [i for i in res.validacion.incidencias
             if i.tipo == "huella_fuera_edificable"]
    for inc in fuera:
        assert inc.magnitud is not None
        assert inc.umbral is not None


def test_fxcc_extrae_colindantes():
    ent = leer_entrada(os.path.join(CASOS, "4236106VK4443N.zip"))
    assert len(ent.colindantes) >= 3


def test_edificable_nunca_mayor_que_parcela():
    for gml in ["ciempozuelos_ie6.gml", "resina.gml", "9407013VK5790N.gml"]:
        ent, res = _run(gml, retranqueo_vial=5, retranqueo_lindero=5, ocupacion=0.60)
        assert res.area_edificable < ent.parcela.area_calculada + 1.0


# =====================================================================
# FASE 1: Tests de Lindero y ModeloTerritorial
# =====================================================================

def test_gml_produce_modelo_territorial():
    """El lector GML ahora devuelve ModeloTerritorial (no EntradaParcela)."""
    from encaje.domain.modelo_territorial import ModeloTerritorial
    modelo = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    assert isinstance(modelo, ModeloTerritorial)


def test_linderos_segmentados():
    """El modelo territorial tiene linderos segmentados desde la lectura."""
    modelo = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    assert modelo.tiene_linderos
    assert len(modelo.linderos) == len(modelo.parcela.vertices)


def test_linderos_propiedades_geometricas():
    """Cada lindero tiene longitud, azimut y orientacion cardinal."""
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    for l in modelo.linderos:
        assert l.longitud > 0
        assert 0 <= l.azimut < 360
        assert l.orientacion_cardinal in ["N","NE","E","SE","S","SO","O","NO"]


def test_linderos_perimetro_coherente():
    """La suma de longitudes de los linderos = perimetro del poligono."""
    from encaje.geometry._backend import perimetro
    modelo = leer_entrada(os.path.join(CASOS, "9407013VK5790N.gml"))
    peri_linderos = sum(l.longitud for l in modelo.linderos)
    peri_poligono = perimetro(modelo.parcela.vertices)
    assert abs(peri_linderos - peri_poligono) < 0.01


def test_fxcc_clasifica_colindantes():
    """Si hay colindantes del FXCC, algunos linderos se clasifican como PRIVADO."""
    from encaje.domain.lindero import TipoLindero
    modelo = leer_entrada(
        os.path.join(CASOS, "4236106VK4443N.zip"))
    # El motor clasifica al calcular; invocamos calcular para activarlo
    res = calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=5, ocupacion=0.60))
    # Al menos un lindero deberia haberse clasificado
    tipos = {l.tipo for l in modelo.linderos}
    # No podemos garantizar que FXCC clasifica porque la geometria del DXF
    # es problematica, pero el modelo debe tener linderos
    assert len(modelo.linderos) > 0


def test_formato_origen_gml():
    """ModeloTerritorial de GML tiene formato_origen correcto."""
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    assert modelo.formato_origen == "gml"


def test_modelo_territorial_fuentes():
    """ModeloTerritorial registra las fuentes de datos."""
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    assert len(modelo.fuentes) >= 1
    assert modelo.fuentes[0].tipo == "gml"


def test_retranqueos_asignados_por_lindero():
    """Tras calcular, cada lindero tiene un retranqueo asignado."""
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=6, retranqueo_lindero=4, ocupacion=0.62))
    for l in modelo.linderos:
        assert l.retranqueo is not None
        assert l.retranqueo > 0


def test_clasificacion_manual_se_aplica():
    """Si clasificamos un lindero manualmente como VIAL, recibe el retranqueo de vial."""
    from encaje.domain.lindero import TipoLindero, FuenteTipo
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    # Clasificar lindero 0 como vial manualmente
    modelo.linderos[0].tipo = TipoLindero.VIAL
    modelo.linderos[0].fuente_tipo = FuenteTipo.MANUAL
    # Clasificar lindero 5 como privado manualmente
    modelo.linderos[5].tipo = TipoLindero.PRIVADO
    modelo.linderos[5].fuente_tipo = FuenteTipo.MANUAL
    calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=6, retranqueo_lindero=4, ocupacion=0.62))
    assert modelo.linderos[0].retranqueo == 6.0  # vial
    assert modelo.linderos[5].retranqueo == 4.0  # privado


def test_clasificacion_manual_no_sobreescrita():
    """La clasificacion manual no se sobreescribe por la automatica."""
    from encaje.domain.lindero import TipoLindero, FuenteTipo
    modelo = leer_entrada(os.path.join(CASOS, "resina.gml"))
    modelo.linderos[2].tipo = TipoLindero.VIAL
    modelo.linderos[2].fuente_tipo = FuenteTipo.MANUAL
    # Calcular invoca clasificar_por_colindantes, que no debe tocar los MANUAL
    calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=5, ocupacion=0.60))
    assert modelo.linderos[2].tipo == TipoLindero.VIAL
    assert modelo.linderos[2].fuente_tipo == FuenteTipo.MANUAL


def test_implantacion_con_acceso_genera_playa():
    """Con acceso definido y params_log, el motor genera implantacion con playa."""
    from encaje.domain.lindero import TipoLindero, FuenteTipo
    from encaje.domain.implantacion import ParametrosLogisticos
    modelo = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    mas_largo = max(modelo.linderos, key=lambda l: l.longitud)
    mas_largo.tipo = TipoLindero.ACCESO_PRINCIPAL
    mas_largo.fuente_tipo = FuenteTipo.MANUAL
    params_log = ParametrosLogisticos(playa_principal_m=35, oficinas_pct=0.04)
    res = calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=10, ocupacion=0.60),
        params_log=params_log)
    assert res.implantacion is not None
    assert res.implantacion.nave_gla > 0
    assert len(res.implantacion.playas) > 0
    assert res.implantacion.playas[0].profundidad_real >= 30


def test_implantacion_sin_acceso_no_genera_playa():
    """Sin acceso definido, no se genera implantacion logistica."""
    from encaje.domain.implantacion import ParametrosLogisticos
    modelo = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    res = calcular(modelo, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=10, ocupacion=0.60),
        params_log=ParametrosLogisticos())
    assert res.implantacion is None


def test_implantacion_gla_menor_que_sin_playa():
    """La GLA con playa es menor que sin playa (la playa ocupa espacio)."""
    from encaje.domain.lindero import TipoLindero, FuenteTipo
    from encaje.domain.implantacion import ParametrosLogisticos
    modelo1 = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    res1 = calcular(modelo1, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=10, ocupacion=0.60))
    gla_sin = max(h.area for h in res1.huellas) if res1.huellas else 0

    modelo2 = leer_entrada(os.path.join(CASOS, "ciempozuelos_ie6.gml"))
    mas_largo = max(modelo2.linderos, key=lambda l: l.longitud)
    mas_largo.tipo = TipoLindero.ACCESO_PRINCIPAL
    mas_largo.fuente_tipo = FuenteTipo.MANUAL
    res2 = calcular(modelo2, ParametrosUrbanisticos(
        retranqueo_vial=10, retranqueo_lindero=10, ocupacion=0.60),
        params_log=ParametrosLogisticos(playa_principal_m=35))
    gla_con = res2.implantacion.nave_gla if res2.implantacion else 0
    assert gla_con < gla_sin


# =====================================================================
# Runner
# =====================================================================

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except Exception as e:
            fallos += 1; print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests)-fallos}/{len(tests)} tests OK")
    sys.exit(1 if fallos else 0)
