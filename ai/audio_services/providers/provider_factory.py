"""Audio provider factory — selects STT/TTS provider based on config.

Provider resolution order (highest → lowest priority):
    1. system_config table (DB) — updated via PUT /v1/admin/voice-config
    2. Environment variables: STT_PROVIDER / TTS_PROVIDER
    3. Hard default: openai

STT_PROVIDER valid values: openai | deepgram | auto (default: openai)
TTS_PROVIDER valid values: openai (default, only option for now)

'auto' mode: Uses Deepgram for STT, falls back to Whisper on error or
if the requested language is not in Deepgram's coverage.
"""
from __future__ import annotations

import logging
import os
import time

from ai.audio_services.providers.base_stt import BaseSTT, TranscriptResult
from ai.audio_services.providers.base_tts import BaseTTS

logger = logging.getLogger(__name__)

# Lazy-initialized singletons
_stt_instances: dict[str, BaseSTT] = {}
_tts_instances: dict[str, BaseTTS] = {}

# DB config cache — refreshed every 60 seconds
_DB_CACHE_TTL = 60.0
_db_cache: dict[str, str] = {}
_db_cache_ts: float = 0.0


def _load_db_config() -> dict[str, str]:
    """Load STT/TTS provider values from system_config table (cached 60 s)."""
    global _db_cache, _db_cache_ts
    now = time.monotonic()
    if now - _db_cache_ts < _DB_CACHE_TTL:
        return _db_cache
    try:
        from prism_inspire.db.session import ScopedSession
        from ai.audio_services.system_config_model import SystemConfig

        session = ScopedSession()
        try:
            rows = (
                session.query(SystemConfig)
                .filter(SystemConfig.key.in_(["stt_provider", "tts_provider"]))
                .all()
            )
            _db_cache = {row.key: row.value for row in rows}
            _db_cache_ts = now
        finally:
            session.close()
            ScopedSession.remove()
    except Exception:
        logger.debug("provider_factory: could not read DB config, using env/defaults", exc_info=True)
    return _db_cache


def invalidate_provider_cache() -> None:
    """Force next provider resolution to re-read DB config and reset instances."""
    global _db_cache_ts
    _db_cache_ts = 0.0
    _stt_instances.clear()
    _tts_instances.clear()


class AudioProviderFactory:
    """Factory for creating and selecting audio providers."""

    @staticmethod
    def get_stt(provider: str | None = None) -> BaseSTT:
        """
        Get an STT provider instance.

        Resolution order: explicit arg → DB config → STT_PROVIDER env var → 'openai'.

        Args:
            provider: Explicit provider name, or None to use configured value.

        Returns:
            A BaseSTT implementation.
        """
        if provider is None:
            db_cfg = _load_db_config()
            provider = db_cfg.get("stt_provider") or os.environ.get("STT_PROVIDER", "openai")

        name = provider
        if name == "auto":
            return _get_auto_stt()

        if name not in _stt_instances:
            _stt_instances[name] = _create_stt(name)
        return _stt_instances[name]

    @staticmethod
    def get_tts(provider: str | None = None) -> BaseTTS:
        """
        Get a TTS provider instance.

        Resolution order: explicit arg → DB config → TTS_PROVIDER env var → 'openai'.

        Args:
            provider: Explicit provider name, or None to use configured value.

        Returns:
            A BaseTTS implementation.
        """
        if provider is None:
            db_cfg = _load_db_config()
            provider = db_cfg.get("tts_provider") or os.environ.get("TTS_PROVIDER", "openai")

        name = provider
        if name not in _tts_instances:
            _tts_instances[name] = _create_tts(name)
        return _tts_instances[name]

    @staticmethod
    def reset() -> None:
        """Clear cached instances (for testing)."""
        _stt_instances.clear()
        _tts_instances.clear()


