"""
Distributor domain models — territories, credit allocation, transactions.
"""
import enum
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text,
    func, ForeignKey, Enum, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from prism_inspire.db.base import Base

USER_ID = "users.user_id"


class TransactionTypeEnum(enum.Enum):
    PURCHASE = "purchase"
    ALLOCATION = "allocation"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


class DistributorTerritory(Base):
    """A territory assigned to a distributor."""
    __tablename__ = "distributor_territories"

    id = Column(UUID(as_uuid=True), primary_key=True)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    region = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    distributor = relationship("Users", foreign_keys=[distributor_id])


class DistributorPractitioner(Base):
    """Relationship between a distributor and practitioners in their network."""
    __tablename__ = "distributor_practitioners"

    id = Column(UUID(as_uuid=True), primary_key=True)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    status = Column(String(20), default="active")  # active, suspended, terminated
    onboarded_at = Column(DateTime(timezone=True), default=func.now())
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    distributor = relationship("Users", foreign_keys=[distributor_id])
    practitioner = relationship("Users", foreign_keys=[practitioner_id])


class DistributorCredit(Base):
    """Credit ledger for a distributor — tracks purchased, allocated, available."""
    __tablename__ = "distributor_credits"

    id = Column(UUID(as_uuid=True), primary_key=True)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False, unique=True)
    total_purchased = Column(Numeric(10, 2), default=0)
    total_allocated = Column(Numeric(10, 2), default=0)
    total_used = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    distributor = relationship("Users", foreign_keys=[distributor_id])

    @property
    def available(self):
        return self.total_purchased - self.total_allocated


class CreditTransaction(Base):
    """Audit log of credit transactions for a distributor."""
    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=True)
    transaction_type = Column(
        Enum(TransactionTypeEnum, name="transaction_type_enum"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=True)
    reference_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    distributor = relationship("Users", foreign_keys=[distributor_id])
    practitioner = relationship("Users", foreign_keys=[practitioner_id])
