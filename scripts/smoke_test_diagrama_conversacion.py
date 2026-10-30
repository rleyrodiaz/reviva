"""Verifica que la pantalla de una conversación renderiza el mapa visual
(diagrama de flujo de solo lectura) sin romper: el JSON de nodos/aristas
sale bien formado, incluye los guiones de la conversación, y un guion con
'</script' en el texto no corta el bloque de datos."""
import json
import re

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models.conversacion import Conversacion
from app.models.guion import Guion


def ultimo_guion_id(conversacion_id):
    with get_db() as db:
        return db.scalar(
            select(Guion.id).where(Guion.conversacion_id == conversacion_id).order_by(Guion.id.desc())
        )

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación DiagramaTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"

# Guion de entrada con texto "peligroso" para el JSON embebido (cierre de script)
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Hola </script><script>alert(1)</script> probando",
        "tipo_respuesta": "opciones",
        "modo_envio": "manual",
        "nodo_padre_id": "",
        "es_entrada": "true",
    },
)
assert r.status_code == 200, r.text
guion_entrada_id = ultimo_guion_id(conv_id)

# Un segundo guion para que la entrada tenga una opción real (bifurcación)
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Segundo guion de la rama",
        "tipo_respuesta": "libre",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
assert r.status_code == 200, r.text
guion_destino_id = ultimo_guion_id(conv_id)

client.post(
    f"{CONV_URL}/guiones/{guion_entrada_id}/opciones",
    data={"texto_opcion": "Sí, contame", "guion_siguiente_id": str(guion_destino_id)},
)
client.post(
    f"{CONV_URL}/guiones/{guion_entrada_id}/opciones",
    data={"texto_opcion": "No, gracias", "guion_siguiente_id": ""},
)

r = client.get(CONV_URL)
assert r.status_code == 200
assert '<script type="application/json" id="diagrama-datos">' in r.text
assert "</script><script>alert(1)" not in r.text, "el texto peligroso no debería cortar el bloque JSON"
print("OK: la página renderiza y el texto conflictivo no rompe el bloque de datos")

match = re.search(
    r'<script type="application/json" id="diagrama-datos">(.*?)</script>',
    r.text, re.DOTALL,
)
assert match is not None, "no se encontró el bloque de datos del diagrama"
data = json.loads(match.group(1).replace("<\\/", "</"))
ids_en_json = {n["id"] for n in data["nodos"]}
assert guion_entrada_id in ids_en_json and guion_destino_id in ids_en_json
nodo_entrada = next(n for n in data["nodos"] if n["id"] == guion_entrada_id)
assert nodo_entrada["es_entrada"] is True
assert nodo_entrada["bifurcacion"] is True, "tiene 2 opciones, debería marcarse como bifurcación"
aristas_desde_entrada = [a for a in data["aristas"] if a["origen"] == guion_entrada_id]
assert len(aristas_desde_entrada) == 2
destinos = {a["destino"] for a in aristas_desde_entrada}
assert destinos == {guion_destino_id, None}
print("OK: el JSON del diagrama trae los nodos y aristas esperados, con la bifurcación marcada")

# Limpieza
r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
with get_db() as db:
    assert db.get(Guion, guion_entrada_id) is None
    assert db.get(Conversacion, conv_id) is None
print("OK: datos de prueba borrados")

print("\nTODO OK: el mapa visual de la conversación funciona de punta a punta.")
