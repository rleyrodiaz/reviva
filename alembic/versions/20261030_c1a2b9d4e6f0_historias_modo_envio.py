"""historias modo envio

Revision ID: c1a2b9d4e6f0
Revises: b78f3a494179
Create Date: 2026-10-30 00:00:00.000000+00:00

Las historias pasan a poder programarse igual que el guion de entrada de
una conversación: manual (solo arranca si un admin aprieta "Proponer
ahora") o automático (una fecha para que el scheduler la proponga sola).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Reutiliza el ENUM modo_envio ya creado para guiones.modo_envio.
MODO_ENVIO = postgresql.ENUM('manual', 'automatico', name='modo_envio', create_type=False)


revision: str = 'c1a2b9d4e6f0'
down_revision: Union[str, None] = 'b78f3a494179'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'historias',
        sa.Column('modo_envio', MODO_ENVIO, server_default='manual', nullable=False),
    )
    op.add_column('historias', sa.Column('fecha_programada', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('historias', 'fecha_programada')
    op.drop_column('historias', 'modo_envio')
