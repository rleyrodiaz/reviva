"""Verifica que la pantalla de Hechos de familia muestre los descartados
(antes desaparecían de la vista) y que 'Reconsiderar' los vuelva a pendiente."""
from fastapi.testclient import TestClient
from scripts._smoke_auth import login_superadmin

from app.main import app
from app.db import get_db
from app.models.hecho_familiar import HechoFamiliar
from app.models.enums import EstadoHechoFamiliar

client = TestClient(app)
login_superadmin(client)

r = client.get("/admin/familias/2/hechos")
assert "Descartados" in r.text
assert "Barti es Contador." in r.text
print("OK: la pantalla muestra la sección Descartados con el hecho descartado")

r = client.post("/admin/familias/2/hechos/2/reconsiderar")
assert r.status_code in (200, 303)

with get_db() as db:
    h = db.get(HechoFamiliar, 2)
    assert h.estado == EstadoHechoFamiliar.pendiente
print("OK: reconsiderar devolvió el hecho a pendiente")

# Dejar todo como estaba
with get_db() as db:
    h = db.get(HechoFamiliar, 2)
    h.estado = EstadoHechoFamiliar.descartado
    db.commit()
print("OK: estado original restaurado")

print("\nTODO OK: los hechos descartados quedan visibles y son reconsiderables.")
