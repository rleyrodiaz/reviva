"""hechos creado por

Revision ID: c7d8e9f0a1b2
Revises: b2c3d4e5f6a7
Create Date: 2026-11-02 00:00:00.000000+00:00

Un hecho de familia cargado a mano por un admin (no rescatado de una
sesión) guarda quién lo cargó.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hechos_familiares', sa.Column('creado_por_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'hechos_familiares_creado_por_id_fkey', 'hechos_familiares', 'usuarios',
        ['creado_por_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('hechos_familiares_creado_por_id_fkey', 'hechos_familiares', type_='foreignkey')
    op.drop_column('hechos_familiares', 'creado_por_id')
