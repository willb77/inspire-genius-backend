"""OpenAI gpt-4o-mini-tts TTS provider."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from ai.audio_services.providers.base_tts import BaseTTS

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = "US/English"


class OpenAITTS(BaseTTS):
    """
    TTS via OpenAI gpt-4o-mini-tts.

    Wraps the existing TTS calls from agent_utils.py behind the BaseTTS
    interface. This is the only TTS provider — no alternatives.
    """

    @property
    def provider_name(self) -> str:
        return "openai"

    async def synthesize(self, text: str, voice_id: str = "coral", **kwargs) -> bytes:
        """Synthesize text to audio bytes using OpenAI TTS."""
        from prism_inspire.core.ai_client import openai

        instructions = kwargs.get("instructions", "")
        accent = kwargs.get("accent", DEFAULT_ACCENT)
        tone = kwargs.get("tone", "Warm")
        response_format = kwargs.get("response_format", "wav")
        speed = kwargs.get("speed", 1)

        formatted_instructions = instructions.format(accent=accent, tone=tone) if instructions else ""

        start = time.monotonic()
        buf = bytearray()

        try:
            async with openai.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice_id,
                instructions=formatted_instructions,
                input=text,
                response_format=response_format,
                speed=speed,
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=65536):
                    if chunk:
                        buf.extend(chunk)

            duration = time.monotonic() - start
            logger.debug(
                "OpenAI TTS synthesized %d bytes in %.2fs (voice=%s)",
                len(buf), duration, voice_id,
            )
            return bytes(buf)

        except Exception:
            logger.exception("OpenAI TTS synthesis failed")
            return b""

    async def synthesize_stream(
        self, text: str, voice_id: str = "coral", **kwargs
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks from OpenAI TTS."""
        from prism_inspire.core.ai_client import openai

        instructions = kwargs.get("instructions", "")
        accent = kwargs.get("accent", DEFAULT_ACCENT)
        tone = kwargs.get("tone", "Warm")
        response_format = kwargs.get("response_format", "wav")
        speed = kwargs.get("speed", 1)

        formatted_instructions = instructions.format(accent=accent, tone=tone) if instructions else ""

        try:
            async with openai.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice_id,
                instructions=formatted_instructions,
                input=text,
                response_format=response_format,
                speed=speed,
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=65536):
                    if chunk:
                        yield chunk
                        await asyncio.sleep(0.001)
        except Exception:
            logger.exception("OpenAI TTS streaming failed")
