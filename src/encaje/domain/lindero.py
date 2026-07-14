"""
Lindero: entidad central del modelo territorial.

Un lindero es un segmento del polígono de la parcela entre dos vértices
consecutivos, enriquecido con información de dominio: qué hay al otro lado
(vial o propiedad privada), qué retranqueo le corresponde, si es un frente
logístico, y de dónde viene esa información.

Todos los algoritmos futuros (retranqueos por lindero, viales, playas de
maniobra, muelles, accesos) leen y escriben propiedades de linderos.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum


class TipoLindero(str, Enum):
    """Clasificacion del lindero segun lo que hay al otro lado."""
    VIAL = "vial"                              # da a via publica (generico)
    ACCESO_PRINCIPAL = "acceso_principal"       # acceso principal de vehiculos pesados
    ACCESO_SECUNDARIO = "acceso_secundario"     # acceso secundario
    PRIVADO = "privado"                        # da a propiedad privada
    DESCONOCIDO = "desconocido"                # no se ha podido determinar


class FuenteTipo(str, Enum):
    """Como se determino el tipo del lindero."""
    AUTOMATICO = "automatico"      # inferido por geometria/colindantes
    MANUAL = "manual"              # indicado por el usuario
    CARTOCIUDAD = "cartociudad"    # cruce con CartoCiudad (IGN)
    SIN_DETERMINAR = "sin_determinar"


class TipoFrente(str, Enum):
    """Tipo de frente logistico de la nave."""
    MUELLES_PRINCIPAL = "muelles_principal"     # playa 35 m por defecto
    MUELLES_SECUNDARIO = "muelles_secundario"   # playa 30 m por defecto
    ACCESO_VL = "acceso_vl"                     # vehiculos ligeros
    LATERAL = "lateral"                         # solo retranqueo urbanistico
    TRASERA = "trasera"                         # patio tecnico / cerramiento
    SIN_ASIGNAR = "sin_asignar"


@dataclass
class Lindero:
    """Un segmento del perimetro de la parcela, con semantica urbanistica."""
    indice: int                                   # posicion en el poligono (0..n-1)
    punto_inicio: tuple[float, float]
    punto_fin: tuple[float, float]

    # Clasificacion urbanistica
    tipo: TipoLindero = TipoLindero.DESCONOCIDO
    fuente_tipo: FuenteTipo = FuenteTipo.SIN_DETERMINAR

    # Retranqueo aplicable a este lindero (None = no asignado aun)
    retranqueo: float | None = None

    # Referencia del colindante al otro lado (si se conoce)
    colindante_ref: str | None = None

    # Frente logistico (se asigna en fases posteriores)
    frente_logistico: TipoFrente = TipoFrente.SIN_ASIGNAR

    # --- Propiedades geometricas (calculadas, no almacenadas) ---

    @property
    def longitud(self) -> float:
        dx = self.punto_fin[0] - self.punto_inicio[0]
        dy = self.punto_fin[1] - self.punto_inicio[1]
        return math.hypot(dx, dy)

    @property
    def azimut(self) -> float:
        """Azimut en grados (0=Norte, 90=Este), sentido horario."""
        dx = self.punto_fin[0] - self.punto_inicio[0]
        dy = self.punto_fin[1] - self.punto_inicio[1]
        return (90 - math.degrees(math.atan2(dy, dx))) % 360

    @property
    def punto_medio(self) -> tuple[float, float]:
        return ((self.punto_inicio[0] + self.punto_fin[0]) / 2,
                (self.punto_inicio[1] + self.punto_fin[1]) / 2)

    @property
    def orientacion_cardinal(self) -> str:
        """Orientacion simplificada: N, NE, E, SE, S, SO, O, NO."""
        az = self.azimut
        cardinales = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
        return cardinales[int((az + 22.5) % 360 / 45)]

    @property
    def es_acceso(self) -> bool:
        """True si este lindero es cualquier tipo de acceso (vial, principal, secundario)."""
        return self.tipo in (TipoLindero.VIAL, TipoLindero.ACCESO_PRINCIPAL,
                             TipoLindero.ACCESO_SECUNDARIO)

    @property
    def es_acceso_principal(self) -> bool:
        return self.tipo == TipoLindero.ACCESO_PRINCIPAL

    @property
    def es_vial(self) -> bool:
        """True si da a via publica (cualquier tipo de acceso)."""
        return self.es_acceso

    def __repr__(self) -> str:
        return (f"Lindero({self.indice}, {self.longitud:.1f}m, "
                f"{self.orientacion_cardinal}, {self.tipo.value})")
