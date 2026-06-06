"""add users.created_at and farmers.is_active (reconcile c7b1a63 model drift)

Sprint 12 reconciliation. Teammate commit c7b1a63 added `created_at` to the
User model and `is_active` to the Farmer model but shipped NO migration, so the
pulled code SELECTs columns that don't exist -> every user/farmer query (incl.
login) errors against the live DB. This migration adds exactly those two
columns to match the model declarations. Kept SEPARATE from the geo_ai tables
migration because users/farmers are teammate-owned (coordinate-DDL rule);
flagged back to the teammate so the missing migration isn't re-derived.

server_default rationale:
- users.created_at  — model has server_default=func.now(); mirrored here so
  existing rows backfill to now() on ADD COLUMN.
- farmers.is_active — model only has a Python-side default=True (no
  server_default). A bare ADD COLUMN would leave existing farmer rows NULL, and
  auth.py's `not farmer.is_active` would then lock out every existing farmer.
  We add server_default=true so existing rows backfill to active. nullable is
  left True to match the model (avoids future autogenerate nullable drift).

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.add_column(
        "farmers",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("farmers", "is_active")
    op.drop_column("users", "created_at")
