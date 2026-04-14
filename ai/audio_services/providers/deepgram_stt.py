"""Deepgram Nova-2 streaming STT provider."""
from __future__ import annotations

import logging
import os
import time
from typing import AsyncIterator

from ai.audio_services.providers.base_stt import BaseSTT, TranscriptResult

logger = logging.getLogger(__name__)

# Deepgram supports 36+ languages — these are primary ones for routing decisions
DEEPGRAM_SUPPORTED_LANGUAGES = {
    "en", "en-US", "en-GB", "en-AU", "en-IN",
    "es", "es-ES", "es-419",
    "fr", "fr-FR", "fr-CA",
    "de", "de-DE",
    "pt", "pt-BR", "pt-PT",
    "it", "it-IT",
    "nl", "nl-NL",
    "ja", "ja-JP",
    "ko", "ko-KR",
    "zh", "zh-CN", "zh-TW",
    "ru", "ru-RU",
    "hi", "hi-IN",
    "ar", "ar-SA",
    "sv", "sv-SE",
    "pl", "pl-PL",
    "da", "da-DK",
    "fi", "fi-FI",
    "no", "no-NO",
    "tr", "tr-TR",
    "uk", "uk-UA",
    "id", "id-ID",
    "ms", "ms-MY",
    "th", "th-TH",
    "vi", "vi-VN",
    "cs", "cs-CZ",
    "ro", "ro-RO",
    "el", "el-GR",
    "bg", "bg-BG",
    "ta", "ta-IN",
}


def _get_deepgram_api_key() -> str:
    """Retrieve Deepgram API key from environment."""
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        # Try Secrets Manager ARN pattern
        arn = os.environ.get("DEEPGRAM_API_KEY_ARN", "")
        if arn:
            try:
                import boto3
                client = boto3.client("secretsmanager")
                response = client.get_secret_value(SecretId=arn)
                key = response.get("SecretString", "")
            except Exception:
                logger.exception("Failed to retrieve Deepgram API key from Secrets Manager")
    return key


class DeepgramSTT(BaseSTT):
    """
    STT via Deepgram Nova-2 with real-time streaming support.

    Features:
    - WebSocket streaming with partial results (interim_results)
    - smart_format + punctuate for clean output
    - Automatic language detection (36+ languages)
    - Speaker diarization support
    """

    @property
    def provider_name(self) -> str:
        return "deepgram"

    @staticmethod
    def supports_language(language: str) -> bool:
        """Check if Deepgram supports a given language code."""
        return language in DEEPGRAM_SUPPORTED_LANGUAGES

    async def transcribe_file(self, audio_file: str, **kwargs) -> TranscriptResult:
        """Transcribe an audio file using Deepgram Nova-2."""
        try:
            from deepgram import DeepgramClient, PrerecordedOptions

            api_key = _get_deepgram_api_key()
            if not api_key:
                raise ValueError("Deepgram API key not configured")

            client = DeepgramClient(api_key)

            with open(audio_file, "rb") as f:
                audio_data = f.read()

            start = time.monotonic()

            language = kwargs.get("language", "en")
            options = PrerecordedOptions(
                model="nova-2",
                smart_format=True,
                punctuate=True,
                diarize=kwargs.get("diarize", False),
                language=language if language != "auto" else None,
                detect_language=language == "auto",
            )

            source = {"buffer": audio_data, "mimetype": _guess_mimetype(audio_file)}
            response = client.listen.rest.v("1").transcribe_file(source, options)

            duration = time.monotonic() - start

            # Extract result from Deepgram response
            result = response.results
            if result and result.channels and result.channels[0].alternatives:
                alt = result.channels[0].alternatives[0]
                detected_lang = (
                    result.channels[0].detected_language
                    if hasattr(result.channels[0], "detected_language")
                    else language
                )
                return TranscriptResult(
                    text=alt.transcript,
                    confidence=alt.confidence,
                    language=detected_lang or language,
                    is_partial=False,
                    provider=self.provider_name,
                    duration_seconds=duration,
                    metadata={
                        "model": "nova-2",
                        "words": len(alt.words) if hasattr(alt, "words") and alt.words else 0,
                    },
                )

            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_partial=False,
                provider=self.provider_name,
                duration_seconds=duration,
            )

        except ImportError:
            logger.error("deepgram-sdk not installed — pip install deepgram-sdk")
            raise
        except Exception:
            logger.exception("Deepgram STT file transcription failed")
            raise

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], **kwargs
    ) -> AsyncIterator[TranscriptResult]:
        """
        Real-time streaming transcription via Deepgram WebSocket.

        Yields partial results as they arrive and a final result on stream end.
        """
        try:
            from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

            api_key = _get_deepgram_api_key()
            if not api_key:
                raise ValueError("Deepgram API key not configured")

            client = DeepgramClient(api_key)
            language = kwargs.get("language", "en")

            options = LiveOptions(
                model="nova-2",
                smart_format=True,
                punctuate=True,
                interim_results=True,
                diarize=kwargs.get("diarize", False),
                language=language if language != "auto" else None,
                detect_language=language == "auto",
                encoding="linear16",
                sample_rate=kwargs.get("sample_rate", 16000),
                channels=1,
            )

            connection = client.listen.live.v("1")

            import asyncio
            results_queue: asyncio.Queue[TranscriptResult] = asyncio.Queue()

            def on_message(self_ws, result, **kw):
                alt = result.channel.alternatives[0] if result.channel.alternatives else None
                if alt and alt.transcript:
                    results_queue.put_nowait(TranscriptResult(
                        text=alt.transcript,
                        confidence=alt.confidence,
                        language=language,
                        is_partial=result.is_final is False,
                        provider="deepgram",
                        metadata={"speech_final": result.speech_final if hasattr(result, "speech_final") else False},
                    ))

            connection.on(LiveTranscriptionEvents.Transcript, on_message)
            connection.start(options)

            # Feed audio chunks
            async for chunk in audio_chunks:
                connection.send(chunk)

            connection.finish()

            # Drain results
            while not results_queue.empty():
                yield results_queue.get_nowait()

        except ImportError:
            logger.error("deepgram-sdk not installed")
            raise
        except Exception:
            logger.exception("Deepgram STT streaming failed")
            raise


def _guess_mimetype(filepath: str) -> str:
    """Guess MIME type from file extension."""
    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "webm": "audio/webm",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
    }.get(ext, "audio/wav")
