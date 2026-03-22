import enum
import uuid

from sqlalchemy import (
    Column, String, Boolean, DateTime,
    Text, Enum, ForeignKey, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base

USER_ID = "users.user_id"


class CreditTransactionTypeEnum(enum.Enum):
    PURCHASE = "purchase"
    ALLOCATION = "allocation"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


class DistributorTerritory(Base):
    __tablename__ = "distributor_territories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distributor_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    name = Column(String(200), nullable=False)
    region = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    distributor = relationship("Users", foreign_keys=[distributor_id])


class DistributorPractitioner(Base):
    __tablename__ = "distributor_practitioners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distributor_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    practitioner_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), default="active")
    onboarded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    distributor = relationship("Users", foreign_keys=[distributor_id])
    practitioner = relationship("Users", foreign_keys=[practitioner_id])


class DistributorCredits(Base):
    __tablename__ = "distributor_credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distributor_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    total_purchased = Column(Numeric(10, 2), default=0)
    total_allocated = Column(Numeric(10, 2), default=0)
    total_used = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )

    distributor = relationship("Users", foreign_keys=[distributor_id])

    @property
    def available(self):
        """Credits available (purchased minus allocated and used)."""
        return (self.total_purchased or 0) - (self.total_allocated or 0) - (self.total_used or 0)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distributor_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    practitioner_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=True,
    )
    transaction_type = Column(
        Enum(CreditTransactionTypeEnum, name="credit_transaction_type_enum"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=True)
    reference_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    distributor = relationship("Users", foreign_keys=[distributor_id])
    practitioner = relationship("Users", foreign_keys=[practitioner_id])
