"""
Parametros logisticos y estructura de implantacion.
Estos parametros son independientes de los urbanisticos (retranqueos,
ocupacion). Los urbanisticos los fija la normativa; los logisticos
los fija el operador.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class TipoOficina(str, Enum):
    INTEGRADA = "integrada"    # dentro de la nave
    EXENTA = "exenta"          # edificio separado


@dataclass
class ParametrosLogisticos:
    """Parametros logisticos configurables por el usuario."""
    playa_principal_m: float = 35.0
    playa_secundaria_m: float = 30.0
    playa_minima_m: float = 31.0
    oficinas_pct: float = 0.04             # % de la GLA (4% por defecto)
    tipo_oficina: TipoOficina = TipoOficina.INTEGRADA
    n_plantas_oficinas: int = 2            # plantas de oficinas (reduce huella)
    profundidad_oficina_m: float = 15.0    # fondo estandar oficina (luz natural)
    modulo_muelle_m: float = 5.5           # separacion entre ejes de muelle
    # Futuro
    altura_libre_m: float = 12.0           # informativo


@dataclass
class Playa:
    """Zona de playa de maniobra reservada."""
    tipo: str                          # "principal" | "secundaria"
    poligono: list[tuple[float, float]]
    profundidad_real: float            # metros reales conseguidos
    lindero_indices: list[int]         # indices de linderos de acceso asociados
    area: float = 0.0


@dataclass
class Oficina:
    """Bloque de oficinas."""
    tipo: str                          # "integrada" | "exenta"
    poligono: list[tuple[float, float]]
    area: float
    posicion: str = ""                 # "NO de la nave", "junto al acceso", etc.


@dataclass
class ImplantacionLogistica:
    """
    Resultado completo de una implantacion. Agrupa la nave, las playas
    y las oficinas. Cada alternativa de implantacion es una instancia.
    """
    nave_poligono: list[tuple[float, float]]
    nave_gla: float
    nave_dims: tuple[float, float] | None = None
    nave_angulo: float = 0.0
    playas: list[Playa] = field(default_factory=list)
    oficinas: list[Oficina] = field(default_factory=list)
    oficinas_area: float = 0.0
    n_muelles: int = 0                 # posiciones de carga estimadas
    longitud_muelles: float = 0.0      # longitud util de fachada para docks
    puntuacion: float = 0.0
    alternativas: list = field(default_factory=list)
    descripcion: str = ""

    @property
    def area_total_ocupada(self) -> float:
        return self.nave_gla + sum(p.area for p in self.playas) + self.oficinas_area
