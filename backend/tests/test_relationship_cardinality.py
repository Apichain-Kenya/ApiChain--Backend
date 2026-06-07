"""Guard: HoneyBatch.validation must be scalar (one-to-one), else build_batch_view
crashes on any batch that has a ValidationResult row."""
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import configure_mappers
from app.models.batch import HoneyBatch
from app.models import geo_ai  # noqa: F401  (registers the backref)


def test_validation_backref_is_scalar():
    configure_mappers()
    assert sa_inspect(HoneyBatch).relationships["validation"].uselist is False
