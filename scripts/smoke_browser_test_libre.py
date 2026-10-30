"""Prueba adicional: camino de texto libre sin ANTHROPIC_API_KEY configurada,
para confirmar que el sistema cae en el fallback en vez de trabarse."""
import re
import sys
import time

import httpx

from scripts._smoke_auth import login_superadmin

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, follow_redirects=True)

login_superadmin(client)

r = client.get("/admin/familias")
familia_url = re.search(r'href="(/admin/familias/\d+)"', r.text).group(1)

r = client.post(
    f"{familia_url}/personajes",
    data={"nombre": "Marta", "foto": "", "descripcion": "", "relacion_con_paciente": "Hermana", "tono_escritura": ""},
)
personaje_url = re.search(r'"(/admin/familias/\d+/personajes/\d+)"', r.text[r.text.find("Marta") - 300:])
personaje_url = re.search(r'"(/admin/familias/\d+/personajes/\d+)"', r.text.split("Marta")[0][-300:]).group(1) \
    if False else None
# más simple: tomar todos los personaje-card y quedarse con el que dice Marta
bloques = re.findall(r'<a class="personaje-card" href="([^"]+)">\s*<h3>([^<]+)</h3>', r.text)
personaje_url = next(url for url, nombre in bloques if nombre == "Marta")
print("personaje_url:", personaje_url)

r = client.post(
    f"{personaje_url}/guiones",
    data={
        "fecha_programada": "2020-01-01T10:00",
        "texto_mensaje": "Che, me acordé de aquel cumpleaños de Juan!",
        "tipo_respuesta": "libre",
        "modo_envio": "automatico",
        "nodo_padre_id": "",
    },
)
guiones_ids = re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)
guion_id = guiones_ids[-1]
print("guion_id:", guion_id)

r = client.post(
    f"{personaje_url}/guiones/{guion_id}/ramas",
    data={"criterio": "El paciente recuerda el cumpleaños", "guion_siguiente_id": ""},
)
assert "El paciente recuerda el cumpleaños" in r.text, "no se agregó la rama"
print("OK: rama libre agregada")
assert "fallback" in r.text
print("OK: rama fallback visible automáticamente")

# Esperar que el scheduler lo mande (modo automático)
encontrado = False
for _ in range(15):
    r = client.get("/chat/2")
    if "Marta" in r.text:
        encontrado = True
        break
    time.sleep(2)
if not encontrado:
    print("FALLO: Marta no aparece en /chat/2 tras el tick del scheduler")
    sys.exit(1)
print("OK: guion automático enviado, Marta aparece en contactos")

personaje_id = personaje_url.rsplit("/", 1)[-1]
chat_url = f"/chat/2/{personaje_id}"
r = client.get(chat_url)
assert "Che, me acordé de aquel cumpleaños de Juan!" in r.text
assert 'name="texto"' in r.text, "esperaba un input de texto libre, no quick replies"
print("OK: conversación muestra input de texto libre (no quick replies)")

r = client.post(f"{chat_url}/responder", data={"texto": "no tengo idea de que hablas", "opcion_id": ""})
assert "bubble-out" in r.text
assert "no tengo idea de que hablas" in r.text
print("OK: respuesta libre registrada; con classifier sin API key debería haber caído en fallback (sin trabarse).")
print("\nTODO OK (camino libre + fallback).")
