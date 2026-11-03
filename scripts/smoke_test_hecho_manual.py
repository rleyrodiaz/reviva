"""Verifica el alta manual de un hecho de familia (admin-only, entra directo
a validado con quien lo cargó). Usa la familia MVP real; limpia lo que crea.

Uso: python -m scripts.smoke_test_hecho_manual
"""
from scripts._smoke_auth import login_superadmin
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.enums import EstadoHechoFamiliar
from app.models.hecho_familiar import HechoFamiliar
from app.models.usuario import Usuario
from sqlalchemy import select

client = TestClient(app)
user = login_superadmin(client)

with get_db() as db:
    superadmin = db.scalar(select(Usuario).where(Usuario.es_superadmin == True))
    FAMILIA_ID = db.scalar(
        select(HechoFamiliar.familia_id).limit(1)
    ) or 2

r = client.post(
    f"/admin/familias/{FAMILIA_ID}/hechos",
    data={"texto": "  Le encantaba jugar al truco con los nietos  "},
    follow_redirects=True,
)
assert r.status_code == 200, r.status_code
assert r.url.path.endswith("/hechos") and "tab=validados" in str(r.url), str(r.url)
assert "Le encantaba jugar al truco con los nietos" in r.text
assert "Manual, cargado por" in r.text
print("OK: hecho manual creado, queda en la tab Validados (?tab=validados), con quién lo cargó")

with get_db() as db:
    hecho = db.scalar(
        select(HechoFamiliar).where(
            HechoFamiliar.familia_id == FAMILIA_ID,
            HechoFamiliar.texto == "Le encantaba jugar al truco con los nietos",
        )
    )
    assert hecho is not None
    assert hecho.estado == EstadoHechoFamiliar.validado
    assert hecho.origen_sesion_id is None
    assert hecho.creado_por_id is not None
    hecho_id = hecho.id
    print(f"OK: estado={hecho.estado}, origen_sesion_id={hecho.origen_sesion_id}, creado_por_id={hecho.creado_por_id}")

# Texto vacío: rechazado
r_vacio = client.post(f"/admin/familias/{FAMILIA_ID}/hechos", data={"texto": "   "})
assert r_vacio.status_code == 400, r_vacio.status_code
print("OK: texto vacío rechazado (400)")

# Editar (botón "Editar" del tab Validados)
r_editar = client.post(
    f"/admin/familias/{FAMILIA_ID}/hechos/{hecho_id}/editar",
    data={"texto": "  Le encantaba jugar al truco, pero hacía trampa  "},
    follow_redirects=True,
)
assert r_editar.status_code == 200, r_editar.status_code
assert "tab=validados" in str(r_editar.url)
assert "Le encantaba jugar al truco, pero hacía trampa" in r_editar.text
with get_db() as db:
    assert db.get(HechoFamiliar, hecho_id).texto == "Le encantaba jugar al truco, pero hacía trampa"
print("OK: editar actualiza el texto y vuelve a la tab Validados")

r_editar_vacio = client.post(f"/admin/familias/{FAMILIA_ID}/hechos/{hecho_id}/editar", data={"texto": "   "})
assert r_editar_vacio.status_code == 400, r_editar_vacio.status_code
print("OK: editar con texto vacío rechazado (400)")

# Borrar (la "x" del tab Validados) — usa el endpoint real, no un delete directo
r_borrar = client.post(f"/admin/familias/{FAMILIA_ID}/hechos/{hecho_id}/borrar", follow_redirects=True)
assert r_borrar.status_code == 200, r_borrar.status_code
assert "tab=validados" in str(r_borrar.url)
assert "Le encantaba jugar al truco, pero hacía trampa" not in r_borrar.text
with get_db() as db:
    assert db.get(HechoFamiliar, hecho_id) is None
print("OK: borrar (x) elimina el hecho para siempre, vuelve a la tab Validados")

print("\nTODO OK.")
