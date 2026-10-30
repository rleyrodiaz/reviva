from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import TamanoFuente, TemaVisual


class Paciente(Base):
    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    foto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preferencias de la vista del paciente — las fija el admin desde el
    # dashboard, no el paciente (público con dificultades cognitivas).
    tema: Mapped[TemaVisual] = mapped_column(
        Enum(TemaVisual, name="tema_visual"), nullable=False, default=TemaVisual.claro
    )
    tamano_fuente: Mapped[TamanoFuente] = mapped_column(
        Enum(TamanoFuente, name="tamano_fuente"), nullable=False, default=TamanoFuente.normal
    )
    push_habilitado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    familia: Mapped["Familia"] = relationship("Familia", back_populates="pacientes")
    interacciones: Mapped[list["Interaccion"]] = relationship("Interaccion", back_populates="paciente")
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        "PushSubscription", back_populates="paciente", cascade="all, delete-orphan"
    )
