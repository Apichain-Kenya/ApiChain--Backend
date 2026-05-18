"""drop aggregators table + documents.aggregator_id

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-18 09:30:00.000000

Sprint 8: the aggregator concept was retired in the 2026-04-12 admin-
enrollment pivot. The router was commented out then; this migration
closes the loop by dropping the table itself and the now-dead
`documents.aggregator_id` FK column.

The downgrade is provided for completeness so an emergency revert is
possible; iteration 2 would design a fresh aggregator schema rather than
revive this one verbatim.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography


revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the FK + column on documents first so the parent table can be
    # dropped without a constraint violation. The constraint name is the
    # PostgreSQL auto-assigned name; if a future env disagrees, run
    # `\d documents` and adjust the name here.
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("documents_aggregator_id_fkey", type_="foreignkey")
        batch.drop_column("aggregator_id")

    op.drop_index(op.f('ix_aggregators_id'), table_name='aggregators')
    op.drop_table('aggregators')


def downgrade() -> None:
    op.create_table(
        'aggregators',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column(
            'region_location',
            Geography(geometry_type='POINT', srid=4326),
            nullable=True,
        ),
        sa.Column('farmers_count', sa.Integer(), nullable=True),
        sa.Column('verification_status', sa.String(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('wallet_address', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone'),
        sa.UniqueConstraint('wallet_address'),
    )
    op.create_index(
        op.f('ix_aggregators_id'), 'aggregators', ['id'], unique=False
    )

    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column('aggregator_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "documents_aggregator_id_fkey",
            "aggregators",
            ["aggregator_id"],
            ["id"],
        )
