"""guiones alto (resize vertical de nodos en el mapa)

Revision ID: a1b2c3d4e5f6
Revises: c4b6d8e0f1a3
Create Date: 2026-10-31 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c4b6d8e0f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guiones', sa.Column('alto', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('guiones', 'alto')
