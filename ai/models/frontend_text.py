import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from prism_inspire.db.base import Base


class FrontendText(Base):
    __tablename__ = "frontend_texts"
    id = Column(UUID(as_uuid=True), primary_key=True)
    selector = Column(String(200), nullable=True)
    routeKey = Column(String(200), nullable=True)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    meta_data = Column(JSON, nullable=True)
    comments = Column(Text, nullable=True)
