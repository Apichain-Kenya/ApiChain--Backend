"""Basic read-only analytics aggregates (Sprint 13). Chain-neutral. No 'aggregator'
entity (dropped Sprint 8) — distributor/retailer semantics only."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.batch import HoneyBatch
from app.models.user import User
from app.models.farmer import Farmer

router = APIRouter(prefix="/analytics", tags=["Analytics"])

STATES = ["CREATED", "HARVESTED", "PROCESSED", "LAB_VERIFIED", "PACKAGED", "DISTRIBUTED"]


def aggregate_batches(batches) -> dict:
    """Pure aggregation over batch-like objects (uses harvest_record.quantity_kg
    and validation.validation_status relationships). Unit-testable without a DB."""
    by_state = {s: 0 for s in STATES}
    total_kg = 0.0
    distributed = 0
    flagged = 0
    for b in batches:
        if b.current_state in by_state:
            by_state[b.current_state] += 1
        h = getattr(b, "harvest_record", None)
        if h is not None and h.quantity_kg is not None:
            total_kg += h.quantity_kg
        if b.current_state == "DISTRIBUTED":
            distributed += 1
        v = getattr(b, "validation", None)
        if v is not None and v.validation_status in ("suspicious", "flagged"):
            flagged += 1
    return {
        "total_batches": len(batches),
        "by_state": by_state,
        "total_kg_harvested": round(total_kg, 2),
        "distributed_count": distributed,
        "flagged_count": flagged,
    }


@router.get("/farmer")
def farmer_analytics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer"])),
):
    """A farmer's own batch aggregates: by state, total kg harvested, distributed,
    and how many need attention (suspicious/flagged authenticity)."""
    batches = db.query(HoneyBatch).filter(
        HoneyBatch.farmer_id == current_user["user_id"]
    ).all()
    return aggregate_batches(batches)


@router.get("/admin")
def admin_analytics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "super_admin"])),
):
    """System-wide rollups + per-role staff counts. No aggregator framing."""
    batches = db.query(HoneyBatch).all()
    agg = aggregate_batches(batches)
    # Per-role staff counts (simple activity proxy) — users by role + farmer count.
    role_counts: dict[str, int] = {}
    for (role,) in db.query(User.role).all():
        role_counts[role] = role_counts.get(role, 0) + 1
    role_counts["farmer"] = db.query(Farmer).count()
    agg["staff_by_role"] = role_counts
    return agg
