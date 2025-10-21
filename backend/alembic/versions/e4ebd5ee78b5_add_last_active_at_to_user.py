"""add_last_active_at_to_user

Revision ID: e4ebd5ee78b5
Revises: e3a7e8db826c
Create Date: 2025-10-21 14:51:55.260463

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4ebd5ee78b5'
down_revision = 'e3a7e8db826c'
branch_labels = None
depends_on = None


def upgrade():
    # Add last_active_at column to user table
    op.add_column('user', sa.Column('last_active_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove last_active_at column from user table
    op.drop_column('user', 'last_active_at')
