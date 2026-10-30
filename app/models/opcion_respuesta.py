from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OpcionRespuesta(Base):
    __tablename__ = "opciones_respuesta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="CASCADE"), nullable=False
    )
    texto_opcion: Mapped[str] = mapped_column(String(300), nullable=False)
    guion_siguiente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="SET NULL"), nullable=True
    )

    guion: Mapped["Guion"] = relationship("Guion", back_populates="opciones", foreign_keys=[guion_id])
    guion_siguiente: Mapped["Guion | None"] = relationship("Guion", foreign_keys=[guion_siguiente_id])
