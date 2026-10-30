"""Verifica en proceso: editar, duplicar, reabrir y borrar guiones."""
import re

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

# Crear un guion de prueba en borrador para no tocar los reales de Carlos.
r = client.post(
    f"{PERSONAJE_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Mensaje de prueba CRUD",
        "tipo_respuesta": "opciones",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
ids = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
guion_id = max(ids)
print("guion creado:", guion_id)

# Editar
r = client.post(
    f"{PERSONAJE_URL}/guiones/{guion_id}/editar",
    data={"fecha_programada": "2099-02-02T11:00", "texto_mensaje": "Mensaje editado CRUD"},
)
r = client.get(PERSONAJE_URL)
assert "Mensaje editado CRUD" in r.text
print("OK: editar guion")

# Duplicar
r = client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/duplicar")
r = client.get(PERSONAJE_URL)
ids_despues = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
assert len(ids_despues) == len(ids) + 1
nuevo_id = max(ids_despues)
assert r.text.count('<div class="texto">Mensaje editado CRUD</div>') == 2
print("OK: duplicar guion, nuevo id =", nuevo_id)

# Forzar el guion original a "enviado" directamente en la base para probar "reabrir"
from sqlalchemy import select
from app.db import get_db
from app.models.guion import Guion
from app.models.enums import EstadoGuion

with get_db() as db:
    g = db.get(Guion, guion_id)
    g.estado = EstadoGuion.enviado

r = client.get(PERSONAJE_URL)
assert "Reabrir con nueva fecha" in r.text
print("OK: 'reabrir' aparece para un guion ya enviado")

r = client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/reabrir", data={"fecha_programada": "2099-03-03T09:00"})
with get_db() as db:
    g = db.get(Guion, guion_id)
    assert g.estado == EstadoGuion.borrador
    assert g.fecha_programada.isoformat().startswith("2099-03-03")
print("OK: reabrir guion (vuelve a borrador con nueva fecha)")

# Borrar el duplicado
r = client.post(f"{PERSONAJE_URL}/guiones/{nuevo_id}/borrar")
r = client.get(PERSONAJE_URL)
assert f"#{nuevo_id} ·" not in r.text
print("OK: borrar guion")

# Limpiar: borrar también el original de prueba
client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/borrar")
r = client.get(PERSONAJE_URL)
assert "Mensaje editado CRUD" not in r.text
print("OK: limpieza de datos de prueba")

print("\nTODO OK: CRUD de guiones funciona.")
