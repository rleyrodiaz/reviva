from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoGuion, ModoEnvio
from app.models.guion import Guion
from app.models.interaccion import Interaccion
from app.models.opcion_respuesta import OpcionRespuesta
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.services.cierre_guion import generar_cierre
from app.services.clasificador import clasificar_respuesta
from app.services.push import enviar_push_paciente

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


def _enviar_guion(db: Session, guion: Guion, paciente_id: int, ahora: datetime) -> Interaccion:
    guion.estado = EstadoGuion.enviado
    interaccion = Interaccion(
        guion_id=guion.id,
        paciente_id=paciente_id,
        texto_enviado=guion.texto_mensaje,
        timestamp_envio=ahora,
    )
    db.add(interaccion)
    db.flush()

    paciente = db.get(Paciente, paciente_id)
    enviar_push_paciente(
        db,
        paciente,
        titulo=guion.personaje.nombre,
        cuerpo=guion.texto_mensaje,
        url=f"/chat/{paciente_id}/{guion.personaje_id}",
    )
    return interaccion


def _activar_guion_siguiente(guion_siguiente: Guion | None, ahora: datetime) -> None:
    """El árbol de guiones no se autorregula por fecha: el scheduler manda
    cualquier guion en `borrador` cuya fecha ya pasó, sea o no el destino de
    una rama todavía no alcanzada. Por eso, apenas una rama/opción elige un
    guion siguiente, lo activamos ya (borrador + fecha inmediata) sin
    importar su estado o fecha previa — así nunca dispara por su cuenta
    antes de ser alcanzado, ni queda trabado si ya se había usado."""
    if guion_siguiente is not None:
        guion_siguiente.estado = EstadoGuion.borrador
        guion_siguiente.fecha_programada = ahora


def registrar_respuesta_opciones(
    interaccion: Interaccion, opcion: OpcionRespuesta, ahora: datetime | None = None
) -> Guion | None:
    """Paso 4: el paciente eligió un quick reply — no hace falta matching.
    Devuelve el guion_siguiente (reabierto en `borrador` si hacía falta) o
    None si la rama es terminal."""
    if opcion.guion_id != interaccion.guion_id:
        raise ValueError("La opción no pertenece al guion de esta interacción.")

    ahora = ahora or datetime.now(timezone.utc)
    interaccion.respuesta_texto = opcion.texto_opcion
    interaccion.opcion_elegida_id = opcion.id
    interaccion.timestamp_respuesta = ahora
    _activar_guion_siguiente(opcion.guion_siguiente, ahora)
    return opcion.guion_siguiente


def registrar_respuesta_libre(
    interaccion: Interaccion, texto_respuesta: str, ahora: datetime | None = None
) -> Guion | None:
    """Paso 5: la respuesta es texto libre. Usa el clasificador de IA
    (adaptador aislado) para elegir la rama; si no matchea con confianza
    suficiente, dispara la rama fallback para no trabar la conversación.
    Si ese fallback no tiene destino armado a mano, no hay nada escrito
    para seguir — en vez de dejar la conversación sin contestar nada, la
    IA genera un cierre breve (ver cierre_guion.py). Un fallback CON
    destino configurado sigue funcionando exactamente igual que siempre."""
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
        mensaje_anterior = interaccion.texto_enviado or guion.texto_mensaje
        interaccion.cierre_generado = generar_cierre(mensaje_anterior, texto_respuesta, guion.personaje)
        return None

    _activar_guion_siguiente(rama_elegida.guion_siguiente, ahora)
    return rama_elegida.guion_siguiente
