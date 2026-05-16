"""add lab_proof_hash to lab_results

Revision ID: 7a3f2b9c4d1e
Revises: 50c45b379e24
Create Date: 2026-05-16 09:00:00.000000

Adds the `lab_proof_hash` column on `lab_results`. Sprint 3 makes the
`lab_results` row the canonical pre-image of the on-chain proof hash anchored
via `anchorLabProof(batchId, proofHash)`. Storing the hash on the row enables
the QR-verification phase to confirm (a) the row hashes to the value stored
here and (b) the value here matches `TraceabilityRegistry.getBatch().labProofHash`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a3f2b9c4d1e'
down_revision: Union[str, Sequence[str], None] = '50c45b379e24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'lab_results',
        sa.Column('lab_proof_hash', sa.String(), nullable=True),
    )
    op.create_index(
        op.f('ix_lab_results_lab_proof_hash'),
        'lab_results',
        ['lab_proof_hash'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_lab_results_lab_proof_hash'),
        table_name='lab_results',
    )
    op.drop_column('lab_results', 'lab_proof_hash')
