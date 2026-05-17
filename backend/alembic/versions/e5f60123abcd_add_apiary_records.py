"""add apiary_records table

Revision ID: e5f60123abcd
Revises: d4e5f6012345
Create Date: 2026-05-16 18:00:00.000000

Sprint 6: persisted pre-image of `createBatch(batchId, apiaryHash, metadataHash)`
for the apiary half of S0. Closes the structured-row symmetry across all six
lifecycle stages.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f60123abcd'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6012345'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'apiary_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('apiary_id', sa.Integer(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('vegetation_type', sa.String(), nullable=True),
        sa.Column('hive_count', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('apiary_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.ForeignKeyConstraint(['apiary_id'], ['apiary_locations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_apiary_records_id'), 'apiary_records', ['id'], unique=False)
    op.create_index(
        op.f('ix_apiary_records_apiary_proof_hash'),
        'apiary_records',
        ['apiary_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_apiary_records_apiary_proof_hash'), table_name='apiary_records')
    op.drop_index(op.f('ix_apiary_records_id'), table_name='apiary_records')
    op.drop_table('apiary_records')
