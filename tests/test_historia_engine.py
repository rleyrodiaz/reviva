from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.conversacion import Conversacion
from app.models.enums import EstadoHechoFamiliar, EstadoHistoriaSesion, OrigenMensajeHistoria
from app.models.familia import Familia
from app.models.hecho_familiar import HechoFamiliar
from app.models.historia import Historia
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.services import historia_engine

# Cierra la sesión sin proponer ningún hecho de familia nuevo — evita que los
# tests que cierran una sesión disparen sin querer una llamada real a la IA
# a través del extractor (que tiene su propia referencia a generar_texto).
_SIN_HECHOS = patch.object(historia_engine, "extraer_hechos_nuevos", return_value=[])


@pytest.fixture
def escenario(db):
    familia = Familia(nombre="Familia Test")
    db.add(familia)
    db.flush()
    paciente = Paciente(familia_id=familia.id, nombre="Paciente Test")
    personaje = Personaje(
        familia_id=familia.id, nombre="Barti", relacion_con_paciente="Nieto",
        tono_escritura="Cariñoso, informal",
    )
    db.add_all([paciente, personaje])
    db.flush()
    historia = Historia(
        personaje_id=personaje.id, titulo="El viaje al mar", epoca="1985", lugar="Mar del Plata",
        participantes="papá, tío Beto", contenido="Fueron en el Renault celeste.",
        duracion_maxima_minutos=10,
    )
    db.add(historia)
    db.flush()
    return {"familia": familia, "paciente": paciente, "personaje": personaje, "historia": historia}


def test_generar_siguiente_mensaje_sin_ia_devuelve_fallback_de_inicio(escenario):
    with patch.object(historia_engine, "generar_texto", return_value=None):
        texto, cerrar = historia_engine.generar_siguiente_mensaje(escenario["historia"], escenario["personaje"], [])
    assert texto == historia_engine.MENSAJE_FALLBACK_INICIO
    assert cerrar is False


def test_generar_siguiente_mensaje_parsea_json_del_modelo(escenario):
    respuesta = '{"mensaje": "Che, ¿te acordás del viaje?", "cerrar": false}'
    with patch.object(historia_engine, "generar_texto", return_value=respuesta) as mock_generar:
        texto, cerrar = historia_engine.generar_siguiente_mensaje(escenario["historia"], escenario["personaje"], [])
    assert texto == "Che, ¿te acordás del viaje?"
    assert cerrar is False
    prompt_usado = mock_generar.call_args.args[0]
    assert "Renault celeste" in prompt_usado
    assert "no inventes" in prompt_usado.lower()  # la regla de no inventar tiene que estar en el prompt
    assert "Mar del Plata" in prompt_usado
    assert "Cariñoso, informal" in prompt_usado


def test_generar_siguiente_mensaje_respuesta_invalida_cae_en_fallback(escenario):
    with patch.object(historia_engine, "generar_texto", return_value="esto no es json"):
        texto, cerrar = historia_engine.generar_siguiente_mensaje(escenario["historia"], escenario["personaje"], [])
    assert texto == historia_engine.MENSAJE_FALLBACK_INICIO


def test_iniciar_sesion_crea_sesion_y_primer_mensaje(db, escenario):
    with patch.object(
        historia_engine, "generar_texto",
        return_value='{"mensaje": "Che, me acordé del viaje al mar...", "cerrar": false}',
    ):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)

    assert sesion.estado == EstadoHistoriaSesion.activa
    assert len(sesion.mensajes) == 1
    assert sesion.mensajes[0].origen == OrigenMensajeHistoria.personaje
    assert sesion.mensajes[0].texto == "Che, me acordé del viaje al mar..."


def test_registrar_respuesta_agrega_mensajes_y_puede_cerrar(db, escenario):
    with patch.object(historia_engine, "generar_texto", return_value='{"mensaje": "Hola!", "cerrar": false}'):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)

    with _SIN_HECHOS, patch.object(
        historia_engine, "generar_texto",
        return_value='{"mensaje": "Bueno, te dejo, la pasé lindo recordando esto ❤️", "cerrar": true}',
    ) as mock_generar:
        historia_engine.registrar_respuesta(db, sesion, "Sí, fuimos en el auto de tu papá")

    assert len(sesion.mensajes) == 3
    assert sesion.mensajes[1].origen == OrigenMensajeHistoria.paciente
    assert sesion.mensajes[1].texto == "Sí, fuimos en el auto de tu papá"
    assert sesion.mensajes[2].origen == OrigenMensajeHistoria.personaje
    assert sesion.estado == EstadoHistoriaSesion.finalizada
    assert sesion.finalizada_en is not None

    prompt_usado = mock_generar.call_args.args[0]
    assert "PACIENTE: Sí, fuimos en el auto de tu papá" in prompt_usado
    assert "BARTI: Hola!" in prompt_usado


def test_prompt_incluye_hechos_familiares_validados(escenario):
    respuesta = '{"mensaje": "Che, ¿cómo estás?", "cerrar": false}'
    with patch.object(historia_engine, "generar_texto", return_value=respuesta) as mock_generar:
        historia_engine.generar_siguiente_mensaje(
            escenario["historia"], escenario["personaje"], [],
            hechos_familiares=["A Katty le gustan las medialunas de grasa.", "Barti es Contador."],
        )
    prompt_usado = mock_generar.call_args.args[0]
    assert "A Katty le gustan las medialunas de grasa." in prompt_usado
    assert "Barti es Contador." in prompt_usado
    assert "no los menciones si no vienen al caso" in prompt_usado.lower()
    assert "si el paciente muestra que no se acuerda" in prompt_usado.lower()


