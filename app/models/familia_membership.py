from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import UserRole


class FamiliaMembership(Base):
    """Un usuario puede administrar más de una familia (y una familia puede
    tener más de un administrador) — esta tabla es la que lo permite, en vez
    de un familia_id único en Usuario."""

    __tablename__ = "familia_memberships"
    __table_args__ = (UniqueConstraint("usuario_id", "familia_id", name="uq_familia_membership_usuario_familia"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    familia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="CASCADE"), nullable=False
    )
    rol: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.admin_familia
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="memberships")
    familia: Mapped["Familia"] = relationship("Familia", back_populates="memberships")
