from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoGuion, ModoEnvio


class Guion(Base):
    __tablename__ = "guiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personaje_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personajes.id", ondelete="CASCADE"), nullable=False
    )
    conversacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversaciones.id", ondelete="CASCADE"), nullable=False
    )
    fecha_programada: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    texto_mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    modo_envio: Mapped[ModoEnvio] = mapped_column(
        Enum(ModoEnvio, name="modo_envio"), nullable=False, default=ModoEnvio.manual
    )
    estado: Mapped[EstadoGuion] = mapped_column(
        Enum(EstadoGuion, name="estado_guion"), nullable=False, default=EstadoGuion.borrador
    )
    nodo_padre_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guiones.id", ondelete="SET NULL"), nullable=True
    )
    # Explícito, lo decide el admin — nunca se infiere solo de que nadie lo
    # señale como destino (eso también le pasa a un guion huérfano de una
    # prueba vieja, y no queremos que se reactive solo como si fuera una
    # entrada real). Lo usan "Vaciar chat" y "Reabrir conversación".
    es_entrada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Posición/ancho en el mapa visual de la conversación (editor de arrastrar
    # y soltar). None = todavía no se movió, el frontend lo ubica con su
    # layout automático de capas.
    pos_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pos_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ancho: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alto: Mapped[int | None] = mapped_column(Integer, nullable=True)

    personaje: Mapped["Personaje"] = relationship("Personaje", back_populates="guiones")
    conversacion: Mapped["Conversacion"] = relationship("Conversacion", back_populates="guiones")
    nodo_padre: Mapped["Guion | None"] = relationship(
        "Guion", remote_side="Guion.id", foreign_keys=[nodo_padre_id]
    )
    ramas_libres: Mapped[list["RamaRespuestaLibre"]] = relationship(
        "RamaRespuestaLibre",
        back_populates="guion",
        foreign_keys="RamaRespuestaLibre.guion_id",
        cascade="all, delete-orphan",
    )
