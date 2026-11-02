"""Prueba de punta a punta del motor de conversación contra la Postgres real.

No requiere ANTHROPIC_API_KEY: para esta demo se reemplaza el clasificador
por uno determinístico (palabra clave "acuerd" => matchea la rama que
recuerda el viaje), así se puede validar el cableado completo
(Postgres + SQLAlchemy + motor) sin depender de la API externa. La lógica
real del adaptador de IA ya está cubierta por tests/test_motor.py.

Uso: .venv\\Scripts\\python.exe scripts\\demo_motor.py
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_db
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

NOMBRE_FAMILIA_DEMO = "Familia Demo MVP"


def _clasificador_demo(pregunta: str, texto: str, ramas: list[tuple[int, str]]) -> ResultadoClasificacion:
    if "acuerd" in texto.lower() and ramas:
        return ResultadoClasificacion(rama_id=ramas[0][0], confianza=0.95)
    return ResultadoClasificacion(rama_id=None, confianza=0.0)


motor.clasificar_respuesta = _clasificador_demo


def _limpiar_demo_previa(db):
    familia = db.scalar(select(Familia).where(Familia.nombre == NOMBRE_FAMILIA_DEMO))
    if familia:
        db.delete(familia)
        db.flush()


def _seed(db):
    ahora = datetime.now(timezone.utc)
    familia = Familia(nombre=NOMBRE_FAMILIA_DEMO)
    db.add(familia)
    db.flush()

    paciente = Paciente(familia_id=familia.id, nombre="Paciente Demo")
    personaje = Personaje(
        familia_id=familia.id,
        nombre="Carlos",
        relacion_con_paciente="Amigo de la infancia",
        tono_escritura="Informal, cariñoso, usa 'vos'",
    )
    db.add_all([paciente, personaje])
    db.flush()

    conversacion = Conversacion(personaje_id=personaje.id, nombre="Mar del Plata")
    db.add(conversacion)
    db.flush()

    g_terminal_si = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=ahora + timedelta(days=1),
        texto_mensaje="¡Qué lindo! Fue un viaje inolvidable.",
        modo_envio=ModoEnvio.manual,
        estado=EstadoGuion.borrador,
    )
    g_terminal_no = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=ahora + timedelta(days=1),
        texto_mensaje="No hay drama, fue hace tiempo. ¡Nos vemos pronto!",
        modo_envio=ModoEnvio.manual,
        estado=EstadoGuion.borrador,
    )
    db.add_all([g_terminal_si, g_terminal_no])
    db.flush()

    g_quien_manejaba = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=ahora + timedelta(days=1),
        texto_mensaje="¡Qué lindo recuerdo! ¿Te acordás quién manejaba?",
        modo_envio=ModoEnvio.manual,
        estado=EstadoGuion.borrador,
    )
    db.add(g_quien_manejaba)
    db.flush()
    db.add_all([
        RamaRespuestaLibre(guion_id=g_quien_manejaba.id, criterio="El paciente dice que manejaba él",
                            guion_siguiente_id=g_terminal_si.id),
        RamaRespuestaLibre(guion_id=g_quien_manejaba.id, es_fallback=True,
                            guion_siguiente_id=g_terminal_no.id),
    ])

    g_fallback = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=ahora + timedelta(days=1),
        texto_mensaje="¿Te acordás del viaje a Mar del Plata en el Renault?",
        modo_envio=ModoEnvio.manual,
        estado=EstadoGuion.borrador,
    )
    db.add(g_fallback)
    db.flush()
    db.add_all([
        RamaRespuestaLibre(guion_id=g_fallback.id, criterio="El paciente dice que sí se acuerda",
                            guion_siguiente_id=g_quien_manejaba.id),
        RamaRespuestaLibre(guion_id=g_fallback.id, es_fallback=True,
                            guion_siguiente_id=g_terminal_no.id),
    ])

    g_inicial = Guion(
        personaje_id=personaje.id,
        conversacion_id=conversacion.id,
        fecha_programada=ahora - timedelta(minutes=1),  # ya vencido
        texto_mensaje="¡Qué bárbaro que me acordé de aquella vez que fuimos a Mar del Plata!",
        modo_envio=ModoEnvio.automatico,
        estado=EstadoGuion.borrador,
    )
    db.add(g_inicial)
    db.flush()
    db.add_all([
        RamaRespuestaLibre(guion_id=g_inicial.id, criterio="El paciente recuerda el viaje",
                            guion_siguiente_id=g_quien_manejaba.id),
        RamaRespuestaLibre(guion_id=g_inicial.id, es_fallback=True,
                            guion_siguiente_id=g_fallback.id),
    ])

    db.flush()
    return paciente, g_inicial


def main():
    with get_db() as db:
        _limpiar_demo_previa(db)
        paciente, g_inicial = _seed(db)
        print(f"Seed OK — familia demo con paciente #{paciente.id}, guion inicial #{g_inicial.id}\n")

        print("== Paso 1: scheduler procesa guiones vencidos ==")
        procesados = motor.procesar_guiones_vencidos(db, paciente.id)
        for g in procesados:
            print(f"  Guion #{g.id} ({g.modo_envio.value}) -> estado={g.estado.value}: \"{g.texto_mensaje}\"")

        interaccion = db.scalar(select(Interaccion).where(Interaccion.guion_id == g_inicial.id))
        print(f"\n== Paso 2: paciente responde texto libre ==")
        respuesta = "Sí, me acuerdo, fuimos en el Renault de papá"
        print(f'  Paciente: "{respuesta}"')
        siguiente = motor.registrar_respuesta_libre(db, interaccion, respuesta)
        print(f"  Rama elegida -> guion siguiente #{siguiente.id}: \"{siguiente.texto_mensaje}\"")

        print("\n== Paso 3: ese guion se envía y el paciente responde de nuevo con texto libre ==")
        interaccion2 = motor._enviar_guion(db, siguiente, paciente.id, datetime.now(timezone.utc))
        respuesta2 = "Me acuerdo que manejaba yo"
        print(f'  Paciente: "{respuesta2}"')
        siguiente2 = motor.registrar_respuesta_libre(db, interaccion2, respuesta2)
        print(f"  -> guion siguiente #{siguiente2.id}: \"{siguiente2.texto_mensaje}\"")

        print("\nDemo OK — motor funcionando de punta a punta contra Postgres.")


if __name__ == "__main__":
    main()