def _create_stt(name: str) -> BaseSTT:
    """Create an STT provider by name."""
    if name == "openai":
        from ai.audio_services.providers.openai_stt import OpenAISTT
        return OpenAISTT()
    elif name == "deepgram":
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        return DeepgramSTT()
    else:
        raise ValueError(f"Unknown STT provider: {name}. Available: openai, deepgram")


def _create_tts(name: str) -> BaseTTS:
    """Create a TTS provider by name."""
    if name == "openai":
        from ai.audio_services.providers.openai_tts import OpenAITTS
        return OpenAITTS()
    else:
        raise ValueError(f"Unknown TTS provider: {name}. Available: openai")


def _get_auto_stt() -> BaseSTT:
    """
    Auto-mode STT: returns DeepgramWithFallback that tries Deepgram first,
    falls back to Whisper on error or unsupported language.
    """
    if "auto" not in _stt_instances:
        _stt_instances["auto"] = _AutoSTT()
    return _stt_instances["auto"]


class _AutoSTT(BaseSTT):
    """Auto-mode STT — Deepgram primary, Whisper fallback."""

    def __init__(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        self._deepgram = DeepgramSTT()
        self._whisper = OpenAISTT()

    @property
    def provider_name(self) -> str:
        return "auto"

    async def transcribe_file(self, audio_file: str, **kwargs) -> TranscriptResult:
        language = kwargs.get("language", "en")

        # Check if Deepgram supports the language
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        if not DeepgramSTT.supports_language(language):
            logger.info("Auto STT: language %s not in Deepgram coverage, using Whisper", language)
            result = await self._whisper.transcribe_file(audio_file, **kwargs)
            _emit_usage_metric("stt", "openai", result.duration_seconds)
            return result

        # Try Deepgram first
        try:
            result = await self._deepgram.transcribe_file(audio_file, **kwargs)
            _emit_usage_metric("stt", "deepgram", result.duration_seconds)
            return result
        except Exception:
            logger.warning("Auto STT: Deepgram failed, falling back to Whisper", exc_info=True)
            result = await self._whisper.transcribe_file(audio_file, **kwargs)
            _emit_usage_metric("stt", "openai", result.duration_seconds)
            return result

    async def transcribe_stream(self, audio_chunks, **kwargs):
        language = kwargs.get("language", "en")

        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        if not DeepgramSTT.supports_language(language):
            async for result in self._whisper.transcribe_stream(audio_chunks, **kwargs):
                _emit_usage_metric("stt", "openai", result.duration_seconds)
                yield result
            return

        try:
            async for result in self._deepgram.transcribe_stream(audio_chunks, **kwargs):
                _emit_usage_metric("stt", "deepgram", result.duration_seconds)
                yield result
        except Exception:
            logger.warning("Auto STT stream: Deepgram failed, falling back to Whisper", exc_info=True)
            async for result in self._whisper.transcribe_stream(audio_chunks, **kwargs):
                _emit_usage_metric("stt", "openai", result.duration_seconds)
                yield result


def _emit_usage_metric(operation: str, provider: str, duration_seconds: float) -> None:
    """
    Emit CloudWatch custom metric for voice provider usage tracking.

    Metric: InspireGenius/Voice
    Dimensions: provider (openai|deepgram), operation (stt|tts)
    """
    try:
        import boto3
        cw = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        cw.put_metric_data(
            Namespace="InspireGenius/Voice",
            MetricData=[
                {
                    "MetricName": "RequestDuration",
                    "Value": duration_seconds,
                    "Unit": "Seconds",
                    "Dimensions": [
                        {"Name": "Provider", "Value": provider},
                        {"Name": "Operation", "Value": operation},
                    ],
                },
                {
                    "MetricName": "RequestCount",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "Provider", "Value": provider},
                        {"Name": "Operation", "Value": operation},
                    ],
                },
            ],
        )
    except Exception:
        # Best-effort metric emission — never fail the request
        logger.debug("Failed to emit voice usage metric", exc_info=True)
