from sqlalchemy import (
    Column, Integer, String, Boolean,
    DateTime, UniqueConstraint, func, ForeignKey
)
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base
from sqlalchemy.dialects.postgresql import UUID


class Question(Base):
    __tablename__ = "questions"
    id = Column(UUID(as_uuid=True), primary_key=True)
    content = Column(String(1000), nullable=False)  # questions
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )
