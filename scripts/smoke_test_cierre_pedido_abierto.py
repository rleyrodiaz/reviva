"""Verifica el fix de cierre_guion.py para pedidos abiertos/sin especificar
(ej. "te puedo pedir unas cosas del super?") al final de la charla: la IA no
tiene que prometer nada concreto NI invitar al paciente a listar/detallar qué
necesita (eso sería, de hecho, otra pregunta, violando la regla de cierre).
También confirma que un pedido puntual simple (medialunas) sigue andando
como antes (control positivo).

Uso: python -m scripts.smoke_test_cierre_pedido_abierto
"""
import re

from app.models.personaje import Personaje
from app.services.cierre_guion import generar_cierre

personaje = Personaje(nombre="Ale", tono_escritura="cálido, informal, usa 'vos'")

transcripcion_super = """Mariuchi: ¿Vas a venir a visitarme?
Paciente: Qué bueno, vení con Katty
Mariuchi: Buenísimo, paso a las 4 con Katty. Besos
Paciente: Te puedo pedir unas cosas del super?"""

FRASES_PROHIBIDAS = [
    "decime", "contame", "avisame", "decime qué", "decime cual",
]

print("=== Escenario del bug: pedido abierto (\"unas cosas del super\") ===")
fallas = 0
for i in range(8):
    texto = generar_cierre(transcripcion_super, "Te puedo pedir unas cosas del super?", personaje)
    termina_pregunta = texto.strip().endswith("?")
    pide_detalle = any(f in texto.lower() for f in FRASES_PROHIBIDAS)
    compromete_algo_concreto = bool(re.search(r"\b(traigo|llevo|compro)\b", texto.lower())) and not pide_detalle
    print(f"  [{i+1}] {texto}")
    if termina_pregunta or pide_detalle:
        print("      -> FALLA: termina en pregunta o le pide que especifique/liste qué necesita")
        fallas += 1
print(f"\n{8-fallas}/8 sin pedir detalle ni terminar en pregunta.")

print("\n=== Control positivo: pedido puntual y simple (medialunas) ===")
transcripcion_medialunas = """Mariuchi: ¿Vas a venir a visitarme?
Paciente: Qué bueno, vení con Katty
Mariuchi: Buenísimo, paso a las 4 con Katty. Besos
Paciente: Me traes medialunas?"""

compromisos = 0
for i in range(5):
    texto = generar_cierre(transcripcion_medialunas, "Me traes medialunas?", personaje)
    tiene_medialunas = "medialuna" in texto.lower()
    print(f"  [{i+1}] {texto}")
    if tiene_medialunas:
        compromisos += 1
print(f"\n{compromisos}/5 mencionan medialunas (se espera que casi todas sí, pedido puntual simple).")

print("\nRevisar a mano los casos marcados arriba.")
