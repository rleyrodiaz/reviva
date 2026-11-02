from app.models.personaje import Personaje
from app.services.ia_cliente import generar_texto


def _armar_prompt(texto_base: str, transcripcion: str, personaje: Personaje) -> str:
    return f"""Estás actuando como {personaje.nombre}, charlando por chat con un paciente mayor con dificultades de memoria, en un ejercicio de estimulación cognitiva.

Esto es toda la charla hasta ahora (incluye la última respuesta del paciente):
{transcripcion}

Ya tenías preparada esta respuesta para seguir la charla después de esa última respuesta del paciente:
"{texto_base}"

Tu tarea es devolver el mensaje final que le vas a mandar al paciente:
- Tiene que incluir, sin cambiarle el sentido, todo lo que dice la respuesta preparada.
- La respuesta preparada es la única fuente de verdad sobre qué pasa de ahora en más. Si menciona algo de forma vaga (ej. "ese día", "en un rato") y en algún punto anterior de la charla ya había quedado precisado (ej. que el día es "hoy"), usá el dato preciso en vez del vago. Pero NUNCA agregues un compromiso, horario, nombre o detalle concreto que la respuesta preparada no menciona ella misma, aunque haya aparecido antes en la charla. Si la respuesta preparada cambia o cancela algo de lo hablado antes (una visita que ya no se hace, un plan que cambió), es así a propósito — no reviertas eso reintroduciendo el dato viejo.
- Si en la última respuesta del paciente hay algo más (una pregunta, un pedido, un comentario) que la respuesta preparada no toca, agregale una respuesta breve y natural a eso, en tu personaje — sin inventar datos que no tenés (si pregunta algo puntual que no podés saber de verdad, no lo inventes: respondé con cariño sin comprometerte a algo específico, pero sin contradecir ni poner en duda lo que ya está establecido en la charla).
- Si la respuesta preparada ya cubre todo lo que dijo el paciente, devolvé ese mismo mensaje preparado, tal cual, sin agregarle nada de más.
- Un solo mensaje corto y natural, como en un chat de verdad, en primera persona, con tu tono habitual.

Respondé ÚNICAMENTE con el mensaje final para el paciente, sin comillas ni texto adicional."""


def adaptar_mensaje_guion(texto_base: str, transcripcion: str, personaje: Personaje) -> str:
    """El contenido de un guion (texto_base) es fijo, lo escribió el admin a
    mano — pero la respuesta libre del paciente que lo disparó puede traer
    algo más que esa respuesta preparada no contempla (ej. "¿vas con Katty?"
    sobre un mensaje pensado solo para confirmar un horario). Antes de
    mandarla, le pedimos a la IA que la complete con eso, sin tocar el
    contenido ya escrito a mano. Se le pasa toda la charla hasta ahora (no
    solo el último mensaje) para que pueda precisar algo vago que el texto
    preparado ya menciona (ej. que el plan es "hoy") — pero el texto
    preparado manda sobre qué pasa de ahora en más: si una rama cambia o
    cancela algo acordado antes, la IA no tiene que reintroducir ese dato
    viejo (ver respuesta_guion._armar_prompt). Ante cualquier falla (sin API
    key, error de red, parseo) se manda el texto preparado tal cual — nunca
    se bloquea el envío por esto."""
    texto = generar_texto(_armar_prompt(texto_base, transcripcion, personaje), max_tokens=250)
    if texto is None:
        return texto_base
    texto = texto.strip().strip('"')
    return texto or texto_base
