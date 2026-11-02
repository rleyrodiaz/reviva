from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Familia(Base):
    __tablename__ = "familias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha_alta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["FamiliaMembership"]] = relationship(
        "FamiliaMembership", back_populates="familia", cascade="all, delete-orphan"
    )
    # passive_deletes=True: al borrar una Familia, dejar que el
    # ondelete=CASCADE de la FK haga el borrado en la base — sin esto,
    # SQLAlchemy intenta por su cuenta poner familia_id en NULL en los hijos
    # antes de borrar, lo que rompe contra la columna NOT NULL.
    pacientes: Mapped[list["Paciente"]] = relationship(
        "Paciente", back_populates="familia", passive_deletes=True
    )
    personajes: Mapped[list["Personaje"]] = relationship(
        "Personaje", back_populates="familia", passive_deletes=True
    )
    hechos_familiares: Mapped[list["HechoFamiliar"]] = relationship(
        "HechoFamiliar", back_populates="familia", cascade="all, delete-orphan"
    )
