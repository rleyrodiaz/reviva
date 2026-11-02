"""Verifica en proceso Activity log + Settings por familia (navbar, 403 para
quien no es admin de esa familia) y las acciones de Settings global que no
son irreversibles: init, y la validación de confirmación de los resets
(selectivo por familia y total). El reset total en sí ("RESET", que hace
drop_all/create_all de toda la base) no se ejercita acá a propósito — es
demasiado destructivo para correrlo contra la Postgres de desarrollo
compartida; solo se prueba que la confirmación incorrecta no hace nada."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.familia import Familia
from app.models.usuario import Usuario
from app.services.auth import hash_password
from scripts._smoke_auth import login_superadmin

client = TestClient(app)
login_superadmin(client)

ADMIN_EMAIL = "smoke-settings-admin@example.com"

with get_db() as db:
    u = db.scalar(select(Usuario).where(Usuario.email == ADMIN_EMAIL))
    if u:
        db.delete(u)

r = client.post("/admin/familias", data={
    "nombre_familia": "Familia SettingsLogTest",
    "nombre_paciente": "Paciente SettingsLogTest",
    "admin_email": ADMIN_EMAIL,
    "admin_nombre": "Admin SettingsLogTest",
    "admin_password": "x12345678",
}, follow_redirects=False)
assert r.status_code == 303, r.text
familia_id = int(r.headers["location"].rstrip("/").rsplit("/", 1)[-1])

admin_client = TestClient(app)
admin_client.post("/login", data={"email": ADMIN_EMAIL, "password": "x12345678"})

# ---- Navbar: el admin de ESTA familia ve el menú Admin (Activity log/Settings) ----
r = admin_client.get(f"/admin/familias/{familia_id}")
assert "Admin" in r.text and "Settings" in r.text
print("OK: el admin de la familia ve Activity log/Settings en el navbar")

# ---- Un usuario sin membership en esta familia no puede entrar (403) ----
with get_db() as db:
    otro_email = "smoke-settings-otro@example.com"
    existente = db.scalar(select(Usuario).where(Usuario.email == otro_email))
    if existente:
        db.delete(existente)
        db.flush()
    db.add(Usuario(nombre="Otro", email=otro_email, password_hash=hash_password("x"), es_superadmin=False))

otro_client = TestClient(app)
otro_client.post("/login", data={"email": otro_email, "password": "x"})
r = otro_client.get(f"/admin/familias/{familia_id}/settings")
assert r.status_code == 403
r = otro_client.get(f"/admin/familias/{familia_id}/activity-log")
assert r.status_code == 403
print("OK: alguien sin acceso a la familia no puede entrar a Settings/Activity log (403)")

# ---- Generar actividad real (crear un guion) y verla en el log de esta familia ----
r = admin_client.post(f"/admin/familias/{familia_id}/personajes", data={"nombre": "Personaje SettingsLogTest"}, follow_redirects=False)
assert r.status_code == 303
from app.models.personaje import Personaje
with get_db() as db:
    personaje_id = db.scalar(select(Personaje.id).where(Personaje.familia_id == familia_id).order_by(Personaje.id.desc()))

r = admin_client.get(f"/admin/familias/{familia_id}/activity-log")
assert r.status_code == 200
print("OK: Activity log de la familia renderiza")

# ---- Settings por familia: stats + reset selectivo ----
r = admin_client.get(f"/admin/familias/{familia_id}/settings")
assert r.status_code == 200 and "Regenerar datos" in r.text
print("OK: la pantalla de Settings por familia renderiza")

r = admin_client.post(f"/admin/familias/{familia_id}/settings/reset-tables", data={"confirm": "borrar mal", "tables": ["activity_log"]}, follow_redirects=False)
assert r.status_code == 303 and "msg=confirm_error" in r.headers["location"]
print("OK: reset-tables con confirmación incorrecta no hace nada")

r = admin_client.post(f"/admin/familias/{familia_id}/settings/reset-tables", data={"confirm": "BORRAR", "tables": []}, follow_redirects=False)
assert r.status_code == 303 and "msg=no_selection" in r.headers["location"]
print("OK: reset-tables sin ninguna tabla elegida no hace nada")

r = admin_client.post(f"/admin/familias/{familia_id}/settings/reset-tables", data={"confirm": "BORRAR", "tables": ["activity_log"]}, follow_redirects=False)
assert r.status_code == 303 and "msg=reset_tables_ok" in r.headers["location"]
with get_db() as db:
    todas = db.scalars(select(ActivityLog).where(ActivityLog.familia_id == familia_id)).all()
    # el propio reset-tables generó una entrada db_reset_parcial DESPUÉS del borrado, así que queda esa una.
    assert len(todas) == 1 and todas[0].accion.value == "db_reset_parcial"
print("OK: reset-tables borra de verdad lo seleccionado, acotado a esta familia")

# ---- Settings global (solo superadmin): init + validación del reset total ----
r = admin_client.get("/admin/settings")
assert r.status_code == 403
print("OK: un admin_familia no puede entrar al Settings global")

r = client.get("/admin/settings")
assert r.status_code == 200 and "Resetear todo" in r.text
print("OK: Settings global renderiza para superadmin")

r = client.post("/admin/settings/init", follow_redirects=False)
assert r.status_code == 303 and "msg=init_ok" in r.headers["location"]
print("OK: 'Inicializar DB' corre sin romper nada")

r = client.post("/admin/settings/reset", data={"confirm": "no es RESET"}, follow_redirects=False)
assert r.status_code == 303 and "msg=confirm_error" in r.headers["location"]
print("OK: reset total con confirmación incorrecta no hace nada (el reset real no se ejercita en este smoke test)")

client.post(f"/admin/familias/{familia_id}/borrar")
with get_db() as db:
    for email in (ADMIN_EMAIL, otro_email):
        u = db.scalar(select(Usuario).where(Usuario.email == email))
        if u:
            db.delete(u)

print("\nTODO OK: Activity log + Settings por familia, y Settings global (salvo el reset total en sí).")
