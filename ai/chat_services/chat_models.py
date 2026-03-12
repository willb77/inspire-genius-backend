from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationStatus(str, Enum):
    active = "active"
    archived = "archived"
    paused = "paused"


class MessageType(str, Enum):
    user = "user"
    assistant = "assistant"


class MessageStatus(str, Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class AudioType(str, Enum):
    user_voice = "user_voice"
    assistant_voice = "assistant_voice"


# Request Models
class CreateConversationRequest(BaseModel):
    agent_id: Optional[UUID] = None
    title: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: str


class StartSessionRequest(BaseModel):
    agent_id: UUID
    conversation_id: Optional[UUID] = None  # If provided, resume existing; if None, create new
    title: Optional[str] = None  # Only used when creating new conversation


class StartSessionResponse(BaseModel):
    conversation_id: str
    title: str
    is_new: bool  # True if newly created, False if existing
    message_count: int
    created_at: datetime
    last_message_at: Optional[datetime] = None

    model_config = ConfigDict(json_encoders={UUID: str})


# Response Models
class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    user_id: UUID
    message_type: MessageType
    content: str
    audio_s3_key: Optional[str] = None
    audio_type: Optional[AudioType] = None
    audio_duration: Optional[int] = None
    has_audio: bool
    status: MessageStatus
    word_count: Optional[int] = None
    character_count: Optional[int] = None
    response_time_ms: Optional[int] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    sequence_number: int
    parent_message_id: Optional[UUID] = None
    sent_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    # ✅ Pydantic v2 config (replace the bad line)
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str}
    )


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    conversation_id: UUID
    total_count: int
    page: int
    page_size: int
    has_next: bool

    model_config = ConfigDict(json_encoders={UUID: str})