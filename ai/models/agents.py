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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from prism_inspire.db.base import Base


class CategoryTypeEnum(enum.Enum):
    File = "file"
    Agent = "agent"
    Both = "both"


class Category(Base):
    __tablename__ = "categories"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    display_name = Column(String(150), nullable=True)
    type = Column(String, nullable=False, default=CategoryTypeEnum.Both.value)
    files = relationship("File", back_populates="category")
    agents = relationship("Agent", back_populates="category")
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)


class Accent(Base):
    __tablename__ = "accents"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    user_preferences = relationship("UserPreference", back_populates="accent")


class Tone(Base):
    __tablename__ = "tones"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    # Many-to-many relationship with UserPreference through UserPreferenceTone
    user_preferences = relationship("UserPreferenceTone", back_populates="tone")


class Gender(Base):
    __tablename__ = "genders"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    user_preferences = relationship("UserPreference", back_populates="gender")


class Prompt(Base):
    __tablename__ = "prompts"
    id = Column(UUID(as_uuid=True), primary_key=True)
    prompt = Column(String, nullable=False)  # The actual prompt text
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    agent = relationship("Agent", back_populates="prompts")  # Relationship to Agent
    user_preferences = relationship("UserPreference", back_populates="prompt")


class Agent(Base):
    __tablename__ = "agents"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    type = Column(
        String(50), nullable=True, default="predefined"
    )  # "custom" or "predefined"
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_active = Column(Boolean, default=True)
    information = Column(String(255), nullable = True)
    category = relationship("Category", back_populates="agents")
    user_preferences = relationship("UserPreference", back_populates="agent")
    # Add backref for prompts if you need to access prompts directly from an agent instance
    prompts = relationship("Prompt", back_populates="agent")


class UserPreference(Base):
    __tablename__ = "user_preferences"
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    accent_id = Column(UUID(as_uuid=True), ForeignKey("accents.id"), nullable=True)
    gender_id = Column(UUID(as_uuid=True), ForeignKey("genders.id"), nullable=True)
    prompt_id = Column(
        UUID(as_uuid=True), ForeignKey("prompts.id"), nullable=True
    )  # New field for selected prompt
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="user_agent_unique"),
    )

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    agent = relationship("Agent", back_populates="user_preferences")
    accent = relationship("Accent", back_populates="user_preferences")
    gender = relationship("Gender", back_populates="user_preferences")
    prompt = relationship(
        "Prompt", back_populates="user_preferences"
    )  # New relationship
    # Many-to-many relationship with Tone through UserPreferenceTone
    tones = relationship("UserPreferenceTone", back_populates="user_preference", cascade="all, delete-orphan")


class UserPreferenceTone(Base):
    """Junction table for many-to-many relationship between UserPreference and Tone"""
    __tablename__ = "user_preference_tones"
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_preference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_preferences.id", ondelete="CASCADE"),
        nullable=False
    )
    tone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tones.id", ondelete="CASCADE"),
        nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        UniqueConstraint("user_preference_id", "tone_id", name="user_pref_tone_unique"),
    )

    user_preference = relationship("UserPreference", back_populates="tones")
    tone = relationship("Tone", back_populates="user_preferences")


class UserAgentAssignment(Base):
    """
    Model to track custom agent assignments for specific users by super admin.
    This allows:
    - Assigning custom agents to users
    - Removing predefined agents from users
    - Controlling which agents a user can access
    """
    __tablename__ = "user_agent_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False
    )
    is_active = Column(Boolean, default=True)  # If False, this agent is explicitly removed for the user
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="user_agent_assignment_unique"),
    )
