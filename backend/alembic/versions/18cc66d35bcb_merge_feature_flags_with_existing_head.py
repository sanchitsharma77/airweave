"""merge feature flags with existing head

Revision ID: 18cc66d35bcb
Revises: 9a977647c5a4, add_feature_flags_001
Create Date: 2025-10-07 13:17:31.914267

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '18cc66d35bcb'
down_revision = ('9a977647c5a4', 'add_feature_flags_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
