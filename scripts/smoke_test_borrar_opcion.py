"""Verifica en proceso: borrar una opción y borrar una rama libre (sin poder
borrar el fallback)."""
import re

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

# Guion tipo opciones con dos opciones de prueba
r = client.post(
    f"{PERSONAJE_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Guion prueba borrar opcion",
        "tipo_respuesta": "opciones",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
ids = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
guion_id = max(ids)

client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/opciones", data={"texto_opcion": "Opcion A", "guion_siguiente_id": ""})
client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/opciones", data={"texto_opcion": "Opcion B", "guion_siguiente_id": ""})

r = client.get(PERSONAJE_URL)
assert '"Opcion A"' in r.text and '"Opcion B"' in r.text
opcion_a_id = re.search(r'/opciones/(\d+)/borrar"\s*\n\s*onsubmit[^>]*>\s*<button[^>]*>✕', r.text)

from sqlalchemy import select
from app.db import get_db
from app.models.opcion_respuesta import OpcionRespuesta

with get_db() as db:
    opcion_a = db.scalar(select(OpcionRespuesta).where(OpcionRespuesta.texto_opcion == "Opcion A"))
    opcion_a_id = opcion_a.id

r = client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/opciones/{opcion_a_id}/borrar")
r = client.get(PERSONAJE_URL)
assert '"Opcion A"' not in r.text
assert '"Opcion B"' in r.text
print("OK: borrar opción individual, la otra queda intacta")

# Guion tipo libre: borrar una rama no-fallback, e intentar borrar el fallback (no debe borrarse)
r = client.post(
    f"{PERSONAJE_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Guion prueba borrar rama",
        "tipo_respuesta": "libre",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
ids2 = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
guion_libre_id = max(ids2)
client.post(f"{PERSONAJE_URL}/guiones/{guion_libre_id}/ramas", data={"criterio": "Criterio X", "guion_siguiente_id": ""})

from app.models.rama_respuesta_libre import RamaRespuestaLibre
with get_db() as db:
    rama_x = db.scalar(select(RamaRespuestaLibre).where(RamaRespuestaLibre.criterio == "Criterio X"))
    rama_x_id = rama_x.id
    fallback = db.scalar(
        select(RamaRespuestaLibre).where(
            RamaRespuestaLibre.guion_id == guion_libre_id, RamaRespuestaLibre.es_fallback == True
        )
    )
    fallback_id = fallback.id

client.post(f"{PERSONAJE_URL}/guiones/{guion_libre_id}/ramas/{rama_x_id}/borrar")
r = client.get(PERSONAJE_URL)
assert "Criterio X" not in r.text
print("OK: borrar rama libre no-fallback")

# Intento de borrar el fallback: no debería desaparecer
client.post(f"{PERSONAJE_URL}/guiones/{guion_libre_id}/ramas/{fallback_id}/borrar")
with get_db() as db:
    still_there = db.get(RamaRespuestaLibre, fallback_id)
    assert still_there is not None
print("OK: el fallback no se puede borrar")

# Limpieza
client.post(f"{PERSONAJE_URL}/guiones/{guion_id}/borrar")
client.post(f"{PERSONAJE_URL}/guiones/{guion_libre_id}/borrar")
r = client.get(PERSONAJE_URL)
assert "Guion prueba borrar opcion" not in r.text
assert "Guion prueba borrar rama" not in r.text
print("OK: limpieza de datos de prueba")

print("\nTODO OK: borrar opciones/ramas funciona.")
