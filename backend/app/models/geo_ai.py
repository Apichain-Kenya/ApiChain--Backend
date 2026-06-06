# app/models/geo_ai.py
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship, backref
from datetime import datetime, timezone
from app.database import Base


class GeoAIPrediction(Base):
    __tablename__ = "geo_ai_predictions"

    id               = Column(Integer, primary_key=True, index=True)
    batch_id         = Column(Integer, ForeignKey("honey_batches.id"),
                              nullable=False, unique=True)

    predicted_moisture = Column(Float, nullable=True)
    predicted_sugar    = Column(Float, nullable=True)
    predicted_hmf      = Column(Float, nullable=True)
    confidence_score   = Column(Float, nullable=True)

    # Triangulation detail stored as plain text JSON
    region_detected      = Column(String, nullable=True)
    flowering_species    = Column(String, nullable=True)  # comma-separated
    triangulation_score  = Column(Float,  nullable=True)
    flora_match_score    = Column(Float,  nullable=True)
    dist_to_zone_km      = Column(Float,  nullable=True)
    n_flowering_species  = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    batch      = relationship("HoneyBatch", backref="geo_prediction")
    validation = relationship("ValidationResult", back_populates="prediction",
                              uselist=False, cascade="all, delete-orphan")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id              = Column(Integer, primary_key=True, index=True)
    batch_id        = Column(Integer, ForeignKey("honey_batches.id"),
                             nullable=False, unique=True)
    prediction_id   = Column(Integer, ForeignKey("geo_ai_predictions.id"),
                             nullable=False)

    authenticity_score = Column(Float,   nullable=True)
    is_valid           = Column(Boolean, default=False)
    # "verified" | "suspicious" | "flagged"
    validation_status  = Column(String,  nullable=True)

    phys_match_score   = Column(Float, nullable=True)
    triangulation_score = Column(Float, nullable=True)
    confidence_score   = Column(Float, nullable=True)

    validated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    batch      = relationship("HoneyBatch", backref=backref("validation", uselist=False))
    prediction = relationship("GeoAIPrediction", back_populates="validation")