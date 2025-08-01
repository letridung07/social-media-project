"""Add Quest and UserQuestProgress models

Revision ID: efafc9853717
Revises: a1397fa0a290
Create Date: 2025-06-19 00:51:44.342528

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'efafc9853717'
down_revision = 'a1397fa0a290'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('quest',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('criteria_type', sa.String(length=50), nullable=False),
    sa.Column('criteria_target_count', sa.Integer(), nullable=False),
    sa.Column('reward_points', sa.Integer(), nullable=True),
    sa.Column('reward_badge_id', sa.Integer(), nullable=True),
    sa.Column('reward_virtual_good_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('start_date', sa.DateTime(), nullable=True),
    sa.Column('end_date', sa.DateTime(), nullable=True),
    sa.Column('repeatable_after_hours', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['reward_badge_id'], ['badge.id'], ),
    sa.ForeignKeyConstraint(['reward_virtual_good_id'], ['virtual_good.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('quest', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quest_criteria_type'), ['criteria_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_quest_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_quest_type'), ['type'], unique=False)

    op.create_table('user_quest_progress',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('quest_id', sa.Integer(), nullable=False),
    sa.Column('current_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('last_progress_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('last_completed_instance_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['quest_id'], ['quest.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'quest_id', name='_user_quest_uc')
    )
    with op.batch_alter_table('user_quest_progress', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_quest_progress_quest_id'), ['quest_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_quest_progress_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_quest_progress_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user_quest_progress', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_quest_progress_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_quest_progress_status'))
        batch_op.drop_index(batch_op.f('ix_user_quest_progress_quest_id'))

    op.drop_table('user_quest_progress')
    with op.batch_alter_table('quest', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quest_type'))
        batch_op.drop_index(batch_op.f('ix_quest_is_active'))
        batch_op.drop_index(batch_op.f('ix_quest_criteria_type'))

    op.drop_table('quest')
    # ### end Alembic commands ###
