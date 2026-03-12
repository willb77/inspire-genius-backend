# Import all models so they are registered with SQLAlchemy
from ai.models.agents import (
    Accent,
    Agent,
    Category,
    CategoryTypeEnum,
    Tone,
    UserPreference,
    UserAgentAssignment,
)
from ai.models.chat import (
    AlexChatMessage,
    AudioTypeEnum,
    ChatMessage,
    Conversation,
    ConversationStatusEnum,
    MessageStatusEnum,
    MessageTypeEnum,
)
from ai.models.files import File
from ai.models.frontend_text import FrontendText

__all__ = [
    "Category",
    "Accent",
    "Tone",
    "Agent",
    "UserPreference",
    "UserAgentAssignment",
    "File",
    "Conversation",
    "ChatMessage",
    "ConversationStatusEnum",
    "MessageTypeEnum",
    "MessageStatusEnum",
    "AudioTypeEnum",
    "AlexChatMessage",
    "CategoryTypeEnum",
    "FrontendText",
]