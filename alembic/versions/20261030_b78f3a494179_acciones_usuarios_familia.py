"""acciones_usuarios_familia

Revision ID: b78f3a494179
Revises: e8df5f88acdd
Create Date: 2026-10-30 15:08:31.452013+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b78f3a494179'
down_revision: Union[str, None] = 'e8df5f88acdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'usuario_agregado_a_familia'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'rol_cambiado'")
    op.execute("ALTER TYPE accion_actividad ADD VALUE 'usuario_quitado_de_familia'")


def downgrade() -> None:
    # Postgres no soporta borrar un valor de un enum sin recrear el tipo
    # entero — no hace falta para este proyecto, se deja como no-op.
    pass
