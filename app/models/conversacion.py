from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personaje_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personajes.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    personaje: Mapped["Personaje"] = relationship("Personaje", back_populates="conversaciones")
    guiones: Mapped[list["Guion"]] = relationship(
        "Guion", back_populates="conversacion", cascade="all, delete-orphan"
    )
