import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoHechoFamiliar, EstadoHistoriaSesion, ModoEnvio, OrigenMensajeHistoria
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


def _minutos_transcurridos(sesion: HistoriaSesion, ahora: datetime) -> float:
    inicio = sesion.iniciada_en
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    return max(0.0, (ahora - inicio).total_seconds() / 60)


def _armar_prompt(
    historia: Historia,
    personaje: Personaje,
    mensajes: list[HistoriaMensaje],
    hechos_familiares: list[str],
    minutos_transcurridos: float = 0.0,
    forzar_cierre: bool = False,
) -> str:
    ficha_personaje = "\n".join(
        filter(
            None,
            [
                f"Relación con el paciente: {personaje.relacion_con_paciente}"
                if personaje.relacion_con_paciente
                else None,
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

    if forzar_cierre:
        regla_cierre = (
            "- Este mensaje tiene que ser el ÚLTIMO de la charla: ya se pasó el tiempo pensado para esta "
            "conversación. Cerrala ahora mismo, con cariño, en tu propio tono — si el paciente ya dijo algo como "
            "que se tiene que ir o despedirse, respondé a eso; si no, encontrá vos una despedida cálida y natural, "
            "sin inventar excusas de vida (trabajo, horarios, viajes) que no están en tu ficha. Como vas a marcar "
            '"cerrar": true, el mensaje en sí tiene que LEERSE como una despedida (algo tipo "te dejo por ahora", '
            '"hablamos en otro momento", "nos vemos pronto"), no solo un comentario cálido sobre lo que se habló.'
        )
    else:
        regla_cierre = (
            "- Si ya se charló lo esencial, o si se está acercando el tiempo pensado para esta charla, podés "
            "cerrarla vos mismo/a, en tu propio tono, sin inventar excusas de vida (trabajo, horarios, viajes) que "
            'no están en tu ficha. Pero marcá "cerrar": true SOLO si el mensaje que estás escribiendo en ese mismo '
            "turno es, en sí mismo, una despedida real (que la persona reconocería como un \"me voy\", \"te dejo\", "
            '"hablamos pronto") — un comentario cálido, una reflexión, o cualquier cosa que invite a seguir '
            'charlando NO cuenta como cierre, aunque suene lindo: ahí marcá "cerrar": false y seguí la charla '
            "normal."
        )

    return f"""Estás actuando como {personaje.nombre} en un ejercicio de estimulación cognitiva por chat con un paciente con dificultades de memoria. Tenés que sonar como una persona real que lo/la quiere, no como un asistente.

Ficha de {personaje.nombre} (no digas nada que la contradiga — por ejemplo no inventes un trabajo, una rutina o un lugar donde vive que no está acá):
{ficha_personaje}

Historia sobre la que están hablando:
{contexto_historia}
{bloque_hechos}

Reglas:
- Solo podés usar hechos de "lo que se sabe" arriba, de "otros datos ya sabidos de la familia", o lo que el paciente ya haya dicho en esta charla. Si te falta un dato que no está en ningún lado de eso, PREGUNTASELO al paciente en vez de inventarlo — que sea él/ella quien complete el recuerdo.
- Si el paciente muestra que no se acuerda de un dato puntual (un nombre, un lugar, etc.) y ese dato SÍ está en "lo que se sabe" o en "otros datos ya sabidos de la familia", ayudalo/a vos con cariño en vez de dejarlo sin resolver o preguntarle de nuevo — para eso están esos datos.
- Lo mismo si pregunta o repite algo que ya se había dicho antes en esta misma charla: contestale con la misma calidez que si fuera la primera vez — NUNCA le hagas notar que ya lo sabía o que ya te lo había preguntado (nada de "como te dije", "ya te lo había dicho", "te lo dije antes", "¿no te acordás?" o cualquier frase que suene a corrección o reproche). Preguntar de nuevo es normal en alguien con problemas de memoria, y señalarlo —por más suave que suene— es maltratarlo/a.
- Ya pasaron {minutos_transcurridos:.0f} de los {historia.duracion_maxima_minutos} minutos pensados para esta charla — guiate por ese tiempo real, no por la cantidad de mensajes, para decidir el ritmo.
{regla_cierre}
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
    minutos_transcurridos: float = 0.0,
    forzar_cierre: bool = False,
) -> tuple[str, bool]:
    """Adaptador aislado: genera el próximo mensaje del personaje dentro de
    una sesión de Historia, grounded en la historia + lo ya conversado (+
    opcionalmente hechos familiares ya validados por el admin). Devuelve
    (texto, debe_cerrar). Ante cualquier falla (sin API key, error de red,
    parseo) devuelve un mensaje de emergencia neutro en vez de dejar al
    paciente sin respuesta.

    `forzar_cierre` es el backstop real por tiempo: si ya se pasó la
    duración máxima configurada, cerramos sí o sí (no queda a criterio del
    modelo, que no tiene noción confiable de minutos reales) — pero nunca
    en seco: igual le pedimos a la IA un último mensaje de despedida en su
    propio tono, grounded en la charla, en vez de un corte mudo."""
    prompt = _armar_prompt(
        historia, personaje, mensajes, hechos_familiares or [], minutos_transcurridos, forzar_cierre
    )
    raw = generar_texto(prompt, max_tokens=400)
    if raw is None:
        return (MENSAJE_FALLBACK_CIERRE if mensajes else MENSAJE_FALLBACK_INICIO), (forzar_cierre or bool(mensajes))
    try:
        texto, cerrar = _parsear(raw)
        return texto, (cerrar or forzar_cierre)
    except Exception:
        logger.exception("Falló el parseo de la respuesta de historia; se usa fallback.")
        return (MENSAJE_FALLBACK_CIERRE if mensajes else MENSAJE_FALLBACK_INICIO), (forzar_cierre or bool(mensajes))


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


def procesar_historias_vencidas(
    db: Session, paciente_id: int, ahora: datetime | None = None
) -> list[Historia]:
    """Equivalente de motor.procesar_guiones_vencidos para historias: busca
    historias en modo automático con fecha ya vencida (acotadas a la
    familia del paciente) y las propone solas. A diferencia de un guion de
    entrada, una Historia es contenido reusable, no algo que pase a
    "enviado" — por eso, una vez disparada, se limpia fecha_programada en
    vez de cambiar de estado: queda consumida hasta que alguien programe
    una fecha nueva."""
    ahora = ahora or datetime.now(timezone.utc)
    paciente = db.get(Paciente, paciente_id)
    vencidas = list(
        db.scalars(
            select(Historia)
            .join(Personaje, Historia.personaje_id == Personaje.id)
            .where(
                Historia.modo_envio == ModoEnvio.automatico,
                Historia.fecha_programada.is_not(None),
                Historia.fecha_programada <= ahora,
                Personaje.familia_id == paciente.familia_id,
            )
        ).all()
    )

    procesadas = []
    for historia in vencidas:
        historia.fecha_programada = None
        iniciar_sesion(db, historia, paciente_id, ahora)
        procesadas.append(historia)

    return procesadas


def iniciar_sesion(
    db: Session,
    historia: Historia,
    paciente_id: int,
    ahora: datetime | None = None,
    texto_inicial: str | None = None,
) -> HistoriaSesion:
    """Arranca la sesión de verdad: la crea y le llega al paciente ya
    mismo. `texto_inicial`, si viene, es un mensaje ya generado y aprobado
    de antes (ver `aprobar_propuesta`) — se usa tal cual, sin generar uno
    nuevo, para que lo que se aprobó sea exactamente lo que se manda."""
    ahora = ahora or datetime.now(timezone.utc)
    sesion = HistoriaSesion(historia_id=historia.id, paciente_id=paciente_id)
    db.add(sesion)
    db.flush()

    if texto_inicial is not None:
        texto, cerrar = texto_inicial, False
    else:
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


def proponer(db: Session, historia: Historia, ahora: datetime | None = None) -> None:
    """Modo manual: genera el primer mensaje y lo deja esperando en la
    Bandeja — no crea ninguna sesión todavía, nada le llega al paciente
    hasta que se apruebe (igual que un guion de entrada manual)."""
    ahora = ahora or datetime.now(timezone.utc)
    hechos = _hechos_validados(db, historia.personaje.familia_id)
    texto, _cerrar = generar_siguiente_mensaje(historia, historia.personaje, [], hechos)
    historia.mensaje_propuesto = texto
    historia.propuesta_en = ahora


def aprobar_propuesta(
    db: Session, historia: Historia, paciente_id: int, mensaje: str, ahora: datetime | None = None
) -> HistoriaSesion:
    """El admin aprueba (y puede haber editado) la propuesta: recién ahora
    se crea la sesión de verdad y le llega al paciente."""
    historia.mensaje_propuesto = None
    historia.propuesta_en = None
    return iniciar_sesion(db, historia, paciente_id, ahora, texto_inicial=mensaje)


def desactivar_propuesta(historia: Historia) -> None:
    """Sacar la propuesta de la Bandeja sin aprobarla — no se manda nada."""
    historia.mensaje_propuesto = None
    historia.propuesta_en = None


def registrar_respuesta(db: Session, sesion: HistoriaSesion, texto_respuesta: str, ahora: datetime | None = None) -> None:
    """El paciente contestó dentro de una sesión de historia activa: guarda
    su mensaje y genera la siguiente intervención del personaje."""
    ahora = ahora or datetime.now(timezone.utc)
    db.add(HistoriaMensaje(sesion_id=sesion.id, origen=OrigenMensajeHistoria.paciente, texto=texto_respuesta))
    db.flush()
    db.refresh(sesion)

    historia = sesion.historia
    hechos = _hechos_validados(db, historia.personaje.familia_id)
    minutos_transcurridos = _minutos_transcurridos(sesion, ahora)
    forzar_cierre = minutos_transcurridos >= historia.duracion_maxima_minutos
    texto, cerrar = generar_siguiente_mensaje(
        historia, historia.personaje, list(sesion.mensajes), hechos, minutos_transcurridos, forzar_cierre
    )
    db.add(HistoriaMensaje(sesion_id=sesion.id, origen=OrigenMensajeHistoria.personaje, texto=texto))
    _cerrar_si_hace_falta(db, sesion, cerrar, ahora)
    db.flush()
    db.refresh(sesion)

    paciente = db.get(Paciente, sesion.paciente_id)
    enviar_push_paciente(
        db, paciente, titulo=historia.personaje.nombre, cuerpo=texto,
        url=f"/chat/{sesion.paciente_id}/{historia.personaje_id}",
    )
