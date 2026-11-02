from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.conversacion import Conversacion
from app.models.enums import EstadoGuion, ModoEnvio
from app.models.familia import Familia
from app.models.guion import Guion
from app.models.interaccion import Interaccion
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.models.rama_respuesta_libre import RamaRespuestaLibre
from app.services import motor
from app.services.clasificador import ResultadoClasificacion

AHORA = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
PASADO = AHORA - timedelta(hours=1)
FUTURO = AHORA + timedelta(days=1)


@pytest.fixture
def escenario(db):
    """Familia + paciente + personaje base para todos los tests del motor."""
    familia = Familia(nombre="Familia Test")
    db.add(familia)
    db.flush()
    paciente = Paciente(familia_id=familia.id, nombre="Paciente Test")
    personaje = Personaje(familia_id=familia.id, nombre="Carlos")
    db.add_all([paciente, personaje])
    db.flush()
    conversacion = Conversacion(personaje_id=personaje.id, nombre="Conversación Test")
    db.add(conversacion)
    db.flush()
    return {
        "familia": familia,
        "paciente": paciente,
        "personaje": personaje,
        "conversacion": conversacion,
    }


def _nuevo_guion(db, personaje, conversacion, modo_envio, fecha, texto="Hola", es_entrada=False):
    guion = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=fecha,
        texto_mensaje=texto,
        modo_envio=modo_envio,
        estado=EstadoGuion.borrador,
        es_entrada=es_entrada,
    )
    db.add(guion)
    db.flush()
    return guion


def test_procesar_vencidos_entrada_manual_no_la_toca_el_scheduler(db, escenario):
    # La fecha no participa en nada para un guion de entrada manual: pasar
    # a la bandeja es una acción explícita del admin (ver
    # configurar_conversacion en admin.py), nunca algo que decida el
    # scheduler aunque la fecha ya haya pasado.
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, PASADO,
        es_entrada=True,
    )

    procesados = motor.procesar_guiones_vencidos(db, escenario["paciente"].id, ahora=AHORA)

    assert procesados == []
    assert guion.estado == EstadoGuion.borrador


def test_procesar_vencidos_manual_no_entrada_se_envia_directo(db, escenario):
    # Un guion manual que NO es de entrada (ya arrancó la conversación) ya
    # no pasa por la bandeja: fluye solo según el diseño de la cadena.
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, PASADO,
        es_entrada=False,
    )

    motor.procesar_guiones_vencidos(db, escenario["paciente"].id, ahora=AHORA)

    assert guion.estado == EstadoGuion.enviado


def test_editar_texto_del_guion_no_reescribe_lo_ya_enviado(db, escenario):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO,
        texto="Texto original",
    )
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)
    assert interaccion.texto_enviado == "Texto original"

    # El admin edita el guion después de que ya se mandó (para la próxima vez).
    guion.texto_mensaje = "Texto editado despues"

    assert interaccion.texto_enviado == "Texto original"


def test_procesar_vencidos_automatico_se_envia_directo(db, escenario):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )

    motor.procesar_guiones_vencidos(db, escenario["paciente"].id, ahora=AHORA)

    assert guion.estado == EstadoGuion.enviado
    interaccion = db.scalar(select(Interaccion).where(Interaccion.guion_id == guion.id))
    assert interaccion is not None
    assert interaccion.paciente_id == escenario["paciente"].id
    # SQLite no conserva tzinfo en datetimes; comparamos el valor naive.
    assert interaccion.timestamp_envio == AHORA.replace(tzinfo=None)


def test_procesar_vencidos_ignora_guiones_futuros(db, escenario):
    _nuevo_guion(db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, FUTURO)

    procesados = motor.procesar_guiones_vencidos(db, escenario["paciente"].id, ahora=AHORA)

    assert procesados == []


def test_aprobar_guion_pendiente_lo_envia(db, escenario):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, PASADO
    )
    guion.estado = EstadoGuion.pendiente_aprobacion

    interaccion = motor.aprobar_guion(db, guion, escenario["paciente"].id, ahora=AHORA)

    assert guion.estado == EstadoGuion.enviado
    assert interaccion.guion_id == guion.id
    assert interaccion.paciente_id == escenario["paciente"].id
    assert interaccion.timestamp_envio == AHORA


def test_aprobar_guion_que_no_esta_pendiente_falla(db, escenario):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, PASADO
    )

    with pytest.raises(ValueError):
        motor.aprobar_guion(db, guion, escenario["paciente"].id, ahora=AHORA)


def test_registrar_respuesta_libre_con_match_avanza_a_esa_rama(db, escenario, monkeypatch):
    guion_recuerda = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, FUTURO, texto="Bien!"
    )
    guion_no_recuerda = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, FUTURO, texto="Está bien igual"
    )
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )
    rama_recuerda = RamaRespuestaLibre(
        guion_id=guion.id, criterio="El paciente recuerda el viaje",
        guion_siguiente_id=guion_recuerda.id,
    )
    rama_fallback = RamaRespuestaLibre(
        guion_id=guion.id, es_fallback=True, guion_siguiente_id=guion_no_recuerda.id,
    )
    db.add_all([rama_recuerda, rama_fallback])
    db.flush()
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)

    monkeypatch.setattr(
        motor, "clasificar_respuesta",
        lambda pregunta, texto, ramas: ResultadoClasificacion(rama_id=rama_recuerda.id, confianza=0.9),
    )
    monkeypatch.setattr(
        motor, "adaptar_mensaje_guion",
        lambda texto_base, transcripcion, personaje: f"{texto_base} (adaptado con: {transcripcion})",
    )

    siguiente = motor.registrar_respuesta_libre(db, interaccion, "Sí, fuimos en el Renault", ahora=AHORA)

    assert siguiente is guion_recuerda
    assert interaccion.rama_libre_elegida_id == rama_recuerda.id
    assert interaccion.respuesta_texto == "Sí, fuimos en el Renault"
    # El destino no queda solo "activado" para que lo mande el scheduler
    # después: se manda ya mismo, con el texto adaptado a toda la charla
    # hasta ahora, no solo a esta última respuesta (ver respuesta_guion.py).
    assert guion_recuerda.estado == EstadoGuion.enviado
    nueva_interaccion = db.scalar(select(Interaccion).where(Interaccion.guion_id == guion_recuerda.id))
    assert nueva_interaccion.texto_enviado == (
        "Bien! (adaptado con: CARLOS: Hola\nPACIENTE: Sí, fuimos en el Renault)"
    )


