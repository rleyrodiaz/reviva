import json
import logging
import re

from app.models.enums import OrigenMensajeHistoria
from app.models.historia import Historia
from app.models.historia_mensaje import HistoriaMensaje
from app.services.ia_cliente import generar_texto

logger = logging.getLogger(__name__)


def _armar_prompt(historia: Historia, mensajes: list[HistoriaMensaje]) -> str:
    comentarios_paciente = "\n".join(
        f"- {m.texto}" for m in mensajes if m.origen == OrigenMensajeHistoria.paciente
    )
    if not comentarios_paciente:
        return ""

    return f"""Un paciente charló con un familiar sobre esta historia: "{historia.titulo}".

Ya sabíamos esto de la historia:
{historia.contenido}

Esto es lo que el PACIENTE (no el familiar) dijo durante la charla:
{comentarios_paciente}

De lo que dijo el paciente, identificá datos NUEVOS sobre la familia que valga la pena recordar para usar en OTRAS charlas futuras (gustos, preferencias, logros, datos de otras personas de la familia). No repitas nada que ya estuviera en "lo que sabíamos" arriba, y no incluyas detalles que sean solo parte de esta anécdota puntual y no sirvan fuera de ella.

Respondé ÚNICAMENTE con un JSON de la forma {{"hechos": ["dato 1", "dato 2"]}}, con una lista vacía si no hay nada nuevo que valga la pena, sin texto adicional."""


def extraer_hechos_nuevos(historia: Historia, mensajes: list[HistoriaMensaje]) -> list[str]:
    """Adaptador aislado: mira SOLO lo que dijo el paciente (nunca lo que dijo
    el personaje, para no terminar validando una alucinación de la IA como si
    fuera un hecho real) y propone datos generales de familia que podrían
    servir en otras historias. Quedan pendientes de que el admin los apruebe
    — nunca se usan solos. Ante cualquier falla, devuelve lista vacía en vez
    de romper el cierre de la sesión."""
    prompt = _armar_prompt(historia, mensajes)
    if not prompt:
        return []

    raw = generar_texto(prompt, max_tokens=300, familia_id=historia.personaje.familia_id)
    if raw is None:
        return []

    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match is None:
            return []
        data = json.loads(match.group(0))
        hechos = data.get("hechos", [])
        return [str(h).strip() for h in hechos if str(h).strip()]
    except Exception:
        logger.exception("Falló el parseo de hechos familiares detectados.")
        return []
