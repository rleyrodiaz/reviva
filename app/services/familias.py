from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.familia import Familia
from app.models.usuario import Usuario


def list_familias_propias(usuario: Usuario, db: Session) -> list[Familia]:
    """Familias del usuario: todas si es superadmin (tiene acceso a
    cualquiera aunque no tenga membresía ahí), o las de sus membresías
    reales para cualquier otro usuario."""
    if usuario.es_superadmin:
        return list(db.scalars(select(Familia).order_by(Familia.nombre)).all())
    familia_ids = [m.familia_id for m in usuario.memberships]
    if not familia_ids:
        return []
    return list(
        db.scalars(select(Familia).where(Familia.id.in_(familia_ids)).order_by(Familia.nombre)).all()
    )


def familias_navbar(usuario: Usuario, familia_actual_id: int | None) -> dict:
    """Para el selector de familia del navbar ("en qué familia estoy
    parado, y a cuáles me puedo mover"): abre su propia sesión corta en vez
    de depender de la `db` de la ruta que renderiza la página, así
    funciona igual sin importar qué ruta/template lo llame."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        familias = list_familias_propias(usuario, db)
        actual = next((f for f in familias if f.id == familia_actual_id), None)
        return {
            "actual_nombre": actual.nombre if actual else None,
            "todas": [{"id": f.id, "nombre": f.nombre} for f in familias],
        }
    finally:
        db.close()


def contadores_pendientes(familia_id: int) -> dict:
    """Para el badge del nav (Bandeja/Hechos): cuántos ítems están
    esperando revisión en esta familia. Abre su propia sesión corta, igual
    que familias_navbar, para no depender de la `db` de la ruta que
    renderiza la página — así funciona en cualquier pantalla, no solo en
    el dashboard."""
    from app.db import SessionLocal
    from app.models.enums import EstadoGuion, EstadoHechoFamiliar
    from app.models.guion import Guion
    from app.models.hecho_familiar import HechoFamiliar
    from app.models.historia import Historia
    from app.models.personaje import Personaje

    db = SessionLocal()
    try:
        guiones_pendientes = db.scalar(
            select(func.count())
            .select_from(Guion)
            .join(Personaje)
            .where(Personaje.familia_id == familia_id, Guion.estado == EstadoGuion.pendiente_aprobacion)
        ) or 0
        historias_pendientes = db.scalar(
            select(func.count())
            .select_from(Historia)
            .join(Personaje)
            .where(Personaje.familia_id == familia_id, Historia.mensaje_propuesto.is_not(None))
        ) or 0
        bandeja = guiones_pendientes + historias_pendientes
        hechos = db.scalar(
            select(func.count())
            .select_from(HechoFamiliar)
            .where(
                HechoFamiliar.familia_id == familia_id,
                HechoFamiliar.estado == EstadoHechoFamiliar.pendiente,
            )
        )
        return {"bandeja": bandeja, "hechos": hechos or 0}
    finally:
        db.close()


def es_admin_de(usuario: Usuario, familia_id: int) -> bool:
    """Para el navbar: si corresponde mostrarle el menú "Admin" (Activity
    log/Settings) de esta familia puntual — superadmin siempre, o quien
    tenga membership admin_familia en ella."""
    if usuario.es_superadmin:
        return True
    return any(
        m.familia_id == familia_id and m.rol == UserRole.admin_familia
        for m in usuario.memberships
    )
