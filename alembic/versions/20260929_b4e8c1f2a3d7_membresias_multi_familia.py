"""membresias multi-familia

Revision ID: b4e8c1f2a3d7
Revises: 72797d0b3ff4
Create Date: 2026-09-29 00:00:00.000000+00:00

Un usuario administrador ahora puede pertenecer a mas de una familia: se
reemplaza el familia_id unico (y el rol global) de Usuario por una tabla de
membresias (usuario_id, familia_id, rol), una fila por cada familia que
administra. El superadmin pasa a ser un flag global (es_superadmin),
separado del rol por familia, porque no depende de ninguna familia puntual.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# La reutilización de un ENUM ya creado por una migración anterior necesita
# el tipo específico de Postgres (create_type=False no lo respeta el sa.Enum
# genérico) para no intentar un CREATE TYPE duplicado.
USER_ROLE = postgresql.ENUM('superadmin', 'admin_familia', 'familiar', name='user_role', create_type=False)


revision: str = 'b4e8c1f2a3d7'
down_revision: Union[str, None] = '72797d0b3ff4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'usuarios',
        sa.Column('es_superadmin', sa.Boolean(), server_default='false', nullable=False),
    )
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE usuarios SET es_superadmin = true WHERE rol = 'superadmin'"))

    op.create_table(
        'familia_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('familia_id', sa.Integer(), nullable=False),
        sa.Column('rol', USER_ROLE, nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['familia_id'], ['familias.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usuario_id', 'familia_id', name='uq_familia_membership_usuario_familia'),
    )

    # Cada usuario con familia_id ya asignado (admin_familia o familiar) pasa
    # a tener una membresía equivalente. El superadmin no necesita una: ya
    # tiene acceso a todo via es_superadmin.
    conn.execute(sa.text("""
        INSERT INTO familia_memberships (usuario_id, familia_id, rol, creado_en)
        SELECT id, familia_id, rol, now()
        FROM usuarios
        WHERE familia_id IS NOT NULL AND rol <> 'superadmin'
    """))

    op.drop_column('usuarios', 'familia_id')
    op.drop_column('usuarios', 'rol')


def downgrade() -> None:
    op.add_column('usuarios', sa.Column('rol', USER_ROLE, nullable=True))
    op.add_column('usuarios', sa.Column('familia_id', sa.Integer(), nullable=True))
    op.create_foreign_key('usuarios_familia_id_fkey', 'usuarios', 'familias', ['familia_id'], ['id'], ondelete='SET NULL')

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE usuarios SET rol = 'superadmin' WHERE es_superadmin"))
    # Solo se puede volver a un familia_id por usuario: tomamos la membresía
    # más vieja de cada uno (downgrade con pérdida si tenía más de una).
    conn.execute(sa.text("""
        UPDATE usuarios u
        SET familia_id = m.familia_id, rol = m.rol
        FROM (
            SELECT DISTINCT ON (usuario_id) usuario_id, familia_id, rol
            FROM familia_memberships
            ORDER BY usuario_id, id
        ) m
        WHERE u.id = m.usuario_id
    """))
    conn.execute(sa.text("UPDATE usuarios SET rol = 'admin_familia' WHERE rol IS NULL"))
    op.alter_column('usuarios', 'rol', nullable=False)

    op.drop_table('familia_memberships')
    op.drop_column('usuarios', 'es_superadmin')
