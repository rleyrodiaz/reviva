from unittest.mock import MagicMock, patch

from app.config import Settings
from app.services import ia_cliente


def _settings(**overrides):
    base = dict(
        database_url="sqlite:///:memory:",
        secret_key="x",
        ia_proveedor="anthropic",
        ia_modelo="modelo-test",
        anthropic_api_key="",
        openai_api_key="",
    )
    base.update(overrides)
    return Settings(**base)


def test_sin_api_key_devuelve_none(monkeypatch):
    monkeypatch.setattr(ia_cliente, "get_settings", lambda: _settings())
    assert ia_cliente.generar_texto("hola") is None


def test_proveedor_no_reconocido_devuelve_none(monkeypatch):
    monkeypatch.setattr(
        ia_cliente, "get_settings", lambda: _settings(ia_proveedor="gemini", anthropic_api_key="x")
    )
    assert ia_cliente.generar_texto("hola") is None


def test_usa_anthropic_cuando_esta_configurado(monkeypatch):
    monkeypatch.setattr(ia_cliente, "get_settings", lambda: _settings(anthropic_api_key="clave-fake"))
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="  respuesta del modelo  ")]
    with patch("anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = fake_response
        resultado = ia_cliente.generar_texto("hola", max_tokens=123)
    assert resultado == "respuesta del modelo"
    MockAnthropic.assert_called_once_with(api_key="clave-fake")
    kwargs = MockAnthropic.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "modelo-test"
    assert kwargs["max_tokens"] == 123


def test_usa_openai_cuando_esta_configurado(monkeypatch):
    monkeypatch.setattr(
        ia_cliente, "get_settings",
        lambda: _settings(ia_proveedor="openai", ia_modelo="gpt-test", openai_api_key="clave-fake"),
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="respuesta openai"))]
    with patch("openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = fake_response
        resultado = ia_cliente.generar_texto("hola")
    assert resultado == "respuesta openai"
    MockOpenAI.assert_called_once_with(api_key="clave-fake")
    assert MockOpenAI.return_value.chat.completions.create.call_args.kwargs["model"] == "gpt-test"


def test_error_de_red_devuelve_none(monkeypatch):
    monkeypatch.setattr(ia_cliente, "get_settings", lambda: _settings(anthropic_api_key="clave-fake"))
    with patch("anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.side_effect = RuntimeError("timeout")
        assert ia_cliente.generar_texto("hola") is None
