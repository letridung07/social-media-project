"""Add last_used to Hashtag and usage_count to post_hashtags

Revision ID: trendinghashtags0001
Revises:
Create Date: 2024-05-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'trendinghashtags0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hashtag', sa.Column('last_used', sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now()))
    op.add_column('post_hashtags', sa.Column('usage_count', sa.Integer(), nullable=True, server_default=sa.text('1')))
    # For existing rows in post_hashtags, usage_count will be NULL.
    # If we want to initialize them to 1, we'd need an update statement.
    # However, for SQLite, direct ALTER TABLE for default might not work as expected for existing rows.
    # And server_default=sa.text('1') is more portable for new rows.
    # For existing rows, a separate data migration would be cleaner if they must be updated.
    # For this task, new hashtags will get 1, assuming new usages increment this.

    # Update existing Hashtag rows to have a last_used timestamp if they are NULL (e.g. newly created column)
    # This might be better handled in a data migration or application logic upon first use.
    # For now, setting a default should handle new entries. If specific backfill is needed:
    # op.execute('UPDATE hashtag SET last_used = CURRENT_TIMESTAMP WHERE last_used IS NULL')
    # For post_hashtags, if we need to set existing NULL usage_count to 1:
    # op.execute('UPDATE post_hashtags SET usage_count = 1 WHERE usage_count IS NULL')
    # However, nullable=True and server_default is often preferred for schema changes to avoid locking/long updates.
    # Let's assume nullable=True is acceptable for now, and application logic will handle counts.
    # Revisiting the default for usage_count: nullable=False, server_default='1' might be better if all entries must have it.
    # Let's make them non-nullable and provide server defaults.
    op.alter_column('hashtag', 'last_used', server_default=None, existing_type=sa.DateTime(), nullable=False, existing_server_default=sa.func.now())
    op.alter_column('post_hashtags', 'usage_count', server_default=None, existing_type=sa.Integer(), nullable=False, existing_server_default=sa.text('1'))



def downgrade():
    op.drop_column('post_hashtags', 'usage_count')
    op.drop_column('hashtag', 'last_used')
