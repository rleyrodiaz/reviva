from unittest.mock import patch

from app.models.enums import OrigenMensajeHistoria
from app.services import extractor_hechos


class _MensajeFalso:
    def __init__(self, origen, texto):
        self.origen = origen
        self.texto = texto


class _PersonajeFalso:
    familia_id = 1


class _HistoriaFalsa:
    titulo = "El viaje al mar"
    contenido = "Fueron en el Renault celeste."
    personaje = _PersonajeFalso()


def test_sin_mensajes_de_paciente_no_llama_a_la_ia():
    with patch.object(extractor_hechos, "generar_texto") as mock_generar:
        hechos = extractor_hechos.extraer_hechos_nuevos(
            _HistoriaFalsa(), [_MensajeFalso(OrigenMensajeHistoria.personaje, "Hola!")]
        )
    mock_generar.assert_not_called()
    assert hechos == []


def test_extrae_hechos_del_json_devuelto():
    mensajes = [
        _MensajeFalso(OrigenMensajeHistoria.personaje, "Che, ¿te acordás del viaje?"),
        _MensajeFalso(OrigenMensajeHistoria.paciente, "Sí, y a Katty le encantan las medialunas de grasa"),
    ]
    respuesta = '{"hechos": ["A Katty le gustan las medialunas de grasa."]}'
    with patch.object(extractor_hechos, "generar_texto", return_value=respuesta) as mock_generar:
        hechos = extractor_hechos.extraer_hechos_nuevos(_HistoriaFalsa(), mensajes)
    assert hechos == ["A Katty le gustan las medialunas de grasa."]
    prompt_usado = mock_generar.call_args.args[0]
    assert "Sí, y a Katty le encantan las medialunas de grasa" in prompt_usado
    assert "Che, ¿te acordás del viaje?" not in prompt_usado  # nunca lo dicho por el personaje


def test_lista_vacia_si_la_ia_no_encuentra_nada():
    mensajes = [_MensajeFalso(OrigenMensajeHistoria.paciente, "no me acuerdo de nada")]
    with patch.object(extractor_hechos, "generar_texto", return_value='{"hechos": []}'):
        hechos = extractor_hechos.extraer_hechos_nuevos(_HistoriaFalsa(), mensajes)
    assert hechos == []


def test_sin_ia_devuelve_lista_vacia():
    mensajes = [_MensajeFalso(OrigenMensajeHistoria.paciente, "algo")]
    with patch.object(extractor_hechos, "generar_texto", return_value=None):
        hechos = extractor_hechos.extraer_hechos_nuevos(_HistoriaFalsa(), mensajes)
    assert hechos == []


def test_respuesta_invalida_devuelve_lista_vacia():
    mensajes = [_MensajeFalso(OrigenMensajeHistoria.paciente, "algo")]
    with patch.object(extractor_hechos, "generar_texto", return_value="esto no es json"):
        hechos = extractor_hechos.extraer_hechos_nuevos(_HistoriaFalsa(), mensajes)
    assert hechos == []
