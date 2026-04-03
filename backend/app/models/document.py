from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    doc_type = Column(String, nullable=True)  # e.g., license, certificate

    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=True)
    aggregator_id = Column(Integer, ForeignKey("aggregators.id"), nullable=True)

    farmer = relationship("Farmer", back_populates="documents")
    aggregator = relationship("Aggregator", back_populates="documents")