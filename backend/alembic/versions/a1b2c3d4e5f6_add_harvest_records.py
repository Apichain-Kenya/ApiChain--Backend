"""add harvest_records table

Revision ID: a1b2c3d4e5f6
Revises: 7a3f2b9c4d1e
Create Date: 2026-05-16 12:00:00.000000

Sprint 5: persisted pre-image of `recordHarvest(batchId, harvestHash)`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '7a3f2b9c4d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'harvest_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('harvest_date', sa.DateTime(), nullable=False),
        sa.Column('quantity_kg', sa.Float(), nullable=False),
        sa.Column('hive_ids', sa.JSON(), nullable=False),
        sa.Column('gps_lat', sa.Float(), nullable=True),
        sa.Column('gps_lon', sa.Float(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('harvest_proof_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['honey_batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index(op.f('ix_harvest_records_id'), 'harvest_records', ['id'], unique=False)
    op.create_index(
        op.f('ix_harvest_records_harvest_proof_hash'),
        'harvest_records',
        ['harvest_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_harvest_records_harvest_proof_hash'), table_name='harvest_records')
    op.drop_index(op.f('ix_harvest_records_id'), table_name='harvest_records')
    op.drop_table('harvest_records')
