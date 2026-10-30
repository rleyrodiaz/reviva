"""Verifica en proceso el fix de es_entrada explícito:
- "vaciar chat" ya NO toca estado ni fecha de ningún guion (solo borra
  historial); reactivar es responsabilidad exclusiva de "Reabrir conversación".
- un guion marcado es_entrada=True se reactiva con "Reabrir conversación".
- un guion NO marcado y sin nada que lo referencie (huérfano) NO se reactiva,
  y aparece con la advertencia "huérfano" en la pantalla de la conversación."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models.guion import Guion
from app.models.enums import EstadoGuion


def ultimo_guion_id(conversacion_id):
    with get_db() as db:
        return db.scalar(
            select(Guion.id).where(Guion.conversacion_id == conversacion_id).order_by(Guion.id.desc())
        )

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación EsEntradaTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"
print("OK: conversación de prueba creada, id =", conv_id)

# Guion de entrada real (marcado explícitamente)
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Entrada real marcada",
        "tipo_respuesta": "libre",
        "modo_envio": "manual",
        "nodo_padre_id": "",
        "es_entrada": "true",
    },
)
assert r.status_code == 200, r.text
guion_entrada_id = ultimo_guion_id(conv_id)
print("OK: guion de entrada creado y marcado, id =", guion_entrada_id)

# Guion huérfano: no marcado como entrada, y nadie lo referencia como destino
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "fecha_programada": "2099-01-01T10:00",
        "texto_mensaje": "Guion huerfano de prueba",
        "tipo_respuesta": "libre",
        "modo_envio": "manual",
        "nodo_padre_id": "",
    },
)
assert r.status_code == 200, r.text
guion_huerfano_id = ultimo_guion_id(conv_id)
assert guion_huerfano_id != guion_entrada_id
print("OK: guion huérfano creado (sin marcar), id =", guion_huerfano_id)

with get_db() as db:
    g1 = db.get(Guion, guion_entrada_id)
    g2 = db.get(Guion, guion_huerfano_id)
    assert g1.es_entrada is True
    assert g2.es_entrada is False
    g1.estado = EstadoGuion.enviado
    g2.estado = EstadoGuion.enviado
    db.commit()
print("OK: estado inicial de ambos guiones en 'enviado' (simulando que ya se mandaron)")

r = client.get(CONV_URL)
assert '"huerfano": true' in r.text or '"huerfano":true' in r.text
print("OK: el mapa de la conversación marca al guion huérfano como tal")

# Vaciar el chat de Carlos (personaje_id=3) -> NO debe tocar ningún guion
r = client.post(f"{PERSONAJE_URL}/vaciar-chat")
if r.status_code not in (200, 303):
    print("STATUS:", r.status_code)
    print(r.text[:3000])
assert r.status_code in (200, 303)

with get_db() as db:
    g1 = db.get(Guion, guion_entrada_id)
    g2 = db.get(Guion, guion_huerfano_id)
    assert g1.estado == EstadoGuion.enviado, "vaciar-chat no debería tocar el guion de entrada"
    assert g2.estado == EstadoGuion.enviado, "vaciar-chat no debería tocar el guion huérfano"
print("OK: vaciar-chat no reactivó ningún guion (solo borra historial)")

# Reabrir la conversación -> debe reactivar SOLO el de entrada, con la fecha elegida
r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/reabrir", data={"fecha_programada": "2020-05-05T00:00"})
assert r.status_code in (200, 303)

with get_db() as db:
    g1 = db.get(Guion, guion_entrada_id)
    g2 = db.get(Guion, guion_huerfano_id)
    assert g1.estado == EstadoGuion.borrador, "el guion de entrada debería reactivarse al reabrir"
    assert g1.fecha_programada.isoformat().startswith("2020-05-05")
    assert g2.estado == EstadoGuion.enviado, "el guion huérfano NO debería reactivarse nunca"
print("OK: reabrir conversación reactivó el guion de entrada y dejó intacto el huérfano")

# Limpieza
r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
with get_db() as db:
    assert db.get(Guion, guion_entrada_id) is None
    assert db.get(Guion, guion_huerfano_id) is None
print("OK: conversación de prueba borrada")

print("\nTODO OK: es_entrada explícito funciona; huérfanos ya no se reactivan solos.")
