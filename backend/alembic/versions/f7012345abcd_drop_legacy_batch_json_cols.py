"""drop legacy *_data JSON columns on honey_batches

Revision ID: f7012345abcd
Revises: e5f60123abcd
Create Date: 2026-05-17 12:00:00.000000

Sprint 7: now that every lifecycle stage has a structured row + indexed
*_proof_hash (apiary_records / harvest_records / process_records /
lab_results / packaging_records / distribution_records), the six legacy
JSON mirror columns on honey_batches are no longer read anywhere. They
were kept for one sprint as a rollback path; this migration removes them.

metadata_payload stays — it's still the canonical source for
metadataHash until the Sprint 8 schema rewrite (backlog #1).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7012345abcd'
down_revision: Union[str, Sequence[str], None] = 'e5f60123abcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_COLS = (
    'apiary_data',
    'harvest_data',
    'process_data',
    'lab_proof_data',
    'packaging_data',
    'distribution_data',
)


def upgrade() -> None:
    for col in _LEGACY_COLS:
        op.drop_column('honey_batches', col)


def downgrade() -> None:
    # Reversible within one sprint: recreate as nullable JSON. Data is lost,
    # but the structured rows hold the canonical pre-image so /verify still
    # works.
    for col in _LEGACY_COLS:
        op.add_column('honey_batches', sa.Column(col, sa.JSON(), nullable=True))
