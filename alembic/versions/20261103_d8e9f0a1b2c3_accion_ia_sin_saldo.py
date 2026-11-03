"""accion ia sin saldo

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-03 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'ia_sin_saldo'")


def downgrade() -> None:
    # Postgres no soporta borrar un valor de un enum sin recrear el tipo
    # entero — no hace falta para este proyecto, se deja como no-op.
    pass
