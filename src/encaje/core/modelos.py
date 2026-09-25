"""
Contratos de datos del motor. El motor recibe una EntradaParcela (parcela
+ colindantes, venga de donde venga) y unos ParametrosUrbanisticos, y
devuelve un Resultado con su Validacion.

El formato de entrada (GML, ZIP FXCC, GeoJSON, SHP...) es indiferente:
todos los lectores producen la misma EntradaParcela.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from .validacion import Validacion, UmbralesValidacion


class ModoHuella(str, Enum):
    """Que devolver cuando el rectangulo unico no alcanza la ocupacion."""
    AUTO = "auto"
    RECTANGULO = "rect"
    HUELLA_L = "huella"
    AMBAS = "ambas"
    MULTINAVE = "multinave"   # varias naves ortogonales dentro del edificable


@dataclass
class Parcela:
    """Geometria de la parcela principal."""
    referencia: str
    vertices: list[tuple[float, float]]
    area_declarada: float
    epsg: int = 25830

    @property
    def area_calculada(self) -> float:
        from ..geometry import _backend as g
        return g.area(self.vertices)

    @property
    def discrepancia_pct(self) -> float:
        if not self.area_declarada:
            return 0.0
        return abs(self.area_calculada - self.area_declarada) / self.area_declarada * 100


@dataclass
class Colindante:
    """Una parcela vecina (del FXCC). Geometria + datos alfanumericos."""
    referencia: str
    vertices: list[tuple[float, float]]
    epsg: int = 25830
    uso: str | None = None
    superficie: float | None = None
    domicilio: str | None = None
    datos_brutos: dict = field(default_factory=dict)

    @property
    def area_calculada(self) -> float:
        from ..geometry import _backend as g
        return g.area(self.vertices) if len(self.vertices) >= 3 else 0.0

    @property
    def tiene_edificacion(self) -> bool:
        return self.datos_brutos.get("edificacion_m2", 0) > 10


@dataclass
class EntradaParcela:
    """
    Modelo unificado de entrada. Todos los lectores (GML, FXCC, ...)
    producen esta estructura. El motor solo conoce esto.
    """
    parcela: Parcela
    colindantes: list[Colindante] = field(default_factory=list)
    formato_origen: str = "desconocido"

    @property
    def tiene_colindantes(self) -> bool:
        return len(self.colindantes) > 0


@dataclass
class ParametrosUrbanisticos:
    """Parametros de entrada. Validados en __post_init__."""
    retranqueo_vial: float = 0.0
    retranqueo_lindero: float = 0.0
    ocupacion: float = 0.60
    edificabilidad: float | None = None
    modo_huella: ModoHuella = ModoHuella.AUTO
    umbrales: UmbralesValidacion = field(default_factory=UmbralesValidacion)

    def __post_init__(self):
        if not 0 < self.ocupacion <= 1:
            raise ValueError(f"ocupacion debe estar entre 0 y 1, recibido {self.ocupacion}")
        if self.retranqueo_vial < 0 or self.retranqueo_lindero < 0:
            raise ValueError("los retranqueos no pueden ser negativos")
        if self.edificabilidad is not None and self.edificabilidad <= 0:
            raise ValueError("la edificabilidad debe ser positiva")

    @property
    def retranqueo_efectivo(self) -> float:
        return max(self.retranqueo_vial, self.retranqueo_lindero)


@dataclass
class Huella:
    """Una variante de implantacion."""
    tipo: str
    poligono: list[tuple[float, float]]
    area: float
    dims: tuple[float, float] | None = None
    angulo: float | None = None
    alcanza_objetivo: bool = True


@dataclass
class Resultado:
    """Salida completa del motor."""
    parcela: Parcela
    parametros: ParametrosUrbanisticos
    poligono_edificable: list[tuple[float, float]]
    area_edificable: float
    gla_objetivo: float
    huellas: list[Huella] = field(default_factory=list)
    colindantes: list[Colindante] = field(default_factory=list)
    implantacion: object = None      # ImplantacionLogistica (si hay accesos)
    multinave: list = field(default_factory=list)  # lista de ImplantacionLogistica (modo multinave)
    angulo_parcela: float = 0.0
    compacidad: float = 0.0
    validacion: Validacion = field(default_factory=Validacion)

    @property
    def estado(self):
        return self.validacion.estado
