"""Login del superadmin para scripts de smoke test — un solo lugar, para no
repetir el email/contraseña reales en cada script (eso fue justo lo que pasó
antes: la contraseña quedó hardcodeada en 17 archivos y se subió así a un
repo público). Las credenciales se leen de .env (nunca commiteado)."""
from app.config import get_settings


def login_superadmin(client):
    settings = get_settings()
    if not settings.superadmin_email or not settings.superadmin_password:
        raise RuntimeError(
            "Faltan SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD en .env — "
            "hacen falta para que los scripts de smoke test puedan loguearse."
        )
    return client.post(
        "/login",
        data={"email": settings.superadmin_email, "password": settings.superadmin_password},
    )
