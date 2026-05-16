"""add process_records table

Revision ID: b2c3d4e5f601
Revises: a1b2c3d4e5f6
Create Date: 2026-05-16 12:01:00.000000

Sprint 5: persisted pre-image of `recordProcessing(batchId, processHash)`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f601'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'process_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('extraction_method', sa.String(), nullable=False),
        sa.Column('moisture_content', sa.Float(), nullable=True),
        sa.Column('handling_notes', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('process_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_process_records_id'), 'process_records', ['id'], unique=False)
    op.create_index(
        op.f('ix_process_records_process_proof_hash'),
        'process_records',
        ['process_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_process_records_process_proof_hash'), table_name='process_records')
    op.drop_index(op.f('ix_process_records_id'), table_name='process_records')
    op.drop_table('process_records')
