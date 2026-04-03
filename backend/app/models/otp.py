from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base

class OTP(Base):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, default=datetime.utcnow)