"""
Segmentacion del poligono de la parcela en linderos y funciones de
clasificacion geometrica. Convierte una lista de vertices en una lista
de Lindero, cada uno con sus propiedades geometricas.
"""
from __future__ import annotations
import math

from ..domain.lindero import Lindero, TipoLindero, FuenteTipo
from ..core.modelos import Parcela, Colindante
from . import _backend as g


def segmentar_linderos(parcela: Parcela) -> list[Lindero]:
    """
    Convierte el poligono de la parcela en una lista de Lindero.
    Cada par de vertices consecutivos define un lindero.
    Todos empiezan como DESCONOCIDO / SIN_DETERMINAR.
    """
    vertices = parcela.vertices
    n = len(vertices)
    linderos = []
    for i in range(n):
        j = (i + 1) % n
        linderos.append(Lindero(
            indice=i,
            punto_inicio=vertices[i],
            punto_fin=vertices[j]))
    return linderos


def clasificar_por_colindantes(linderos: list[Lindero],
                               colindantes: list[Colindante],
                               tolerancia: float = 2.0) -> None:
    """
    Clasifica linderos como PRIVADO si ambos extremos del segmento estan
    cerca de los vertices de alguna parcela colindante. Modifica los
    linderos in-place.

    NOTA: la ausencia de colindante NO implica vial (puede faltar en la
    descarga del FXCC). Solo se usa para confirmar linderos privados.
    """
    for lindero in linderos:
        if lindero.tipo != TipoLindero.DESCONOCIDO:
            continue  # ya clasificado (manual o por otra fuente)
        for col in colindantes:
            if len(col.vertices) < 3:
                continue
            if (_punto_cerca(lindero.punto_inicio, col.vertices, tolerancia) and
                    _punto_cerca(lindero.punto_fin, col.vertices, tolerancia)):
                lindero.tipo = TipoLindero.PRIVADO
                lindero.fuente_tipo = FuenteTipo.AUTOMATICO
                lindero.colindante_ref = col.referencia
                break


def asignar_retranqueos(linderos: list[Lindero],
                        retranqueo_vial: float,
                        retranqueo_lindero: float) -> None:
    """
    Asigna el retranqueo a cada lindero segun su tipo.
    DESCONOCIDO recibe el mayor (conservador).
    Solo asigna si el lindero no tiene retranqueo ya asignado.
    """
    for lindero in linderos:
        if lindero.retranqueo is not None:
            continue  # ya tiene retranqueo manual
        if lindero.es_acceso:  # VIAL, ACCESO_PRINCIPAL, ACCESO_SECUNDARIO
            lindero.retranqueo = retranqueo_vial
        elif lindero.tipo == TipoLindero.PRIVADO:
            lindero.retranqueo = retranqueo_lindero
        else:  # DESCONOCIDO: conservador
            lindero.retranqueo = max(retranqueo_vial, retranqueo_lindero)


def retranqueos_por_segmento(linderos: list[Lindero]) -> list[float]:
    """
    Devuelve una lista de retranqueos, uno por segmento del poligono,
    en el mismo orden que los vertices. Para pasar al offset por segmento.
    """
    return [l.retranqueo or 0.0 for l in linderos]


def lindero_mas_largo(linderos: list[Lindero],
                      tipo: TipoLindero | None = None) -> Lindero | None:
    """Devuelve el lindero mas largo, opcionalmente filtrado por tipo."""
    candidatos = linderos if tipo is None else [l for l in linderos if l.tipo == tipo]
    return max(candidatos, key=lambda l: l.longitud) if candidatos else None


# --------------------------------------------------------------------------
# Funciones auxiliares
# --------------------------------------------------------------------------

def _punto_cerca(punto: tuple[float, float],
                 poligono: list[tuple[float, float]],
                 tolerancia: float) -> bool:
    return any(math.hypot(punto[0] - q[0], punto[1] - q[1]) < tolerancia
               for q in poligono)