def test_cerrar_sesion_crea_hechos_familiares_pendientes(db, escenario):
    with patch.object(historia_engine, "generar_texto", return_value='{"mensaje": "Hola!", "cerrar": false}'):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)

    with patch.object(
        historia_engine, "extraer_hechos_nuevos",
        return_value=["A Katty le gustan las medialunas de grasa.", "Barti es Contador."],
    ) as mock_extraer, patch.object(
        historia_engine, "generar_texto",
        return_value='{"mensaje": "Chau, te quiero!", "cerrar": true}',
    ):
        historia_engine.registrar_respuesta(db, sesion, "Che, a Katty le encantan las medialunas de grasa")

    mock_extraer.assert_called_once()
    hechos = db.query(HechoFamiliar).filter_by(familia_id=escenario["familia"].id).all()
    assert {h.texto for h in hechos} == {
        "A Katty le gustan las medialunas de grasa.", "Barti es Contador.",
    }
    assert all(h.estado == EstadoHechoFamiliar.pendiente for h in hechos)
    assert all(h.origen_sesion_id == sesion.id for h in hechos)


def test_cerrar_sesion_sin_hechos_nuevos_no_crea_nada(db, escenario):
    with patch.object(historia_engine, "generar_texto", return_value='{"mensaje": "Hola!", "cerrar": false}'):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)

    with _SIN_HECHOS, patch.object(
        historia_engine, "generar_texto", return_value='{"mensaje": "Chau!", "cerrar": true}',
    ):
        historia_engine.registrar_respuesta(db, sesion, "ok")

    assert db.query(HechoFamiliar).count() == 0


def test_solo_hechos_validados_de_la_misma_familia_se_usan(db, escenario):
    otra_familia = Familia(nombre="Otra Familia")
    db.add(otra_familia)
    db.flush()
    db.add_all([
        HechoFamiliar(familia_id=escenario["familia"].id, texto="Validado propio", estado=EstadoHechoFamiliar.validado),
        HechoFamiliar(familia_id=escenario["familia"].id, texto="Pendiente propio", estado=EstadoHechoFamiliar.pendiente),
        HechoFamiliar(familia_id=escenario["familia"].id, texto="Descartado propio", estado=EstadoHechoFamiliar.descartado),
        HechoFamiliar(familia_id=otra_familia.id, texto="Validado de otra familia", estado=EstadoHechoFamiliar.validado),
    ])
    db.flush()

    hechos = historia_engine._hechos_validados(db, escenario["familia"].id)

    assert hechos == ["Validado propio"]


def test_prompt_informa_minutos_reales_no_solo_cantidad_de_mensajes(escenario):
    respuesta = '{"mensaje": "Che, ¿cómo estás?", "cerrar": false}'
    with patch.object(historia_engine, "generar_texto", return_value=respuesta) as mock_generar:
        historia_engine.generar_siguiente_mensaje(
            escenario["historia"], escenario["personaje"], [], minutos_transcurridos=7,
        )
    prompt_usado = mock_generar.call_args.args[0]
    assert "7 de los 10 minutos" in prompt_usado


def test_registrar_respuesta_fuerza_cierre_al_pasarse_del_tiempo_aunque_la_ia_diga_que_no(db, escenario):
    """El backstop real: si ya se pasó la duración máxima, la sesión se
    cierra sí o sí, aunque el modelo (mockeado acá) devuelva cerrar=false —
    nunca queda a su criterio cuando se acabó el tiempo de verdad."""
    with patch.object(historia_engine, "generar_texto", return_value='{"mensaje": "Hola!", "cerrar": false}'):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)
    # Simula que la sesión arrancó hace más de los 10 minutos configurados.
    sesion.iniciada_en = datetime.now(timezone.utc) - timedelta(minutes=15)
    db.flush()

    with _SIN_HECHOS, patch.object(
        historia_engine, "generar_texto", return_value='{"mensaje": "Todo bien!", "cerrar": false}',
    ) as mock_generar:
        historia_engine.registrar_respuesta(db, sesion, "Todo bien, ¿y vos?")

    prompt_usado = mock_generar.call_args.args[0]
    assert "ÚLTIMO" in prompt_usado
    assert sesion.estado == EstadoHistoriaSesion.finalizada


def test_registrar_respuesta_no_fuerza_cierre_si_todavia_no_paso_el_tiempo(db, escenario):
    with patch.object(historia_engine, "generar_texto", return_value='{"mensaje": "Hola!", "cerrar": false}'):
        sesion = historia_engine.iniciar_sesion(db, escenario["historia"], escenario["paciente"].id)

    with _SIN_HECHOS, patch.object(
        historia_engine, "generar_texto", return_value='{"mensaje": "Todo bien!", "cerrar": false}',
    ):
        historia_engine.registrar_respuesta(db, sesion, "Todo bien, ¿y vos?")

    assert sesion.estado == EstadoHistoriaSesion.activa
