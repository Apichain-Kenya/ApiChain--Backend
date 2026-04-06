"""add missing columns to farmers and aggregators

Revision ID: ad730960cdbd
Revises: bcf067da2d31
Create Date: 2026-04-06 10:10:20.590833

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad730960cdbd'
down_revision: Union[str, Sequence[str], None] = 'bcf067da2d31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FIX: These columns exist in the SQLAlchemy models but were missing from
    # the original migration (bcf067da2d31). Adding them to sync DB with models.
    # NOTE: Removed auto-detected 'drop_table spatial_ref_sys' — that is a PostGIS
    # system table and must never be managed by Alembic.
    op.add_column('aggregators', sa.Column('farmers_count', sa.Integer(), nullable=True))
    op.add_column('aggregators', sa.Column('address', sa.String(), nullable=True))
    op.add_column('farmers', sa.Column('email', sa.String(), nullable=True))
    op.add_column('farmers', sa.Column('address', sa.String(), nullable=True))
    op.create_unique_constraint('uq_farmers_email', 'farmers', ['email'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_farmers_email', 'farmers', type_='unique')
    op.drop_column('farmers', 'address')
    op.drop_column('farmers', 'email')
    op.drop_column('aggregators', 'address')
    op.drop_column('aggregators', 'farmers_count')
