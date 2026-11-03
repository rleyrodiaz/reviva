from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoHechoFamiliar


class HechoFamiliar(Base):
    """Un dato general de familia (gustos, logros, datos de otra persona).
    Tiene dos orígenes posibles: rescatado de lo que el PACIENTE dijo en una
    sesión de Historia (nunca de lo que dijo el personaje, para no terminar
    validando una alucinación de la IA como si fuera un hecho real) — ese
    queda `pendiente` hasta que un admin lo aprueba; o cargado a mano por un
    admin (`origen_sesion_id` None, `creado_por_id` seteado) — como ahí no
    hay nada de la IA para revisar, entra directo en `validado`."""

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
    # Nula para los rescatados de una sesión (son automáticos, nadie los
    # "carga"). Para un hecho agregado a mano por un admin, acá queda quién
    # fue — y el propio origen_sesion_id en None ya indica que es manual.
    creado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    familia: Mapped["Familia"] = relationship("Familia", back_populates="hechos_familiares")
    origen_sesion: Mapped["HistoriaSesion | None"] = relationship("HistoriaSesion")
    creado_por: Mapped["Usuario | None"] = relationship("Usuario")
