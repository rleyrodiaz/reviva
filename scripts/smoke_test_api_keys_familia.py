"""Verifica de punta a punta el flujo de API Keys por familia (Settings >
API Keys): guardar una key la cifra en la base, nunca se vuelve a mostrar
completa, la primera que se carga queda activa sola, generar_texto() la usa
de verdad para esa familia, y si no hay ninguna configurada deja un aviso en
el Activity log (una sola vez por hora) en vez de fallar en silencio.

Crea una familia descartable, corre todo el flujo contra ella y la borra al
final (api_keys se va en cascada con la familia).

Uso: python -m scripts.smoke_test_api_keys_familia
"""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.enums import AccionActividad
from app.models.familia import Familia
from app.models.familia_api_key import FamiliaApiKey
from app.services import ia_cliente
from scripts._smoke_auth import login_superadmin

NOMBRE_FAMILIA = "__smoke_api_keys__"

client = TestClient(app)
login_superadmin(client)

with get_db() as db:
    sobrante = db.scalar(select(Familia).where(Familia.nombre == NOMBRE_FAMILIA))
    if sobrante is not None:
        client.post(f"/admin/familias/{sobrante.id}/borrar", follow_redirects=False)

r = client.post(
    "/admin/familias",
    data={
        "nombre_familia": NOMBRE_FAMILIA,
        "nombre_paciente": "Paciente de prueba",
        "admin_email": "smoke-api-keys@example.com",
        "admin_nombre": "Admin de prueba",
        "admin_password": "clave-de-prueba-123",
    },
    follow_redirects=False,
)
assert r.status_code == 303, f"no se pudo crear la familia de prueba: {r.status_code} {r.text}"

with get_db() as db:
    familia = db.scalar(select(Familia).where(Familia.nombre == NOMBRE_FAMILIA))
    assert familia is not None
    familia_id = familia.id

try:
    # 1) Sin ninguna key cargada: generar_texto(familia_id=...) devuelve
    #    None (no rompe) y deja UN aviso en el Activity log, no más de uno
    #    aunque se llame varias veces en la misma hora.
    assert ia_cliente.generar_texto("hola", familia_id=familia_id) is None
    assert ia_cliente.generar_texto("hola de nuevo", familia_id=familia_id) is None
    with get_db() as db:
        avisos = db.scalars(
            select(ActivityLog).where(
                ActivityLog.accion == AccionActividad.ia_sin_api_key,
                ActivityLog.familia_id == familia_id,
            )
        ).all()
        assert len(avisos) == 1, f"esperaba exactamente 1 aviso de 'sin API key', hay {len(avisos)}"

    r = client.get(f"/admin/familias/{familia_id}/settings/api-keys")
    assert r.status_code == 200
    assert "todavía no tiene un proveedor de IA activo" in r.text

    # 2) Cargar la primera key (anthropic): queda activa sola.
    r = client.post(
        f"/admin/familias/{familia_id}/settings/api-keys",
        data={"proveedor": "anthropic", "api_key": "sk-ant-abcd1234EFGH"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    with get_db() as db:
        familia = db.get(Familia, familia_id)
        assert familia.proveedor_ia_activo == "anthropic", familia.proveedor_ia_activo
        fila = db.scalar(select(FamiliaApiKey).where(FamiliaApiKey.familia_id == familia_id))
        assert fila.api_key_cifrada != "sk-ant-abcd1234EFGH", "la key se guardó en texto plano"

    # 3) La pantalla nunca vuelve a mostrar la key completa.
    r = client.get(f"/admin/familias/{familia_id}/settings/api-keys")
    assert "sk-ant-abcd1234EFGH" not in r.text
    assert "EFGH" in r.text, "no se ve ni la máscara con los últimos caracteres"

    # 4) generar_texto resuelve de verdad la key de esta familia (se prueba
    #    el resolver directamente, sin gastar una llamada real a Anthropic).
    resuelto = ia_cliente._resolver_credencial_familia(familia_id)
    assert resuelto == ("anthropic", "sk-ant-abcd1234EFGH"), resuelto

    # 5) Cargar una segunda key (openai) no pisa el proveedor activo.
    r = client.post(
        f"/admin/familias/{familia_id}/settings/api-keys",
        data={"proveedor": "openai", "api_key": "sk-openai-wxyz9999"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    with get_db() as db:
        familia = db.get(Familia, familia_id)
        assert familia.proveedor_ia_activo == "anthropic"

    # 6) Cambiar manualmente el proveedor activo a openai.
    r = client.post(
        f"/admin/familias/{familia_id}/settings/api-keys/activo",
        data={"proveedor": "openai"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    with get_db() as db:
        familia = db.get(Familia, familia_id)
        assert familia.proveedor_ia_activo == "openai"

    # 7) Borrar la key activa deja a la familia sin proveedor activo (no
    #    se queda apuntando a un proveedor sin key).
    with get_db() as db:
        fila_openai = db.scalar(
            select(FamiliaApiKey).where(
                FamiliaApiKey.familia_id == familia_id, FamiliaApiKey.proveedor == "openai"
            )
        )
        fila_openai_id = fila_openai.id
    r = client.post(f"/admin/familias/{familia_id}/settings/api-keys/{fila_openai_id}/borrar", follow_redirects=False)
    assert r.status_code == 303, r.text
    with get_db() as db:
        familia = db.get(Familia, familia_id)
        assert familia.proveedor_ia_activo is None

    print("OK: guardar cifra la key, nunca se muestra completa, la primera carga queda activa,")
    print("    generar_texto la resuelve de verdad, elegir activo y borrar funcionan, y sin")
    print("    ninguna key configurada se deja un aviso (uno solo) en el Activity log.")
finally:
    client.post(f"/admin/familias/{familia_id}/borrar", follow_redirects=False)
    with get_db() as db:
        assert db.get(Familia, familia_id) is None, "no se pudo limpiar la familia de prueba"

print("\nTODO OK.")
