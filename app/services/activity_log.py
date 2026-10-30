from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.enums import AccionActividad


def registrar_actividad(
    db: Session,
    accion: AccionActividad,
    usuario_id: int | None = None,
    familia_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detalle: str | None = None,
    session_id: str | None = None,
) -> None:
    db.add(ActivityLog(
        usuario_id=usuario_id,
        familia_id=familia_id,
        accion=accion,
        target_type=target_type,
        target_id=target_id,
        detalle=detalle,
        session_id=session_id,
    ))
