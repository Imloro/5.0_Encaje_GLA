#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# probar_encajes.sh
# Lanza varias variantes de encaje sobre un GML y deja un KML por variante
# en la carpeta salidas_encaje/. Sirve para comparar opciones rapidamente.
#
# Uso:
#   bash probar_encajes.sh                              # usa el GML por defecto
#   bash probar_encajes.sh ruta/a/tu_parcela.gml       # usa otro GML
#
# Requisitos (ya cumplidos en tu Codespace):
#   - pip install -e .    (shapely y pyproj instalados)
#   - estar en la raiz del repo (donde estan las carpetas src/ y tests/)
# ---------------------------------------------------------------------------
set -euo pipefail

GML="${1:-parcela_agrupada_0429VK4602N.gml}"
OUT="salidas_encaje"

if [ ! -f "$GML" ]; then
  echo "No encuentro el GML: $GML"
  echo "Pasa la ruta correcta:  bash probar_encajes.sh ruta/a/tu.gml"
  exit 1
fi

mkdir -p "$OUT"
echo "GML de entrada: $GML"
echo "Los KML se guardaran en: $OUT/"
echo

# Funcion: ejecuta una variante y muestra solo las lineas de resumen
run () {
  nombre="$1"; shift
  echo "=================================================="
  echo ">> $nombre"
  echo "=================================================="
  PYTHONPATH=src python -m encaje.cli "$GML" "$@" --salida "$OUT/$nombre.kml" \
    | grep -E "Area edificable|GLA objetivo|Huella|Multinave|VALIDACION" || true
  echo
}

# --- Variantes MULTINAVE (juega con separacion / nº naves / tamano minimo) ---
run mn_pocas_grandes  --vial 6 --lindero 4 --ocupacion 60 \
                      --modo multinave --sep 15 --max-naves 6 --min-nave 4000
run mn_mas_naves      --vial 6 --lindero 4 --ocupacion 60 \
                      --modo multinave --sep 10 --max-naves 8 --min-nave 2500
run mn_muy_separadas  --vial 6 --lindero 4 --ocupacion 60 \
                      --modo multinave --sep 25 --max-naves 4 --min-nave 6000

# --- Comparativa: una sola nave (modos originales del motor) ---
run una_nave_rect     --vial 6 --lindero 4 --ocupacion 60 --modo rect
run una_huella_L      --vial 6 --lindero 4 --ocupacion 60 --modo huella

echo "=================================================="
echo "Listo. KML generados:"
ls -1 "$OUT"
echo
echo "Abre cada .kml en Google Earth para comparar."
echo "Para cambiar parametros, edita los numeros de este script"
echo "(--sep, --max-naves, --min-nave, --vial, --lindero, --ocupacion)."
