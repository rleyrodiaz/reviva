"""accion historia aprobada desactivada

Revision ID: c4b6d8e0f1a3
Revises: d3e5f7a8b9c2
Create Date: 2026-10-30 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4b6d8e0f1a3'
down_revision: Union[str, None] = 'd3e5f7a8b9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'historia_aprobada'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'historia_desactivada'")


def downgrade() -> None:
    # Postgres no soporta borrar un valor de un enum sin recrear el tipo
    # entero — no hace falta para este proyecto, se deja como no-op.
    pass
