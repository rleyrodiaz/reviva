from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import OrigenMensajeHistoria


class HistoriaMensaje(Base):
    __tablename__ = "historia_mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sesion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("historia_sesiones.id", ondelete="CASCADE"), nullable=False
    )
    origen: Mapped[OrigenMensajeHistoria] = mapped_column(
        Enum(OrigenMensajeHistoria, name="origen_mensaje_historia"), nullable=False
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sesion: Mapped["HistoriaSesion"] = relationship("HistoriaSesion", back_populates="mensajes")
