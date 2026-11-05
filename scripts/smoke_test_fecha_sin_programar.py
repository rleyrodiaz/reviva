"""Verifica el fix de la fecha "01/01/2099" filtrándose al campo de fecha de
un nodo de entrada en modo manual: la columna es tz-aware, y lo que guarda
la DB para el sentinel "sin programar" vuelve con el offset de la sesión
(ej. "2099-01-01 00:00:00-03:00"), nunca `==` a un datetime(2099,1,1)
armado de nuevo en Python — comparar por año evita ese lío de huso horario
(ver admin.AÑO_SIN_PROGRAMAR).

Usa conversaciones manuales reales que ya tenían el sentinel guardado.

Uso: python -m scripts.smoke_test_fecha_sin_programar
"""
from app.db import get_db
from app.models.guion import Guion
from app.models.enums import ModoEnvio
from app.routers.admin import AÑO_SIN_PROGRAMAR
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from scripts._smoke_auth import login_superadmin

client = TestClient(app)
login_superadmin(client)

with get_db() as db:
    manuales = db.scalars(
        select(Guion).where(Guion.es_entrada.is_(True), Guion.modo_envio == ModoEnvio.manual)
    ).all()
    candidato = next((g for g in manuales if g.fecha_programada.year == AÑO_SIN_PROGRAMAR), None)
    assert candidato is not None, (
        "No hay ningún nodo de entrada manual con el sentinel guardado en esta DB para probar."
    )
    familia_id = candidato.personaje.familia_id
    personaje_id = candidato.personaje_id
    conversacion_id = candidato.conversacion_id
    guion_id = candidato.id

r = client.get(f"/admin/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}")
assert r.status_code == 200
assert '"2099' not in r.text, f"El sentinel 2099 se filtró al HTML (guion {guion_id})."
print(f"OK: el guion {guion_id} (manual, sentinel {AÑO_SIN_PROGRAMAR}) no filtra 2099 al campo de fecha.")
print("\nTODO OK.")
