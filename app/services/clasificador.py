import json
import logging
import re
from dataclasses import dataclass

from app.services.ia_cliente import generar_texto

logger = logging.getLogger(__name__)


@dataclass
class ResultadoClasificacion:
    rama_id: int | None
    confianza: float


def _armar_prompt(pregunta: str, texto_respuesta: str, ramas: list[tuple[int, str]]) -> str:
    opciones = "\n".join(f"- id {rid}: {criterio}" for rid, criterio in ramas)
    return (
        "Un paciente en un ejercicio de estimulación cognitiva respondió a un mensaje. "
        "Tenés que decidir a cuál de las siguientes ramas de conversación corresponde su "
        "respuesta, interpretándola en relación a lo que se le preguntó (no en abstracto: "
        'una respuesta puede sonar "positiva" y no tener nada que ver con la pregunta).\n\n'
        f'Lo que se le preguntó al paciente:\n"{pregunta}"\n\n'
        f'Respuesta del paciente:\n"{texto_respuesta}"\n\n'
        f"Ramas posibles:\n{opciones}\n\n"
        'Respondé ÚNICAMENTE con un JSON de la forma {"rama_elegida": <id o "ninguna">, '
        '"confianza": <número entre 0 y 1>}, sin texto adicional.'
    )


def _parsear_resultado(raw: str) -> ResultadoClasificacion:
    # Algunos modelos envuelven la respuesta en un bloque ```json ... ``` a
    # pesar de que se les pide "solo el JSON" — buscamos el objeto {...} en
    # vez de asumir que `raw` es JSON puro.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise ValueError(f"No se encontró un JSON en la respuesta del modelo: {raw!r}")
    data = json.loads(match.group(0))
    rama_elegida = data.get("rama_elegida")
    confianza = float(data.get("confianza", 0.0))
    rama_id = int(rama_elegida) if rama_elegida not in (None, "ninguna") else None
    return ResultadoClasificacion(rama_id=rama_id, confianza=confianza)


def clasificar_respuesta(
    pregunta: str, texto_respuesta: str, ramas: list[tuple[int, str]], familia_id: int | None = None
) -> ResultadoClasificacion:
    """Adaptador aislado (SPEC sección 6): dada la pregunta del guion, la
    respuesta del paciente y las ramas disponibles -(id, criterio)- de ESE
    guion puntual, le pide a la IA que elija a cuál corresponde. La pregunta
    es necesaria para interpretar la respuesta correctamente — sin ella, una
    respuesta que no tiene nada que ver con lo preguntado (ej. "hoy viene
    Tommy" respondiendo a "¿Querés que te visite?") se puede clasificar mal
    porque "suena" afirmativa en abstracto. Ante cualquier falla (sin API
    key, error de red, parseo) devuelve "sin match" para que el motor
    dispare el fallback y la conversación nunca quede trabada.
    """
    if not ramas:
        return ResultadoClasificacion(rama_id=None, confianza=0.0)

    prompt = _armar_prompt(pregunta, texto_respuesta, ramas)
    raw = generar_texto(prompt, max_tokens=200, familia_id=familia_id)
    if raw is None:
        return ResultadoClasificacion(rama_id=None, confianza=0.0)

    try:
        return _parsear_resultado(raw)
    except Exception:
        logger.exception("Falló el parseo de la clasificación; se usa fallback.")
        return ResultadoClasificacion(rama_id=None, confianza=0.0)
