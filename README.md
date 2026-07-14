# Encaje Catastral — Motor de cálculo de GLA

Motor de cálculo geométrico **determinista** que procesa parcelas
catastrales españolas (GML) y calcula la GLA (Gross Leasable Area) posible
según retranqueos y ocupación, generando un KML para Google Earth.

**El motor no depende de ninguna IA.** Todos los cálculos (offset de
retranqueos, orientación, inscripción de huella, conversión de coordenadas)
son deterministas y están implementados en código. Mismo input → mismo
output, siempre, en segundos.

## Instalación

```bash
cd encaje-catastral
pip install -e .
```

Dependencias: `shapely` y `pyproj` hacen el trabajo geométrico pesado.
El motor **también funciona sin ellas** (fallback puro en Python), pero
instalarlas lo hace más rápido y robusto.

## Uso — GitHub Codespaces (recomendado, sin instalar nada)

1. Sube este proyecto a un repositorio de GitHub.
2. En el repositorio: botón verde **Code → Codespaces → Create codespace**.
3. Espera a que se prepare el entorno (instala dependencias solo).
4. Al terminar, se abre automáticamente la interfaz web en el navegador.
   Si no, en la pestaña **Ports** haz clic en el puerto 8000.
5. Sube el GML, introduce los parámetros, pulsa **Calcular** y descarga el KML.

No requiere instalar nada en tu ordenador ni permisos de administrador.
Todo corre en el Codespace (en la nube de GitHub) y se accede desde el navegador.

## Uso — local (opcional)

Si prefieres ejecutarlo en tu máquina:

```bash
pip install -e . flask
python webapp/app.py
# abrir http://localhost:8000
```

## Formatos de entrada

El motor acepta dos formatos, que se transforman internamente en el mismo
modelo (`EntradaParcela` = `Parcela` + lista de `Colindante`):

- **GML catastral** (`.gml`): geometría fiable de la parcela.
- **ZIP FXCC** (`.zip`): "Parcela y colindantes en formato FXCC" del Catastro,
  con una carpeta por referencia (DXF de geometría + ASC de datos).

Flujo recomendado: subir el **GML** (geometría exacta de la parcela) y,
opcionalmente, el **ZIP FXCC** para añadir los colindantes y sus datos. La
geometría de la parcela se toma siempre del GML; del FXCC se aprovechan los
colindantes. (El DXF del FXCC entrega la parcela como segmentos dispersos,
poco fiables para reconstruir el anillo; por eso prevalece el GML.)

Añadir un formato nuevo (GeoJSON, SHP...) = añadir un lector en
`io/lectores/` que devuelva `EntradaParcela`. El motor no cambia.

## Validación geométrica (no "nivel de confianza")

El motor es determinista: no estima, calcula. Por eso el resultado no lleva
un "nivel de confianza" sino un **estado de validación geométrica**, derivado
de comprobaciones con **magnitud medida**:

- 🟢 **VÁLIDA**: todas las comprobaciones pasan.
- 🟡 **REQUIERE REVISIÓN**: incidencias menores (p. ej. un vértice fuera por
  tolerancia numérica).
- 🔴 **NO VÁLIDA**: incumple restricciones geométricas o urbanísticas.

Cada incidencia indica el motivo y la **magnitud** (p. ej. "la huella
sobresale 2,98 m; umbral 0,05 m"), para distinguir una tolerancia numérica
de un error real. El umbral que separa tolerancia de error es configurable
(`--tolerancia-vertice` en CLI, campo "tolerancia" en la web).

## Uso — línea de comandos

```bash
# GML solo
encaje parcela.gml --retranqueo 5 --ocupacion 60

# GML + FXCC (colindantes)
encaje parcela.gml --fxcc colindantes.zip --vial 10 --lindero 5 --ocupacion 60

# ZIP FXCC directamente
encaje colindantes.zip --retranqueo 6 --ocupacion 62 --modo ambas

# Ajustar el umbral de validación
encaje parcela.gml --retranqueo 5 --ocupacion 60 --tolerancia-vertice 0.1
```

## Arquitectura

Separación estricta en tres capas:

```
src/encaje/
├── geometry/     MOTOR — geometría pura, sin red ni IA
│   ├── _backend.py    área, offset, ray-casting, rect. mínimo rotado
│   ├── crs.py         conversión UTM ↔ WGS84 (pyproj o fallback)
│   └── huella.py      orientación óptima, inscribir rectángulo / L
├── core/         ORQUESTACIÓN
│   ├── modelos.py     dataclasses: Parcela, Colindante, EntradaParcela, Resultado
│   ├── validacion.py  Estado, Incidencia (con magnitud medida), Validacion
│   └── motor.py       pipeline: EntradaParcela + Parametros → Resultado
├── io/           ENTRADA / SALIDA
│   ├── lectores/      capa agnostica de formato
│   │   ├── gml.py         GML → EntradaParcela
│   │   ├── fxcc.py        ZIP FXCC → EntradaParcela (parcela + colindantes)
│   │   └── deteccion.py   detecta formato y despacha (+ combinar GML+FXCC)
│   └── kml_writer.py  Resultado → KML (parcela, colindantes, edificable, huellas)
├── cli.py        interfaz línea de comandos
└── gui.py        interfaz gráfica de escritorio (opcional)

webapp/           CAPA WEB (fina, sobre el motor)
├── app.py             servidor Flask: recibe GML, llama al motor, sirve KML
└── templates/
    └── index.html     interfaz de navegador (subir, calcular, descargar)

.devcontainer/    configuración de GitHub Codespaces
└── devcontainer.json
```

El motor recibe una `Parcela` y unos `ParametrosUrbanisticos` y devuelve un
`Resultado`. No sabe que existen la CLI, la web ni Google Earth. La capa web
(`webapp/`) es una envoltura fina: traduce HTTP a llamadas al motor y nada más.

## Tests

```bash
PYTHONPATH=src python tests/test_motor.py
# o con pytest:
PYTHONPATH=src pytest tests/ -v
```

Los tests son casos reales de calibración (Ciempozuelos, Resina,
parcelas giradas). Verifican que cada cambio no rompe resultados ya
validados.

## Fase 2 (futuro) — Claude como capa de interacción

El motor está diseñado para que, opcionalmente, Claude pueda integrarse
**solo como interfaz**: interpretar consultas en lenguaje natural, ayudar
con la normativa urbanística, rellenar los `ParametrosUrbanisticos`, lanzar
el motor y redactar informes. Claude nunca hace los cálculos: los hace el
motor. La frontera es la dataclass `ParametrosUrbanisticos` de entrada y
`Resultado` de salida.

## Limitaciones actuales

- La identificación de viales (qué lindero da a calle) no está resuelta de
  forma fiable desde el catastro. Se investiga vía CARTOCIUDAD (IGN).
- El retranqueo diferenciado por lindero usa por ahora el valor mayor de
  forma uniforme; el offset por segmento con valores distintos por lado
  está en el backend pero no expuesto en la CLI.
