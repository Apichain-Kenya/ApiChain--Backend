from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime, timezone
from app.database import Base


class EthWallet(Base):
    __tablename__ = "eth_wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    user_role = Column(String, nullable=False)  # employee role, e.g. "farmer", "harvest_processor", "packager", or "distributor"
    wallet_address = Column(String, unique=True, nullable=False, index=True)
    encrypted_key = Column(Text, nullable=False)
    blockchain_role = Column(String, nullable=True)  # "BEEKEEPER" or "PROCESSOR"
    role_granted = Column(Boolean, default=False)
    role_tx_hash = Column(String, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