def test_registrar_respuesta_libre_destino_entrada_manual_no_se_adapta_ni_se_manda(db, escenario, monkeypatch):
    # Si una rama apunta a un guion de entrada manual (caso raro, pero
    # posible), tiene que seguir yendo a la bandeja tal cual estaba escrito
    # — nada de adaptarlo con IA de antemano ni mandarlo solo.
    destino_entrada = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, FUTURO,
        texto="Entrada de otra conversación", es_entrada=True,
    )
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )
    rama = RamaRespuestaLibre(
        guion_id=guion.id, criterio="Dispara la otra conversación", guion_siguiente_id=destino_entrada.id,
    )
    rama_fallback = RamaRespuestaLibre(guion_id=guion.id, es_fallback=True)
    db.add_all([rama, rama_fallback])
    db.flush()
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)

    monkeypatch.setattr(
        motor, "clasificar_respuesta",
        lambda pregunta, texto, ramas: ResultadoClasificacion(rama_id=rama.id, confianza=0.9),
    )
    def _no_debería_llamarse(*a, **kw):
        raise AssertionError("un destino de entrada manual no debería pasar por la IA")
    monkeypatch.setattr(motor, "adaptar_mensaje_guion", _no_debería_llamarse)

    siguiente = motor.registrar_respuesta_libre(db, interaccion, "dale, arranquemos la otra", ahora=AHORA)

    assert siguiente is destino_entrada
    assert destino_entrada.estado == EstadoGuion.borrador
    assert destino_entrada.fecha_programada == AHORA
    assert db.scalar(select(Interaccion).where(Interaccion.guion_id == destino_entrada.id)) is None


def test_registrar_respuesta_libre_sin_match_dispara_fallback(db, escenario, monkeypatch):
    guion_fallback_destino = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.manual, FUTURO
    )
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )
    rama_recuerda = RamaRespuestaLibre(guion_id=guion.id, criterio="Recuerda el viaje")
    rama_fallback = RamaRespuestaLibre(
        guion_id=guion.id, es_fallback=True, guion_siguiente_id=guion_fallback_destino.id
    )
    db.add_all([rama_recuerda, rama_fallback])
    db.flush()
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)

    monkeypatch.setattr(
        motor, "clasificar_respuesta",
        lambda pregunta, texto, ramas: ResultadoClasificacion(rama_id=None, confianza=0.0),
    )
    def _no_debería_llamarse(*a, **kw):
        raise AssertionError("un fallback CON destino armado no debería generar un cierre con IA")
    monkeypatch.setattr(motor, "generar_cierre", _no_debería_llamarse)
    monkeypatch.setattr(
        motor, "adaptar_mensaje_guion",
        lambda texto_base, transcripcion, personaje: texto_base,
    )

    siguiente = motor.registrar_respuesta_libre(db, interaccion, "no sé de qué hablás", ahora=AHORA)

    assert siguiente is guion_fallback_destino
    assert interaccion.rama_libre_elegida_id == rama_fallback.id
    assert interaccion.cierre_generado is None


def test_registrar_respuesta_libre_baja_confianza_tambien_cae_en_fallback(db, escenario, monkeypatch):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )
    rama_recuerda = RamaRespuestaLibre(guion_id=guion.id, criterio="Recuerda el viaje")
    rama_fallback = RamaRespuestaLibre(guion_id=guion.id, es_fallback=True)
    db.add_all([rama_recuerda, rama_fallback])
    db.flush()
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)

    monkeypatch.setattr(
        motor, "clasificar_respuesta",
        lambda pregunta, texto, ramas: ResultadoClasificacion(rama_id=rama_recuerda.id, confianza=0.2),
    )
    monkeypatch.setattr(motor, "generar_cierre", lambda anterior, texto, personaje: "Un cierre cualquiera")

    siguiente = motor.registrar_respuesta_libre(db, interaccion, "mmm", ahora=AHORA)

    assert siguiente is None  # la rama fallback no tenía guion_siguiente cargado
    assert interaccion.rama_libre_elegida_id == rama_fallback.id
    assert interaccion.cierre_generado == "Un cierre cualquiera"


def test_registrar_respuesta_libre_sin_fallback_configurado_falla(db, escenario, monkeypatch):
    guion = _nuevo_guion(
        db, escenario["personaje"], escenario["conversacion"], ModoEnvio.automatico, PASADO
    )
    rama_recuerda = RamaRespuestaLibre(guion_id=guion.id, criterio="Recuerda el viaje")
    db.add(rama_recuerda)
    db.flush()
    interaccion = motor._enviar_guion(db, guion, escenario["paciente"].id, AHORA)

    monkeypatch.setattr(
        motor, "clasificar_respuesta",
        lambda pregunta, texto, ramas: ResultadoClasificacion(rama_id=None, confianza=0.0),
    )

    with pytest.raises(ValueError):
        motor.registrar_respuesta_libre(db, interaccion, "no sé", ahora=AHORA)
