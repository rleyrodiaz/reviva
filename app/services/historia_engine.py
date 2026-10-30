import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoHechoFamiliar, EstadoHistoriaSesion, OrigenMensajeHistoria
from app.models.hecho_familiar import HechoFamiliar
from app.models.historia import Historia
from app.models.historia_mensaje import HistoriaMensaje
from app.models.historia_sesion import HistoriaSesion
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.services.extractor_hechos import extraer_hechos_nuevos
from app.services.ia_cliente import generar_texto
from app.services.push import enviar_push_paciente

logger = logging.getLogger(__name__)

MENSAJE_FALLBACK_INICIO = "Che, me acordé de algo lindo... ¿tenés un ratito para charlar?"
MENSAJE_FALLBACK_CIERRE = "Bueno, te dejo por ahora — ¡seguimos charlando otro día! ❤️"


def _armar_prompt(
    historia: Historia,
    personaje: Personaje,
    mensajes: list[HistoriaMensaje],
    hechos_familiares: list[str],
) -> str:
    ficha_personaje = "\n".join(
        filter(
            None,
            [
                f"Relación con el paciente: {personaje.relacion_con_paciente}"
                if personaje.relacion_con_paciente
                else None,
                f"Descripción: {personaje.descripcion}" if personaje.descripcion else None,
                f"Tono de escritura: {personaje.tono_escritura}" if personaje.tono_escritura else None,
            ],
        )
    ) or "(sin datos adicionales sobre este personaje)"

    contexto_historia = "\n".join(
        filter(
            None,
            [
                f"Cuándo: {historia.epoca}" if historia.epoca else None,
                f"Dónde: {historia.lugar}" if historia.lugar else None,
                f"Quiénes estaban: {historia.participantes}" if historia.participantes else None,
                f"Lo que se sabe:\n{historia.contenido}",
            ],
        )
    )

    transcripcion = (
        "\n".join(
            f"{'PACIENTE' if m.origen == OrigenMensajeHistoria.paciente else personaje.nombre.upper()}: {m.texto}"
            for m in mensajes
        )
        or "(todavía no empezó la charla)"
    )

    bloque_hechos = ""
    if hechos_familiares:
        lista = "\n".join(f"- {h}" for h in hechos_familiares)
        bloque_hechos = f"""

Otros datos ya sabidos de la familia (no los menciones si no vienen al caso, pero si el paciente busca uno de estos datos puntuales y no lo encuentra, sí usalo — ver regla de abajo):
{lista}"""

    return f"""Estás actuando como {personaje.nombre} en un ejercicio de estimulación cognitiva por chat con un paciente con dificultades de memoria. Tenés que sonar como una persona real que lo/la quiere, no como un asistente.

Ficha de {personaje.nombre} (no digas nada que la contradiga — por ejemplo no inventes un trabajo, una rutina o un lugar donde vive que no está acá):
{ficha_personaje}

Historia sobre la que están hablando:
{contexto_historia}
{bloque_hechos}

Reglas:
- Solo podés usar hechos de "lo que se sabe" arriba, de "otros datos ya sabidos de la familia", o lo que el paciente ya haya dicho en esta charla. Si te falta un dato que no está en ningún lado de eso, PREGUNTASELO al paciente en vez de inventarlo — que sea él/ella quien complete el recuerdo.
- Si el paciente muestra que no se acuerda de un dato puntual (un nombre, un lugar, etc.) y ese dato SÍ está en "lo que se sabe" o en "otros datos ya sabidos de la familia", ayudalo/a vos con cariño en vez de dejarlo sin resolver o preguntarle de nuevo — para eso están esos datos.
- Esta charla debería sentirse como una conversación de a lo sumo {historia.duracion_maxima_minutos} minutos entre personas reales — no la estires de más ni la llenes de relleno.
- Si ya se charló lo esencial, o si esto ya lleva varios intercambios, cerrala con cariño vos mismo/a, en tu propio tono, sin inventar excusas de vida (trabajo, horarios, viajes) que no están en tu ficha.
- Un solo mensaje corto por turno, como en un chat de verdad.
- El paciente es una persona mayor con dificultades cognitivas: usá un lenguaje cálido, claro y respetuoso, sin jerga moderna ni muletillas juveniles (nada de "ey", "posta", "chabón", "capo" y similares) — hablale como realmente le hablaría alguien de tu relación con él/ella, no como si le escribieras a un amigo de tu misma edad.

Conversación hasta ahora:
{transcripcion}

Respondé ÚNICAMENTE con un JSON de la forma {{"mensaje": "<tu próximo mensaje, en primera persona, tal como lo escribirías vos>", "cerrar": <true si este mensaje es una despedida que termina la charla, false si no>}}, sin texto adicional."""


