"""
Repair a `honey_batches` row that was orphaned because the on-chain tx
succeeded but the local DB commit failed.

Reads the authoritative state from the smart contract (state, beekeeper,
6 hashes, 6 block timestamps) and upserts a `HoneyBatch` row with what
can be recovered. The off-chain `*_data` JSON payloads cannot be
recovered — they never reached the DB and are not stored on-chain.
Affected columns will be left NULL with a one-line note.

Usage:
    python scripts/reconcile_batches.py <batch_id>
    python scripts/reconcile_batches.py 0xabc123...
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models.batch import HoneyBatch  # noqa: E402
from app.services.blockchain import blockchain_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reconcile_batches")

STATE_NAMES = ["CREATED", "HARVESTED", "PROCESSED", "LAB_VERIFIED", "PACKAGED", "DISTRIBUTED"]


def _batch_id_to_bytes(batch_id: str) -> bytes:
    hex_part = batch_id[2:] if batch_id.startswith("0x") else batch_id
    return bytes.fromhex(hex_part)


def _ts_to_dt(ts: int):
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def reconcile(batch_id: str) -> int:
    if not blockchain_service.is_connected or blockchain_service.registry is None:
        logger.error("Blockchain unavailable — cannot reconcile")
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

    db = SessionLocal()
    try:
        row = (
            db.query(HoneyBatch)
            .filter(HoneyBatch.blockchain_batch_id == batch_id)
            .first()
        )
        if row is None:
            logger.info("No local row found — inserting new orphan-repair row")
            row = HoneyBatch(
                blockchain_batch_id=batch_id,
                farmer_id=0,  # unknown — off-chain link broken
                current_state=state_name,
                created_at=_ts_to_dt(timeline.get("created_at")) or datetime.now(timezone.utc),
            )
            db.add(row)
        else:
            logger.info("Local row found — updating mirrored columns")

        row.current_state = state_name
        # Timestamps from chain
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
        logger.exception("Reconciliation failed")
        return 4
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id", help="The blockchain batch ID (0x... hex string)")
    args = parser.parse_args()
    return reconcile(args.batch_id)


if __name__ == "__main__":
    sys.exit(main())
