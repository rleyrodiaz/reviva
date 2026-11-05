import pytest

from app.config import Settings
from app.services import cifrado


def _settings(**overrides):
    base = dict(database_url="sqlite:///:memory:", secret_key="una-secret-key-de-test")
    base.update(overrides)
    return Settings(**base)


def test_cifrar_y_descifrar_devuelve_el_texto_original(monkeypatch):
    monkeypatch.setattr(cifrado, "get_settings", lambda: _settings())
    cifrado._fernet.cache_clear()
    cifrada = cifrado.cifrar_api_key("sk-ant-super-secreta")
    assert cifrada != "sk-ant-super-secreta"
    assert cifrado.descifrar_api_key(cifrada) == "sk-ant-super-secreta"


def test_descifrar_con_otra_clave_falla(monkeypatch):
    monkeypatch.setattr(cifrado, "get_settings", lambda: _settings(secret_key="clave-uno"))
    cifrado._fernet.cache_clear()
    cifrada = cifrado.cifrar_api_key("sk-ant-super-secreta")

    monkeypatch.setattr(cifrado, "get_settings", lambda: _settings(secret_key="clave-dos"))
    cifrado._fernet.cache_clear()
    with pytest.raises(cifrado.ApiKeyIlegible):
        cifrado.descifrar_api_key(cifrada)
    cifrado._fernet.cache_clear()
