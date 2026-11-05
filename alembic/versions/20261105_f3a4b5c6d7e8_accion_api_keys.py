"""accion api keys

Revision ID: f3a4b5c6d7e8
Revises: e1f2a3b4c5d6
Create Date: 2026-11-05 00:00:00.000001+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'ia_sin_api_key'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'api_key_guardada'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'api_key_borrada'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'ia_proveedor_cambiado'")


def downgrade() -> None:
    # Postgres no soporta borrar un valor de un enum sin recrear el tipo
    # entero — no hace falta para este proyecto, se deja como no-op.
    pass
