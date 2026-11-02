from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoGuion, ModoEnvio
from app.models.guion import Guion
from app.models.interaccion import Interaccion
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.services.cierre_guion import generar_cierre
from app.services.clasificador import clasificar_respuesta
from app.services.push import enviar_push_paciente
from app.services.respuesta_guion import adaptar_mensaje_guion

CONFIANZA_MINIMA = 0.6


def procesar_guiones_vencidos(
    db: Session, paciente_id: int, ahora: datetime | None = None
) -> list[Guion]:
    """Pasos 1-2 del motor (SPEC sección 5): busca guiones vencidos en
    `borrador` y los manda. La fecha solo tiene sentido para automático
    (decide el momento exacto del envío) — tanto para el guion de entrada
    como, en los hecho, para cualquier guion que no sea de entrada (siempre
    fluyen solos). Un guion de entrada manual NO pasa por acá: entrar a la
    bandeja es una acción explícita del admin desde el panel de la
    conversación (ver configurar_conversacion en admin.py), no algo que la
    fecha o el scheduler decidan. El scheduler llama a esta función una vez
    por cada paciente del sistema, así que el filtro por familia es
    necesario para que cada paciente solo reciba guiones de personajes de
    SU familia — sin él, cualquier guion vencido se le atribuía al primer
    paciente que el loop procesara en ese tick, sin importar de qué familia
    fuera."""
    ahora = ahora or datetime.now(timezone.utc)
    paciente = db.get(Paciente, paciente_id)
    vencidos = list(
        db.scalars(
            select(Guion)
            .join(Personaje, Guion.personaje_id == Personaje.id)
            .where(
                Guion.estado == EstadoGuion.borrador,
                Guion.fecha_programada <= ahora,
                Personaje.familia_id == paciente.familia_id,
            )
        ).all()
    )

    procesados = []
    for guion in vencidos:
        if guion.es_entrada and guion.modo_envio == ModoEnvio.manual:
            continue
        _enviar_guion(db, guion, paciente_id, ahora)
        procesados.append(guion)

    return procesados


def aprobar_guion(
    db: Session, guion: Guion, paciente_id: int, ahora: datetime | None = None
) -> Interaccion:
    """El admin confirma desde la bandeja de `pendiente_aprobacion` el envío
    de un guion en modo manual."""
    if guion.estado != EstadoGuion.pendiente_aprobacion:
        raise ValueError(
            f"El guion {guion.id} no está pendiente de aprobación (estado={guion.estado})."
        )
    return _enviar_guion(db, guion, paciente_id, ahora or datetime.now(timezone.utc))


def _transcripcion_guion(db: Session, personaje_id: int, paciente_id: int) -> str:
    """Toda la charla guionada hasta ahora entre este personaje y este
    paciente, en orden — para que la IA pueda chequear consistencia contra
    cualquier punto anterior, no solo contra el último mensaje."""
    interacciones = db.scalars(
        select(Interaccion)
        .join(Guion)
        .where(Guion.personaje_id == personaje_id, Interaccion.paciente_id == paciente_id)
        .order_by(Interaccion.timestamp_envio)
    ).all()
    if not interacciones:
        return "(sin mensajes previos)"
    lineas = []
    for i in interacciones:
        nombre_personaje = i.guion.personaje.nombre.upper()
        lineas.append(f"{nombre_personaje}: {i.texto_enviado or i.guion.texto_mensaje}")
        if i.respuesta_texto:
            lineas.append(f"PACIENTE: {i.respuesta_texto}")
        if i.cierre_generado:
            lineas.append(f"{nombre_personaje}: {i.cierre_generado}")
    return "\n".join(lineas)


