from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AccionActividad


class ActivityLog(Base):
    """Registro global de actividad administrativa (todas las familias) —
    pantalla "Activity log" del navbar, visible solo a superadmin."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    familia_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="SET NULL"), nullable=True
    )
    accion: Mapped[AccionActividad] = mapped_column(
        Enum(AccionActividad, name="accion_actividad"), nullable=False
    )
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario: Mapped["Usuario | None"] = relationship("Usuario")
    familia: Mapped["Familia | None"] = relationship("Familia")
