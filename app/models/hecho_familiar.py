from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoHechoFamiliar


class HechoFamiliar(Base):
    """Un dato general de familia (gustos, logros, datos de otra persona)
    rescatado de lo que el PACIENTE dijo en una sesión de Historia — nunca de
    lo que dijo el personaje, para no terminar validando una alucinación de
    la IA como si fuera un hecho real. Queda pendiente de aprobación del
    admin antes de poder alimentar el prompt de otras historias."""

    __tablename__ = "hechos_familiares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="CASCADE"), nullable=False
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[EstadoHechoFamiliar] = mapped_column(
        Enum(EstadoHechoFamiliar, name="estado_hecho_familiar"),
        nullable=False,
        default=EstadoHechoFamiliar.pendiente,
    )
    origen_sesion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("historia_sesiones.id", ondelete="SET NULL"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    familia: Mapped["Familia"] = relationship("Familia", back_populates="hechos_familiares")
    origen_sesion: Mapped["HistoriaSesion | None"] = relationship("HistoriaSesion")
