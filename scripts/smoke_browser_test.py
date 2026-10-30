"""Simula un navegador (cookies + redirects) contra el server real corriendo
en localhost:8000, para probar el flujo de punta a punta sin depender de un
navegador de verdad (no disponible en esta máquina)."""
import re
import sys
import time

import httpx

from scripts._smoke_auth import login_superadmin

BASE = "http://127.0.0.1:8000"


def paso(nombre):
    print(f"\n=== {nombre} ===")


def assert_in(texto, contenido, nombre):
    if texto not in contenido:
        print(f"FALLO: no se encontró {texto!r} en {nombre}")
        print(contenido[:1500])
        sys.exit(1)
    print(f"OK: {texto!r} presente en {nombre}")


client = httpx.Client(base_url=BASE, follow_redirects=True)

paso("1. GET / redirige a /login")
r = client.get("/")
print("URL final:", r.url, "status:", r.status_code)
assert str(r.url).endswith("/login"), f"esperaba terminar en /login, terminó en {r.url}"
assert_in('name="email"', r.text, "/login")

paso("2. Login como superadmin")
r = login_superadmin(client)
print("URL final:", r.url, "status:", r.status_code)
assert_in("Familia MVP", r.text, "listado de familias")

paso("3. Entrar a la familia")
m = re.search(r'href="(/admin/familias/\d+)"', r.text)
familia_url = m.group(1)
r = client.get(familia_url)
assert_in("Personajes", r.text, "dashboard de familia")

paso("4. Crear personaje Carlos")
r = client.post(
    f"{familia_url}/personajes",
    data={
        "nombre": "Carlos",
        "foto": "",
        "descripcion": "Viajaron juntos a Mar del Plata",
        "relacion_con_paciente": "Amigo de la infancia",
        "tono_escritura": "Informal, usa vos",
    },
)
assert_in("Carlos", r.text, "dashboard tras crear personaje")

m = re.search(r'href="(/admin/familias/\d+/personajes/(\d+))"[^>]*>\s*<h3>Carlos</h3>', r.text)
if not m:
    m = re.search(r'/admin/familias/\d+/personajes/(\d+)', r.text)
personaje_url = re.search(r'"(/admin/familias/\d+/personajes/\d+)"', r.text).group(1)
personaje_id = personaje_url.rsplit("/", 1)[-1]
print("personaje_url:", personaje_url)

paso("5. Abrir detalle del personaje")
r = client.get(personaje_url)
assert_in("Nuevo guion", r.text, "detalle de personaje")

paso("6. Crear guion (opciones, manual, fecha pasada)")
fecha_pasada = "2020-01-01T10:00"
r = client.post(
    f"{personaje_url}/guiones",
    data={
        "fecha_programada": fecha_pasada,
        "texto_mensaje": "Hola! Como estas?",
        "tipo_respuesta": "opciones",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
assert_in("Hola! Como estas?", r.text, "detalle de personaje tras crear guion")

m = re.search(r"#(\d+) ·.*?\n.*?Hola! Como estas\?", r.text)
guion_id = None
for gm in re.finditer(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text):
    guion_id = gm.group(1)
print("guion_id:", guion_id)

paso("7. Agregar dos opciones de respuesta")
r = client.post(
    f"{personaje_url}/guiones/{guion_id}/opciones",
    data={"texto_opcion": "Bien", "guion_siguiente_id": ""},
)
r = client.post(
    f"{personaje_url}/guiones/{guion_id}/opciones",
    data={"texto_opcion": "Mal", "guion_siguiente_id": ""},
)
assert_in('"Bien"', r.text, "detalle de personaje tras agregar opciones")
assert_in('"Mal"', r.text, "detalle de personaje tras agregar opciones")

paso("8. Esperar el tick del scheduler (guion vencido -> pendiente_aprobacion)")
bandeja_url = f"{familia_url}/bandeja"
encontrado = False
for i in range(15):
    r = client.get(bandeja_url)
    if "Hola! Como estas?" in r.text:
        encontrado = True
        break
    time.sleep(2)
if not encontrado:
    print("FALLO: el guion nunca aparecio en la bandeja de aprobacion")
    print(r.text[:1500])
    sys.exit(1)
print("OK: guion visible en bandeja de aprobación")

paso("9. Aprobar el guion desde la bandeja")
r = client.post(
    f"{bandeja_url}/{guion_id}/aprobar", data={"texto_mensaje": "Hola! Como estas?"}
)
assert_in("No hay guiones esperando aprobación", r.text, "bandeja tras aprobar")

paso("10. Ver lista de contactos del paciente")
r = client.get("/chat/2")
assert_in("Carlos", r.text, "lista de contactos")
assert_in("dot-nuevo", r.text, "lista de contactos (indicador de mensaje nuevo)")

paso("11. Abrir la conversación con Carlos")
chat_url = f"/chat/2/{personaje_id}"
r = client.get(chat_url)
assert_in("Hola! Como estas?", r.text, "conversación")
assert_in("quick-reply-btn", r.text, "conversación (botones de opciones)")
assert_in(">Bien<", r.text, "conversación")
assert_in(">Mal<", r.text, "conversación")

paso("12. El paciente responde 'Bien' (quick reply)")
m = re.search(r'name="opcion_id" value="(\d+)">\s*<button class="quick-reply-btn" type="submit">Bien<', r.text)
opcion_id = m.group(1)
r = client.post(f"{chat_url}/responder", data={"opcion_id": opcion_id, "texto": ""})
assert_in("bubble-out", r.text, "conversación tras responder")
assert_in("Bien", r.text, "conversación tras responder")
assert_in("Esperando el próximo mensaje", r.text, "conversación tras responder (sin guion siguiente)")

print("\n\nTODO OK: flujo completo funcionando de punta a punta.")
