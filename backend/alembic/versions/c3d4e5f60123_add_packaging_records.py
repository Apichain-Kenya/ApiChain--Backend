"""add packaging_records table

Revision ID: c3d4e5f60123
Revises: b2c3d4e5f601
Create Date: 2026-05-16 12:02:00.000000

Sprint 5: persisted pre-image of `recordPackaging(batchId, packagingHash)`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f60123'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f601'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'packaging_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('unit_count', sa.Integer(), nullable=False),
        sa.Column('jar_ids', sa.JSON(), nullable=False),
        sa.Column('qr_codes', sa.JSON(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('packaging_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_packaging_records_id'), 'packaging_records', ['id'], unique=False)
    op.create_index(
        op.f('ix_packaging_records_packaging_proof_hash'),
        'packaging_records',
        ['packaging_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_packaging_records_packaging_proof_hash'), table_name='packaging_records')
    op.drop_index(op.f('ix_packaging_records_id'), table_name='packaging_records')
    op.drop_table('packaging_records')
