from unittest.mock import patch

from app.services import clasificador


def test_sin_ramas_no_llama_a_nadie():
    resultado = clasificador.clasificar_respuesta("¿Todo bien?", "hola", [])
    assert resultado.rama_id is None
    assert resultado.confianza == 0.0


def test_generar_texto_devuelve_none_cae_en_fallback():
    with patch.object(clasificador, "generar_texto", return_value=None):
        resultado = clasificador.clasificar_respuesta("¿Todo bien?", "hola", [(1, "criterio")])
    assert resultado.rama_id is None
    assert resultado.confianza == 0.0


def test_clasifica_con_match():
    with patch.object(clasificador, "generar_texto", return_value='{"rama_elegida": 5, "confianza": 0.9}'):
        resultado = clasificador.clasificar_respuesta(
            "¿Te acordás del viaje a la playa?", "me acuerdo", [(5, "recuerda el viaje")]
        )
    assert resultado.rama_id == 5
    assert resultado.confianza == 0.9


def test_json_envuelto_en_markdown_se_parsea_igual():
    # Algunos modelos devuelven ```json\n{...}\n``` a pesar de pedirles "solo
    # el JSON" (pasó de verdad probando contra la API real de Anthropic).
    with patch.object(
        clasificador, "generar_texto",
        return_value='```json\n{"rama_elegida": 7, "confianza": 0.8}\n```',
    ):
        resultado = clasificador.clasificar_respuesta("¿Todo bien?", "hola", [(7, "criterio")])
    assert resultado.rama_id == 7
    assert resultado.confianza == 0.8


def test_ninguna_cae_en_fallback():
    with patch.object(clasificador, "generar_texto", return_value='{"rama_elegida": "ninguna", "confianza": 0.1}'):
        resultado = clasificador.clasificar_respuesta("¿Te acordás del viaje?", "no sé", [(1, "criterio")])
    assert resultado.rama_id is None
    assert resultado.confianza == 0.1


def test_respuesta_sin_json_valido_cae_en_fallback():
    with patch.object(clasificador, "generar_texto", return_value="esto no es json"):
        resultado = clasificador.clasificar_respuesta("¿Todo bien?", "hola", [(1, "criterio")])
    assert resultado.rama_id is None
    assert resultado.confianza == 0.0
