"""Abstract base class for Text-to-Speech providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseTTS(ABC):
    """Abstract TTS provider interface."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g., 'openai')."""
        ...

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str = "coral", **kwargs) -> bytes:
        """
        Synthesize text to audio bytes.

        Args:
            text: The text to synthesize.
            voice_id: Voice identifier.
            **kwargs: Provider-specific options (instructions, accent, tone, format, speed).

        Returns:
            Audio bytes in the requested format.
        """
        ...

    @abstractmethod
    async def synthesize_stream(
        self, text: str, voice_id: str = "coral", **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Stream synthesized audio chunks.

        Args:
            text: The text to synthesize.
            voice_id: Voice identifier.
            **kwargs: Provider-specific options.

        Yields:
            Audio byte chunks for streaming playback.
        """
        ...
        yield  # pragma: no cover
