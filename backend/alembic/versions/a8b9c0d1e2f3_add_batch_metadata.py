"""add batch_metadata table

Revision ID: a8b9c0d1e2f3
Revises: f7012345abcd
Create Date: 2026-05-18 09:00:00.000000

Sprint 8: persisted pre-image of the on-chain `metadataHash` anchored at S0.
Closes the last verifiability gap — every chain hash in the six-stage
lifecycle is now recomputable from a single normalized DB row.

Honey-type and management-method enums are enforced at the Pydantic layer
(see app/schemas/batch.py) rather than via PostgreSQL ENUM types, so the
allowed-values list can be amended with a single Python edit instead of an
ALTER TYPE migration. `honey_batches.metadata_payload` (JSON) is left in
place for one sprint as a legacy mirror; it will be dropped in Sprint 9
once the frontend confirms the typed path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7012345abcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'batch_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('honey_type', sa.String(), nullable=False),
        sa.Column('expected_yield_kg', sa.Numeric(8, 2), nullable=False),
        sa.Column('harvest_window_start', sa.Date(), nullable=False),
        sa.Column('harvest_window_end', sa.Date(), nullable=False),
        sa.Column('apiary_management_method', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('metadata_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_batch_metadata_id'), 'batch_metadata', ['id'], unique=False)
    op.create_index(
        op.f('ix_batch_metadata_metadata_proof_hash'),
        'batch_metadata',
        ['metadata_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_batch_metadata_metadata_proof_hash'), table_name='batch_metadata')
    op.drop_index(op.f('ix_batch_metadata_id'), table_name='batch_metadata')
    op.drop_table('batch_metadata')
