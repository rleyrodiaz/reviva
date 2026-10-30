"""Verifica en proceso el alta de familias con el modelo de membresías
multi-familia: un admin nuevo se crea con nombre+contraseña; reusar el email
de un admin YA existente lo agrega como admin de la familia nueva también
(no falla, y no lo saca de la familia anterior)."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app
from app.db import get_db
from app.models.familia import Familia
from app.models.familia_membership import FamiliaMembership
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.models.enums import UserRole
from sqlalchemy import select

client = TestClient(app)
login_superadmin(client)

r = client.get("/admin/familias")
assert "Nueva familia" in r.text
print("OK: el botón aparece en la pantalla de familias (superadmin)")

# Familia A con un admin nuevo
r = client.post(
    "/admin/familias",
    data={
        "nombre_familia": "Familia SmokeTest A",
        "nombre_paciente": "Paciente A",
        "admin_email": "smoketest.multifamilia@example.com",
        "admin_nombre": "Admin Multi",
        "admin_password": "clave12345",
    },
)
assert r.status_code in (200, 303)

with get_db() as db:
    familia_a = db.scalar(select(Familia).where(Familia.nombre == "Familia SmokeTest A"))
    admin = db.scalar(select(Usuario).where(Usuario.email == "smoketest.multifamilia@example.com"))
    assert familia_a is not None and admin is not None
    assert admin.es_superadmin is False
    familia_a_id = familia_a.id
    admin_id = admin.id
print("OK: familia A creada con un admin nuevo")

# Falta nombre/contraseña para un email realmente nuevo -> 400
r = client.post(
    "/admin/familias",
    data={
        "nombre_familia": "Familia Incompleta",
        "nombre_paciente": "X",
        "admin_email": "nuevo.sin.datos@example.com",
    },
)
assert r.status_code == 400
print("OK: email nuevo sin nombre/contraseña rechazado con 400")

# Familia B reusando el MISMO email de admin -> se agrega como admin ahí también
r = client.post(
    "/admin/familias",
    data={
        "nombre_familia": "Familia SmokeTest B",
        "nombre_paciente": "Paciente B",
        "admin_email": "smoketest.multifamilia@example.com",
    },
)
assert r.status_code in (200, 303), r.text[:500]

with get_db() as db:
    familia_b = db.scalar(select(Familia).where(Familia.nombre == "Familia SmokeTest B"))
    assert familia_b is not None
    familia_b_id = familia_b.id
    usuarios_con_ese_email = db.scalars(
        select(Usuario).where(Usuario.email == "smoketest.multifamilia@example.com")
    ).all()
    assert len(usuarios_con_ese_email) == 1, "no debería haber creado un usuario duplicado"
    memberships = db.scalars(
        select(FamiliaMembership).where(FamiliaMembership.usuario_id == admin_id)
    ).all()
    familia_ids_del_admin = {m.familia_id for m in memberships}
    assert familia_ids_del_admin == {familia_a_id, familia_b_id}
print("OK: el mismo admin ahora tiene membresía en las dos familias, sin duplicar el usuario")

# Ese admin puede entrar a AMBAS familias, y a ninguna otra
client2 = TestClient(app)
client2.post("/login", data={"email": "smoketest.multifamilia@example.com", "password": "clave12345"})
r = client2.get(f"/admin/familias/{familia_a_id}")
assert r.status_code == 200
r = client2.get(f"/admin/familias/{familia_b_id}")
assert r.status_code == 200
r = client2.get("/admin/familias/1")
assert r.status_code == 403
print("OK: el admin entra a sus dos familias, y no puede entrar a una ajena (403)")

# Al loguearse con dos familias propias, va al listado (no directo a una)
r = client2.post(
    "/login",
    data={"email": "smoketest.multifamilia@example.com", "password": "clave12345"},
    follow_redirects=False,
)
assert r.headers["location"] == "/admin/familias"
print("OK: con más de una familia, el login lo manda al listado para elegir")

# Limpieza
with get_db() as db:
    for fid in (familia_a_id, familia_b_id):
        for p in db.scalars(select(Paciente).where(Paciente.familia_id == fid)).all():
            db.delete(p)
    db.flush()
    for fid in (familia_a_id, familia_b_id):
        db.delete(db.get(Familia, fid))
    db.delete(db.get(Usuario, admin_id))
print("OK: datos de prueba borrados")

print("\nTODO OK: alta de familias con admins multi-familia funciona de punta a punta.")
