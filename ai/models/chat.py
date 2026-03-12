import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from prism_inspire.db.base import Base


class ConversationStatusEnum(enum.Enum):
    active = "active"
    archived = "archived"
    paused = "paused"


class MessageTypeEnum(enum.Enum):
    user = "user"
    assistant = "assistant"


class MessageStatusEnum(enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class AudioTypeEnum(enum.Enum):
    user_voice = "user_voice"
    assistant_voice = "assistant_voice"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    title = Column(String(255), nullable=True)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    status = Column(
        Enum(ConversationStatusEnum),
        nullable=False,
        default=ConversationStatusEnum.active,
    )
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    user = relationship("Users", backref="conversations")
    agent = relationship("Agent", backref="conversations")
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    @property
    def latest_message(self):
        if self.messages:
            return max(self.messages, key=lambda msg: msg.created_at)
        return None

    @property
    def is_active(self):
        return self.status == ConversationStatusEnum.active and not self.is_deleted


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True)

    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    message_type = Column(
        Enum(MessageTypeEnum), nullable=False, default=MessageTypeEnum.user
    )
    content = Column(Text, nullable=False)

    audio_s3_key = Column(String(500), nullable=True)
    audio_type = Column(Enum(AudioTypeEnum), nullable=True)
    audio_duration = Column(Integer, nullable=True)
    has_audio = Column(Boolean, default=False)

    status = Column(
        Enum(MessageStatusEnum), nullable=False, default=MessageStatusEnum.sent
    )
    word_count = Column(Integer, nullable=True)
    character_count = Column(Integer, nullable=True)

    response_time_ms = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)

    sequence_number = Column(Integer, nullable=False)

    parent_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    sent_at = Column(DateTime(timezone=True), default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "sequence_number", name="conversation_sequence_unique"
        ),
    )

    conversation = relationship("Conversation", back_populates="messages")
    user = relationship("Users", backref="chat_messages")
    parent_message = relationship("ChatMessage", remote_side=[id], backref="replies")

    @property
    def is_user_message(self):
        return self.message_type == MessageTypeEnum.user

    @property
    def is_assistant_message(self):
        return self.message_type == MessageTypeEnum.assistant

    @property
    def has_valid_audio(self):
        return self.has_audio and self.audio_s3_key and self.audio_type

    @property
    def is_read(self):
        return self.status == MessageStatusEnum.read or self.read_at is not None


class AlexChatMessage(Base):
    __tablename__ = "alex_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True)
    message_type = Column(
        Enum(MessageTypeEnum, name="message_type"),
        nullable=True,
        default=MessageTypeEnum.user,
    )
    device_key = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
