"""
Interfaz de linea de comandos.

Uso:
  python -m encaje.cli parcela.gml --retranqueo 5 --ocupacion 60
  python -m encaje.cli parcela.gml --fxcc colindantes.zip --vial 10 --lindero 5
  python -m encaje.cli colindantes.zip --retranqueo 6 --ocupacion 62 --modo ambas
"""
from __future__ import annotations
import argparse
import os
import sys

from .io.lectores.deteccion import leer_entrada
from .io.kml_writer import escribir_kml
from .core.modelos import ParametrosUrbanisticos, ModoHuella
from .core.motor import calcular
from .core.validacion import UmbralesValidacion
from .geometry._backend import backend_info
from .geometry.crs import crs_info


def construir_parser():
    p = argparse.ArgumentParser(
        prog="encaje",
        description="Motor de calculo de GLA sobre parcelas catastrales.")
    p.add_argument("entrada", help="GML catastral o ZIP FXCC")
    p.add_argument("--fxcc", default=None,
                   help="ZIP FXCC con colindantes (si la entrada es un GML)")
    p.add_argument("--retranqueo", type=float, default=None,
                   help="Retranqueo uniforme (m)")
    p.add_argument("--vial", type=float, default=None, help="Retranqueo a vial (m)")
    p.add_argument("--lindero", type=float, default=None, help="Retranqueo a lindero (m)")
    p.add_argument("--ocupacion", type=float, default=60.0, help="Ocupacion (%)")
    p.add_argument("--edif", type=float, default=None, help="Edificabilidad m2t/m2s")
    p.add_argument("--modo", choices=["auto", "rect", "huella", "ambas"],
                   default="auto")
    p.add_argument("--tolerancia-vertice", type=float, default=0.05,
                   help="Umbral (m) tolerancia vs error para vertices fuera")
    p.add_argument("--salida", default=None, help="Ruta KML de salida")
    p.add_argument("--abrir", action="store_true", help="Abrir en Google Earth")
    return p


def main(argv=None):
    args = construir_parser().parse_args(argv)

    if not os.path.exists(args.entrada):
        print(f"ERROR: no existe {args.entrada}", file=sys.stderr)
        return 1

    if args.retranqueo is not None:
        vial = lindero = args.retranqueo
    else:
        vial = args.vial or 0.0
        lindero = args.lindero or 0.0

    params = ParametrosUrbanisticos(
        retranqueo_vial=vial, retranqueo_lindero=lindero,
        ocupacion=args.ocupacion / 100.0, edificabilidad=args.edif,
        modo_huella=ModoHuella(args.modo),
        umbrales=UmbralesValidacion(tolerancia_vertice_m=args.tolerancia_vertice))

    entrada = leer_entrada(args.entrada, fxcc=args.fxcc)
    resultado = calcular(entrada, params)
    p = entrada.parcela

    print("=" * 62)
    print(f"ENCAJE CATASTRAL  |  {p.referencia}")
    print(f"Backend: {backend_info()}  |  CRS: {crs_info()}")
    print(f"Formato entrada: {entrada.formato_origen}")
    print("=" * 62)
    print(f"Area parcela:      {p.area_calculada:,.2f} m2 "
          f"(catastro {p.area_declarada:,.0f}, delta {p.discrepancia_pct:.3f}%)")
    print(f"Compacidad:        {resultado.compacidad*100:.1f}% "
          f"(orientacion {resultado.angulo_parcela:.1f} grados)")
    print(f"Retranqueo:        {params.retranqueo_efectivo} m")
    print(f"Area edificable:   {resultado.area_edificable:,.2f} m2")
    print(f"GLA objetivo:      {resultado.gla_objetivo:,.0f} m2")
    if resultado.colindantes:
        print(f"Colindantes:       {len(resultado.colindantes)}")
    if entrada.tiene_linderos:
        from .domain.lindero import TipoLindero
        n_v = len(entrada.linderos_vial)
        n_p = len(entrada.linderos_privados)
        n_d = len(entrada.linderos_desconocidos)
        print(f"Linderos:          {len(entrada.linderos)} total "
              f"({n_v} vial, {n_p} privado, {n_d} sin determinar)")
    print("-" * 62)
    for hu in resultado.huellas:
        dims = f"{hu.dims[0]:.0f}x{hu.dims[1]:.0f}m" if hu.dims else ""
        est = "OK" if hu.alcanza_objetivo else "no alcanza objetivo"
        print(f"  Huella {hu.tipo:10s}: {hu.area:>9,.0f} m2  {dims:>14s}  {est}")
    print("-" * 62)
    est = resultado.estado
    simbolo = {"VALIDA": "[OK]", "REQUIERE_REVISION": "[!]", "NO_VALIDA": "[X]"}
    print(f"VALIDACION: {simbolo[est.value]} {est.value} ({est.color})")
    for inc in resultado.validacion.incidencias:
        print(f"  [{inc.gravedad.value:5s}] {inc}")
    print("=" * 62)

    salida = args.salida or os.path.splitext(args.entrada)[0] + "_encaje.kml"
    escribir_kml(resultado, salida)
    print(f"KML generado: {salida}")

    if args.abrir:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from scripts.abrir_google_earth import abrir
        abrir(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
