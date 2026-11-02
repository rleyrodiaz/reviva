"""quitar tipo_respuesta/opciones (ya no se puede crear ese tipo de nodo)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-31 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('interacciones', 'opcion_elegida_id')
    op.drop_table('opciones_respuesta')
    op.drop_column('guiones', 'tipo_respuesta')
    op.execute("DROP TYPE tipo_respuesta")


def downgrade() -> None:
    op.execute("CREATE TYPE tipo_respuesta AS ENUM ('libre', 'opciones')")
    op.add_column(
        'guiones',
        sa.Column('tipo_respuesta', sa.Enum('libre', 'opciones', name='tipo_respuesta'), nullable=False, server_default='libre'),
    )
    op.create_table(
        'opciones_respuesta',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('guion_id', sa.Integer(), sa.ForeignKey('guiones.id', ondelete='CASCADE'), nullable=False),
        sa.Column('texto_opcion', sa.String(300), nullable=False),
        sa.Column('guion_siguiente_id', sa.Integer(), sa.ForeignKey('guiones.id', ondelete='SET NULL'), nullable=True),
    )
    op.add_column(
        'interacciones',
        sa.Column('opcion_elegida_id', sa.Integer(), sa.ForeignKey('opciones_respuesta.id', ondelete='SET NULL'), nullable=True),
    )
