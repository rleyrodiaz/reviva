"""historias bandeja aprobacion

Revision ID: d3e5f7a8b9c2
Revises: a9d4e1f2b3c7
Create Date: 2026-10-30 00:00:00.000000+00:00

Una historia manual, al proponerla, ahora pasa por la bandeja de
aprobación igual que el guion de entrada manual — el primer mensaje
generado se guarda en mensaje_propuesto hasta que se aprueba o se
desactiva, en vez de arrancar la sesión directo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e5f7a8b9c2'
down_revision: Union[str, None] = 'a9d4e1f2b3c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('historias', sa.Column('mensaje_propuesto', sa.Text(), nullable=True))
    op.add_column('historias', sa.Column('propuesta_en', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('historias', 'propuesta_en')
    op.drop_column('historias', 'mensaje_propuesto')
