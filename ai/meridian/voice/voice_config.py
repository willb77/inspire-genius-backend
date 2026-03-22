from __future__ import annotations

"""
Voice-First & Multi-Language Configuration.

Configurable parameters for TTS/STT integration and cultural adaptation.
Integrates with Nexus for cultural context and existing audio services.
"""

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


class FormalityLevel(str, Enum):
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FORMAL = "formal"


class DepthPreference(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


class EncouragementStyle(str, Enum):
    WARM = "warm"
    DIRECT = "direct"
    BALANCED = "balanced"


SUPPORTED_LANGUAGES = [
    "en", "es", "fr", "de", "pt", "zh-CN", "zh-TW", "ja",
    "ko", "ar", "hi", "ru", "it", "nl", "sv", "pl",
]

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "pt": "Portuguese", "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi",
    "ru": "Russian", "it": "Italian", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
}


class CommunicationPreferences(BaseModel):
    """User-level communication preferences for Meridian interactions."""
    language: str = "en"
    formality: FormalityLevel = FormalityLevel.PROFESSIONAL
    depth: DepthPreference = DepthPreference.STANDARD
    encouragement: EncouragementStyle = EncouragementStyle.BALANCED
    focus_area: Optional[str] = None  # e.g., "career", "learning", "resilience"
    cultural_context: Optional[str] = None  # country code for Nexus adaptation
    voice_enabled: bool = False
    voice_id: str = "coral"  # TTS voice (matches existing audio_services voices)
    accent: str = "US/English"
    tone: str = "Warm"


class VoiceConfig:
    """
    Manages voice-first and multi-language configuration.

    Integrates with:
    - Nexus for cultural adaptation
    - Existing audio_services for TTS/STT
    - User preferences for personalization
    """

    def __init__(self) -> None:
        self._user_prefs: dict[str, CommunicationPreferences] = {}

    def get_preferences(self, user_id: str) -> CommunicationPreferences:
        """Get communication preferences for a user."""
        return self._user_prefs.get(user_id, CommunicationPreferences())

    def update_preferences(
        self, user_id: str, updates: dict[str, Any]
    ) -> CommunicationPreferences:
        """Update communication preferences for a user."""
        prefs = self._user_prefs.get(user_id, CommunicationPreferences())
        for key, value in updates.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        self._user_prefs[user_id] = prefs
        logger.info(f"VoiceConfig: updated preferences for user {user_id}")
        return prefs

    def get_tts_params(self, user_id: str) -> dict[str, Any]:
        """Get TTS parameters for the audio service integration."""
        prefs = self.get_preferences(user_id)
        return {
            "voice": prefs.voice_id,
            "accent": prefs.accent,
            "tone": prefs.tone,
            "language": prefs.language,
        }

    def build_system_prompt_suffix(self, user_id: str) -> str:
        """Build a system prompt suffix based on user preferences."""
        prefs = self.get_preferences(user_id)
        parts = []

        if prefs.formality == FormalityLevel.CASUAL:
            parts.append("Use casual, conversational language.")
        elif prefs.formality == FormalityLevel.FORMAL:
            parts.append("Use formal, polished language appropriate for executive settings.")

        if prefs.depth == DepthPreference.BRIEF:
            parts.append("Keep responses concise — 2-3 sentences max.")
        elif prefs.depth == DepthPreference.DETAILED:
            parts.append("Provide thorough, detailed explanations with examples.")

        if prefs.encouragement == EncouragementStyle.WARM:
            parts.append("Be extra encouraging and affirming.")
        elif prefs.encouragement == EncouragementStyle.DIRECT:
            parts.append("Be direct and straightforward — skip the fluff.")

        if prefs.language != "en":
            lang_name = LANGUAGE_NAMES.get(prefs.language, prefs.language)
            parts.append(f"Respond in {lang_name}.")

        if prefs.cultural_context:
            parts.append(f"Adapt communication style for {prefs.cultural_context} cultural context.")

        return " ".join(parts)

    @staticmethod
    def list_languages() -> list[dict[str, str]]:
        """List all supported languages."""
        return [{"code": code, "name": LANGUAGE_NAMES.get(code, code)} for code in SUPPORTED_LANGUAGES]