def _enviar_guion(
    db: Session, guion: Guion, paciente_id: int, ahora: datetime,
    contexto_respuesta: str | None = None, transcripcion: str | None = None,
) -> Interaccion:
    """Manda el guion tal cual, salvo que venga con `contexto_respuesta` — la
    respuesta libre del paciente que disparó este guion como destino de una
    rama. En ese caso, el texto que se manda no es el template a secas: se le
    pide a la IA que lo complete con lo que el paciente haya traído de más
    (ver respuesta_guion.py), sin tocar el contenido ya escrito a mano. Para
    eso necesita `transcripcion` — toda la charla hasta ahora, no solo el
    último mensaje — así no contradice ni vuelve ambiguo algo que ya había
    quedado claro antes (ej. que el plan es "hoy")."""
    guion.estado = EstadoGuion.enviado
    texto_final = guion.texto_mensaje
    if contexto_respuesta is not None:
        texto_final = adaptar_mensaje_guion(
            guion.texto_mensaje, transcripcion or guion.texto_mensaje, guion.personaje
        )

    interaccion = Interaccion(
        guion_id=guion.id,
        paciente_id=paciente_id,
        texto_enviado=texto_final,
        timestamp_envio=ahora,
    )
    db.add(interaccion)
    db.flush()

    paciente = db.get(Paciente, paciente_id)
    enviar_push_paciente(
        db,
        paciente,
        titulo=guion.personaje.nombre,
        cuerpo=texto_final,
        url=f"/chat/{paciente_id}/{guion.personaje_id}",
    )
    return interaccion


def _activar_guion_siguiente(guion_siguiente: Guion | None, ahora: datetime) -> None:
    """El árbol de guiones no se autorregula por fecha: el scheduler manda
    cualquier guion en `borrador` cuya fecha ya pasó, sea o no el destino de
    una rama todavía no alcanzada. Por eso, apenas una rama elige un
    guion siguiente, lo activamos ya (borrador + fecha inmediata) sin
    importar su estado o fecha previa — así nunca dispara por su cuenta
    antes de ser alcanzado, ni queda trabado si ya se había usado."""
    if guion_siguiente is not None:
        guion_siguiente.estado = EstadoGuion.borrador
        guion_siguiente.fecha_programada = ahora


def registrar_respuesta_libre(
    db: Session, interaccion: Interaccion, texto_respuesta: str, ahora: datetime | None = None
) -> Guion | None:
    """Paso 5: la respuesta es texto libre. Usa el clasificador de IA
    (adaptador aislado) para elegir la rama; si no matchea con confianza
    suficiente, dispara la rama fallback para no trabar la conversación.
    Si ese fallback no tiene destino armado a mano, no hay nada escrito
    para seguir — en vez de dejar la conversación sin contestar nada, la
    IA genera un cierre breve (ver cierre_guion.py). Un fallback CON
    destino configurado sigue funcionando exactamente igual que siempre.

    El guion destino se manda ya mismo (no se deja para el próximo tick del
    scheduler) pasándole el texto de esta respuesta como contexto, así la IA
    puede completar el mensaje preparado con algo que el paciente haya
    traído de más (ver respuesta_guion.py) — salvo que el destino sea un
    guion de entrada manual, que tiene que seguir yendo a la bandeja tal
    cual, sin adaptar nada de antemano."""
    guion = interaccion.guion
    ramas = [r for r in guion.ramas_libres if not r.es_fallback]
    resultado = clasificar_respuesta(
        guion.texto_mensaje, texto_respuesta, [(r.id, r.criterio) for r in ramas]
    )

    rama_elegida = None
    if resultado.rama_id is not None and resultado.confianza >= CONFIANZA_MINIMA:
        rama_elegida = next((r for r in ramas if r.id == resultado.rama_id), None)

    if rama_elegida is None:
        rama_elegida = next((r for r in guion.ramas_libres if r.es_fallback), None)
        if rama_elegida is None:
            raise ValueError(f"El guion {guion.id} no tiene rama fallback configurada.")

    ahora = ahora or datetime.now(timezone.utc)
    interaccion.respuesta_texto = texto_respuesta
    interaccion.rama_libre_elegida_id = rama_elegida.id
    interaccion.timestamp_respuesta = ahora

    if rama_elegida.es_fallback and rama_elegida.guion_siguiente_id is None:
        transcripcion = _transcripcion_guion(db, guion.personaje_id, interaccion.paciente_id)
        interaccion.cierre_generado = generar_cierre(transcripcion, texto_respuesta, guion.personaje)
        return None

    destino = rama_elegida.guion_siguiente
    if destino is None:
        return None
    if destino.es_entrada and destino.modo_envio == ModoEnvio.manual:
        _activar_guion_siguiente(destino, ahora)
        return destino

    transcripcion = _transcripcion_guion(db, guion.personaje_id, interaccion.paciente_id)
    _enviar_guion(
        db, destino, interaccion.paciente_id, ahora,
        contexto_respuesta=texto_respuesta, transcripcion=transcripcion,
    )
    return destino
