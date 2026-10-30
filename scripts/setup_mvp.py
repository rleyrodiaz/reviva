"""Deja la base lista para probar el MVP (SPEC sección 9): crea (o actualiza)
el usuario superadmin y una familia con un paciente, si todavía no existen.
Los personajes y guiones se cargan después a mano desde el dashboard.

Uso: .venv\\Scripts\\python.exe scripts\\setup_mvp.py
"""
from sqlalchemy import select

from app.config import get_settings
from app.db import get_db
from app.models.familia import Familia
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.services.auth import hash_password

_settings = get_settings()
if not _settings.superadmin_email or not _settings.superadmin_password:
    raise SystemExit("Faltan SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD en .env.")
EMAIL = _settings.superadmin_email
NOMBRE = _settings.superadmin_nombre or "Admin"
PASSWORD = _settings.superadmin_password

NOMBRE_FAMILIA = "Familia MVP"
NOMBRE_PACIENTE = "Paciente MVP"


def main():
    with get_db() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == EMAIL.lower()))
        if usuario:
            usuario.password_hash = hash_password(PASSWORD)
            usuario.es_superadmin = True
            print(f"Usuario existente actualizado como superadmin (id={usuario.id}).")
        else:
            usuario = Usuario(
                email=EMAIL.lower(),
                nombre=NOMBRE,
                password_hash=hash_password(PASSWORD),
                es_superadmin=True,
            )
            db.add(usuario)
            print("Usuario superadmin creado.")

        familia = db.scalar(select(Familia).where(Familia.nombre == NOMBRE_FAMILIA))
        if not familia:
            familia = Familia(nombre=NOMBRE_FAMILIA)
            db.add(familia)
            db.flush()
            print(f"Familia creada (id={familia.id}).")
        else:
            print(f"Familia ya existía (id={familia.id}).")

        paciente = db.scalar(select(Paciente).where(Paciente.familia_id == familia.id))
        if not paciente:
            paciente = Paciente(familia_id=familia.id, nombre=NOMBRE_PACIENTE)
            db.add(paciente)
            db.flush()
            print(f"Paciente creado (id={paciente.id}).")
        else:
            print(f"Paciente ya existía (id={paciente.id}).")

        print(f"\nLogin admin: {EMAIL} / {PASSWORD}")
        print(f"Dashboard: /admin/familias/{familia.id}")
        print(f"Chat paciente: /chat/{paciente.id}")


if __name__ == "__main__":
    main()
