import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


def _generar_con_anthropic(prompt: str, api_key: str, modelo: str, max_tokens: int) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


def _generar_con_openai(prompt: str, api_key: str, modelo: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


_PROVEEDORES = {
    "anthropic": _generar_con_anthropic,
    "openai": _generar_con_openai,
}


def generar_texto(prompt: str, max_tokens: int = 400) -> str | None:
    """Adaptador aislado y compartido por todo lo que necesite pedirle algo a
    la IA (clasificador de respuestas, motor de historias). El proveedor y el
    modelo son decisión de la familia (IA_PROVEEDOR / IA_MODELO en .env), sin
    tocar el resto del código. Devuelve None ante cualquier falla (sin API
    key, proveedor no reconocido, error de red) — quien lo llama decide cómo
    degradar, nunca se propaga la excepción."""
    settings = get_settings()
    proveedor = settings.ia_proveedor.strip().lower()
    api_key = settings.anthropic_api_key if proveedor == "anthropic" else settings.openai_api_key

    if not api_key:
        logger.warning("No hay API key configurada para el proveedor de IA '%s'.", proveedor)
        return None

    funcion = _PROVEEDORES.get(proveedor)
    if funcion is None:
        logger.error("IA_PROVEEDOR '%s' no reconocido (opciones: %s).", proveedor, list(_PROVEEDORES))
        return None

    try:
        return funcion(prompt, api_key, settings.ia_modelo, max_tokens)
    except Exception:
        logger.exception("Falló la llamada a la IA (%s).", proveedor)
        return None
