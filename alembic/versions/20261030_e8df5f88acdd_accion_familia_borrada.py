"""accion_familia_borrada

Revision ID: e8df5f88acdd
Revises: a9d65cece9f3
Create Date: 2026-10-30 14:06:32.317742+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8df5f88acdd'
down_revision: Union[str, None] = 'a9d65cece9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'familia_borrada'")


def downgrade() -> None:
    # Postgres no soporta borrar un valor de un enum sin recrear el tipo
    # entero — no hace falta para este proyecto, se deja como no-op.
    pass
