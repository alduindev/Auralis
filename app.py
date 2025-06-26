import datetime
import dateparser
import ollama
import time
import re
import requests
from spellchecker import SpellChecker

spell = SpellChecker(language='es')

class MemoriaConversacional:
    def __init__(self):
        self.ultimo_monto = None
        self.ultima_moneda = None
        self.ultimo_texto = ""
        self.ultima_fecha = None

memoria = MemoriaConversacional()

def corregir_ortografia(texto):
    inicio = time.time()
    palabras = texto.split()
    corregidas = [
        spell.correction(p) if p in spell.unknown([p]) else p
        for p in palabras
    ]
    print(f"⏳ Tiempo en corrección ortográfica: {time.time() - inicio:.2f} s")
    return ' '.join(corregidas)

def corregir_gramatica(texto):
    inicio = time.time()
    response = ollama.chat(
        model="mistral",
        messages=[{
            "role": "user",
            "content": f"Corrige ortografía, gramática y signos de puntuación del siguiente texto. Devuélvelo corregido sin explicar:\n\n\"{texto}\""
        }]
    )
    print(f"⏳ Tiempo en corrección gramatical: {time.time() - inicio:.2f} s")
    return response['message']['content'].strip()

def ajustar_fecha_futura(fecha):
    ahora = datetime.datetime.now()
    if fecha and fecha < ahora:
        try:
            return fecha.replace(year=ahora.year + 1)
        except ValueError:
            return fecha + datetime.timedelta(days=365)
    return fecha

def contiene_intencion_fecha(texto):
    texto = texto.lower()
    claves = [
        "cuándo", "cuando", "falta", "faltan", "queda", "quedan", "navidad",
        "año nuevo", "cumpleaños", "semana santa", "hoy", "qué día", "que día",
        "que fecha", "fecha actual", "día actual", "hasta", "para", "cuánto falta"
    ]
    return any(p in texto for p in claves)

def extraer_fecha_de_respuesta(texto):
    posibles = re.findall(r"\d{4}-\d{2}-\d{2}", texto)
    if posibles:
        return posibles[0]
    match = re.search(r"(\d{1,2} de [a-zA-Záéíóúñ]+( del| de)? \d{4})", texto, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def convertir_moneda(texto: str):
    texto = texto.lower().replace(",", ".").replace("s/", "pen ").replace("$", "usd ")

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(usd|eur|pen|ars|mxn|clp|soles|dólares|euros)?\s*(a|en)?\s*(usd|eur|pen|ars|mxn|clp|soles|dólares|euros)?",
        texto
    )
    if not match:
        if memoria.ultimo_monto and memoria.ultima_moneda:
            if " a " in texto or " en " in texto:
                texto = f"{memoria.ultimo_monto} {memoria.ultima_moneda} {texto}"
                return convertir_moneda(texto)
        return None

    cantidad, desde, _, hacia = match.groups()

    simbolos = {
        "soles": "PEN", "dólares": "USD", "euros": "EUR"
    }

    desde = simbolos.get(desde, desde).upper() if desde else "PEN"
    hacia = simbolos.get(hacia, hacia).upper() if hacia else "USD"

    try:
        cantidad = float(cantidad)
    except ValueError:
        return None

    memoria.ultimo_monto = cantidad
    memoria.ultima_moneda = desde

    url = f"https://api.exchangerate.host/convert?from={desde}&to={hacia}&amount={cantidad}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            resultado = data.get("result")
            if resultado is not None:
                return f"💱 {cantidad:.2f} {desde} = {resultado:.2f} {hacia}"
    except:
        return "❌ No se pudo obtener la tasa de cambio en este momento."
    return None

