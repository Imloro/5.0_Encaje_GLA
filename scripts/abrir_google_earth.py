"""
Utilidad para abrir un KML en Google Earth segun la plataforma.
Detecta Windows, macOS y Linux.
"""
from __future__ import annotations
import os
import subprocess
import sys


def abrir(path_kml: str) -> None:
    """Abre el KML con la aplicacion por defecto (Google Earth si es el
    handler de .kml, o el navegador para Google Earth Web)."""
    path_kml = os.path.abspath(path_kml)
    if not os.path.exists(path_kml):
        print(f"No existe el KML: {path_kml}", file=sys.stderr)
        return

    try:
        if sys.platform.startswith("win"):
            os.startfile(path_kml)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path_kml], check=False)
        else:
            subprocess.run(["xdg-open", path_kml], check=False)
        print(f"Abriendo {path_kml} ...")
    except Exception as e:
        print(f"No se pudo abrir automaticamente: {e}", file=sys.stderr)
        print(f"Abrelo manualmente en Google Earth: {path_kml}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        abrir(sys.argv[1])
