from sqlalchemy import select
from sqlalchemy.orm import Session

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