def interpretar_fecha(pregunta: str):
    total_inicio = time.time()
    errores = spell.unknown(pregunta.split())
    entrada_final = corregir_gramatica(corregir_ortografia(pregunta)) if errores else pregunta.strip()

    memoria.ultimo_texto = entrada_final
    print(f"📝 Entrada corregida: \"{entrada_final}\"")

    if not contiene_intencion_fecha(entrada_final):
        print(f"⏲️ Tiempo total sin análisis de fecha: {time.time() - total_inicio:.2f} s")
        return None, entrada_final

    if any(x in entrada_final.lower() for x in ["hoy", "qué día es", "que día es", "qué fecha es", "día actual"]):
        fecha_actual = datetime.datetime.now()
        print(f"📆 Fecha actual: {fecha_actual.strftime('%Y-%m-%d')}")
        print(f"⏲️ Tiempo total interpretación: {time.time() - total_inicio:.2f} s")
        return fecha_actual, entrada_final

    inicio_modelo = time.time()
    response = ollama.chat(
        model="mistral",
        messages=[{
            "role": "user",
            "content": f"Extrae solo la fecha (explícita o implícita) del siguiente texto. Devuélvela como texto o en formato YYYY-MM-DD, sin explicar:\n\n{entrada_final}"
        }]
    )
    print(f"📡 Tiempo modelo: {time.time() - inicio_modelo:.2f} s")
    texto_respuesta = response['message']['content'].strip()
    print(f"🧠 Respuesta cruda del modelo: {texto_respuesta}")

    fecha_extraida = extraer_fecha_de_respuesta(texto_respuesta)
    fecha_objetivo = dateparser.parse(fecha_extraida, languages=["es"]) if fecha_extraida else None

    if not fecha_objetivo:
        fecha_objetivo = dateparser.parse(entrada_final, languages=["es"])
        if fecha_objetivo:
            print("⚠️ Fallback: usando dateparser sobre la entrada completa.")

    fecha_objetivo = ajustar_fecha_futura(fecha_objetivo)
    memoria.ultima_fecha = fecha_objetivo

    print(f"⏲️ Tiempo total interpretación: {time.time() - total_inicio:.2f} s")
    return fecha_objetivo, entrada_final

def responder_conocimiento_general(pregunta: str):
    inicio = time.time()
    print("🤖 Interpretando como pregunta general...")
    response = ollama.chat(
        model="mistral",
        messages=[{
            "role": "user",
            "content": f"Responde esta pregunta como un asistente conversacional experto:\n\n{pregunta}"
        }]
    )
    print(f"📡 Tiempo modelo general: {time.time() - inicio:.2f} s")
    return response['message']['content'].strip()

def cuanto_falta(pregunta: str):
    fecha, entrada_final = interpretar_fecha(pregunta)
    if fecha:
        ahora = datetime.datetime.now()
        diferencia = fecha - ahora
        dias = diferencia.days
        horas = diferencia.seconds // 3600
        minutos = (diferencia.seconds % 3600) // 60
        return f"⏱️ Faltan {dias} días, {horas} horas y {minutos} minutos para {fecha.strftime('%d de %B de %Y, %H:%M')}."
    return responder_conocimiento_general(entrada_final)

def detectar_intencion(texto: str) -> str:
    texto = texto.lower()
    if re.search(r"\d+.*(dólares|soles|usd|eur|pen|ars|mxn|clp|euros)", texto):
        return "moneda"
    elif contiene_intencion_fecha(texto):
        return "fecha"
    return "general"

def motor_respuesta(pregunta: str):
    intencion = detectar_intencion(pregunta)
    if intencion == "moneda":
        resultado = convertir_moneda(pregunta)
        if resultado:
            return resultado
    elif intencion == "fecha":
        return cuanto_falta(pregunta)
    return responder_conocimiento_general(pregunta)

# === MAIN: consola y servidor web ===
if __name__ == "__main__":
    import threading
    from flask import Flask, render_template_string, request
    import socket

    app = Flask(__name__)
    HTML = """
    <!DOCTYPE html>
    <html lang="es">
    <head><meta charset="UTF-8"><title>Asistente IA Web</title></head>
    <body style="font-family:sans-serif; padding:2rem;">
        <h2>🤖 Asistente IA (modo web)</h2>
        <form method="post">
            <input type="text" name="pregunta" style="width:60%; padding:0.5rem;" autofocus required>
            <button type="submit">Preguntar</button>
        </form>
        {% if respuesta %}
        <div style="margin-top:2rem;">
            <h3>Respuesta:</h3>
            <p>{{ respuesta }}</p>
        </div>
        {% endif %}
    </body>
    </html>
    """

    @app.route("/", methods=["GET", "POST"])
    def index():
        respuesta = ""
        if request.method == "POST":
            pregunta = request.form["pregunta"]
            if pregunta:
                respuesta = motor_respuesta(pregunta)
        return render_template_string(HTML, respuesta=respuesta)

    ip_local = socket.gethostbyname(socket.gethostname())
    print(f"🌐 Servidor disponible en http://{ip_local}:8000")
    threading.Thread(target=lambda: app.run(host=ip_local, port=8000, debug=False, use_reloader=False)).start()

    while True:
        try:
            pregunta = input("¿Qué quieres saber?: ").strip()
            if pregunta:
                print(motor_respuesta(pregunta))
        except KeyboardInterrupt:
            print("\n👋 Hasta luego.")
            break
        except Exception as e:
            print(f"⚠️ Error: {e}")
