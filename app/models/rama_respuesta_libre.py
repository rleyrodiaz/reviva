from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RamaRespuestaLibre(Base):
    __tablename__ = "ramas_respuesta_libre"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="CASCADE"), nullable=False
    )
    # Descripción en lenguaje natural que usa la IA para matchear la respuesta
    # del paciente contra esta rama. Nula solo en la rama fallback.
    criterio: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guion_siguiente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="SET NULL"), nullable=True
    )

    guion: Mapped["Guion"] = relationship("Guion", back_populates="ramas_libres", foreign_keys=[guion_id])
    guion_siguiente: Mapped["Guion | None"] = relationship("Guion", foreign_keys=[guion_siguiente_id])
