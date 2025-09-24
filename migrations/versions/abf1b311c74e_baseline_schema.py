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
    # users
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(length=120), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # exercise.owner_id
    with op.batch_alter_table('exercise', schema=None) as batch_op:
        if not has_column('exercise', 'owner_id'):
            batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_exercise_owner_user',
                referent_table='user',
                local_cols=['owner_id'],
                remote_cols=['id'],
            )

    # program.user_id + program.deload_week
    with op.batch_alter_table('program', schema=None) as batch_op:
        if not has_column('program', 'user_id'):
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_program_user',
                referent_table='user',
                local_cols=['user_id'],
                remote_cols=['id'],
            )
        if not has_column('program', 'deload_week'):
            batch_op.add_column(sa.Column('deload_week', sa.Integer(), nullable=True))

    # program_exercise.position
    with op.batch_alter_table('program_exercise', schema=None) as batch_op:
        if not has_column('program_exercise', 'position'):
            batch_op.add_column(sa.Column('position', sa.Integer(), server_default='0', nullable=True))
            batch_op.alter_column('position', server_default=None)

    # workout.user_id
    with op.batch_alter_table('workout', schema=None) as batch_op:
        if not has_column('workout', 'user_id'):
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                constraint_name='fk_workout_user',
                referent_table='user',
                local_cols=['user_id'],
                remote_cols=['id'],
            )

    # set_log.user_id
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


# helpers
from sqlalchemy import inspect
def has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c['name'] for c in insp.get_columns(table_name)]
    except Exception:
        cols = []
    return column_name in cols

def drop_fk_if_exists(table_name: str, fk_name: str):
    try:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
    except Exception:
        pass
