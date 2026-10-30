from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    session_max_age_hours: int = 12
    # Proveedor y modelo del clasificador de respuestas libres (SPEC sección 6):
    # decisión de la familia, seteable sin tocar código. "anthropic" u "openai".
    ia_proveedor: str = "anthropic"
    ia_modelo: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    vapid_public_key: str = ""
    vapid_private_key_path: str = "vapid_private_key.pem"
    vapid_claims_email: str = "admin@example.com"
    # Credenciales del superadmin — usadas por scripts/setup_mvp.py y por los
    # scripts de smoke test para loguearse. Nunca hardcodeadas en código: se
    # leen de acá para que la contraseña real solo viva en .env (gitignored).
    superadmin_email: str = ""
    superadmin_nombre: str = ""
    superadmin_password: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
