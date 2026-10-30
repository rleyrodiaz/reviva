"""Verifica en proceso el navbar nuevo (Settings + Activity log, solo
superadmin) y las acciones de Settings que no son irreversibles sobre la
base real: init, y el reset selectivo de tablas (probado contra el propio
activity_log, para no tocar datos de otras pruebas). El reset total
("RESET", que hace drop_all/create_all de toda la base) no se ejercita acá
a propósito — es demasiado destructivo para corratarlo contra la Postgres
de desarrollo compartida; su lógica de confirmación sí se prueba."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.conversacion import Conversacion
from app.models.familia import Familia
from app.models.familia_membership import FamiliaMembership
from app.models.guion import Guion
from app.models.usuario import Usuario
from app.services.auth import hash_password

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

# ---- Navbar: solo superadmin ve los links ----
r = client.get("/admin/familias")
assert "Activity log" in r.text and "Settings" in r.text, "superadmin debería ver el navbar"
print("OK: superadmin ve Activity log/Settings en el navbar")

with get_db() as db:
    no_super_email = "smoke-no-super@example.com"
    existente = db.scalar(select(Usuario).where(Usuario.email == no_super_email))
    if existente:
        db.delete(existente)
        db.flush()
    no_super = Usuario(nombre="Sin Super", email=no_super_email, password_hash=hash_password("x"), es_superadmin=False)
    db.add(no_super)
    db.flush()
    no_super_id = no_super.id

client2 = TestClient(app)
client2.post("/login", data={"email": no_super_email, "password": "x"})
r = client2.get("/admin/familias")
assert "Activity log" not in r.text and "Settings" not in r.text
print("OK: un admin_familia (no superadmin) no ve el navbar")

r = client2.get("/admin/settings")
assert r.status_code == 403
r = client2.get("/admin/activity-log")
assert r.status_code == 403
print("OK: un admin_familia (no superadmin) no puede entrar a Settings/Activity log (403)")

# ---- Generar actividad real (crear + borrar un guion) y verla en el log ----
r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación SettingsLogTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"

r = client.post(f"{CONV_URL}/guiones", data={"texto_mensaje": "Hola", "tipo_respuesta": "libre", "nodo_padre_id": ""})
assert r.status_code == 200
with get_db() as db:
    guion_id = db.scalar(select(Guion.id).where(Guion.conversacion_id == conv_id).order_by(Guion.id.desc()))

r = client.get("/admin/activity-log")
assert r.status_code == 200 and "Guion creado" in r.text
print("OK: crear un guion queda en el Activity log")

r = client.post(f"{CONV_URL}/guiones/{guion_id}/borrar")
assert r.status_code == 200
r = client.get(f"/admin/activity-log?accion=guion_borrado")
assert "Guion borrado" in r.text
print("OK: borrar un guion queda en el Activity log, y el filtro por acción funciona")

client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")

# ---- Settings: stats + init (no destructivo) ----
r = client.get("/admin/settings")
assert r.status_code == 200 and "Resetear todo" in r.text
print("OK: la pantalla de Settings renderiza con sus tres secciones")

r = client.post("/admin/settings/init", follow_redirects=False)
assert r.status_code == 303 and "msg=init_ok" in r.headers["location"]
print("OK: 'Inicializar DB' corre sin romper nada")

# ---- Reset selectivo: confirmación mal escrita no borra nada ----
r = client.post("/admin/settings/reset-tables", data={"confirm": "borrar mal", "tables": ["activity_log"]}, follow_redirects=False)
assert r.status_code == 303 and "msg=confirm_error" in r.headers["location"]
print("OK: reset-tables con confirmación incorrecta no hace nada")

# ---- Reset selectivo: sin tablas elegidas no hace nada aunque confirme bien ----
r = client.post("/admin/settings/reset-tables", data={"confirm": "BORRAR", "tables": []}, follow_redirects=False)
assert r.status_code == 303 and "msg=no_selection" in r.headers["location"]
print("OK: reset-tables sin ninguna tabla elegida no hace nada")

# ---- Reset selectivo real, acotado al propio activity_log (no toca otras tablas) ----
r = client.post("/admin/settings/reset-tables", data={"confirm": "BORRAR", "tables": ["activity_log"]}, follow_redirects=False)
assert r.status_code == 303 and "msg=reset_tables_ok" in r.headers["location"]
with get_db() as db:
    from app.models.activity_log import ActivityLog
    quedan = db.scalar(select(ActivityLog.id).limit(1))
    # el propio reset-tables generó una entrada db_reset_parcial DESPUÉS del borrado, así que queda esa una.
    todas = db.scalars(select(ActivityLog)).all()
    assert len(todas) == 1 and todas[0].accion.value == "db_reset_parcial"
print("OK: reset-tables borra de verdad lo seleccionado (probado sobre el propio activity_log)")

# ---- Reset total: solo se prueba la validación de confirmación (NO se ejecuta el reset real) ----
r = client.post("/admin/settings/reset", data={"confirm": "no es RESET"}, follow_redirects=False)
assert r.status_code == 303 and "msg=confirm_error" in r.headers["location"]
print("OK: reset total con confirmación incorrecta no hace nada (el reset real no se ejercita en este smoke test)")

with get_db() as db:
    db.delete(db.get(Usuario, no_super_id))

print("\nTODO OK: navbar + Activity log + Settings (salvo el reset total en sí) funcionan de punta a punta.")
