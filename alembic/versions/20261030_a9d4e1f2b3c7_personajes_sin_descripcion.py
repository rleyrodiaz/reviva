"""personajes sin descripcion

Revision ID: a9d4e1f2b3c7
Revises: f2a7c3b8d4e1
Create Date: 2026-10-30 00:00:00.000000+00:00

Sacamos el campo "Descripción / historia compartida" del personaje: la
base de conocimiento real de anécdotas ya es Historia.contenido (lo único
de lo que la IA puede sacar hechos), y relación + tono de escritura ya
cubren el resto. Tenerlo en el personaje además confundía, porque sugería
ser el lugar para anécdotas que en realidad van en cada Historia.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9d4e1f2b3c7'
down_revision: Union[str, None] = 'f2a7c3b8d4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('personajes', 'descripcion')


def downgrade() -> None:
    op.add_column('personajes', sa.Column('descripcion', sa.Text(), nullable=True))
