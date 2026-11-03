"""Prueba con la IA real (no mockeada) el bug reportado: un cierre generado
por cierre_guion.py repitió un dato correcto ("a la tarde") pero con un tono
de reproche ("como te dije") — inaceptable para un paciente con problemas de
memoria. Corre varias veces (no es determinístico) y chequea que nunca
aparezcan frases de corrección, y que el dato correcto siga ahí.

Uso: python -m scripts.smoke_test_cierre_tono
"""
from app.services.cierre_guion import generar_cierre
from app.services.respuesta_guion import adaptar_mensaje_guion

REPETICIONES = 5
FRASES_PROHIBIDAS = [
    "como te dije", "como ya te dije", "ya te lo dije", "ya te había dicho",
    "ya te lo había dicho", "te lo dije antes", "te lo había dicho antes",
    "no te acordás", "no te acordas", "acordate que", "ya te conté",
]


class _PersonajeFake:
    nombre = "Mamá"


def _tiene_frase_prohibida(texto):
    t = texto.lower()
    return next((f for f in FRASES_PROHIBIDAS if f in t), None)


print("=== cierre_guion.generar_cierre: repite un dato ya dicho sin retar (el bug real) ===")
transcripcion = (
    "MAMÁ: Hoy te quería avisar que te voy a visitar a la tarde.\n"
    "PACIENTE: que bueno, me encanta\n"
    "MAMÁ: Perfecto, llevo pepas y medialunas. Nos vemos a la tarde, Mamá."
)
fallas = 0
for i in range(REPETICIONES):
    texto = generar_cierre(transcripcion, "a que hora venis", _PersonajeFake())
    prohibida = _tiene_frase_prohibida(texto)
    tiene_dato = "tarde" in texto.lower()
    problema = bool(prohibida) or not tiene_dato
    if problema:
        fallas += 1
    detalle = f"FALLÓ (frase prohibida: {prohibida!r})" if prohibida else ("FALLÓ (no repite 'a la tarde')" if not tiene_dato else "OK")
    print(f"  [{i + 1}] {detalle}: {texto!r}")
print(f"  -> {fallas}/{REPETICIONES} fallaron")

print("\n=== respuesta_guion.adaptar_mensaje_guion: mismo chequeo, otro camino de código ===")
fallas2 = 0
for i in range(REPETICIONES):
    texto = adaptar_mensaje_guion(
        "Nos vemos a la tarde entonces",
        transcripcion + "\nPACIENTE: a que hora venis",
        _PersonajeFake(),
    )
    prohibida = _tiene_frase_prohibida(texto)
    if prohibida:
        fallas2 += 1
    detalle = f"FALLÓ (frase prohibida: {prohibida!r})" if prohibida else "OK"
    print(f"  [{i + 1}] {detalle}: {texto!r}")
print(f"  -> {fallas2}/{REPETICIONES} fallaron")

print(f"\nTOTAL fallas: {fallas + fallas2} (de {REPETICIONES * 2} corridas)")
