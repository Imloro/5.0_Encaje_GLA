"""
Servidor web minimo. Capa FINA sobre el motor: recibe la entrada (GML o
ZIP FXCC) y los parametros por HTTP, llama a encaje.core.motor.calcular
(sin modificarlo) y devuelve el KML para descargar.
"""
from __future__ import annotations
import os
import sys
import tempfile
import uuid

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "src"))

from flask import Flask, request, render_template, send_file, jsonify

from encaje.io.lectores.deteccion import leer_entrada
from encaje.io.kml_writer import escribir_kml
from encaje.core.modelos import ParametrosUrbanisticos, ModoHuella
from encaje.core.validacion import UmbralesValidacion
from encaje.core.motor import calcular
from encaje.domain.lindero import TipoLindero, FuenteTipo
from encaje.geometry._backend import backend_info, bbox
from encaje.geometry.crs import crs_info

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB

_SALIDA = os.path.join(tempfile.gettempdir(), "encaje_kml")
os.makedirs(_SALIDA, exist_ok=True)

# Cache temporal de modelos precargados (precargar_id → path)
_PRECARGADOS: dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html", backend=backend_info(), crs=crs_info())


@app.route("/precargar", methods=["POST"])
def precargar_endpoint():
    """
    Sube el GML (+FXCC opcional), extrae la geometria y devuelve los linderos
    como JSON con coordenadas normalizadas para renderizar en SVG. El usuario
    clasifica los linderos visualmente ANTES de calcular.
    """
    try:
        if "entrada" not in request.files or request.files["entrada"].filename == "":
            return jsonify({"error": "Sube un archivo GML o ZIP FXCC."}), 400

        f = request.files["entrada"]
        ext = os.path.splitext(f.filename)[1].lower() or ".gml"
        pid = uuid.uuid4().hex
        entrada_path = os.path.join(_SALIDA, f"{pid}{ext}")
        f.save(entrada_path)

        fxcc_path = None
        if "fxcc" in request.files and request.files["fxcc"].filename:
            fxcc_path = os.path.join(_SALIDA, f"{pid}_fxcc.zip")
            request.files["fxcc"].save(fxcc_path)

        modelo = leer_entrada(entrada_path, fxcc=fxcc_path)

        # Guardar paths para el calculo posterior
        _PRECARGADOS[pid] = {"entrada": entrada_path, "fxcc": fxcc_path}

        # Coordenadas SVG: normalizar UTM al viewport
        SVG_W, SVG_H, MARGIN = 420, 380, 30
        xmin, ymin, xmax, ymax = bbox(modelo.parcela.vertices)
        W, H = xmax - xmin, ymax - ymin
        escala = min((SVG_W - 2 * MARGIN) / max(W, 1),
                     (SVG_H - 2 * MARGIN) / max(H, 1))

        def to_svg(x, y):
            return (MARGIN + (x - xmin) * escala,
                    MARGIN + (ymax - y) * escala)  # Y invertida

        # Vertices de la parcela para el poligono SVG
        verts_svg = [to_svg(x, y) for x, y in modelo.parcela.vertices]

        # Colindantes para el fondo
        cols_svg = []
        for c in modelo.colindantes:
            if len(c.vertices) >= 3:
                cols_svg.append({
                    "referencia": c.referencia,
                    "vertices": [to_svg(x, y) for x, y in c.vertices],
                })

        # Linderos con coordenadas SVG
        linderos_json = []
        for l in modelo.linderos:
            ini_svg = to_svg(*l.punto_inicio)
            fin_svg = to_svg(*l.punto_fin)
            mid_svg = ((ini_svg[0] + fin_svg[0]) / 2,
                       (ini_svg[1] + fin_svg[1]) / 2)
            linderos_json.append({
                "indice": l.indice,
                "inicio": ini_svg,
                "fin": fin_svg,
                "medio": mid_svg,
                "longitud": round(l.longitud, 1),
                "orientacion": l.orientacion_cardinal,
                "tipo": l.tipo.value,
                "fuente": l.fuente_tipo.value,
            })

        return jsonify({
            "precargar_id": pid,
            "referencia": modelo.parcela.referencia,
            "area": round(modelo.parcela.area_calculada),
            "vertices_svg": verts_svg,
            "colindantes_svg": cols_svg,
            "linderos": linderos_json,
            "svg_size": [SVG_W, SVG_H],
            "n_colindantes": len(modelo.colindantes),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/calcular", methods=["POST"])
def calcular_endpoint():
    tmp_files = []
    try:
        # Opcion A: reutilizar archivos precargados (tras /precargar)
        pid = request.form.get("precargar_id", "").strip()
        if pid and pid in _PRECARGADOS:
            entrada_tmp = _PRECARGADOS[pid]["entrada"]
            fxcc_tmp = _PRECARGADOS[pid]["fxcc"]
        else:
            # Opcion B: subir archivos directamente (sin precargar)
            if "entrada" not in request.files or request.files["entrada"].filename == "":
                return jsonify({"error": "Sube un archivo GML o ZIP FXCC."}), 400
            f = request.files["entrada"]
            ext = os.path.splitext(f.filename)[1].lower() or ".gml"
            entrada_tmp = os.path.join(_SALIDA, f"{uuid.uuid4().hex}{ext}")
            f.save(entrada_tmp)
            tmp_files.append(entrada_tmp)

            fxcc_tmp = None
            if "fxcc" in request.files and request.files["fxcc"].filename:
                ff = request.files["fxcc"]
                fxcc_tmp = os.path.join(_SALIDA, f"{uuid.uuid4().hex}.zip")
                ff.save(fxcc_tmp)
                tmp_files.append(fxcc_tmp)

        def num(nombre, defecto):
            v = request.form.get(nombre, "").strip()
            return float(v) if v else defecto

        vial = num("vial", 0.0)
        lindero_r = num("lindero", 0.0)
        uniforme = num("retranqueo", 0.0)
        if uniforme > 0:
            vial = lindero_r = uniforme
        ocupacion = num("ocupacion", 60.0) / 100.0
        edif_raw = request.form.get("edif", "").strip()
        edif = float(edif_raw) if edif_raw else None
        modo = request.form.get("modo", "auto")
        tol = num("tolerancia", 0.05)

        params = ParametrosUrbanisticos(
            retranqueo_vial=vial, retranqueo_lindero=lindero_r,
            ocupacion=ocupacion, edificabilidad=edif,
            modo_huella=ModoHuella(modo),
            umbrales=UmbralesValidacion(tolerancia_vertice_m=tol))

        entrada = leer_entrada(entrada_tmp, fxcc=fxcc_tmp)

        # --- PARAMETROS LOGISTICOS ---
        from encaje.domain.implantacion import ParametrosLogisticos, TipoOficina
        playa = num("playa", 35.0)
        oficinas_pct = num("oficinas_pct", 0.0) / 100.0  # 0 = desactivado
        tipo_ofi = request.form.get("tipo_oficina", "integrada")
        n_plantas = int(num("n_plantas", 2))
        modulo_muelle = num("modulo_muelle", 5.5)
        params_log = None
        if playa > 0 or oficinas_pct > 0:
            params_log = ParametrosLogisticos(
                playa_principal_m=playa,
                oficinas_pct=oficinas_pct,
                tipo_oficina=TipoOficina(tipo_ofi) if tipo_ofi else TipoOficina.INTEGRADA,
                n_plantas_oficinas=max(n_plantas, 1),
                modulo_muelle_m=modulo_muelle)

        # --- APLICAR CLASIFICACIONES MANUALES DE LINDEROS ---
        import json as _json
        clasif_raw = request.form.get("linderos_clasificacion", "").strip()
        if clasif_raw:
            try:
                clasifs = _json.loads(clasif_raw)
                for item in clasifs:
                    idx = item.get("indice")
                    tipo = item.get("tipo")
                    if idx is not None and 0 <= idx < len(entrada.linderos):
                        lind = entrada.linderos[idx]
                        tipo_map = {
                            "vial": TipoLindero.VIAL,
                            "acceso_principal": TipoLindero.ACCESO_PRINCIPAL,
                            "acceso_secundario": TipoLindero.ACCESO_SECUNDARIO,
                            "privado": TipoLindero.PRIVADO,
                        }
                        lind.tipo = tipo_map.get(tipo, TipoLindero.DESCONOCIDO)
                        lind.fuente_tipo = FuenteTipo.MANUAL
            except _json.JSONDecodeError:
                pass  # ignorar si el JSON es invalido

        parcela = entrada.parcela
        resultado = calcular(entrada, params, params_log)

        kml_id = uuid.uuid4().hex
        escribir_kml(resultado, os.path.join(_SALIDA, f"{kml_id}.kml"))

        huellas = [{
            "tipo": h.tipo, "area": round(h.area),
            "dims": f"{h.dims[0]:.0f}x{h.dims[1]:.0f}m" if h.dims else "",
            "alcanza": h.alcanza_objetivo,
        } for h in resultado.huellas]

        incidencias = [{
            "gravedad": i.gravedad.value, "tipo": i.tipo,
            "mensaje": str(i),
        } for i in resultado.validacion.incidencias]

        colindantes = [{
            "referencia": c.referencia, "area": round(c.area_calculada),
            "uso": c.uso or "",
        } for c in resultado.colindantes]

        # Implantacion logistica (si existe)
        impl_json = None
        if resultado.implantacion:
            imp = resultado.implantacion

            def _impl_to_json(im):
                return {
                    "nave_gla": round(im.nave_gla),
                    "nave_dims": f"{im.nave_dims[0]:.0f}x{im.nave_dims[1]:.0f}m"
                                 if im.nave_dims else "",
                    "nave_angulo": round(im.nave_angulo, 1),
                    "n_muelles": im.n_muelles,
                    "longitud_muelles": round(im.longitud_muelles),
                    "score": round(im.puntuacion, 3),
                    "descripcion": im.descripcion,
                    "playas": [{"tipo": p.tipo,
                                "profundidad": round(p.profundidad_real, 1),
                                "area": round(p.area)}
                               for p in im.playas],
                    "oficinas": [{"tipo": o.tipo, "area": round(o.area),
                                  "posicion": o.posicion}
                                 for o in im.oficinas],
                }

            impl_json = _impl_to_json(imp)
            impl_json["alternativas"] = [_impl_to_json(a)
                                         for a in getattr(imp, 'alternativas', [])]

        # Limpiar cache de precarga
        if pid and pid in _PRECARGADOS:
            del _PRECARGADOS[pid]

        return jsonify({
            "referencia": parcela.referencia,
            "formato": entrada.formato_origen,
            "area_parcela": round(parcela.area_calculada),
            "discrepancia": round(parcela.discrepancia_pct, 3),
            "compacidad": round(resultado.compacidad * 100, 1),
            "orientacion": round(resultado.angulo_parcela, 1),
            "area_edificable": round(resultado.area_edificable),
            "gla_objetivo": round(resultado.gla_objetivo),
            "estado": resultado.estado.value,
            "estado_color": resultado.estado.color,
            "huellas": huellas,
            "incidencias": incidencias,
            "colindantes": colindantes,
            "implantacion": impl_json,
            "kml_id": kml_id,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for t in tmp_files:
            try:
                os.remove(t)
            except OSError:
                pass


@app.route("/descargar/<kml_id>")
def descargar(kml_id):
    if not all(c in "0123456789abcdef" for c in kml_id):
        return "ID invalido", 400
    kml_path = os.path.join(_SALIDA, f"{kml_id}.kml")
    if not os.path.exists(kml_path):
        return "KML no encontrado o expirado", 404
    return send_file(kml_path, as_attachment=True, download_name="encaje.kml",
                     mimetype="application/vnd.google-earth.kml+xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
