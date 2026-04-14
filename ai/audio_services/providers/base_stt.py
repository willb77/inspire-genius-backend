"""Abstract base class for Speech-to-Text providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class TranscriptResult:
    """Standardized transcription result from any STT provider."""
    text: str
    confidence: float = 1.0
    language: str = "en"
    is_partial: bool = False
    provider: str = ""
    duration_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


class BaseSTT(ABC):
    """Abstract STT provider interface."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g., 'openai', 'deepgram')."""
        ...

    @abstractmethod
    async def transcribe_file(self, audio_file: str, **kwargs) -> TranscriptResult:
        """
        Transcribe an audio file.

        Args:
            audio_file: Path to the audio file.
            **kwargs: Provider-specific options (language, model, etc.)

        Returns:
            TranscriptResult with the transcribed text.
        """
        ...

    @abstractmethod
    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], **kwargs
    ) -> AsyncIterator[TranscriptResult]:
        """
        Transcribe a stream of audio chunks in real-time.

        Args:
            audio_chunks: Async iterator yielding raw audio bytes.
            **kwargs: Provider-specific options.

        Yields:
            TranscriptResult for each partial or final segment.
        """
        ...
        # Make this an async generator so subclasses can use `yield`
        yield  # pragma: no cover
