import requests

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.apiary import ApiaryLocation
from app.models.environmental_data import EnvironmentalData


scheduler = BackgroundScheduler()


def fetch_all_environmental_data():

    db: Session = SessionLocal()

    try:
        apiaries = db.query(ApiaryLocation).all()

        for apiary in apiaries:

            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": apiary.latitude,
                    "longitude": apiary.longitude,
                    "current": ",".join([
                        "temperature_2m",
                        "relative_humidity_2m",
                        "rain",
                        "wind_speed_10m"
                    ])
                },
                timeout=10
            )

            data = response.json()

            current = data.get("current", {})

            env = EnvironmentalData(
                apiary_id=apiary.id,

                temperature=current.get("temperature_2m"),
                humidity=current.get("relative_humidity_2m"),
                rainfall=current.get("rain"),
                wind_speed=current.get("wind_speed_10m"),

                weather_source="open-meteo"
            )

            db.add(env)

        db.commit()

    finally:
        db.close()


def _reconcile_pending_batches_job():
    """Wrapper so an import-time failure of `reconcile_batches` (or a
    transient chain outage during a tick) cannot kill the scheduler."""
    try:
        # Lazy import — `scripts/` is added to sys.path by the module's own
        # bootstrap, but we should not couple service startup to that side
        # effect. Import inside the job keeps the dependency one-way.
        import logging
        import sys
        from pathlib import Path

        backend_root = Path(__file__).resolve().parent.parent.parent
        scripts_dir = backend_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from reconcile_batches import reconcile_pending_batches  # type: ignore

        summary = reconcile_pending_batches()
        if summary.get("scanned"):
            logging.getLogger(__name__).info(
                "reconciler tick: %s", summary
            )
    except Exception:
        logging.getLogger(__name__).exception("reconciler tick failed")


def start_scheduler():
    # Idempotent — under `uvicorn --reload` the lifespan handler can fire twice
    # for the same process. Re-entering would raise SchedulerAlreadyRunningError.
    if scheduler.running:
        return

    scheduler.add_job(
        fetch_all_environmental_data,
        "interval",
        hours=6,
        id="fetch_environmental_data",
        replace_existing=True,
    )

    # Sprint 6: auto-recovers batches stuck in pending_confirmation after the
    # request returned HTTP 202, and any pre-existing orphans from prior
    # "commit failed after on-chain success" paths.
    scheduler.add_job(
        _reconcile_pending_batches_job,
        "interval",
        seconds=60,
        id="reconcile_pending_batches",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)