from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Interaccion(Base):
    __tablename__ = "interacciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    # Copia del texto del guion en el momento del envío — si después se edita
    # el guion, el historial del paciente no debe cambiar retroactivamente.
    texto_enviado: Mapped[str | None] = mapped_column(Text, nullable=True)
    respuesta_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    rama_libre_elegida_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ramas_respuesta_libre.id", ondelete="SET NULL"), nullable=True
    )
    timestamp_envio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp_respuesta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Cuando la respuesta cae en un fallback sin destino armado (nada
    # escrito a mano para seguir), la IA genera un cierre breve en vez de
    # dejar la conversación sin contestar nada — se guarda acá para que
    # quede en el historial igual que cualquier otro mensaje.
    cierre_generado: Mapped[str | None] = mapped_column(Text, nullable=True)

    guion: Mapped["Guion"] = relationship("Guion")
    paciente: Mapped["Paciente"] = relationship("Paciente", back_populates="interacciones")
    rama_libre_elegida: Mapped["RamaRespuestaLibre | None"] = relationship("RamaRespuestaLibre")
