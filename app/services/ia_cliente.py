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
# Lista pública para que la pantalla de Settings > API Keys ofrezca estos
# mismos proveedores sin duplicar la lista — agregar uno nuevo acá alcanza
# para que aparezca ahí también.
PROVEEDORES_DISPONIBLES = list(_PROVEEDORES)


def _avisar_una_vez_por_hora(accion, familia_id: int | None, detalle: str | None = None) -> None:
    """Deja una entrada en el Activity log (ver admin.activity_log_page) para
    que el admin se entere sin tener que mirar los logs del servidor. A lo
    sumo una por hora por familia (o global si familia_id es None, caso de
    la key de .env), para no inundarlo si siguen llegando respuestas
    mientras sigue sin resolverse. Abre su propia sesión corta porque este
    adaptador no recibe una `db` de quien lo llama (ver generar_texto) —
    nunca debe romper el llamado real por esto."""
    from sqlalchemy import select

    from app.db import get_db
    from app.models.activity_log import ActivityLog
    from app.services.activity_log import registrar_actividad

    try:
        with get_db() as db:
            ultima = db.scalar(
                select(ActivityLog)
                .where(ActivityLog.accion == accion, ActivityLog.familia_id == familia_id)
                .order_by(ActivityLog.creado_en.desc())
            )
            if ultima and ultima.creado_en >= datetime.now(timezone.utc) - timedelta(hours=1):
                return
            registrar_actividad(db, accion, familia_id=familia_id, detalle=detalle)
    except Exception:
        logger.exception("No se pudo registrar el aviso en el Activity log.")


def _resolver_credencial_familia(familia_id: int) -> tuple[str, str] | None:
    """Busca la API key que esa familia cargó para su proveedor activo
    (Settings > API Keys). None si todavía no eligió proveedor activo o no
    hay una key guardada para él — generar_texto lo trata como "sin API
    key" en vez de intentar la llamada."""
    from sqlalchemy import select

    from app.db import get_db
    from app.models.familia import Familia
    from app.models.familia_api_key import FamiliaApiKey
    from app.services.cifrado import descifrar_api_key

    with get_db() as db:
        familia = db.get(Familia, familia_id)
        if familia is None or not familia.proveedor_ia_activo:
            return None
        fila = db.scalar(
            select(FamiliaApiKey).where(
                FamiliaApiKey.familia_id == familia_id,
                FamiliaApiKey.proveedor == familia.proveedor_ia_activo,
            )
        )
        if fila is None:
            return None
        return familia.proveedor_ia_activo, descifrar_api_key(fila.api_key_cifrada)


def generar_texto(prompt: str, max_tokens: int = 400, familia_id: int | None = None) -> str | None:
    """Adaptador aislado y compartido por todo lo que necesite pedirle algo a
    la IA (clasificador de respuestas, motor de historias, cierres). Con
    familia_id, usa la API key que esa familia cargó en Settings > API Keys
    para su proveedor activo; sin él (scripts, smoke tests), cae a la key
    global de .env (IA_PROVEEDOR / IA_MODELO). El modelo sigue siendo
    decisión global (IA_MODELO) incluso con key por familia — no se pidió
    elegirlo por familia. Devuelve None ante cualquier falla (sin API key,
    proveedor no reconocido, error de red) — quien lo llama decide cómo
    degradar, nunca se propaga la excepción. Los casos de "sin API key" y
    "sin saldo" además quedan registrados en el Activity log, acotados a la
    familia cuando la hay (ver _avisar_una_vez_por_hora)."""
    from app.models.enums import AccionActividad

    settings = get_settings()
    modelo = settings.ia_modelo

    if familia_id is not None:
        resuelto = _resolver_credencial_familia(familia_id)
        if resuelto is None:
            logger.warning("La familia %s no tiene una API key activa configurada.", familia_id)
            _avisar_una_vez_por_hora(AccionActividad.ia_sin_api_key, familia_id)
            return None
        proveedor, api_key = resuelto
    else:
        # Sin familia_id (scripts, smoke tests): cae a la key global de
        # .env tal como funcionaba antes de que existieran las keys por
        # familia — no se registra en el Activity log de ninguna familia.
        proveedor = settings.ia_proveedor.strip().lower()
        api_key = settings.anthropic_api_key if proveedor == "anthropic" else settings.openai_api_key
        if not api_key:
            logger.warning("No hay API key configurada para el proveedor de IA '%s'.", proveedor)
            return None

    funcion = _PROVEEDORES.get(proveedor)
    if funcion is None:
        logger.error("Proveedor de IA '%s' no reconocido (opciones: %s).", proveedor, list(_PROVEEDORES))
        return None

    try:
        return funcion(prompt, api_key, modelo, max_tokens)
    except SinSaldo:
        logger.error("Sin saldo en la cuenta de IA (%s, familia=%s).", proveedor, familia_id)
        _avisar_una_vez_por_hora(AccionActividad.ia_sin_saldo, familia_id, detalle=f"Proveedor: {proveedor}")
        return None
    except Exception:
        logger.exception("Falló la llamada a la IA (%s).", proveedor)
        return None
