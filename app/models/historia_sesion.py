from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoHistoriaSesion


class HistoriaSesion(Base):
    """Un intento de charla sobre una Historia con el paciente. A diferencia
    de Interaccion (una pregunta, una respuesta), acá puede haber varios
    intercambios — por eso el detalle vive en HistoriaMensaje."""

    __tablename__ = "historia_sesiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    historia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("historias.id", ondelete="CASCADE"), nullable=False
    )
    paciente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    estado: Mapped[EstadoHistoriaSesion] = mapped_column(
        Enum(EstadoHistoriaSesion, name="estado_historia_sesion"),
        nullable=False,
        default=EstadoHistoriaSesion.activa,
    )
    iniciada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finalizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    historia: Mapped["Historia"] = relationship("Historia", back_populates="sesiones")
    paciente: Mapped["Paciente"] = relationship("Paciente")
    mensajes: Mapped[list["HistoriaMensaje"]] = relationship(
        "HistoriaMensaje",
        back_populates="sesion",
        cascade="all, delete-orphan",
        # Por id, no por creado_en: el mensaje del paciente y la respuesta
        # del personaje generada en la misma llamada se insertan en la misma
        # transacción, y server_default=func.now() devuelve el mismo valor
        # para ambos — ordenar por creado_en los deja en orden arbitrario
        # (afecta tanto el chat como, más grave, la transcripción que se le
        # manda a la IA para decidir el próximo mensaje).
        order_by="HistoriaMensaje.id",
    )
