from app.models.personaje import Personaje
from app.services.ia_cliente import generar_texto

MENSAJE_FALLBACK = "Dale, después seguimos hablando ❤️"


def _armar_prompt(transcripcion: str, texto_respuesta: str, personaje: Personaje) -> str:
    return f"""Estás actuando como {personaje.nombre}, respondiéndole por chat a un paciente mayor con dificultades de memoria, en un ejercicio de estimulación cognitiva.

Esto es toda la charla hasta ahora:
{transcripcion}

Y esto es lo que el paciente te contestó por último, sin que haya ningún guion preparado para esta respuesta puntual:
"{texto_respuesta}"

Tenés que contestarle algo breve y cálido, en tu personaje, y dejar en claro que la charla se cierra ahí por ahora (una despedida natural, no la dejes a mitad de una pregunta).

Reglas:
- No termines con una pregunta ni le pidas nada al paciente (ni confirmación, ni que te cuente más) — es un cierre, no tiene que generar otra respuesta. Terminá con una afirmación o un saludo.
- No contradigas ni vuelvas ambiguo ningún dato que ya haya quedado establecido en cualquier punto de la charla (horarios, días, nombres, compromisos, etc.) — revisá toda la charla, no solo el último mensaje.
- Si tenés que repetirle algo que ya se había dicho antes (porque pregunta de nuevo, o parece no acordarse), contestale con la misma calidez que si fuera la primera vez — NUNCA le hagas notar que ya lo sabía o que ya te lo había preguntado (nada de "como te dije", "ya te lo había dicho", "te lo dije antes", "¿no te acordás?" o cualquier frase que suene a corrección o reproche). Es una persona con problemas de memoria: preguntar de nuevo es normal, y señalarlo —por más suave que suene— es maltratarla.
- No te comprometas con algo específico que no podrías saber o cumplir de verdad (por ejemplo, si pide algo puntual como un medicamento concreto, no digas qué le vas a traer ni cuándo — simplemente reconocé lo que dijo con cariño, sin prometer nada concreto al respecto).
- Si lo que pidió es algo simple y concreto que tiene sentido prometer (por ejemplo, traerle algo simple como medialunas), sí podés comprometerte, pero sin contradecir lo que ya se dijo antes en la charla (si ya se dio un momento o un plan — "a la tarde", "mañana", etc. —, mantenelo; no inventes que lo harías "ahora mismo" si no es así).
- Un solo mensaje corto, como en un chat de verdad, en primera persona.
- Lenguaje cálido y respetuoso, sin jerga moderna ni muletillas juveniles (nada de "ey", "posta", "chabón", "capo" y similares).

Respondé ÚNICAMENTE con el mensaje para el paciente, sin comillas ni texto adicional."""


def generar_cierre(transcripcion: str, texto_respuesta: str, personaje: Personaje) -> str:
    """Cuando una respuesta libre no matchea ninguna rama con nombre Y el
    fallback no tiene un destino armado a mano, no hay nada escrito para
    seguir — en vez de dejar al paciente sin ninguna contestación, le
    pedimos a la IA un cierre breve y en personaje, grounded en toda la
    charla hasta ahora (no solo el último mensaje, para no contradecir nada
    dicho antes, ej. inventar "ahora mismo" cuando ya se había dicho "a la
    tarde"). Ante cualquier falla (sin API key, error de red, parseo)
    devuelve un cierre neutro genérico, nunca deja al paciente sin
    respuesta."""
    texto = generar_texto(_armar_prompt(transcripcion, texto_respuesta, personaje), max_tokens=200)
    if texto is None:
        return MENSAJE_FALLBACK
    texto = texto.strip().strip('"')
    return texto or MENSAJE_FALLBACK
