"""
Validacion geometrica. El motor es determinista: no hay "confianza", hay
estado de validacion. Cada comprobacion produce (o no) una Incidencia con
tipo, gravedad y MAGNITUD MEDIDA, para distinguir una tolerancia numerica
de un error real de calculo.

Estado global:
  VALIDA           (verde)    ninguna incidencia de gravedad alta o media
  REQUIERE_REVISION(amarillo) incidencias menores (tolerancias)
  NO_VALIDA        (rojo)     incumple restricciones geometricas/urbanisticas
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Gravedad(str, Enum):
    INFO = "info"        # informativo, no afecta al estado
    MENOR = "menor"      # tolerancia -> REQUIERE_REVISION
    GRAVE = "grave"      # error real -> NO_VALIDA


class Estado(str, Enum):
    VALIDA = "VALIDA"
    REQUIERE_REVISION = "REQUIERE_REVISION"
    NO_VALIDA = "NO_VALIDA"

    @property
    def color(self) -> str:
        return {"VALIDA": "verde",
                "REQUIERE_REVISION": "amarillo",
                "NO_VALIDA": "rojo"}[self.value]


@dataclass
class Incidencia:
    """Una comprobacion que ha detectado algo. Incluye la magnitud medida."""
    tipo: str                    # identificador: "vertice_fuera", etc.
    gravedad: Gravedad
    mensaje: str                 # explicacion legible
    magnitud: float | None = None    # valor medido (m, m2, %, ...)
    unidad: str = ""             # "m", "m2", "%"
    umbral: float | None = None      # umbral aplicado para clasificar

    def __str__(self) -> str:
        s = self.mensaje
        if self.magnitud is not None:
            s += f" (magnitud: {self.magnitud:.3g} {self.unidad}".rstrip()
            if self.umbral is not None:
                s += f"; umbral: {self.umbral:.3g} {self.unidad}".rstrip()
            s += ")"
        return s


@dataclass
class Validacion:
    """Acumula incidencias y deriva el estado global."""
    incidencias: list[Incidencia] = field(default_factory=list)

    def anadir(self, incidencia: Incidencia) -> None:
        self.incidencias.append(incidencia)

    @property
    def estado(self) -> Estado:
        gravedades = {i.gravedad for i in self.incidencias}
        if Gravedad.GRAVE in gravedades:
            return Estado.NO_VALIDA
        if Gravedad.MENOR in gravedades:
            return Estado.REQUIERE_REVISION
        return Estado.VALIDA

    @property
    def graves(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.gravedad == Gravedad.GRAVE]

    @property
    def menores(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.gravedad == Gravedad.MENOR]

    @property
    def informativas(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.gravedad == Gravedad.INFO]


@dataclass
class UmbralesValidacion:
    """Umbrales configurables que separan tolerancia (menor) de error (grave)."""
    # Un vertice de la huella fuera del edificable: si la distancia maxima
    # fuera es menor que este umbral, es tolerancia numerica (menor); si es
    # mayor, es error real (grave).
    tolerancia_vertice_m: float = 0.05
    # Discrepancia de superficie parcela calculada vs. catastro declarada
    tolerancia_area_pct: float = 2.0
    # Margen por el que el edificable puede superar (por error) a la parcela
    tolerancia_edificable_m2: float = 1.0
