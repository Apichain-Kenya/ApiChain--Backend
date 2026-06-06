"""sprint13: drop qr_codes from packaging_records (one QR per batch)"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("packaging_records", "qr_codes")


def downgrade():
    op.add_column("packaging_records",
                  sa.Column("qr_codes", sa.JSON(), nullable=False,
                            server_default=sa.text("'[]'::json")))
