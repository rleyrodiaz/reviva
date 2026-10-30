from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Global, no depende de ninguna familia puntual — separado del rol por
    # familia (ver FamiliaMembership), que es lo que controla el acceso a
    # cada /admin/familias/{id}/... en particular.
    es_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    memberships: Mapped[list["FamiliaMembership"]] = relationship(
        "FamiliaMembership", back_populates="usuario", cascade="all, delete-orphan"
    )
