"""
ModeloTerritorial: modelo unificado de entrada al motor.

Reemplaza a EntradaParcela como la estructura que el motor recibe.
Contiene la parcela, sus linderos (con semantica), los colindantes,
las fuentes de datos y los metadatos.

Los lectores (GML, FXCC, futuros GeoJSON/SHP) producen esta estructura.
El motor solo conoce esto — es independiente del formato de entrada.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

from ..core.modelos import Parcela, Colindante
from .lindero import Lindero


@dataclass
class FuenteDatos:
    """Registro de procedencia de la informacion."""
    tipo: str                # "gml", "fxcc", "cartociudad", "manual"
    path: str | None = None
    fecha: datetime | None = None


@dataclass
class ModeloTerritorial:
    """
    Modelo unificado de entrada. Todos los lectores producen esta estructura.
    El motor solo conoce esto.

    Respecto a EntradaParcela, anade:
    - linderos: los segmentos del perimetro con semantica urbanistica
    - fuentes: trazabilidad del origen de los datos
    - metadatos: informacion contextual
    """
    parcela: Parcela
    linderos: list[Lindero] = field(default_factory=list)
    colindantes: list[Colindante] = field(default_factory=list)
    fuentes: list[FuenteDatos] = field(default_factory=list)
    metadatos: dict = field(default_factory=dict)

    @property
    def tiene_colindantes(self) -> bool:
        return len(self.colindantes) > 0

    @property
    def tiene_linderos(self) -> bool:
        return len(self.linderos) > 0

    @property
    def linderos_vial(self) -> list[Lindero]:
        from .lindero import TipoLindero
        return [l for l in self.linderos if l.tipo == TipoLindero.VIAL]

    @property
    def linderos_privados(self) -> list[Lindero]:
        from .lindero import TipoLindero
        return [l for l in self.linderos if l.tipo == TipoLindero.PRIVADO]

    @property
    def linderos_desconocidos(self) -> list[Lindero]:
        from .lindero import TipoLindero
        return [l for l in self.linderos if l.tipo == TipoLindero.DESCONOCIDO]

    @property
    def formato_origen(self) -> str:
        tipos = [f.tipo for f in self.fuentes]
        if "gml" in tipos and "fxcc" in tipos:
            return "gml+fxcc"
        return tipos[0] if tipos else "desconocido"
