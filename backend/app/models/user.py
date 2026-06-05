from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship # type: ignore    
from sqlalchemy.sql import func                                                                                             
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    phone = Column(String, unique=True)
    password = Column(String)
    role = Column(String)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())