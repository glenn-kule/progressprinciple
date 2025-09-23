"""baseline schema

Revision ID: 6ce9b66dfe9a
Revises: 
Create Date: 2025-09-22 01:20:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6ce9b66dfe9a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1) Create users table (new)
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(length=120), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # 2) exercise.owner_id (nullable, FK -> user.id)
    with op.batch_alter_table('exercise', schema=None) as batch_op:
        if not has_column('exercise', 'owner_id'):
            batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_exercise_owner_user',
                referent_table='user',
                local_cols=['owner_id'],
                remote_cols=['id'],
            )

    # 3) program.user_id (required), program.deload_week (nullable)
    with op.batch_alter_table('program', schema=None) as batch_op:
        if not has_column('program', 'user_id'):
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_program_user',
                referent_table='user',
                local_cols=['user_id'],
                remote_cols=['id'],
            )
            # backfill nulls to some user if needed is app-level; keep nullable in migration, app enforces presence
        if not has_column('program', 'deload_week'):
            batch_op.add_column(sa.Column('deload_week', sa.Integer(), nullable=True))

    # 4) program_exercise.position
    with op.batch_alter_table('program_exercise', schema=None) as batch_op:
        if not has_column('program_exercise', 'position'):
            batch_op.add_column(sa.Column('position', sa.Integer(), nullable=True, server_default='0'))
            batch_op.alter_column('position', server_default=None)

    # 5) workout.user_id (nullable -> app writes it)
    with op.batch_alter_table('workout', schema=None) as batch_op:
        if not has_column('workout', 'user_id'):
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_workout_user',
                referent_table='user',
                local_cols=['user_id'],
                remote_cols=['id'],
            )

    # 6) set_log.user_id (nullable -> app writes it)
    with op.batch_alter_table('set_log', schema=None) as batch_op:
        if not has_column('set_log', 'user_id'):
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_setlog_user',
                referent_table='user',
                local_cols=['user_id'],
                remote_cols=['id'],
            )


def downgrade():
    # reverse order of creation to drop constraints cleanly
    with op.batch_alter_table('set_log', schema=None) as batch_op:
        drop_fk_if_exists('set_log', 'fk_setlog_user')
        if has_column('set_log', 'user_id'):
            batch_op.drop_column('user_id')

    with op.batch_alter_table('workout', schema=None) as batch_op:
        drop_fk_if_exists('workout', 'fk_workout_user')
        if has_column('workout', 'user_id'):
            batch_op.drop_column('user_id')

    with op.batch_alter_table('program_exercise', schema=None) as batch_op:
        if has_column('program_exercise', 'position'):
            batch_op.drop_column('position')

    with op.batch_alter_table('program', schema=None) as batch_op:
        drop_fk_if_exists('program', 'fk_program_user')
        if has_column('program', 'user_id'):
            batch_op.drop_column('user_id')
        if has_column('program', 'deload_week'):
            batch_op.drop_column('deload_week')

    with op.batch_alter_table('exercise', schema=None) as batch_op:
        drop_fk_if_exists('exercise', 'fk_exercise_owner_user')
        if has_column('exercise', 'owner_id'):
            batch_op.drop_column('owner_id')

    op.drop_table('user')


# ---- helpers (Alembic runs this file as a module; safe to include) ----
from sqlalchemy import inspect
from alembic import context

def has_column(table_name: str, column_name: str) -> bool:
    """Check column presence using the connection Alembic is using."""
    bind = op.get_bind()
    insp = inspect(bind)
    cols = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in cols

def drop_fk_if_exists(table_name: str, fk_name: str):
    """SQLite batch mode needs named FKs; dropping is safe if exists."""
    bind = op.get_bind()
    insp = inspect(bind)
    # On SQLite, Alembic rebuilds the table; just attempt drop by name
    try:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
    except Exception:
        # ignore if it doesn't exist
        pass
