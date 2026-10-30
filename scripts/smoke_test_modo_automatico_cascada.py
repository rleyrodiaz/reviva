"""Verifica en proceso que el modo de envío solo aplica al guion de
entrada, y que la fecha solo participa en automático:
- automático: la fecha decide el momento exacto del envío (vía scheduler).
- manual: la fecha no participa de nada — guardar con modo manual manda
  derecho a la bandeja de aprobación, sin esperar a que pase ninguna fecha
  ni depender del scheduler.
Una vez que la conversación arrancó, el resto de la cadena fluye sola, sin
pasar de nuevo por la bandeja — sin importar qué modo tenga guardado cada
guion ni el modo del guion de entrada."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models.conversacion import Conversacion
from app.models.enums import EstadoGuion
from app.models.guion import Guion
from app.services.motor import procesar_guiones_vencidos

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"

r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación ModoAutomaticoTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"
assert r.status_code == 200, "crear la conversación debería dejarte ya parado en su propio mapa"
print("OK: crear la conversación (solo con el nombre) te lleva directo a su mapa")


def crear(texto, tipo):
    r = client.post(
        f"{CONV_URL}/guiones",
        data={"texto_mensaje": texto, "tipo_respuesta": tipo, "nodo_padre_id": ""},
    )
    assert r.status_code == 200, r.text
    with get_db() as db:
        return db.scalar(
            select(Guion.id).where(Guion.conversacion_id == conv_id).order_by(Guion.id.desc())
        )


def configurar(fecha, modo, reabrir=False):
    data = {"fecha_programada": fecha, "modo_envio": modo}
    if reabrir:
        data["reabrir"] = "true"
    return client.post(f"{CONV_URL}/configuracion", data=data)


AHORA = datetime.now(timezone.utc)
PASADO = AHORA - timedelta(minutes=5)
FUTURO_ISO = "2099-06-01T09:00"

# 1) El primer guion creado se vuelve de entrada solo, sin pedir fecha/modo
guion1_id = crear("Entrada", "opciones")
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.es_entrada is True
    assert g1.modo_envio.value == "manual"
    assert g1.fecha_programada.year == 2099, "sin configurar todavía, la fecha queda 'sin programar'"
print("OK: el primer guion creado es la entrada, sin que se haya pedido fecha ni modo")

# 2) Un guion nuevo que no es de entrada NO hereda el modo del de entrada:
# siempre queda automático, porque una vez que la conversación arranca el
# resto de la cadena tiene que fluir sola.
guion2_id = crear("Guion intermedio", "libre")
with get_db() as db:
    assert db.get(Guion, guion2_id).es_entrada is False
    assert db.get(Guion, guion2_id).modo_envio.value == "automatico"
print("OK: un guion nuevo no-entrada siempre se crea automático, no hereda nada del de entrada")

# 3) Automático con fecha futura: fija fecha/modo, no manda nada todavía.
r = configurar(FUTURO_ISO, "automatico")
assert r.status_code in (200, 303), r.text
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.fecha_programada.isoformat().startswith("2099-06-01")
    assert g1.modo_envio.value == "automatico"
    assert g1.estado == EstadoGuion.borrador
    assert db.get(Guion, guion2_id).modo_envio.value == "automatico", \
        "el modo del guion de entrada no debería tocar a los demás"
print("OK: automático con fecha futura solo guarda los datos, no manda nada todavía")

# 4) Manual: guardar manda derecho a la bandeja, la fecha no importa.
r = configurar(FUTURO_ISO, "manual")
assert r.status_code in (200, 303), r.text
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.modo_envio.value == "manual"
    assert g1.estado == EstadoGuion.pendiente_aprobacion, \
        "guardar en manual debería mandar derecho a la bandeja, sin esperar el scheduler ni la fecha"
print("OK: guardar en manual manda derecho a la bandeja aunque la fecha sea futura")

# El scheduler no toca un guion de entrada manual (ya sea en borrador o
# pendiente_aprobacion): pasar a la bandeja es una acción explícita, no algo
# que la fecha decida.
with get_db() as db:
    procesar_guiones_vencidos(db, paciente_id=2, ahora=AHORA)
    db.commit()
    assert db.get(Guion, guion1_id).estado == EstadoGuion.pendiente_aprobacion
print("OK: el scheduler no mueve al guion de entrada manual")

# 5) Una vez que la conversación arrancó, un guion no-entrada vencido fluye
# solo, sin pasar por la bandeja — aunque el de entrada sea manual.
with get_db() as db:
    db.get(Guion, guion2_id).fecha_programada = PASADO
    db.commit()
    procesar_guiones_vencidos(db, paciente_id=2, ahora=AHORA)
    db.commit()
    assert db.get(Guion, guion2_id).estado == EstadoGuion.enviado, \
        "un guion que no es de entrada no debería pasar por la bandeja, sin importar el modo de la conversación"
print("OK: un guion no-entrada vencido se manda solo, sin pedir aprobación de nuevo")

# 6) Automático: "Guardar" (sin reabrir) no toca el estado de un guion ya
# enviado; "Reabrir" sí lo vuelve a borrador.
r = configurar(FUTURO_ISO, "automatico")
assert r.status_code in (200, 303)
with get_db() as db:
    db.get(Guion, guion1_id).estado = EstadoGuion.enviado
    db.commit()
r = configurar("2030-01-01T09:00", "automatico")
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(Guion, guion1_id).estado == EstadoGuion.enviado
    assert db.get(Guion, guion1_id).fecha_programada.isoformat().startswith("2030-01-01")
print("OK: en automático, 'Guardar' actualiza la fecha pero no reabre un guion ya enviado")

r = configurar("2030-02-02T09:00", "automatico", reabrir=True)
assert r.status_code in (200, 303)
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.estado == EstadoGuion.borrador
    assert g1.fecha_programada.isoformat().startswith("2030-02-02")
print("OK: en automático, 'Reabrir' sí vuelve el guion de entrada a borrador")

# 7) Manual: guardar (sin tocar "reabrir") manda a la bandeja aunque ya
# estuviera "enviado" — en manual, guardar y reabrir son lo mismo.
with get_db() as db:
    db.get(Guion, guion1_id).estado = EstadoGuion.enviado
    db.commit()
r = configurar("2030-03-03T09:00", "manual")
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(Guion, guion1_id).estado == EstadoGuion.pendiente_aprobacion
print("OK: en manual, 'Guardar' solo ya manda a la bandeja aunque el guion ya se hubiera enviado antes")

# Limpieza
client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
with get_db() as db:
    assert db.get(Conversacion, conv_id) is None
print("OK: datos de prueba borrados")

print("\nTODO OK: la fecha solo participa en automático; en manual, guardar manda derecho a la bandeja.")
