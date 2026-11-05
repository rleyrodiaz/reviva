import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class ApiKeyIlegible(Exception):
    """La API key guardada no se pudo descifrar — típicamente porque
    API_KEYS_ENCRYPTION_KEY cambió después de guardarla."""


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    secreto = settings.api_keys_encryption_key or settings.secret_key
    clave = base64.urlsafe_b64encode(hashlib.sha256(secreto.encode()).digest())
    return Fernet(clave)


def cifrar_api_key(texto_plano: str) -> str:
    return _fernet().encrypt(texto_plano.encode()).decode()


def descifrar_api_key(texto_cifrado: str) -> str:
    try:
        return _fernet().decrypt(texto_cifrado.encode()).decode()
    except InvalidToken as e:
        raise ApiKeyIlegible("No se pudo descifrar la API key guardada.") from e
