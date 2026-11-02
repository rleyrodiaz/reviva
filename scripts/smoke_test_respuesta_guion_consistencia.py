"""Prueba con la IA real (no mockeada) que adaptar_mensaje_guion respeta la
regla nueva: el texto preparado manda sobre qué pasa de ahora en más, y no
hay que reintroducir datos viejos que una rama está cambiando/cancelando a
propósito. Corre cada caso varias veces (la IA no es determinística) y
reporta cuántas veces falló cada chequeo — no hace asserts duros porque un
prompt no garantiza 100%, pero sirve para ver si la tasa de fallas es alta.

Uso: python scripts\\smoke_test_respuesta_guion_consistencia.py
"""
from app.services.respuesta_guion import adaptar_mensaje_guion


class _PersonajeFake:
    def __init__(self, nombre):
        self.nombre = nombre


TOMMY = _PersonajeFake("Tommy")
REPETICIONES = 4


def _correr(nombre_caso, texto_base, transcripcion, chequeos):
    print(f"\n=== {nombre_caso} ===")
    fallas = 0
    for i in range(REPETICIONES):
        resultado = adaptar_mensaje_guion(texto_base, transcripcion, TOMMY)
        ok = True
        for descripcion, condicion in chequeos:
            paso = condicion(resultado)
            if not paso:
                ok = False
                print(f"  [{i + 1}] FALLÓ: {descripcion} -> {resultado!r}")
        if ok:
            print(f"  [{i + 1}] OK: {resultado!r}")
        else:
            fallas += 1
    print(f"  -> {fallas}/{REPETICIONES} fallaron")
    return fallas


total_fallas = 0

# Caso 1 (el bug reportado): una rama "respuesta negativa" cancela una
# visita que ya se había acordado antes en la charla. La IA NO debería
# reintroducir el horario/las medialunas del plan viejo.
total_fallas += _correr(
    "cancela un plan ya establecido",
    texto_base="No te preocupes, mañana te llamo",
    transcripcion=(
        "TOMMY: Buenísimo, paso a las 16 y llevo medialunas\n"
        "TOMMY: Querés que te visite?\n"
        "PACIENTE: no gracias"
    ),
    chequeos=[
        ("no debería mencionar las 16/16hs", lambda r: "16" not in r),
        ("no debería mencionar medialunas", lambda r: "medialuna" not in r.lower()),
    ],
)

# Caso 2 (control positivo): el texto preparado tiene una referencia vaga
# ("ese día") que la charla anterior ya precisó ("hoy"). Esto SÍ tiene que
# seguir funcionando como antes.
total_fallas += _correr(
    "precisa una referencia vaga ya establecida",
    texto_base="Nos vemos ese día, como quedamos",
    transcripcion=(
        "TOMMY: Te parece si nos vemos hoy?\n"
        "PACIENTE: si, hoy esta bien"
    ),
    chequeos=[
        ("debería decir 'hoy' en vez de dejarlo vago", lambda r: "hoy" in r.lower()),
    ],
)

# Caso 3 (control positivo, revisión manual): el paciente trae algo de más
# que el texto preparado no toca (una pregunta puntual que la IA no puede
# saber de verdad) — no hay un chequeo de texto confiable para "no inventó
# un dato", así que solo se imprime para que lo revises a ojo: tiene que
# responder con cariño sin afirmar ni negar si Katty va.
print("\n=== responde algo extra sin inventar datos puntuales (revisión manual) ===")
for i in range(REPETICIONES):
    resultado = adaptar_mensaje_guion(
        texto_base="Dale, te veo entonces",
        transcripcion=(
            "TOMMY: Te parece si nos vemos hoy?\n"
            "PACIENTE: si, pero vas a venir con Katty?"
        ),
        personaje=TOMMY,
    )
    print(f"  [{i + 1}] {resultado!r}")

print(f"\nTOTAL fallas (casos con chequeo automático): {total_fallas} (de {REPETICIONES * 2} corridas)")
