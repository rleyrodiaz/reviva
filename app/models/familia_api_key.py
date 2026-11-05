from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FamiliaApiKey(Base):
    """La API key de IA que cargó una familia para un proveedor puntual
    (anthropic, openai, los que se vayan agregando a _PROVEEDORES en
    ia_cliente.py). Una familia puede tener una guardada por proveedor;
    cuál de esos proveedores es el que de verdad se usa para sus llamadas
    es Familia.proveedor_ia_activo. Nada impide que dos familias distintas
    tengan guardado el mismo valor de key (una cuenta de Anthropic
    compartida entre varias) — cada fila es independiente."""

    __tablename__ = "familia_api_keys"
    __table_args__ = (
        UniqueConstraint("familia_id", "proveedor", name="uq_familia_api_key_proveedor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("familias.id", ondelete="CASCADE"), nullable=False
    )
    proveedor: Mapped[str] = mapped_column(String(30), nullable=False)
    # Nunca en texto plano — ver app/services/cifrado.py.
    api_key_cifrada: Mapped[str] = mapped_column(String(1000), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    familia: Mapped["Familia"] = relationship("Familia", back_populates="api_keys")
