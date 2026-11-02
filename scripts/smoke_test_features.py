"""Verifica en proceso (TestClient, sin servidor real) las 4 features nuevas:
edición de personajes, tema/tamaño de letra del paciente, y el endpoint de
estado que usa el polling de sonido."""
import re
import sys

from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app

client = TestClient(app, base_url="http://testserver")

login_superadmin(client)

r = client.get("/admin/familias/2/personajes/3")
assert r.status_code == 200
assert "Editar personaje" in r.text
print("OK: bloque de edición visible en detalle de personaje")

r = client.post(
    "/admin/familias/2/personajes/3/editar",
    data={
        "nombre": "Carlos Editado",
        "foto": "/static/images/aruiz.jpeg",
        "relacion_con_paciente": "Amigo de toda la vida",
        "tono_escritura": "Informal",
    },
    follow_redirects=True,
)
assert r.status_code == 200
assert "Carlos Editado" in r.text, "no se ve el nombre editado"
print("OK: personaje editado correctamente")

r = client.get("/chat/2")
assert "aruiz.jpeg" in r.text or 'src="/static/images/aruiz.jpeg"' in r.text
print("OK: la foto editada aparece en el chat del paciente")

r = client.post(
    "/admin/familias/2/pacientes/2/configuracion",
    data={"tema": "oscuro", "tamano_fuente": "grande"},
    follow_redirects=True,
)
assert r.status_code == 200
print("OK: configuración de tema/tamaño guardada sin error")

r = client.get("/chat/2")
assert 'data-theme="oscuro"' in r.text, "no se aplicó el tema oscuro"
assert 'data-font-size="grande"' in r.text, "no se aplicó el tamaño de letra"
print("OK: tema oscuro y tamaño de letra 'grande' aplicados en el chat")

r = client.get("/chat/2/estado")
assert r.status_code == 200
data = r.json()
assert "ultima_interaccion_id" in data and isinstance(data["ultima_interaccion_id"], int)
print("OK: endpoint de estado responde", data)

r = client.get("/chat/2")
assert 'data-paciente-id="2"' in r.text
assert "notificaciones.js" in r.text
print("OK: script de notificación de sonido incluido en la pantalla de contactos")

r = client.get("/chat/2/3")
assert "notificaciones.js" in r.text
print("OK: script de notificación de sonido incluido en la conversación")

# Volvemos el paciente a tema claro / normal para no dejar la demo en modo oscuro
client.post("/admin/familias/2/pacientes/2/configuracion", data={"tema": "claro", "tamano_fuente": "normal"})

print("\nTODO OK: las 4 features funcionan.")
