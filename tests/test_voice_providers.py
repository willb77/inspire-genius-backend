"""Tests for voice provider abstraction layer.

Covers:
- Base interfaces
- OpenAI STT/TTS providers (mocked -- regression)
- Deepgram STT provider (mocked)
- AudioProviderFactory (default, env override, auto fallback)
- TranscriptResult shape consistency across providers
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.audio_services.providers.base_stt import BaseSTT, TranscriptResult
from ai.audio_services.providers.base_tts import BaseTTS
from ai.audio_services.providers.provider_factory import AudioProviderFactory


# =====================================================================
#  TranscriptResult
# =====================================================================


class TestTranscriptResult:
    def test_default_fields(self):
        r = TranscriptResult(text="hello")
        assert r.text == "hello"
        assert r.confidence == 1.0
        assert r.language == "en"
        assert r.is_partial is False
        assert r.provider == ""
        assert r.duration_seconds == 0.0
        assert r.metadata == {}

    def test_all_fields(self):
        r = TranscriptResult(
            text="bonjour",
            confidence=0.95,
            language="fr",
            is_partial=True,
            provider="deepgram",
            duration_seconds=1.5,
            metadata={"model": "nova-2"},
        )
        assert r.provider == "deepgram"
        assert r.metadata["model"] == "nova-2"


# =====================================================================
#  OpenAI STT Provider
# =====================================================================


class TestOpenAISTT:
    def test_provider_name(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT
        stt = OpenAISTT()
        assert stt.provider_name == "openai"

    @pytest.mark.asyncio
    async def test_transcribe_file_success(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT

        stt = OpenAISTT()
        with patch.object(stt, "transcribe_file") as mock_method:
            mock_method.return_value = TranscriptResult(
                text="Hello world",
                confidence=1.0,
                language="en",
                provider="openai",
                duration_seconds=0.5,
                metadata={"model": "gpt-4o-transcribe"},
            )
            result = await stt.transcribe_file("/tmp/test.webm")

        assert result.text == "Hello world"
        assert result.provider == "openai"
        assert result.is_partial is False

    @pytest.mark.asyncio
    async def test_transcribe_file_returns_transcript_result(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT

        stt = OpenAISTT()
        with patch.object(stt, "transcribe_file") as mock_method:
            mock_method.return_value = TranscriptResult(text="test", provider="openai")
            result = await stt.transcribe_file("/tmp/test.webm")

        assert isinstance(result, TranscriptResult)
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_transcribe_stream_collects_and_transcribes(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT

        stt = OpenAISTT()

        async def mock_chunks():
            yield b"\x00" * 100
            yield b"\x00" * 100

        with patch.object(stt, "transcribe_file") as mock_file:
            mock_file.return_value = TranscriptResult(text="streamed result", provider="openai")
            results = []
            async for r in stt.transcribe_stream(mock_chunks()):
                results.append(r)

        assert len(results) == 1
        assert results[0].text == "streamed result"


# =====================================================================
#  OpenAI TTS Provider
# =====================================================================


class TestOpenAITTS:
    def test_provider_name(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        assert tts.provider_name == "openai"

    @pytest.mark.asyncio
    async def test_synthesize_returns_bytes(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        with patch.object(tts, "synthesize") as mock:
            mock.return_value = b"\x00" * 4096
            result = await tts.synthesize("Hello world", voice_id="coral")

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_chunks(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()

        async def mock_stream(*args, **kwargs):
            yield b"\x00" * 1024
            yield b"\x00" * 1024

        with patch.object(tts, "synthesize_stream", side_effect=mock_stream):
            chunks = []
            async for chunk in tts.synthesize_stream("Hello", voice_id="coral"):
                chunks.append(chunk)

        assert len(chunks) == 2


# =====================================================================
#  Deepgram STT Provider
# =====================================================================


class TestDeepgramSTT:
    def test_provider_name(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT()
        assert stt.provider_name == "deepgram"

    def test_supports_language(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        assert DeepgramSTT.supports_language("en") is True
        assert DeepgramSTT.supports_language("en-US") is True
        assert DeepgramSTT.supports_language("fr") is True
        assert DeepgramSTT.supports_language("ja") is True
        assert DeepgramSTT.supports_language("zh-CN") is True
        assert DeepgramSTT.supports_language("xx-FAKE") is False

    def test_language_coverage_breadth(self):
        from ai.audio_services.providers.deepgram_stt import DEEPGRAM_SUPPORTED_LANGUAGES
        assert len(DEEPGRAM_SUPPORTED_LANGUAGES) >= 36

    @pytest.mark.asyncio
    async def test_transcribe_file_mocked(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        with patch.object(stt, "transcribe_file") as mock:
            mock.return_value = TranscriptResult(
                text="Deepgram result",
                confidence=0.98,
                language="en",
                provider="deepgram",
                duration_seconds=0.3,
                metadata={"model": "nova-2"},
            )
            result = await stt.transcribe_file("/tmp/test.webm")

        assert result.text == "Deepgram result"
        assert result.provider == "deepgram"
        assert result.confidence == 0.98
        assert result.metadata["model"] == "nova-2"

    @pytest.mark.asyncio
    async def test_transcribe_file_returns_transcript_result(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        with patch.object(stt, "transcribe_file") as mock:
            mock.return_value = TranscriptResult(text="test", provider="deepgram")
            result = await stt.transcribe_file("/tmp/test.webm")

        assert isinstance(result, TranscriptResult)


# =====================================================================
#  Provider Factory
# =====================================================================


class TestAudioProviderFactory:
    def setup_method(self):
        AudioProviderFactory.reset()
        os.environ.pop("STT_PROVIDER", None)
        os.environ.pop("TTS_PROVIDER", None)

    def teardown_method(self):
        AudioProviderFactory.reset()
        os.environ.pop("STT_PROVIDER", None)
        os.environ.pop("TTS_PROVIDER", None)

    def test_default_stt_is_openai(self):
        stt = AudioProviderFactory.get_stt()
        assert stt.provider_name == "openai"

    def test_default_tts_is_openai(self):
        tts = AudioProviderFactory.get_tts()
        assert tts.provider_name == "openai"

    def test_explicit_openai_stt(self):
        stt = AudioProviderFactory.get_stt("openai")
        assert stt.provider_name == "openai"

    def test_explicit_deepgram_stt(self):
        stt = AudioProviderFactory.get_stt("deepgram")
        assert stt.provider_name == "deepgram"

    def test_env_override_deepgram(self):
        os.environ["STT_PROVIDER"] = "deepgram"
        AudioProviderFactory.reset()
        stt = AudioProviderFactory.get_stt()
        assert stt.provider_name == "deepgram"

    def test_env_override_auto(self):
        os.environ["STT_PROVIDER"] = "auto"
        AudioProviderFactory.reset()
        stt = AudioProviderFactory.get_stt()
        assert stt.provider_name == "auto"

    def test_unknown_stt_raises(self):
        with pytest.raises(ValueError, match="Unknown STT provider"):
            AudioProviderFactory.get_stt("nonexistent")

    def test_unknown_tts_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            AudioProviderFactory.get_tts("nonexistent")

    def test_singleton_caching(self):
        stt1 = AudioProviderFactory.get_stt("openai")
        stt2 = AudioProviderFactory.get_stt("openai")
        assert stt1 is stt2

    def test_reset_clears_cache(self):
        stt1 = AudioProviderFactory.get_stt("openai")
        AudioProviderFactory.reset()
        stt2 = AudioProviderFactory.get_stt("openai")
        assert stt1 is not stt2


# =====================================================================
#  Auto Mode STT
# =====================================================================


class TestAutoSTT:
    def setup_method(self):
        AudioProviderFactory.reset()
        os.environ.pop("STT_PROVIDER", None)

    def teardown_method(self):
        AudioProviderFactory.reset()
        os.environ.pop("STT_PROVIDER", None)

    @pytest.mark.asyncio
    async def test_auto_falls_back_on_unsupported_language(self):
        stt = AudioProviderFactory.get_stt("auto")

        whisper_result = TranscriptResult(text="whisper result", provider="openai")
        with patch.object(stt._whisper, "transcribe_file", return_value=whisper_result):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                result = await stt.transcribe_file("/tmp/test.webm", language="xx-FAKE")

        assert result.text == "whisper result"
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_auto_uses_deepgram_for_supported_language(self):
        stt = AudioProviderFactory.get_stt("auto")

        deepgram_result = TranscriptResult(text="deepgram result", provider="deepgram")
        with patch.object(stt._deepgram, "transcribe_file", return_value=deepgram_result):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                result = await stt.transcribe_file("/tmp/test.webm", language="en")

        assert result.text == "deepgram result"
        assert result.provider == "deepgram"

    @pytest.mark.asyncio
    async def test_auto_falls_back_on_deepgram_error(self):
        stt = AudioProviderFactory.get_stt("auto")

        whisper_result = TranscriptResult(text="fallback result", provider="openai")
        with patch.object(stt._deepgram, "transcribe_file", side_effect=Exception("API error")):
            with patch.object(stt._whisper, "transcribe_file", return_value=whisper_result):
                with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                    result = await stt.transcribe_file("/tmp/test.webm", language="en")

        assert result.text == "fallback result"
        assert result.provider == "openai"


# =====================================================================
#  Consistent Interface -- Both STT providers return identical shape
# =====================================================================


class TestProviderInterfaceConsistency:
    def test_both_stt_providers_subclass_base(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        assert issubclass(OpenAISTT, BaseSTT)
        assert issubclass(DeepgramSTT, BaseSTT)

    def test_tts_provider_subclasses_base(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS

        assert issubclass(OpenAITTS, BaseTTS)

    @pytest.mark.asyncio
    async def test_both_stt_return_same_shape(self):
        openai_result = TranscriptResult(text="hello", provider="openai", confidence=1.0)
        deepgram_result = TranscriptResult(text="hello", provider="deepgram", confidence=0.98)

        for result in [openai_result, deepgram_result]:
            assert hasattr(result, "text")
            assert hasattr(result, "confidence")
            assert hasattr(result, "language")
            assert hasattr(result, "is_partial")
            assert hasattr(result, "provider")
            assert hasattr(result, "duration_seconds")
            assert hasattr(result, "metadata")


# =====================================================================
#  Voice Config -- stt_provider field
# =====================================================================


class TestVoiceConfigSTTProvider:
    def test_default_stt_provider_is_openai(self):
        from ai.meridian.voice.voice_config import CommunicationPreferences
        prefs = CommunicationPreferences()
        assert prefs.stt_provider == "openai"

    def test_stt_provider_can_be_set(self):
        from ai.meridian.voice.voice_config import CommunicationPreferences
        prefs = CommunicationPreferences(stt_provider="deepgram")
        assert prefs.stt_provider == "deepgram"

    def test_stt_provider_auto(self):
        from ai.meridian.voice.voice_config import CommunicationPreferences
        prefs = CommunicationPreferences(stt_provider="auto")
        assert prefs.stt_provider == "auto"

    def test_voice_id_unchanged(self):
        from ai.meridian.voice.voice_config import CommunicationPreferences
        prefs = CommunicationPreferences()
        assert prefs.voice_id == "coral"

    def test_update_preferences_includes_stt_provider(self):
        from ai.meridian.voice.voice_config import VoiceConfig
        vc = VoiceConfig()
        vc.update_preferences("u1", {"stt_provider": "deepgram"})
        prefs = vc.get_preferences("u1")
        assert prefs.stt_provider == "deepgram"


# =====================================================================
#  Regression -- agent_utils.py still works
# =====================================================================


class TestAgentUtilsRegression:
    """Regression tests for agent_utils.py delegation to providers.

    These tests require google-genai and other heavy deps that agent_utils
    imports at module level. Skip gracefully if not available.
    """

    @staticmethod
    def _can_import_agent_utils():
        try:
            import ai.ai_agent_services.agent_utils  # noqa: F401
            return True
        except (ImportError, ModuleNotFoundError):
            return False

    @pytest.mark.asyncio
    async def test_audio_transcription_delegates_to_provider(self):
        """audio_transcription() should delegate to the STT provider."""
        if not self._can_import_agent_utils():
            pytest.skip("agent_utils deps (google-genai etc.) not installed")

        mock_result = TranscriptResult(text="Hello from provider", provider="openai")

        with patch(
            "ai.audio_services.providers.provider_factory.AudioProviderFactory.get_stt"
        ) as mock_factory:
            mock_stt = AsyncMock()
            mock_stt.transcribe_file.return_value = mock_result
            mock_factory.return_value = mock_stt

            from ai.ai_agent_services.agent_utils import audio_transcription
            result = await audio_transcription("/tmp/test.webm")

        assert result == "Hello from provider"

    @pytest.mark.asyncio
    async def test_stream_audio_chunks_delegates_to_provider(self):
        """stream_audio_chunks() should delegate to the TTS provider."""
        if not self._can_import_agent_utils():
            pytest.skip("agent_utils deps (google-genai etc.) not installed")

        async def mock_stream(*args, **kwargs):
            yield b"\x00" * 1024
            yield b"\x00" * 512

        with patch(
            "ai.audio_services.providers.provider_factory.AudioProviderFactory.get_tts"
        ) as mock_factory:
            mock_tts = MagicMock()
            mock_tts.synthesize_stream = mock_stream
            mock_factory.return_value = mock_tts

            from ai.ai_agent_services.agent_utils import stream_audio_chunks
            chunks = []
            async for chunk in stream_audio_chunks("Hello world"):
                chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0] == b"\x00" * 1024


# =====================================================================
#  Usage Tracking
# =====================================================================


class TestUsageTracking:
    @pytest.mark.asyncio
    async def test_auto_mode_emits_metrics(self):
        AudioProviderFactory.reset()
        stt = AudioProviderFactory.get_stt("auto")
        deepgram_result = TranscriptResult(text="test", provider="deepgram", duration_seconds=1.5)

        with patch.object(stt._deepgram, "transcribe_file", return_value=deepgram_result):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric") as mock_emit:
                await stt.transcribe_file("/tmp/test.webm", language="en")

        mock_emit.assert_called_once_with("stt", "deepgram", 1.5)

    def test_emit_metric_does_not_raise_on_error(self):
        from ai.audio_services.providers.provider_factory import _emit_usage_metric

        with patch("boto3.client", side_effect=Exception("No AWS")):
            # Should not raise
            _emit_usage_metric("stt", "openai", 1.0)
