"""drop honey_batches.metadata_payload legacy JSON mirror

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-05-18 14:00:00.000000

Sprint 9: the typed batch_metadata row introduced in Sprint 8 is now
authoritative for `metadataHash`. The legacy free-form dict path was
removed (BatchCreateRequest.metadata is BatchMetadataInput, no Union),
so the JSON mirror column on honey_batches has no remaining readers or
writers. This migration drops it. Reversible — re-adds as nullable JSON;
data is lost but the canonical pre-image lives on batch_metadata.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c0d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('honey_batches', 'metadata_payload')


def downgrade() -> None:
    op.add_column(
        'honey_batches',
        sa.Column('metadata_payload', sa.JSON(), nullable=True),
    )
