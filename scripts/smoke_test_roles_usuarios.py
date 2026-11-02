"""Verifica en proceso: rol familiar (crea/edita pero no aprueba), módulo
Usuarios (agregar/cambiar rol/quitar, con la regla de "al menos un admin"),
Activity log y Settings re-acotados por familia, y el navbar nuevo."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.familia import Familia
from app.models.usuario import Usuario
from app.services.auth import hash_password
from scripts._smoke_auth import login_superadmin

client = TestClient(app)
login_superadmin(client)

ADMIN_EMAIL = "smoke-roles-admin@example.com"
FAMILIAR_EMAIL = "smoke-roles-familiar@example.com"

with get_db() as db:
    for email in (ADMIN_EMAIL, FAMILIAR_EMAIL):
        u = db.scalar(select(Usuario).where(Usuario.email == email))
        if u:
            db.delete(u)

# ---- Crear una familia de prueba (su primer admin: ADMIN_EMAIL) ----
r = client.post("/admin/familias", data={
    "nombre_familia": "Familia RolesTest",
    "nombre_paciente": "Paciente RolesTest",
    "admin_email": ADMIN_EMAIL,
    "admin_nombre": "Admin RolesTest",
    "admin_password": "x12345678",
}, follow_redirects=False)
assert r.status_code == 303, r.text
familia_id = int(r.headers["location"].rstrip("/").rsplit("/", 1)[-1])

admin_client = TestClient(app)
admin_client.post("/login", data={"email": ADMIN_EMAIL, "password": "x12345678"})

# ---- Navbar: el admin ve Dashboard/Bandeja/Hechos/Usuarios + Admin ▾ ----
r = admin_client.get(f"/admin/familias/{familia_id}")
assert all(x in r.text for x in ["Dashboard", "Bandeja", "Hechos", "Usuarios", "Admin"]), r.text[:2000]
print("OK: el admin ve el navbar completo de su familia")

# ---- El admin agrega a alguien como "familiar" ----
r = admin_client.post(f"/admin/familias/{familia_id}/usuarios", data={
    "email": FAMILIAR_EMAIL, "nombre": "Familiar Test", "password": "y12345678", "rol": "familiar",
}, follow_redirects=False)
assert r.status_code == 303, r.text
print("OK: un admin_familia (no superadmin) puede agregar gente a SU familia")

familiar_client = TestClient(app)
familiar_client.post("/login", data={"email": FAMILIAR_EMAIL, "password": "y12345678"})

# ---- Navbar del familiar: ve Dashboard/Hechos, NO Bandeja/Usuarios/Admin ----
r = familiar_client.get(f"/admin/familias/{familia_id}")
assert "Dashboard" in r.text and "Hechos" in r.text
assert "Bandeja" not in r.text and ">Usuarios<" not in r.text and "Admin ▾" not in r.text and "Borrar personaje" not in r.text
print("OK: el navbar del familiar no muestra Bandeja/Usuarios/Admin")

# ---- El familiar PUEDE crear un guion (crear/editar contenido) ----
r = familiar_client.post(f"{'' }/admin/familias/{familia_id}/personajes", data={
    "nombre": "Personaje Test",
}, follow_redirects=False)
assert r.status_code == 303, r.text
personaje_id = int(r.headers["location"].rstrip("/").rsplit("/", 1)[-1].split("?")[0]) if "personajes/" in r.headers["location"] else None
# la ruta de crear_personaje redirige al dashboard, no a la ficha — tomamos el personaje recién creado por DB:
from app.models.personaje import Personaje
with get_db() as db:
    personaje_id = db.scalar(select(Personaje.id).where(Personaje.familia_id == familia_id).order_by(Personaje.id.desc()))
print("OK: el familiar puede crear un personaje (contenido)")

r = familiar_client.post(f"/admin/familias/{familia_id}/personajes/{personaje_id}/conversaciones", data={
    "nombre": "Conv Test",
}, follow_redirects=False)
assert r.status_code == 303, r.text
from app.models.conversacion import Conversacion
with get_db() as db:
    conversacion_id = db.scalar(select(Conversacion.id).where(Conversacion.personaje_id == personaje_id).order_by(Conversacion.id.desc()))

r = familiar_client.post(
    f"/admin/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones",
    data={"texto_mensaje": "Hola", "tipo_respuesta": "opciones", "nodo_padre_id": ""},
)
assert r.status_code == 200, r.text
print("OK: el familiar puede crear un guion")

# ---- El familiar NO puede ver/usar la bandeja (403) ----
r = familiar_client.get(f"/admin/familias/{familia_id}/bandeja")
assert r.status_code == 403
print("OK: el familiar no puede entrar a la bandeja (403)")

# ---- El familiar NO puede entrar a Usuarios/Settings/Activity log (403) ----
for ruta in ("usuarios", "settings", "activity-log"):
    r = familiar_client.get(f"/admin/familias/{familia_id}/{ruta}")
    assert r.status_code == 403, f"{ruta}: {r.status_code}"
print("OK: el familiar no puede entrar a Usuarios/Settings/Activity log (403)")

# ---- El admin SÍ puede todo eso ----
for ruta in ("usuarios", "settings", "activity-log", "bandeja"):
    r = admin_client.get(f"/admin/familias/{familia_id}/{ruta}")
    assert r.status_code == 200, f"{ruta}: {r.status_code}"
print("OK: el admin_familia sí puede entrar a Usuarios/Settings/Activity log/Bandeja")

# ---- No se puede dejar la familia sin ningún admin ----
with get_db() as db:
    from app.models.familia_membership import FamiliaMembership
    membership_admin = db.scalar(
        select(FamiliaMembership).join(Usuario).where(
            FamiliaMembership.familia_id == familia_id, Usuario.email == ADMIN_EMAIL
        )
    )
    membership_admin_id = membership_admin.id

r = admin_client.post(f"/admin/familias/{familia_id}/usuarios/{membership_admin_id}/rol", data={"rol": "familiar"})
assert r.status_code == 400, r.text
print("OK: no se puede degradar al último admin de la familia")

r = admin_client.post(f"/admin/familias/{familia_id}/usuarios/{membership_admin_id}/borrar")
assert r.status_code == 400, r.text
print("OK: no se puede quitar al último admin de la familia")

# ---- Settings por familia: reset selectivo solo toca ESTA familia ----
r = admin_client.post(f"/admin/familias/{familia_id}/settings/reset-tables", data={"confirm": "BORRAR", "tables": ["activity_log"]}, follow_redirects=False)
assert r.status_code == 303 and "reset_tables_ok" in r.headers["location"]
with get_db() as db:
    from app.models.activity_log import ActivityLog
    restantes = db.scalars(select(ActivityLog).where(ActivityLog.familia_id == familia_id)).all()
    assert len(restantes) == 1 and restantes[0].accion.value == "db_reset_parcial"
print("OK: el reset selectivo por familia solo toca su propio activity_log")

# ---- Settings global: solo superadmin ----
r = admin_client.get("/admin/settings")
assert r.status_code == 403
r = client.get("/admin/settings")
assert r.status_code == 200
print("OK: Settings global sigue siendo solo de superadmin")

# ---- limpieza ----
client.post(f"/admin/familias/{familia_id}/borrar")
with get_db() as db:
    for email in (ADMIN_EMAIL, FAMILIAR_EMAIL):
        u = db.scalar(select(Usuario).where(Usuario.email == email))
        if u:
            db.delete(u)

print("\nTODO OK: roles, Usuarios, navbar y el reacotado de Activity log/Settings funcionan de punta a punta.")