def _parsear(raw: str) -> tuple[str, bool]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise ValueError(f"No se encontró un JSON en la respuesta del modelo: {raw!r}")
    data = json.loads(match.group(0))
    mensaje = str(data.get("mensaje", "")).strip()
    if not mensaje:
        raise ValueError("El modelo devolvió un mensaje vacío.")
    return mensaje, bool(data.get("cerrar", False))


def generar_siguiente_mensaje(
    historia: Historia,
    personaje: Personaje,
    mensajes: list[HistoriaMensaje],
    hechos_familiares: list[str] | None = None,
) -> tuple[str, bool]:
    """Adaptador aislado: genera el próximo mensaje del personaje dentro de
    una sesión de Historia, grounded en la historia + lo ya conversado (+
    opcionalmente hechos familiares ya validados por el admin). Devuelve
    (texto, debe_cerrar). Ante cualquier falla (sin API key, error de red,
    parseo) devuelve un mensaje de emergencia neutro en vez de dejar al
    paciente sin respuesta."""
    prompt = _armar_prompt(historia, personaje, mensajes, hechos_familiares or [])
    raw = generar_texto(prompt, max_tokens=400)
    if raw is None:
        return (MENSAJE_FALLBACK_CIERRE if mensajes else MENSAJE_FALLBACK_INICIO), bool(mensajes)
    try:
        return _parsear(raw)
    except Exception:
        logger.exception("Falló el parseo de la respuesta de historia; se usa fallback.")
        return (MENSAJE_FALLBACK_CIERRE if mensajes else MENSAJE_FALLBACK_INICIO), bool(mensajes)


def _hechos_validados(db: Session, familia_id: int) -> list[str]:
    return list(
        db.scalars(
            select(HechoFamiliar.texto).where(
                HechoFamiliar.familia_id == familia_id,
                HechoFamiliar.estado == EstadoHechoFamiliar.validado,
            )
        ).all()
    )


def _cerrar_si_hace_falta(db: Session, sesion: HistoriaSesion, cerrar: bool, ahora: datetime) -> None:
    if not cerrar:
        return
    sesion.estado = EstadoHistoriaSesion.finalizada
    sesion.finalizada_en = ahora
    # Al cerrar, rescatamos de lo que dijo el PACIENTE (nunca del personaje)
    # candidatos a hechos de familia, para que el admin los revise y decida
    # si alimentan el prompt de otras historias.
    hechos = extraer_hechos_nuevos(sesion.historia, list(sesion.mensajes))
    for texto in hechos:
        db.add(
            HechoFamiliar(
                familia_id=sesion.historia.personaje.familia_id,
                texto=texto,
                origen_sesion_id=sesion.id,
            )
        )


def iniciar_sesion(
    db: Session, historia: Historia, paciente_id: int, ahora: datetime | None = None
) -> HistoriaSesion:
    """El admin le propone la historia al paciente ahora: arranca una sesión
    nueva y genera el primer mensaje del personaje."""
    ahora = ahora or datetime.now(timezone.utc)
    sesion = HistoriaSesion(historia_id=historia.id, paciente_id=paciente_id)
    db.add(sesion)
    db.flush()

    hechos = _hechos_validados(db, historia.personaje.familia_id)
    texto, cerrar = generar_siguiente_mensaje(historia, historia.personaje, [], hechos)
    db.add(HistoriaMensaje(sesion_id=sesion.id, origen=OrigenMensajeHistoria.personaje, texto=texto))
    _cerrar_si_hace_falta(db, sesion, cerrar, ahora)
    db.flush()

    paciente = db.get(Paciente, paciente_id)
    enviar_push_paciente(
        db, paciente, titulo=historia.personaje.nombre, cuerpo=texto,
        url=f"/chat/{paciente_id}/{historia.personaje_id}",
    )
    return sesion


def registrar_respuesta(db: Session, sesion: HistoriaSesion, texto_respuesta: str, ahora: datetime | None = None) -> None:
    """El paciente contestó dentro de una sesión de historia activa: guarda
    su mensaje y genera la siguiente intervención del personaje."""
    ahora = ahora or datetime.now(timezone.utc)
    db.add(HistoriaMensaje(sesion_id=sesion.id, origen=OrigenMensajeHistoria.paciente, texto=texto_respuesta))
    db.flush()
    db.refresh(sesion)

    historia = sesion.historia
    hechos = _hechos_validados(db, historia.personaje.familia_id)
    texto, cerrar = generar_siguiente_mensaje(historia, historia.personaje, list(sesion.mensajes), hechos)
    db.add(HistoriaMensaje(sesion_id=sesion.id, origen=OrigenMensajeHistoria.personaje, texto=texto))
    _cerrar_si_hace_falta(db, sesion, cerrar, ahora)
    db.flush()
    db.refresh(sesion)

    paciente = db.get(Paciente, sesion.paciente_id)
    enviar_push_paciente(
        db, paciente, titulo=historia.personaje.nombre, cuerpo=texto,
        url=f"/chat/{sesion.paciente_id}/{historia.personaje_id}",
    )
