"""Verifica el aviso de "sin saldo de IA": que un 402 de Anthropic (o un
insufficient_quota de OpenAI) quede registrado en el Activity log (global,
visible en cualquier familia), que no se duplique si sigue fallando dentro
de la misma hora, y que el banner aparezca en el dashboard. Limpia lo que
crea.

Uso: python -m scripts.smoke_test_ia_sin_saldo
"""
from unittest.mock import MagicMock, patch

from scripts._smoke_auth import login_superadmin
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models.activity_log import ActivityLog
from app.models.enums import AccionActividad
from app.models.familia import Familia
from app.services import ia_cliente
from sqlalchemy import select

client = TestClient(app)
login_superadmin(client)

# Limpieza previa, por si quedó algo de una corrida anterior
with get_db() as db:
    for e in db.scalars(select(ActivityLog).where(ActivityLog.accion == AccionActividad.ia_sin_saldo)):
        db.delete(e)

import anthropic
resp_402 = MagicMock()
resp_402.status_code = 402
error_402 = anthropic.APIStatusError("saldo insuficiente", response=resp_402, body={"type": "error", "error": {"type": "billing_error", "message": "saldo insuficiente"}})

with patch("app.services.ia_cliente.get_settings") as mock_settings, \
     patch("anthropic.Anthropic") as mock_cliente_anthropic:
    mock_settings.return_value.ia_proveedor = "anthropic"
    mock_settings.return_value.anthropic_api_key = "fake-key"
    mock_settings.return_value.ia_modelo = "claude-haiku-4-5-20251001"
    mock_cliente_anthropic.return_value.messages.create.side_effect = error_402

    resultado1 = ia_cliente.generar_texto("hola")
    assert resultado1 is None
    print("OK: generar_texto devuelve None ante un 402 (no rompe al que llama)")

    with get_db() as db:
        entradas = db.scalars(select(ActivityLog).where(ActivityLog.accion == AccionActividad.ia_sin_saldo)).all()
        assert len(entradas) == 1, f"esperaba 1 entrada, hay {len(entradas)}"
        print("OK: quedó 1 entrada en el Activity log tras el primer 402")

    # Un segundo 402 inmediatamente después no debería duplicar la entrada
    resultado2 = ia_cliente.generar_texto("hola de nuevo")
    assert resultado2 is None
    with get_db() as db:
        entradas = db.scalars(select(ActivityLog).where(ActivityLog.accion == AccionActividad.ia_sin_saldo)).all()
        assert len(entradas) == 1, f"se duplicó: hay {len(entradas)}"
        print("OK: un segundo fallo dentro de la misma hora no duplica la entrada")

# El banner y el Activity log tienen que verse en CUALQUIER familia (evento global)
with get_db() as db:
    alguna_familia_id = db.scalar(select(Familia.id))

r_dash = client.get(f"/admin/familias/{alguna_familia_id}")
assert r_dash.status_code == 200
assert "Se agotaron los créditos" in r_dash.text
print(f"OK: el banner aparece en el dashboard de la familia {alguna_familia_id}")

r_log = client.get(f"/admin/familias/{alguna_familia_id}/activity-log")
assert r_log.status_code == 200
assert "Sin saldo de IA" in r_log.text
print(f"OK: la entrada aparece en el Activity log de la familia {alguna_familia_id}")

# Limpieza
with get_db() as db:
    for e in db.scalars(select(ActivityLog).where(ActivityLog.accion == AccionActividad.ia_sin_saldo)):
        db.delete(e)
print("Limpieza OK")

print("\nTODO OK.")
