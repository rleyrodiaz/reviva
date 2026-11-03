"""Prueba con la IA real (no mockeada) que generar_siguiente_mensaje solo
marca "cerrar" cuando el mensaje en sí es una despedida real — el bug
reportado fue una sesión que terminó con un comentario cálido de
continuación ("vos viviste esa época hermosa...") marcado como cierre, sin
ninguna despedida. Corre cada caso varias veces (no es determinístico) y
muestra el resultado para revisión — un cierre real debe leerse como tal.

Uso: python -m scripts.smoke_test_historia_cierre
"""
from app.services.historia_engine import generar_siguiente_mensaje
from app.models.enums import OrigenMensajeHistoria

REPETICIONES = 4


class _PersonajeFake:
    nombre = "Alejandro"
    relacion_con_paciente = "hijo"
    tono_escritura = "cálido, cercano"


class _HistoriaFake:
    titulo = "Recuerdos Susana"
    epoca = "fines de los 60 y los 70"
    lugar = "Quinta Once Varas, San Miguel"
    participantes = "Elsie, Mariano, Pérez Celis"
    contenido = (
        "- Se juntaban varios amigos en la quinta de Elsie y Mariano\n"
        "- Iban artistas, intelectuales, periodistas\n"
        "- Se presentaban libros, entre ellos uno de la propia Elsie Rivero\n"
        "- Pérez Celis, el pintor, era parte de ese círculo"
    )
    duracion_maxima_minutos = 10


class _Mensaje:
    def __init__(self, origen, texto):
        self.origen = origen
        self.texto = texto


PERSONAJE = _PersonajeFake()
HISTORIA = _HistoriaFake()

# Transcripción real que disparó el bug: a los ~7 minutos (bajo el tope de
# 10), el paciente todavía está aportando recuerdos con gusto — no hay
# ninguna señal de querer despedirse.
MENSAJES_SIN_SEÑAL_DE_CIERRE = [
    _Mensaje(OrigenMensajeHistoria.personaje, "Hola, ¿cómo estás? Te quería preguntar sobre esos encuentros en la Quinta Once Varas. ¿Te acordás de esa época?"),
    _Mensaje(OrigenMensajeHistoria.paciente, "si"),
    _Mensaje(OrigenMensajeHistoria.personaje, "Qué bueno que te acuerdes. Contame, ¿quiénes eran los que iban a esos encuentros?"),
    _Mensaje(OrigenMensajeHistoria.paciente, "se presentaba libros, nos reuniamos con gente de la cultura, periodistas famosos"),
    _Mensaje(OrigenMensajeHistoria.personaje, "Qué linda época esa, con presentaciones de libros y toda esa gente de la cultura. ¿Recordás algún libro en particular?"),
    _Mensaje(OrigenMensajeHistoria.paciente, "me acuerdo que Elsie Rivero presentó un libro, no me acuerdo el nombre"),
]

# Control: el paciente SÍ da una señal clara de querer terminar — un cierre
# real tiene que seguir funcionando.
MENSAJES_CON_SEÑAL_DE_CIERRE = MENSAJES_SIN_SEÑAL_DE_CIERRE + [
    _Mensaje(OrigenMensajeHistoria.personaje, "Qué bueno tener presentes esos momentos. ¿Te acordás de algo más de esa época?"),
    _Mensaje(OrigenMensajeHistoria.paciente, "no, ya me cansé, dejamos para otro día"),
]


def _parece_despedida(texto: str) -> bool:
    marcas = ["te dejo", "hablamos", "nos vemos", "chau", "cuidate", "cuídate", "otro día", "más adelante", "beso"]
    t = texto.lower()
    return any(m in t for m in marcas)


print("=== Sin señal de cierre (el caso del bug): no debería cerrar, y si cierra, tiene que ser una despedida real ===")
fallas_1 = 0
for i in range(REPETICIONES):
    texto, cerrar = generar_siguiente_mensaje(
        HISTORIA, PERSONAJE, MENSAJES_SIN_SEÑAL_DE_CIERRE, minutos_transcurridos=7.2, forzar_cierre=False,
    )
    problema = cerrar and not _parece_despedida(texto)
    etiqueta = "FALLÓ (cerrar=True pero no suena a despedida)" if problema else "OK"
    if problema:
        fallas_1 += 1
    print(f"  [{i + 1}] cerrar={cerrar} {etiqueta}: {texto!r}")
print(f"  -> {fallas_1}/{REPETICIONES} fallaron")

print("\n=== Con señal de cierre clara ('ya me cansé, dejamos para otro día'): tiene que cerrar con una despedida real ===")
fallas_2 = 0
for i in range(REPETICIONES):
    texto, cerrar = generar_siguiente_mensaje(
        HISTORIA, PERSONAJE, MENSAJES_CON_SEÑAL_DE_CIERRE, minutos_transcurridos=8.0, forzar_cierre=False,
    )
    problema = not cerrar or not _parece_despedida(texto)
    etiqueta = "FALLÓ" if problema else "OK"
    if problema:
        fallas_2 += 1
    print(f"  [{i + 1}] cerrar={cerrar} {etiqueta}: {texto!r}")
print(f"  -> {fallas_2}/{REPETICIONES} fallaron")

print("\n=== Forzado por tiempo (ya se pasaron los 10 minutos): tiene que cerrar sí o sí, con una despedida real ===")
fallas_3 = 0
for i in range(REPETICIONES):
    texto, cerrar = generar_siguiente_mensaje(
        HISTORIA, PERSONAJE, MENSAJES_SIN_SEÑAL_DE_CIERRE, minutos_transcurridos=10.5, forzar_cierre=True,
    )
    problema = not cerrar or not _parece_despedida(texto)
    etiqueta = "FALLÓ" if problema else "OK"
    if problema:
        fallas_3 += 1
    print(f"  [{i + 1}] cerrar={cerrar} {etiqueta}: {texto!r}")
print(f"  -> {fallas_3}/{REPETICIONES} fallaron")

print(f"\nTOTAL fallas: {fallas_1 + fallas_2 + fallas_3} (de {REPETICIONES * 3} corridas)")
