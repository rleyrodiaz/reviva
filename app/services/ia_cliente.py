import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings

logger = logging.getLogger(__name__)


class SinSaldo(Exception):
    """Créditos agotados en la cuenta del proveedor de IA — distinto de
    cualquier otra falla (sin key, red, parseo) porque sí se puede avisar
    algo específico y útil al admin (ver _registrar_saldo_agotado)."""


def _generar_con_anthropic(prompt: str, api_key: str, modelo: str, max_tokens: int) -> str:
    import anthropic
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIStatusError as e:
        # Sin crédito: Anthropic devuelve 402 (error type "billing_error").
        if e.status_code == 402:
            raise SinSaldo("Sin créditos en la cuenta de Anthropic.") from e
        raise
    return response.content[0].text.strip()


def _generar_con_openai(prompt: str, api_key: str, modelo: str, max_tokens: int) -> str:
    import openai
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )
    except openai.RateLimitError as e:
        # OpenAI manda el agotamiento de saldo como un 429 con code "insufficient_quota".
        if getattr(e, "code", None) == "insufficient_quota":
            raise SinSaldo("Sin créditos en la cuenta de OpenAI.") from e
        raise
    return response.choices[0].message.content.strip()


_PROVEEDORES = {
    "anthropic": _generar_con_anthropic,
    "openai": _generar_con_openai,
}


def _registrar_saldo_agotado(proveedor: str) -> None:
    """Deja una entrada en el Activity log (global, sin familia_id — afecta
    a toda la app por igual, ver admin.activity_log_page) para que el admin
    se entere sin tener que mirar los logs del servidor. A lo sumo una por
    hora, para no inundarlo si siguen llegando respuestas mientras no hay
    saldo. Abre su propia sesión corta porque este adaptador no recibe una
    `db` de quien lo llama (ver generar_texto) — nunca debe romper el
    llamado real por esto."""
    from sqlalchemy import select

    from app.db import get_db
    from app.models.activity_log import ActivityLog
    from app.models.enums import AccionActividad
    from app.services.activity_log import registrar_actividad

    try:
        with get_db() as db:
            ultima = db.scalar(
                select(ActivityLog)
                .where(ActivityLog.accion == AccionActividad.ia_sin_saldo)
                .order_by(ActivityLog.creado_en.desc())
            )
            if ultima and ultima.creado_en >= datetime.now(timezone.utc) - timedelta(hours=1):
                return
            registrar_actividad(db, AccionActividad.ia_sin_saldo, detalle=f"Proveedor: {proveedor}")
    except Exception:
        logger.exception("No se pudo registrar el aviso de saldo agotado en el Activity log.")


def generar_texto(prompt: str, max_tokens: int = 400) -> str | None:
    """Adaptador aislado y compartido por todo lo que necesite pedirle algo a
    la IA (clasificador de respuestas, motor de historias). El proveedor y el
    modelo son decisión de la familia (IA_PROVEEDOR / IA_MODELO en .env), sin
    tocar el resto del código. Devuelve None ante cualquier falla (sin API
    key, proveedor no reconocido, error de red) — quien lo llama decide cómo
    degradar, nunca se propaga la excepción. El caso de "sin saldo" además
    queda registrado en el Activity log (ver _registrar_saldo_agotado)."""
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
    except SinSaldo:
        logger.error("Sin saldo en la cuenta de IA (%s).", proveedor)
        _registrar_saldo_agotado(proveedor)
        return None
    except Exception:
        logger.exception("Falló la llamada a la IA (%s).", proveedor)
        return None
