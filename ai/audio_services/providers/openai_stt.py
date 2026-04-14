"""OpenAI Whisper (gpt-4o-transcribe) STT provider."""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from ai.audio_services.providers.base_stt import BaseSTT, TranscriptResult

logger = logging.getLogger(__name__)


class OpenAISTT(BaseSTT):
    """
    STT via OpenAI gpt-4o-transcribe (Whisper).

    Wraps the existing transcription calls from agent_utils.py behind
    the BaseSTT interface. Default provider — no disruption to callers.
    """

    @property
    def provider_name(self) -> str:
        return "openai"

    async def transcribe_file(self, audio_file: str, **kwargs) -> TranscriptResult:
        """Transcribe an audio file using OpenAI gpt-4o-transcribe."""
        from prism_inspire.core.ai_client import openai

        start = time.monotonic()
        file = open(audio_file, "rb")
        try:
            model = kwargs.get("model", "gpt-4o-transcribe")
            transcription = await openai.audio.transcriptions.create(
                model=model,
                file=file,
                response_format="text",
            )

            duration = time.monotonic() - start

            if isinstance(transcription, str) and transcription.strip():
                text = transcription
            elif isinstance(transcription, dict) and "text" in transcription:
                text = transcription["text"]
            else:
                text = ""

            return TranscriptResult(
                text=text,
                confidence=1.0,  # Whisper doesn't return confidence
                language=kwargs.get("language", "en"),
                is_partial=False,
                provider=self.provider_name,
                duration_seconds=duration,
                metadata={"model": model},
            )
        except Exception as e:
            logger.exception("OpenAI STT transcription failed")
            raise Exception("Can you please repeat that?") from e
        finally:
            file.close()

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], **kwargs
    ) -> AsyncIterator[TranscriptResult]:
        """
        OpenAI Whisper doesn't support real-time streaming natively.

        Collects chunks into a buffer and transcribes on flush.
        For true streaming, use Deepgram.
        """
        import tempfile
        import os

        buf = bytearray()
        async for chunk in audio_chunks:
            buf.extend(chunk)

        if not buf:
            return

        # Write to temp file and transcribe
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(bytes(buf))
            temp_path = f.name

        try:
            result = await self.transcribe_file(temp_path, **kwargs)
            yield result
        finally:
            os.unlink(temp_path)
