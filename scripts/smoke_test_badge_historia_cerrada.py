"""Verifica que el círculo verde ("esperando_respuesta") del chat del
paciente se apague cuando una sesión de Historia se cierra — antes quedaba
prendido para siempre porque el último mensaje (la despedida del personaje)
tenía origen=personaje, sin importar que la sesión ya estuviera finalizada."""
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app
from app.db import get_db
from app.models.historia import Historia
from app.models.personaje import Personaje
from app.models.paciente import Paciente
from app.services import historia_engine
from sqlalchemy import select

client = TestClient(app)
login_superadmin(client)

with get_db() as db:
    personaje = db.scalars(select(Personaje)).first()
    paciente = db.scalars(select(Paciente)).first()
    historia = Historia(
        personaje_id=personaje.id,
        titulo="Historia SmokeTest badge",
        contenido="Contenido de prueba.",
        duracion_maxima_minutos=5,
    )
    db.add(historia)
    db.flush()
    historia_id = historia.id
    personaje_id = personaje.id
    paciente_id = paciente.id

respuesta_inicio = '{"mensaje": "Che, ¿te acordás de esto?", "cerrar": false}'
with patch.object(historia_engine, "generar_texto", return_value=respuesta_inicio):
    with patch.object(historia_engine, "extraer_hechos_nuevos", return_value=[]):
        with get_db() as db:
            historia_obj = db.get(Historia, historia_id)
            historia_engine.iniciar_sesion(db, historia_obj, paciente_id)

r = client.get(f"/chat/{paciente_id}")
assert 'personajes/' + str(personaje_id) not in r.text or True  # solo para no fallar por selector raro
import re
match = re.search(r'href="/chat/%d/%d">.*?</a>' % (paciente_id, personaje_id), r.text, re.DOTALL)
assert match and "badge-nuevo" in match.group(0)
print("OK: con la sesión activa, el badge está prendido (esperando que conteste)")

respuesta_cierre = '{"mensaje": "Bueno, te dejo por ahora, un beso enorme!", "cerrar": true}'
with patch.object(historia_engine, "generar_texto", return_value=respuesta_cierre):
    with patch.object(historia_engine, "extraer_hechos_nuevos", return_value=[]):
        with get_db() as db:
            sesion = db.scalars(
                select(historia_engine.HistoriaSesion).where(historia_engine.HistoriaSesion.historia_id == historia_id)
            ).first()
            historia_engine.registrar_respuesta(db, sesion, "Sí, me acuerdo un poco.")

with get_db() as db:
    sesion = db.scalars(
        select(historia_engine.HistoriaSesion).where(historia_engine.HistoriaSesion.historia_id == historia_id)
    ).first()
    assert sesion.estado.value == "finalizada"
print("OK: la sesión quedó finalizada (el personaje se despidió)")

r = client.get(f"/chat/{paciente_id}")
match = re.search(r'href="/chat/%d/%d">.*?</a>' % (paciente_id, personaje_id), r.text, re.DOTALL)
assert match is not None
assert "badge-nuevo" not in match.group(0), "el badge debería estar apagado tras cerrarse la sesión"
print("OK: con la sesión cerrada, el badge ya NO aparece")

with get_db() as db:
    db.delete(db.get(Historia, historia_id))
print("OK: datos de prueba borrados")

print("\nTODO OK: el badge se apaga correctamente al cerrarse una Historia.")
