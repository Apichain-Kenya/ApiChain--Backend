"""add distribution_records table

Revision ID: d4e5f6012345
Revises: c3d4e5f60123
Create Date: 2026-05-16 12:03:00.000000

Sprint 5: persisted pre-image of `recordDistribution(batchId, distributionHash)`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6012345'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f60123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'distribution_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('retailer_name', sa.String(), nullable=False),
        sa.Column('transport_reference', sa.String(), nullable=True),
        sa.Column('handover_notes', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('distribution_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_distribution_records_id'), 'distribution_records', ['id'], unique=False)
    op.create_index(
        op.f('ix_distribution_records_distribution_proof_hash'),
        'distribution_records',
        ['distribution_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_distribution_records_distribution_proof_hash'), table_name='distribution_records')
    op.drop_index(op.f('ix_distribution_records_id'), table_name='distribution_records')
    op.drop_table('distribution_records')
