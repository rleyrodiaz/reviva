"""familia api keys

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-11-05 00:00:00.000000+00:00

Cada familia puede cargar su propia API key de IA por proveedor
(anthropic, openai, ...), en vez de depender solo de la key global de
.env. proveedor_ia_activo en familias dice cuál de esas keys guardadas
se usa de verdad.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('familias', sa.Column('proveedor_ia_activo', sa.String(length=30), nullable=True))

    op.create_table(
        'familia_api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('familia_id', sa.Integer(), nullable=False),
        sa.Column('proveedor', sa.String(length=30), nullable=False),
        sa.Column('api_key_cifrada', sa.String(length=1000), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['familia_id'], ['familias.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('familia_id', 'proveedor', name='uq_familia_api_key_proveedor'),
    )


def downgrade() -> None:
    op.drop_table('familia_api_keys')
    op.drop_column('familias', 'proveedor_ia_activo')
