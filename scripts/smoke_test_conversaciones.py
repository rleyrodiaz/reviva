"""Verifica en proceso el flujo completo de Conversaciones: crear, listar,
renombrar, reabrir, traer guion de otra conversación, y borrar."""
import re

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

r = client.get(PERSONAJE_URL)
assert "Nueva conversación" in r.text
print("OK: pantalla de personaje muestra conversaciones, no guiones sueltos")

# Crear conversación de prueba
r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación SmokeTest"})
assert "Conversación SmokeTest" in r.text
conv_id = int(re.search(r'/conversaciones/(\d+)">\s*<strong>Conversaci\xf3n SmokeTest', r.text).group(1))
print("OK: conversación creada, id =", conv_id)

CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"

# Crear un guion de entrada (opciones) dentro de esta conversación
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Entrada de la conversación de prueba",
        "tipo_respuesta": "opciones",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
assert "Entrada de la conversación de prueba" in r.text
guion_ids = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
guion_id = max(guion_ids)
print("OK: guion de entrada creado, id =", guion_id)

# Renombrar la conversación
r = client.post(f"{CONV_URL[:CONV_URL.rfind('/conversaciones/')]}/conversaciones/{conv_id}/editar", data={"nombre": "SmokeTest Renombrada"})
r = client.get(PERSONAJE_URL)
assert "SmokeTest Renombrada" in r.text
print("OK: conversación renombrada")

# Reabrir la conversación con nueva fecha -> debe reactivar el guion de entrada
r = client.post(
    f"{PERSONAJE_URL}/conversaciones/{conv_id}/reabrir",
    data={"fecha_programada": "2020-01-01T00:00"},
)
from sqlalchemy import select
from app.db import get_db
from app.models.guion import Guion
from app.models.enums import EstadoGuion

with get_db() as db:
    g = db.get(Guion, guion_id)
    assert g.estado == EstadoGuion.borrador
    assert g.fecha_programada.isoformat().startswith("2020-01-01")
print("OK: reabrir conversación reactivó el guion de entrada con la nueva fecha")

# Traer un guion de OTRA conversación (Carlos ya tiene guiones en su "Conversación inicial")
r = client.get(f"{PERSONAJE_URL}/conversaciones/{conv_id}")
assert "Traer guion de otra conversación" in r.text
opciones_importar = re.findall(r'<option value="(\d+)">([^/]+) / ([^—]+) — ', r.text)
assert len(opciones_importar) > 0, "no hay guiones de otras conversaciones para importar"
guion_origen_id = opciones_importar[0][0]
r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/guiones/importar", data={"guion_origen_id": guion_origen_id})
assert r.status_code == 200
print("OK: se importó una copia de un guion de otra conversación")

# Borrar la conversación completa
r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
r = client.get(PERSONAJE_URL)
assert "SmokeTest Renombrada" not in r.text
with get_db() as db:
    assert db.get(Guion, guion_id) is None, "el guion debería haberse borrado en cascada"
print("OK: borrar conversación elimina también sus guiones (cascada)")

print("\nTODO OK: flujo de Conversaciones funciona de punta a punta.")
