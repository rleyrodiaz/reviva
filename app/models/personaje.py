from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Personaje(Base):
    __tablename__ = "personajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    foto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    relacion_con_paciente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tono_escritura: Mapped[str | None] = mapped_column(Text, nullable=True)

    familia: Mapped["Familia"] = relationship("Familia", back_populates="personajes")
    guiones: Mapped[list["Guion"]] = relationship("Guion", back_populates="personaje")
    conversaciones: Mapped[list["Conversacion"]] = relationship(
        "Conversacion", back_populates="personaje", cascade="all, delete-orphan"
    )
    historias: Mapped[list["Historia"]] = relationship(
        "Historia", back_populates="personaje", cascade="all, delete-orphan"
    )
