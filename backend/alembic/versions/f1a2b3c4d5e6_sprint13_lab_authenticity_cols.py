"""sprint13: drop purity_score+passed_quality_check, add authenticity cols to lab_results"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lab_results", sa.Column("predicted_moisture", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("predicted_sugar", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("predicted_hmf", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("authenticity_score", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("validation_status", sa.String(), nullable=True))
    op.add_column("lab_results", sa.Column("explanation", sa.String(), nullable=True))
    op.drop_column("lab_results", "purity_score")
    op.drop_column("lab_results", "passed_quality_check")


def downgrade():
    op.add_column("lab_results", sa.Column("passed_quality_check", sa.Boolean(), nullable=True))
    op.add_column("lab_results", sa.Column("purity_score", sa.Float(), nullable=True))
    op.drop_column("lab_results", "explanation")
    op.drop_column("lab_results", "validation_status")
    op.drop_column("lab_results", "authenticity_score")
    op.drop_column("lab_results", "predicted_hmf")
    op.drop_column("lab_results", "predicted_sugar")
    op.drop_column("lab_results", "predicted_moisture")
