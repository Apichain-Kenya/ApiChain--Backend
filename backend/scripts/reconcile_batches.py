"""
Repair a `honey_batches` row that was orphaned because the on-chain tx
succeeded but the local DB commit failed, or finished broadcasting but
the receipt arrived after the request timed out (Sprint 6 pending path).

Reads the authoritative state from the smart contract (state, 6 hashes,
6 block timestamps) and upserts a `HoneyBatch` row with what can be
recovered. The off-chain `*_data` JSON payloads cannot be recovered —
they never reached the DB and are not stored on-chain. Affected columns
will be left NULL.

Usage:
    python scripts/reconcile_batches.py <batch_id>
    python scripts/reconcile_batches.py 0xabc123...

Importable API (Sprint 6):
    reconcile_batch(db, batch_id) -> int
    reconcile_pending_batches(db) -> dict
The scheduler in `app/services/environment_scheduler.py` runs the latter
every 60 s.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import or_, and_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.batch import HoneyBatch  # noqa: E402
from app.services.blockchain import blockchain_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reconcile_batches")

STATE_NAMES = ["CREATED", "HARVESTED", "PROCESSED", "LAB_VERIFIED", "PACKAGED", "DISTRIBUTED"]

# (tx_hash_column, timestamp_column) pairs — same order as STATE_NAMES.
# Used by `reconcile_pending_batches` to find rows where the tx was sent
# but the receipt has not yet been mirrored back into the DB.
_STAGE_TX_TS_PAIRS = (
    ("create_tx_hash", "created_at"),
    ("harvest_tx_hash", "harvested_at"),
    ("process_tx_hash", "processed_at"),
    ("lab_verify_tx_hash", "lab_verified_at"),
    ("packaging_tx_hash", "packaged_at"),
    ("distribution_tx_hash", "distributed_at"),
)


def _batch_id_to_bytes(batch_id: str) -> bytes:
    hex_part = batch_id[2:] if batch_id.startswith("0x") else batch_id
    return bytes.fromhex(hex_part)


def _ts_to_dt(ts: int):
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def reconcile_batch(db: Session, batch_id: str) -> int:
    """Mirror chain state for a single batch into the local DB.

    Returns 0 on success, non-zero error code matching the original CLI.
    Idempotent — only writes if there is something to mirror. Never calls
    a chain write function; this is strictly chain → DB.
    """
    if not blockchain_service.is_connected or blockchain_service.registry is None:
        logger.error("Blockchain unavailable — cannot reconcile %s", batch_id)
        return 2

    batch_id_bytes = _batch_id_to_bytes(batch_id)
    try:
        batch_data = blockchain_service.get_batch(batch_id_bytes)
        timeline = blockchain_service.get_batch_timeline(batch_id_bytes)
    except Exception as e:
        logger.error("Batch %s not found on chain: %s", batch_id, e)
        return 3

    state_idx = batch_data["state"]
    state_name = STATE_NAMES[state_idx] if 0 <= state_idx < len(STATE_NAMES) else str(state_idx)
    logger.info("On-chain state for %s: %s (idx %d)", batch_id, state_name, state_idx)

    try:
        row = (
            db.query(HoneyBatch)
            .filter(HoneyBatch.blockchain_batch_id == batch_id)
            .first()
        )
        if row is None:
            logger.info("No local row for %s — inserting orphan-repair row", batch_id)
            row = HoneyBatch(
                blockchain_batch_id=batch_id,
                farmer_id=0,
                current_state=state_name,
                created_at=_ts_to_dt(timeline.get("created_at")) or datetime.now(timezone.utc),
            )
            db.add(row)
        else:
            logger.info("Local row found for %s — mirroring chain state", batch_id)

        row.current_state = state_name
        if timeline.get("created_at"):
            row.created_at = _ts_to_dt(timeline["created_at"])
        row.harvested_at = _ts_to_dt(timeline.get("harvested_at"))
        row.processed_at = _ts_to_dt(timeline.get("processed_at"))
        row.lab_verified_at = _ts_to_dt(timeline.get("lab_verified_at"))
        row.packaged_at = _ts_to_dt(timeline.get("packaged_at"))
        row.distributed_at = _ts_to_dt(timeline.get("distributed_at"))

        db.commit()
        logger.info("Reconciled %s. Off-chain *_data payloads remain NULL (unrecoverable).", batch_id)
        return 0
    except Exception:
        db.rollback()
        logger.exception("Reconciliation failed for %s", batch_id)
        return 4


def reconcile_pending_batches(db: Optional[Session] = None) -> dict:
    """Scan for batches where a tx_hash is set but the matching timestamp
    is NULL, and try to mirror chain state for each.

    This is the auto-reconciler entry point invoked by apscheduler. It
    handles both Sprint 5 "DB commit failed after on-chain success"
    orphans and Sprint 6 "ReceiptPendingError returned HTTP 202" rows.

    Returns a summary dict for logging: `{scanned, reconciled, failed}`.
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    summary = {"scanned": 0, "reconciled": 0, "failed": 0}
    try:
        # Build OR-of-ANDs: any (tx_set AND timestamp_null) pair triggers a scan.
        pending_predicates = [
            and_(
                getattr(HoneyBatch, tx_col).isnot(None),
                getattr(HoneyBatch, ts_col).is_(None),
            )
            for tx_col, ts_col in _STAGE_TX_TS_PAIRS
        ]
        candidates = db.query(HoneyBatch).filter(or_(*pending_predicates)).all()
        summary["scanned"] = len(candidates)
        if not candidates:
            return summary

        logger.info("reconcile_pending_batches: %d candidate(s)", len(candidates))
        for row in candidates:
            rc = reconcile_batch(db, row.blockchain_batch_id)
            if rc == 0:
                summary["reconciled"] += 1
            else:
                summary["failed"] += 1
        return summary
    finally:
        if owns_session:
            db.close()


# Back-compat alias for the original CLI signature.
def reconcile(batch_id: str) -> int:
    db = SessionLocal()
    try:
        return reconcile_batch(db, batch_id)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id", help="The blockchain batch ID (0x... hex string)")
    args = parser.parse_args()
    return reconcile(args.batch_id)


if __name__ == "__main__":
    sys.exit(main())
