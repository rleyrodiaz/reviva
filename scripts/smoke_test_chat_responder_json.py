"""Verifica en proceso que /chat/.../responder devuelve JSON con el
próximo mensaje del personaje (si lo hay) en vez de redirigir — es lo que
ahora consume chat.js para mostrar la devolución con una demora creíble en
vez de recargar la página de golpe. También que un fallback sin destino
armado genera un cierre con IA en vez de dejar al paciente sin contestar
nada (mockeado para no depender de la IA real ni de su no-determinismo)."""
import re

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

import app.services.motor as motor_mod
from app.db import get_db
from app.main import app
from app.models.conversacion import Conversacion
from app.models.guion import Guion
from app.models.opcion_respuesta import OpcionRespuesta
from app.services.motor import procesar_guiones_vencidos

motor_mod.generar_cierre = lambda anterior, texto, personaje: "Dale, un beso, después seguimos hablando"

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"
PACIENTE_ID = 2
PERSONAJE_ID = 3

r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación ChatJsonTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"


def crear(texto, tipo):
    r = client.post(
        f"{CONV_URL}/guiones",
        data={"texto_mensaje": texto, "tipo_respuesta": tipo, "nodo_padre_id": ""},
    )
    assert r.status_code == 200, r.text
    with get_db() as db:
        return db.scalar(
            select(Guion.id).where(Guion.conversacion_id == conv_id).order_by(Guion.id.desc())
        )


# Guion de entrada (opciones) -> guion2 (libre, sin ramas con nombre, solo fallback sin destino)
guion1_id = crear("¿Querés que te cuente una novedad?", "opciones")
guion2_id = crear("Guion destino", "libre")

r = client.post(
    f"{CONV_URL}/guiones/{guion1_id}/conectar",
    data={"destino_id": str(guion2_id), "etiqueta": "Sí, contame"},
)
assert r.status_code == 200, r.text
opcion_id = r.json()["arista"]["id"]

r = client.post(f"{CONV_URL}/configuracion", data={"fecha_programada": "2020-01-01T10:00", "modo_envio": "automatico"})
assert r.status_code in (200, 303), r.text

with get_db() as db:
    procesar_guiones_vencidos(db, paciente_id=PACIENTE_ID)
    db.commit()
    assert db.get(Guion, guion1_id).estado.value == "enviado"
print("OK: guion de entrada automático se manda solo, queda esperando respuesta")

# Responder con la opción -> debería devolver JSON con el texto de guion2
r = client.post(
    f"/chat/{PACIENTE_ID}/{PERSONAJE_ID}/responder",
    data={"opcion_id": str(opcion_id)},
)
assert r.status_code == 200, r.text
data = r.json()
assert data["ok"] is True
assert data["respuesta_texto"] == "Guion destino"
assert data["siguiente_tipo"] == "libre"
assert data["siguiente_opciones"] is None
print("OK: responder una opción devuelve JSON con el próximo mensaje del personaje")

# Responder texto libre a guion2 (sin ramas con nombre, solo fallback sin
# destino armado) -> el clasificador no llama a la IA real (lista de ramas
# con nombre vacía, "sin match" seguro) y el cierre lo genera generar_cierre
# (mockeado arriba) en vez de dejar al paciente sin contestar nada.
r = client.post(
    f"/chat/{PACIENTE_ID}/{PERSONAJE_ID}/responder",
    data={"texto": "necesito medicamentos"},
)
assert r.status_code == 200, r.text
data = r.json()
assert data["ok"] is True
assert data["respuesta_texto"] == "Dale, un beso, después seguimos hablando"
assert data["siguiente_tipo"] is None
print("OK: un fallback sin destino genera un cierre con IA en vez de quedar sin contestar nada")

# El cierre queda en el historial: sigue apareciendo igual después de recargar la página.
r = client.get(f"/chat/{PACIENTE_ID}/{PERSONAJE_ID}")
assert r.status_code == 200
assert "Dale, un beso, después seguimos hablando" in r.text
print("OK: el cierre generado queda guardado y se ve igual después de recargar")

client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
with get_db() as db:
    assert db.get(Conversacion, conv_id) is None
print("OK: datos de prueba borrados")

print("\nTODO OK: /chat/.../responder devuelve JSON con el próximo mensaje del personaje, de punta a punta.")
