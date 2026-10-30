from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Historia(Base):
    __tablename__ = "historias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personaje_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personajes.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    # Texto libre a propósito: no todas las historias tienen fecha/lugar exactos.
    epoca: Mapped[str | None] = mapped_column(String(150), nullable=True)
    lugar: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Nombres sueltos ("papá, tío Beto") — no siempre son Personajes cargados en el sistema.
    participantes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # La base de conocimiento real: anécdotas y detalles sueltos que la IA puede
    # usar. Es el único material del que puede sacar hechos — todo lo que no
    # esté acá (o no lo haya dicho el paciente en la sesión) no lo puede inventar.
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    duracion_maxima_minutos: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    personaje: Mapped["Personaje"] = relationship("Personaje", back_populates="historias")
    sesiones: Mapped[list["HistoriaSesion"]] = relationship(
        "HistoriaSesion", back_populates="historia", cascade="all, delete-orphan"
    )
