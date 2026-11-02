"""usuarios ultima familia

Revision ID: f2a7c3b8d4e1
Revises: c1a2b9d4e6f0
Create Date: 2026-10-30 00:00:00.000000+00:00

Guarda la última familia que visitó cada usuario, para saber a cuál
mandarlo al loguearse cuando pertenece a más de una.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a7c3b8d4e1'
down_revision: Union[str, None] = 'c1a2b9d4e6f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('ultima_familia_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'usuarios_ultima_familia_id_fkey', 'usuarios', 'familias',
        ['ultima_familia_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('usuarios_ultima_familia_id_fkey', 'usuarios', type_='foreignkey')
    op.drop_column('usuarios', 'ultima_familia_id')
