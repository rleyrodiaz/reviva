"""Verifica en proceso el flujo de Web Push: endpoint de clave pública,
suscripción, envío real de guion disparando el push (mockeado), y limpieza de
suscripciones vencidas."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app
from app.services.push import WebPushException

client = TestClient(app)
login_superadmin(client)

r = client.get("/push/vapid-public-key")
assert r.status_code == 200
assert len(r.json()["public_key"]) > 0
print("OK: clave pública VAPID disponible")

# Habilitar push para el paciente 2
r = client.post(
    "/admin/familias/2/pacientes/2/configuracion",
    data={"tema": "claro", "tamano_fuente": "normal", "push_habilitado": "true"},
    follow_redirects=True,
)
r = client.get("/chat/2")
assert 'data-push-habilitado="true"' in r.text
print("OK: push habilitado se refleja en el chat del paciente")

# Suscribir un "dispositivo" de prueba
r = client.post(
    "/push/2/suscribir",
    json={
        "endpoint": "https://ejemplo-push.test/endpoint-1",
        "keys": {"p256dh": "clave-p256dh-fake", "auth": "clave-auth-fake"},
    },
)
assert r.status_code == 200 and r.json()["ok"] is True
print("OK: suscripción guardada")

# Crear un guion automático vencido y ver que dispare el push (mockeado)
import re
PERSONAJE_URL = "/admin/familias/2/personajes/3"
r = client.post(
    f"{PERSONAJE_URL}/guiones",
    data={
        "fecha_programada": "2020-01-01T10:00",
        "texto_mensaje": "Mensaje de prueba push",
        "tipo_respuesta": "opciones",
        "modo_envio": "automatico",
        "nodo_padre_id": "",
    },
)
ids = [int(x) for x in re.findall(r'nodo-guion">\s*<div class="meta">\s*#(\d+)', r.text)]
guion_id = max(ids)

with patch("app.services.push.webpush") as mock_webpush:
    from app.db import get_db
    from app.services import motor
    with get_db() as db:
        motor.procesar_guiones_vencidos(db, paciente_id=2)
    assert mock_webpush.called, "no se llamó a webpush()"
    kwargs = mock_webpush.call_args.kwargs
    assert kwargs["subscription_info"]["endpoint"] == "https://ejemplo-push.test/endpoint-1"
    print("OK: procesar_guiones_vencidos disparó el push con la suscripción correcta")

# Simular que la suscripción venció (410) y verificar que se borra sola
resp_410 = MagicMock(status_code=410)
with patch("app.services.push.webpush", side_effect=WebPushException("gone", response=resp_410)):
    with get_db() as db:
        r2 = client.post(
            f"{PERSONAJE_URL}/guiones",
            data={
                "fecha_programada": "2020-01-01T10:00",
                "texto_mensaje": "Otro mensaje",
                "tipo_respuesta": "opciones",
                "modo_envio": "automatico",
                "nodo_padre_id": "",
            },
        )
    with get_db() as db:
        motor.procesar_guiones_vencidos(db, paciente_id=2)

from sqlalchemy import select
from app.models.push_subscription import PushSubscription
with get_db() as db:
    quedan = db.scalars(select(PushSubscription).where(PushSubscription.paciente_id == 2)).all()
    assert len(quedan) == 0, "la suscripción vencida debería haberse borrado"
print("OK: suscripción vencida (410) se limpia sola")

# Deshabilitar push y limpiar datos de prueba
client.post(
    "/admin/familias/2/pacientes/2/configuracion",
    data={"tema": "claro", "tamano_fuente": "normal"},
)
with get_db() as db:
    from app.models.guion import Guion
    for gid in [guion_id]:
        g = db.get(Guion, gid)
        if g:
            db.delete(g)

print("\nTODO OK: Web Push funciona de punta a punta (mockeado).")
