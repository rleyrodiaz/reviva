"""Verifica en proceso que, para el guion de entrada en modo manual, la
fecha no participa de nada: configurarlo como manual (desde el panel de la
conversación) lo manda derecho a la bandeja de aprobación, sin esperar a
que ninguna fecha pase ni depender del scheduler. Y que "Desactivar" en la
bandeja lo saca sin que el scheduler lo vuelva a tomar."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models.guion import Guion
from app.models.enums import EstadoGuion
from app.models.interaccion import Interaccion
from app.services.motor import procesar_guiones_vencidos

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación DescartarTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"

r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "texto_mensaje": "Guion para probar la bandeja",
        "tipo_respuesta": "libre",
        "nodo_padre_id": "",
    },
)
assert r.status_code == 200, r.text
with get_db() as db:
    guion_id = db.scalar(
        select(Guion.id).where(Guion.conversacion_id == conv_id).order_by(Guion.id.desc())
    )
    assert db.get(Guion, guion_id).estado == EstadoGuion.borrador
print("OK: guion de entrada creado, id =", guion_id)

# Configurar como manual manda derecho a la bandeja — la fecha (cualquiera
# que sea) no decide nada, y no hace falta que corra el scheduler.
r = client.post(
    f"{CONV_URL}/configuracion",
    data={"fecha_programada": "2030-01-01T10:00", "modo_envio": "manual"},
)
assert r.status_code in (200, 303), r.text
with get_db() as db:
    assert db.get(Guion, guion_id).estado == EstadoGuion.pendiente_aprobacion
print("OK: configurar como manual manda derecho a la bandeja, sin esperar ninguna fecha")

r = client.get("/admin/familias/2/bandeja")
assert f"#{guion_id}" in r.text
print("OK: aparece en la bandeja")

# El scheduler nunca debería tocar este guion mientras sea manual de entrada.
with get_db() as db:
    procesar_guiones_vencidos(db, paciente_id=2)
    db.commit()
    assert db.get(Guion, guion_id).estado == EstadoGuion.pendiente_aprobacion
    interacciones = db.scalars(select(Interaccion).where(Interaccion.guion_id == guion_id)).all()
    assert len(interacciones) == 0, "no debería haberse enviado nada solo"
print("OK: el scheduler no lo manda solo ni lo saca de la bandeja")

# "Desactivar" lo saca de la bandeja sin aprobarlo.
r = client.post(f"/admin/familias/2/bandeja/{guion_id}/desactivar")
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(Guion, guion_id).estado == EstadoGuion.borrador
print("OK: 'Desactivar' saca el guion de la bandeja y lo vuelve a borrador")

r = client.get("/admin/familias/2/bandeja")
assert f"#{guion_id}" not in r.text
print("OK: ya no aparece en la bandeja")

# El scheduler tampoco lo revive estando en borrador: la fecha no participa.
with get_db() as db:
    procesar_guiones_vencidos(db, paciente_id=2)
    db.commit()
    assert db.get(Guion, guion_id).estado == EstadoGuion.borrador, \
        "un guion de entrada manual desactivado no debería reaparecer solo"
print("OK: desactivado, el scheduler no lo vuelve a mandar a la bandeja")

# Guardar de nuevo en manual lo vuelve a mandar a la bandeja (no hace falta
# tocar "Reabrir" en particular: en manual, guardar y reabrir son lo mismo).
r = client.post(
    f"{CONV_URL}/configuracion",
    data={"fecha_programada": "2030-01-01T10:00", "modo_envio": "manual"},
)
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(Guion, guion_id).estado == EstadoGuion.pendiente_aprobacion
r = client.get("/admin/familias/2/bandeja")
assert f"#{guion_id}" in r.text
print("OK: volver a guardar en manual lo manda de nuevo a la bandeja")

r = client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
print("OK: limpieza hecha")

print("\nTODO OK: en manual la fecha no participa de nada — la bandeja se maneja con Aprobar/Desactivar.")
