"""Verifica en proceso el mapa de conversación interactivo — que ahora
reemplaza del todo a la vieja lista de tarjetas "Guiones": crear un guion
desde el modal con la posición del click ya cargada (solo pide texto y tipo
de respuesta — fecha y modo quedan del lado del panel de la conversación),
guardar posición/ancho (arrastrar/agrandar), editar texto rápido (tipear),
conectar dos guiones (a un destino existente o a "fin"), reapuntar el
fallback de un guion libre (a un destino o a "sin destino") sin crear una
rama nueva, duplicar, reabrir, y borrar nodos/conexiones — todo desde las
mismas rutas que usa el mapa."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models.conversacion import Conversacion
from app.models.enums import EstadoGuion
from app.models.guion import Guion
from app.models.opcion_respuesta import OpcionRespuesta
from app.models.rama_respuesta_libre import RamaRespuestaLibre

client = TestClient(app)
login_superadmin(client)

PERSONAJE_URL = "/admin/familias/2/personajes/3"


def ultimo_guion_id(conversacion_id):
    with get_db() as db:
        return db.scalar(
            select(Guion.id).where(Guion.conversacion_id == conversacion_id).order_by(Guion.id.desc())
        )


r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación InteractivaTest"})
conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
CONV_URL = f"{PERSONAJE_URL}/conversaciones/{conv_id}"

# 1) Crear un guion tipo "opciones" desde el modal (como si el doble click en
# el mapa lo hubiera abierto con pos_x/pos_y cargados) — se vuelve la entrada
# automáticamente, y después el panel de la conversación le pone el modo
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "texto_mensaje": "¿Querés que te cuente una novedad?",
        "tipo_respuesta": "opciones",
        "nodo_padre_id": "",
        "pos_x": "40",
        "pos_y": "60",
    },
)
assert r.status_code == 200, r.text
guion1_id = ultimo_guion_id(conv_id)
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.pos_x == 40 and g1.pos_y == 60
    assert g1.tipo_respuesta.value == "opciones" and g1.es_entrada is True
print("OK: el guion se crea con posición y tipo de respuesta elegidos; se vuelve la entrada solo")

r = client.post(f"{CONV_URL}/configuracion", data={"fecha_programada": "2099-01-01T10:00", "modo_envio": "automatico"})
assert r.status_code in (200, 303), r.text
with get_db() as db:
    assert db.get(Guion, guion1_id).modo_envio.value == "automatico"
print("OK: el panel de la conversación le pone fecha y modo al guion de entrada")

# 2) Editar texto rápido (tipear sobre el nodo)
r = client.post(f"{CONV_URL}/guiones/{guion1_id}/texto-rapido", data={"texto": "Hola, ¿cómo estás?"})
assert r.status_code == 200
assert r.json()["texto"] == "Hola, ¿cómo estás?"
with get_db() as db:
    assert db.get(Guion, guion1_id).texto_mensaje == "Hola, ¿cómo estás?"
print("OK: editar texto rápido actualiza el mensaje sin pasar por el formulario completo")

r = client.post(f"{CONV_URL}/guiones/{guion1_id}/texto-rapido", data={"texto": "   "})
assert r.status_code == 400
print("OK: texto vacío rechazado con 400")

# 3) Guardar posición (arrastrar) y ancho (agrandar)
r = client.post(f"{CONV_URL}/guiones/{guion1_id}/posicion", data={"pos_x": "200", "pos_y": "150", "ancho": "260"})
assert r.status_code == 200
with get_db() as db:
    g1 = db.get(Guion, guion1_id)
    assert g1.pos_x == 200 and g1.pos_y == 150 and g1.ancho == 260
print("OK: mover y agrandar persiste pos_x/pos_y/ancho")

# 4) Crear un segundo guion (tipo libre) y conectar el primero (opciones) con él
r = client.post(
    f"{CONV_URL}/guiones",
    data={
        "texto_mensaje": "Guion destino",
        "tipo_respuesta": "libre",
        "nodo_padre_id": "",
        "pos_x": "200", "pos_y": "300",
    },
)
assert r.status_code == 200, r.text
guion2_id = ultimo_guion_id(conv_id)

r = client.post(
    f"{CONV_URL}/guiones/{guion1_id}/conectar",
    data={"destino_id": str(guion2_id), "etiqueta": "Sí, contame"},
)
assert r.status_code == 200, r.text
arista = r.json()["arista"]
assert arista["origen"] == guion1_id and arista["destino"] == guion2_id
assert arista["etiqueta"] == "Sí, contame" and arista["fallback"] is False
assert arista["tipo"] == "opcion" and isinstance(arista["id"], int)
opcion_id = arista["id"]
with get_db() as db:
    opciones = db.query(OpcionRespuesta).filter_by(guion_id=guion1_id).all()
    assert len(opciones) == 1
    assert opciones[0].texto_opcion == "Sí, contame"
    assert opciones[0].guion_siguiente_id == guion2_id
print("OK: conectar arrastrando crea la opción (tipo opciones) apuntando al destino")

# 5) Conectar sin destino (soltar en un espacio vacío, confirmado del lado
# del cliente) crea un camino que termina en "fin" — ya no hace falta la
# vieja tarjeta para esto.
r = client.post(
    f"{CONV_URL}/guiones/{guion1_id}/conectar",
    data={"destino_id": "", "etiqueta": "No, gracias"},
)
assert r.status_code == 200, r.text
assert r.json()["arista"]["destino"] is None
with get_db() as db:
    opciones = db.query(OpcionRespuesta).filter_by(guion_id=guion1_id, texto_opcion="No, gracias").all()
    assert len(opciones) == 1 and opciones[0].guion_siguiente_id is None
print("OK: soltar en un espacio vacío (con confirmación) crea un camino que termina en 'fin'")

# 6) Fallback de un guion libre: conectar con etiqueta vacía reapunta el
# fallback existente en vez de crear una rama nueva — a un destino real...
r = client.post(
    f"{CONV_URL}/guiones/{guion2_id}/conectar",
    data={"destino_id": str(guion1_id), "etiqueta": ""},
)
assert r.status_code == 200, r.text
arista_fb = r.json()["arista"]
assert arista_fb["fallback"] is True and arista_fb["destino"] == guion1_id
with get_db() as db:
    ramas = db.query(RamaRespuestaLibre).filter_by(guion_id=guion2_id).all()
    assert len(ramas) == 1, "no debería haber creado una rama nueva, solo reapuntar el fallback"
    assert ramas[0].es_fallback and ramas[0].guion_siguiente_id == guion1_id
print("OK: conectar con etiqueta vacía reapunta el fallback a un destino real, sin crear una rama nueva")

# ...y a "sin destino" si también se suelta en el vacío
r = client.post(
    f"{CONV_URL}/guiones/{guion2_id}/conectar",
    data={"destino_id": "", "etiqueta": ""},
)
assert r.status_code == 200, r.text
assert r.json()["arista"]["destino"] is None and r.json()["arista"]["fallback"] is True
with get_db() as db:
    ramas = db.query(RamaRespuestaLibre).filter_by(guion_id=guion2_id).all()
    assert len(ramas) == 1 and ramas[0].guion_siguiente_id is None
print("OK: conectar sin destino ni etiqueta deja el fallback 'sin destino'")

# Conectar a un guion de OTRA conversación debe rechazarse
r = client.post(f"{PERSONAJE_URL}/conversaciones", data={"nombre": "Conversación InteractivaTest Otra"})
otra_conv_id = int(str(r.url).rstrip("/").rsplit("/", 1)[-1])
r = client.post(
    f"{PERSONAJE_URL}/conversaciones/{otra_conv_id}/guiones",
    data={"texto_mensaje": "Otra conversación", "tipo_respuesta": "libre", "nodo_padre_id": ""},
)
assert r.status_code == 200, r.text
guion_otra_id = ultimo_guion_id(otra_conv_id)
r = client.post(
    f"{CONV_URL}/guiones/{guion1_id}/conectar",
    data={"destino_id": str(guion_otra_id), "etiqueta": "cruzado"},
)
assert r.status_code == 400
print("OK: no se puede conectar a un guion de otra conversación")

# El mapa de la página ya trae pos_x/pos_y/ancho guardados, y cada arista con su id/tipo
r = client.get(CONV_URL)
assert '"pos_x": 200' in r.text or '"pos_x":200' in r.text
assert '"tipo": "opcion"' in r.text or '"tipo":"opcion"' in r.text
print("OK: la página renderiza con las posiciones y el id/tipo de cada arista")

# 7) Duplicar un guion (menú "⋮" del mapa) crea una copia independiente
r = client.post(f"{CONV_URL}/guiones/{guion2_id}/duplicar")
assert r.status_code in (200, 303)
with get_db() as db:
    copias = db.query(Guion).filter_by(conversacion_id=conv_id, texto_mensaje="Guion destino").all()
    assert len(copias) == 2, "debería haber quedado el original más la copia"
    copia_id = next(g.id for g in copias if g.id != guion2_id)
    assert db.get(Guion, copia_id).tipo_respuesta == db.get(Guion, guion2_id).tipo_respuesta
print("OK: duplicar un guion desde el mapa crea una copia independiente")

# 8) Reabrir un guion ya enviado (menú "⋮" del mapa) lo vuelve a borrador
with get_db() as db:
    db.get(Guion, guion2_id).estado = EstadoGuion.enviado
    db.commit()
r = client.post(f"{CONV_URL}/guiones/{guion2_id}/reabrir", data={"fecha_programada": "2030-01-01T08:00"})
assert r.status_code in (200, 303)
with get_db() as db:
    g2 = db.get(Guion, guion2_id)
    assert g2.estado == EstadoGuion.borrador
    assert g2.fecha_programada.isoformat().startswith("2030-01-01")
print("OK: reabrir un guion ya enviado desde el mapa lo vuelve a borrador con la nueva fecha")

# 9) Borrar la conexión (click sobre la flecha en el mapa)
r = client.post(f"{CONV_URL}/guiones/{guion1_id}/opciones/{opcion_id}/borrar")
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(OpcionRespuesta, opcion_id) is None
print("OK: borrar la conexión desde el mapa la elimina")

# 10) Borrar un nodo (menú "⋮" del mapa)
r = client.post(f"{CONV_URL}/guiones/{guion2_id}/borrar")
assert r.status_code in (200, 303)
with get_db() as db:
    assert db.get(Guion, guion2_id) is None
    assert db.get(Guion, guion1_id) is not None, "borrar un guion no debería borrar otros"
print("OK: borrar un nodo desde el mapa funciona igual que antes")

# Limpieza
client.post(f"{PERSONAJE_URL}/conversaciones/{conv_id}/borrar")
client.post(f"{PERSONAJE_URL}/conversaciones/{otra_conv_id}/borrar")
with get_db() as db:
    assert db.get(Conversacion, conv_id) is None
print("OK: datos de prueba borrados")

print("\nTODO OK: el mapa reemplaza del todo a la vieja lista de tarjetas — crear/mover/agrandar/tipear/"
      "conectar(incluido fin y fallback)/duplicar/reabrir/borrar funcionan de punta a punta.")
