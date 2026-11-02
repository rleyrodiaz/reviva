from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ModoEnvio


class Historia(Base):
    __tablename__ = "historias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personaje_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personajes.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    # Igual que en el guion de entrada de una conversación: manual significa
    # que solo arranca si alguien aprieta "Proponer ahora" (admin); automático
    # programa una fecha para que el scheduler la proponga sola. Una vez que
    # el scheduler la dispara, limpia fecha_programada (queda consumida) —
    # para volver a programarla hay que poner una fecha nueva.
    modo_envio: Mapped[ModoEnvio] = mapped_column(
        Enum(ModoEnvio, name="modo_envio"), nullable=False, default=ModoEnvio.manual
    )
    fecha_programada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # En modo manual, "Proponer ahora" no arranca la sesión directo: genera
    # el primer mensaje y lo deja acá, esperando aprobación en la Bandeja
    # (igual que el guion de entrada manual) — recién cuando se aprueba se
    # crea la HistoriaSesion de verdad y le llega algo al paciente. Un
    # historia automática nunca pasa por esto: el scheduler la dispara
    # directo, como el guion automático.
    mensaje_propuesto: Mapped[str | None] = mapped_column(Text, nullable=True)
    propuesta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
