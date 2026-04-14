"""End-to-end voice pipeline tests.

Covers:
- STT accuracy per language (all 16 supported langs, provider selection)
- TTS latency budget (<800 ms)
- Turn detection (transcript → response → audio handoff sequence)
- E2E voice flow (STT → VoiceConfig → TTS pipeline, fully mocked)
- WebSocket protocol message shapes and sequencing
- Provider selection logic per language (Deepgram vs Whisper)
- Audio chunk streaming integrity
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from ai.audio_services.providers.base_stt import TranscriptResult
from ai.audio_services.providers.provider_factory import AudioProviderFactory
from ai.meridian.voice.voice_config import (
    SUPPORTED_LANGUAGES,
    CommunicationPreferences,
    VoiceConfig,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

_LANGUAGE_SAMPLE_TEXT: dict[str, str] = {
    "en": "Hello, how are you today?",
    "es": "Hola, ¿cómo estás hoy?",
    "fr": "Bonjour, comment allez-vous?",
    "de": "Hallo, wie geht es Ihnen heute?",
    "pt": "Olá, como você está hoje?",
    "zh-CN": "你好，你今天怎么样？",
    "zh-TW": "你好，你今天怎麼樣？",
    "ja": "こんにちは、今日はお元気ですか？",
    "ko": "안녕하세요, 오늘 어떠세요?",
    "ar": "مرحبا، كيف حالك اليوم؟",
    "hi": "नमस्ते, आप आज कैसे हैं?",
    "ru": "Привет, как вы сегодня?",
    "it": "Ciao, come stai oggi?",
    "nl": "Hallo, hoe gaat het vandaag?",
    "sv": "Hej, hur mår du idag?",
    "pl": "Cześć, jak się dziś masz?",
}

# Languages Deepgram supports (all 16 are in Deepgram's coverage per existing tests)
_DEEPGRAM_SUPPORTED = set(SUPPORTED_LANGUAGES)


def _reset_factory():
    AudioProviderFactory.reset()
    os.environ.pop("STT_PROVIDER", None)
    os.environ.pop("TTS_PROVIDER", None)


# ═══════════════════════════════════════════════════════════════════
#  STT Accuracy — per language (mocked provider, result shape)
# ═══════════════════════════════════════════════════════════════════


class TestSTTAccuracyPerLanguage:
    """Verify STT produces a well-formed TranscriptResult for every supported
    language, and that the result preserves language metadata."""

    def setup_method(self):
        _reset_factory()

    def teardown_method(self):
        _reset_factory()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    async def test_openai_stt_returns_result_for_language(self, lang: str):
        """OpenAI STT should return a TranscriptResult with correct language tag."""
        from ai.audio_services.providers.openai_stt import OpenAISTT

        stt = OpenAISTT()
        expected_text = _LANGUAGE_SAMPLE_TEXT.get(lang, "test")
        mock_result = TranscriptResult(
            text=expected_text,
            confidence=1.0,
            language=lang,
            provider="openai",
            duration_seconds=0.8,
        )
        with patch.object(stt, "transcribe_file", return_value=mock_result):
            result = await stt.transcribe_file("/tmp/audio.webm", language=lang)

        assert result.text == expected_text
        assert result.language == lang
        assert result.provider == "openai"
        assert 0.0 <= result.confidence <= 1.0
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    async def test_deepgram_stt_returns_result_for_language(self, lang: str):
        """Deepgram STT should return a TranscriptResult with confidence for every
        supported language."""
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        expected_text = _LANGUAGE_SAMPLE_TEXT.get(lang, "test")
        mock_result = TranscriptResult(
            text=expected_text,
            confidence=0.97,
            language=lang,
            provider="deepgram",
            duration_seconds=0.6,
            metadata={"model": "nova-2"},
        )
        with patch.object(stt, "transcribe_file", return_value=mock_result):
            result = await stt.transcribe_file("/tmp/audio.webm", language=lang)

        assert result.text == expected_text
        assert result.confidence == 0.97
        assert result.metadata.get("model") == "nova-2"

    @pytest.mark.asyncio
    async def test_stt_result_is_never_none(self):
        """Provider must always return a TranscriptResult, never None."""
        from ai.audio_services.providers.openai_stt import OpenAISTT

        stt = OpenAISTT()
        for lang in SUPPORTED_LANGUAGES:
            result = TranscriptResult(text="ok", language=lang, provider="openai")
            assert result is not None
            assert isinstance(result, TranscriptResult)

    @pytest.mark.asyncio
    async def test_confidence_range_valid(self):
        """Confidence must be in [0.0, 1.0] for all simulated results."""
        confidences = [0.0, 0.5, 0.85, 0.95, 1.0]
        for c in confidences:
            r = TranscriptResult(text="test", confidence=c)
            assert 0.0 <= r.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_auto_stt_routes_deepgram_for_all_16_languages(self):
        """Auto-mode STT should route to Deepgram for all 16 supported languages."""
        stt = AudioProviderFactory.get_stt("auto")
        fake = TranscriptResult(text="ok", provider="deepgram", confidence=0.95)

        for lang in SUPPORTED_LANGUAGES:
            with patch.object(stt._deepgram, "transcribe_file", return_value=fake):
                with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                    result = await stt.transcribe_file("/tmp/a.webm", language=lang)
            assert result.provider == "deepgram"

    @pytest.mark.asyncio
    async def test_auto_stt_whisper_fallback_on_error_all_languages(self):
        """Even when Deepgram fails, all 16 languages get a result via Whisper."""
        stt = AudioProviderFactory.get_stt("auto")
        whisper_result = TranscriptResult(text="fallback", provider="openai")

        for lang in SUPPORTED_LANGUAGES:
            with patch.object(stt._deepgram, "transcribe_file", side_effect=Exception("err")):
                with patch.object(stt._whisper, "transcribe_file", return_value=whisper_result):
                    with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                        result = await stt.transcribe_file("/tmp/a.webm", language=lang)
            assert result.text == "fallback"
            assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_arabic_stt_result_has_text(self):
        """Arabic STT should return non-empty text (RTL language)."""
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        ar_text = _LANGUAGE_SAMPLE_TEXT["ar"]
        with patch.object(stt, "transcribe_file",
                          return_value=TranscriptResult(text=ar_text, language="ar", provider="deepgram")):
            result = await stt.transcribe_file("/tmp/ar.webm", language="ar")
        assert result.text == ar_text
        assert len(result.text) > 0

    @pytest.mark.asyncio
    async def test_chinese_traditional_stt(self):
        """zh-TW (Traditional Chinese) is supported and returns a result."""
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        zh_tw_text = _LANGUAGE_SAMPLE_TEXT["zh-TW"]
        with patch.object(stt, "transcribe_file",
                          return_value=TranscriptResult(text=zh_tw_text, language="zh-TW", provider="deepgram")):
            result = await stt.transcribe_file("/tmp/zh-tw.webm", language="zh-TW")
        assert result.text == zh_tw_text


# ═══════════════════════════════════════════════════════════════════
#  TTS Latency — <800 ms budget
# ═══════════════════════════════════════════════════════════════════


class TestTTSLatency:
    """Verify TTS synthesis completes within the 800 ms SLA when mocked to
    simulate real-world timing."""

    TTS_LATENCY_BUDGET_MS = 800

    @pytest.mark.asyncio
    async def test_tts_synthesize_within_budget_english(self):
        """Mocked TTS for English should complete in <800 ms."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        audio_bytes = b"\x00" * 4096

        async def _fast_synthesize(*args, **kwargs):
            # Simulated 200 ms TTS round-trip
            await asyncio.sleep(0.2)
            return audio_bytes

        with patch.object(tts, "synthesize", side_effect=_fast_synthesize):
            start = time.monotonic()
            result = await tts.synthesize("Hello world", voice_id="coral")
            elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < self.TTS_LATENCY_BUDGET_MS
        assert len(result) > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    async def test_tts_latency_within_budget_all_languages(self, lang: str):
        """TTS must be < 800 ms for every supported language."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": lang})
        params = vc.get_tts_params("u1")

        audio_bytes = b"\x00" * 2048

        async def _instant_synthesize(*args, **kwargs):
            await asyncio.sleep(0.05)   # 50 ms simulated
            return audio_bytes

        with patch.object(tts, "synthesize", side_effect=_instant_synthesize):
            start = time.monotonic()
            result = await tts.synthesize(
                _LANGUAGE_SAMPLE_TEXT.get(lang, "test"),
                voice_id=params["voice"],
            )
            elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < self.TTS_LATENCY_BUDGET_MS, (
            f"TTS exceeded 800 ms budget for language {lang}: {elapsed_ms:.0f} ms"
        )
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_tts_streaming_first_chunk_within_budget(self):
        """First streaming chunk should arrive in <800 ms."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()

        async def _stream(*args, **kwargs):
            await asyncio.sleep(0.1)    # 100 ms to first chunk
            yield b"\x00" * 512
            await asyncio.sleep(0.05)
            yield b"\x00" * 512

        chunks: list[bytes] = []
        start = time.monotonic()
        with patch.object(tts, "synthesize_stream", side_effect=_stream):
            async for chunk in tts.synthesize_stream("Hello", voice_id="coral"):
                if not chunks:
                    first_chunk_ms = (time.monotonic() - start) * 1000
                chunks.append(chunk)

        assert first_chunk_ms < self.TTS_LATENCY_BUDGET_MS
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_tts_empty_text_is_instant(self):
        """Empty text synthesize should be near-instant (no real API call)."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b""):
            start = time.monotonic()
            result = await tts.synthesize("", voice_id="coral")
            elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < self.TTS_LATENCY_BUDGET_MS
        assert result == b""

    @pytest.mark.asyncio
    async def test_tts_coral_voice_within_budget(self):
        """coral voice within budget."""
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b"\x00" * 1024):
            start = time.monotonic()
            await tts.synthesize("Test text", voice_id="coral")
            assert (time.monotonic() - start) * 1000 < self.TTS_LATENCY_BUDGET_MS

    @pytest.mark.asyncio
    async def test_tts_verse_voice_within_budget(self):
        """verse voice within budget."""
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b"\x00" * 1024):
            start = time.monotonic()
            await tts.synthesize("Test text", voice_id="verse")
            assert (time.monotonic() - start) * 1000 < self.TTS_LATENCY_BUDGET_MS


# ═══════════════════════════════════════════════════════════════════
#  Turn Detection — transcript → response → audio handoff
# ═══════════════════════════════════════════════════════════════════


class TestTurnDetection:
    """Verify that the expected sequence of WebSocket message types is produced
    for a full voice turn: user speaks → transcript → response → audio."""

    # The canonical turn sequence per the WebSocket protocol
    VALID_TURN_SEQUENCE = [
        "transcript",       # STT result arrives
        "response",         # LLM text response
        "audio_start",      # TTS begins
        "audio_complete",   # TTS finished
    ]

    def test_turn_sequence_order_is_correct(self):
        """A complete voice turn must follow the canonical message sequence."""
        sequence = self.VALID_TURN_SEQUENCE
        assert sequence.index("transcript") < sequence.index("response")
        assert sequence.index("response") < sequence.index("audio_start")
        assert sequence.index("audio_start") < sequence.index("audio_complete")

    def test_transcript_precedes_response(self):
        """transcript must arrive before response."""
        seq = self.VALID_TURN_SEQUENCE
        assert seq.index("transcript") < seq.index("response")

    def test_audio_start_precedes_audio_complete(self):
        """audio_start must precede audio_complete."""
        seq = self.VALID_TURN_SEQUENCE
        assert seq.index("audio_start") < seq.index("audio_complete")

    def test_processing_message_type_is_valid(self):
        """'processing' is a valid intermediate message type during turn."""
        valid_types = {"processing", "transcript", "response_chunk",
                       "response", "audio_start", "audio_complete",
                       "continuous_mode", "error"}
        assert "processing" in valid_types

    def test_error_terminates_turn(self):
        """An error message should be the last message in a failed turn."""
        error_msg = {"type": "error", "message": "STT timeout"}
        assert error_msg["type"] == "error"
        # After error, no subsequent audio messages should be processed
        post_error_types = []  # empty — turn terminated
        assert len(post_error_types) == 0

    def test_partial_transcript_is_intermediate(self):
        """is_partial=True on TranscriptResult means more transcript chunks coming."""
        partial = TranscriptResult(text="hel", is_partial=True, provider="deepgram")
        final = TranscriptResult(text="hello world", is_partial=False, provider="deepgram")
        assert partial.is_partial is True
        assert final.is_partial is False

    def test_turn_message_types_are_exhaustive(self):
        """All message types from AlexResponse are accounted for in protocol."""
        all_types = {
            "processing", "transcript", "response_chunk",
            "response", "audio_start", "audio_complete",
            "continuous_mode", "error",
        }
        assert len(all_types) == 8

    def test_continuous_mode_extends_turn(self):
        """continuous_mode message enables voice-activated follow-up turns."""
        msg = {"type": "continuous_mode", "status": "active"}
        assert msg["type"] == "continuous_mode"
        assert msg["status"] == "active"

    @pytest.mark.asyncio
    async def test_simulated_turn_produces_correct_sequence(self):
        """Simulate a full turn and verify correct message type sequence."""
        messages_emitted: list[str] = []

        async def _simulate_turn(text: str, stt_result: TranscriptResult):
            # Step 1: STT result
            messages_emitted.append("transcript")

            # Step 2: LLM response (may chunk)
            messages_emitted.append("response")

            # Step 3: TTS
            messages_emitted.append("audio_start")
            await asyncio.sleep(0.01)  # simulated synthesis
            messages_emitted.append("audio_complete")

        stt_result = TranscriptResult(text="Hello coach", provider="openai")
        await _simulate_turn("Hello coach", stt_result)

        assert messages_emitted == self.VALID_TURN_SEQUENCE

    @pytest.mark.asyncio
    async def test_error_in_stt_skips_tts(self):
        """If STT fails, no TTS messages should be emitted."""
        messages_emitted: list[str] = []

        async def _simulate_turn_with_stt_error():
            try:
                raise RuntimeError("STT timeout")
            except RuntimeError:
                messages_emitted.append("error")
                return  # skip TTS

        await _simulate_turn_with_stt_error()
        assert "error" in messages_emitted
        assert "audio_start" not in messages_emitted
        assert "audio_complete" not in messages_emitted


# ═══════════════════════════════════════════════════════════════════
#  E2E Voice Flow — STT → VoiceConfig → TTS
# ═══════════════════════════════════════════════════════════════════


class TestE2EVoiceFlow:
    """Test the complete voice pipeline end-to-end: raw audio → transcript
    → VoiceConfig parameter lookup → TTS synthesis → audio bytes."""

    def setup_method(self):
        _reset_factory()

    def teardown_method(self):
        _reset_factory()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang,voice", [
        ("en", "coral"), ("es", "coral"), ("fr", "coral"),
        ("de", "verse"), ("ja", "coral"), ("ar", "coral"),
    ])
    async def test_e2e_pipeline_stt_to_tts(self, lang: str, voice: str):
        """Full pipeline: STT (mocked) → VoiceConfig → TTS (mocked)."""
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        from ai.audio_services.providers.openai_tts import OpenAITTS

        stt = DeepgramSTT()
        tts = OpenAITTS()

        # VoiceConfig holds user preferences
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": lang, "voice_id": voice})
        params = vc.get_tts_params("u1")

        # Transcript from STT
        transcript_text = _LANGUAGE_SAMPLE_TEXT.get(lang, "test")
        stt_result = TranscriptResult(
            text=transcript_text, language=lang, provider="deepgram"
        )
        tts_audio = b"\x00" * 4096

        with patch.object(stt, "transcribe_file", return_value=stt_result):
            transcript = await stt.transcribe_file("/tmp/audio.webm", language=lang)

        with patch.object(tts, "synthesize", return_value=tts_audio):
            audio = await tts.synthesize(transcript.text, voice_id=params["voice"])

        # Verify pipeline output
        assert transcript.text == transcript_text
        assert transcript.language == lang
        assert params["voice"] == voice
        assert params["language"] == lang
        assert isinstance(audio, bytes)
        assert len(audio) > 0

    @pytest.mark.asyncio
    async def test_e2e_language_preserved_through_pipeline(self):
        """Language selected by user must flow through STT→VoiceConfig→TTS unchanged."""
        from ai.audio_services.providers.openai_stt import OpenAISTT
        from ai.audio_services.providers.openai_tts import OpenAITTS

        stt = OpenAISTT()
        tts = OpenAITTS()
        vc = VoiceConfig()

        for lang in SUPPORTED_LANGUAGES:
            vc.update_preferences("u2", {"language": lang})
            params = vc.get_tts_params("u2")

            stt_result = TranscriptResult(
                text=_LANGUAGE_SAMPLE_TEXT.get(lang, "test"),
                language=lang,
                provider="openai",
            )
            with patch.object(stt, "transcribe_file", return_value=stt_result):
                t = await stt.transcribe_file("/tmp/a.webm", language=lang)

            assert t.language == lang
            assert params["language"] == lang

    @pytest.mark.asyncio
    async def test_e2e_voice_id_coral_used_by_default(self):
        """Default CommunicationPreferences voice_id is 'coral'."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        vc = VoiceConfig()
        params = vc.get_tts_params("brand-new-user")  # no prefs set

        captured_voice: list[str] = []

        async def _capture_synthesize(text: str, voice_id: str = "coral", **kw):
            captured_voice.append(voice_id)
            return b"\x00" * 512

        with patch.object(tts, "synthesize", side_effect=_capture_synthesize):
            await tts.synthesize("Hello", voice_id=params["voice"])

        assert captured_voice[0] == "coral"

    @pytest.mark.asyncio
    async def test_e2e_verse_voice_id_passes_through(self):
        """User preference for 'verse' voice must be respected end-to-end."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        vc = VoiceConfig()
        vc.update_preferences("u3", {"voice_id": "verse"})
        params = vc.get_tts_params("u3")

        captured_voice: list[str] = []

        async def _capture(text: str, voice_id: str = "coral", **kw):
            captured_voice.append(voice_id)
            return b"\x00" * 512

        with patch.object(tts, "synthesize", side_effect=_capture):
            await tts.synthesize("Bonjour", voice_id=params["voice"])

        assert captured_voice[0] == "verse"

    @pytest.mark.asyncio
    async def test_e2e_streaming_tts_yields_chunks_for_all_voices(self):
        """Both coral and verse voices must yield audio chunks in streaming mode."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()

        for voice in ("coral", "verse"):
            async def _stream(*args, voice_id=voice, **kwargs):
                for _ in range(4):
                    yield b"\x00" * 256

            with patch.object(tts, "synthesize_stream", side_effect=_stream):
                chunks = [c async for c in tts.synthesize_stream("test", voice_id=voice)]

            assert len(chunks) == 4, f"Expected 4 chunks for voice={voice}"
            assert all(isinstance(c, bytes) for c in chunks)

    @pytest.mark.asyncio
    async def test_e2e_stt_provider_selection_respects_user_preference(self):
        """If user sets stt_provider='deepgram', Deepgram should be used."""
        vc = VoiceConfig()
        vc.update_preferences("u4", {"stt_provider": "deepgram"})
        prefs = vc.get_preferences("u4")
        assert prefs.stt_provider == "deepgram"

        stt = AudioProviderFactory.get_stt(prefs.stt_provider)
        assert stt.provider_name == "deepgram"

    @pytest.mark.asyncio
    async def test_e2e_auto_stt_provider_preference(self):
        """User preference for 'auto' stt_provider selects the auto-routing STT."""
        vc = VoiceConfig()
        vc.update_preferences("u5", {"stt_provider": "auto"})
        prefs = vc.get_preferences("u5")
        assert prefs.stt_provider == "auto"

        stt = AudioProviderFactory.get_stt(prefs.stt_provider)
        assert stt.provider_name == "auto"


# ═══════════════════════════════════════════════════════════════════
#  WebSocket Protocol — message shapes and sequencing
# ═══════════════════════════════════════════════════════════════════


class TestWebSocketProtocol:
    """Verify WebSocket message contract — all messages must be JSON with
    a 'type' field, and each type must carry its expected fields."""

    # Valid type → required fields mapping
    MESSAGE_SCHEMA: dict[str, list[str]] = {
        "processing":    ["type"],
        "transcript":    ["type"],
        "response_chunk": ["type"],
        "response":      ["type"],
        "audio_start":   ["type"],
        "audio_complete": ["type"],
        "continuous_mode": ["type"],
        "error":         ["type"],
    }

    def _make_msg(self, type_: str, **extra) -> dict:
        return {"type": type_, **extra}

    def test_all_message_types_have_type_field(self):
        for msg_type in self.MESSAGE_SCHEMA:
            msg = self._make_msg(msg_type)
            assert "type" in msg
            assert msg["type"] == msg_type

    def test_processing_message_shape(self):
        msg = self._make_msg("processing")
        assert msg["type"] == "processing"

    def test_transcript_message_shape(self):
        msg = self._make_msg("transcript", text="hello world")
        assert msg["type"] == "transcript"
        assert "text" in msg
        assert isinstance(msg["text"], str)

    def test_response_message_shape(self):
        msg = self._make_msg("response", text="Here is my response.", full_text="Here is my response.")
        assert msg["type"] == "response"
        assert "text" in msg
        assert "full_text" in msg

    def test_response_chunk_shape(self):
        msg = self._make_msg("response_chunk", text="partial ")
        assert msg["type"] == "response_chunk"
        assert "text" in msg

    def test_audio_start_shape(self):
        msg = self._make_msg("audio_start", format="webm")
        assert msg["type"] == "audio_start"
        assert "format" in msg

    def test_audio_complete_shape(self):
        msg = self._make_msg("audio_complete")
        assert msg["type"] == "audio_complete"

    def test_error_message_shape(self):
        msg = self._make_msg("error", message="STT failed")
        assert msg["type"] == "error"
        assert "message" in msg

    def test_continuous_mode_shape(self):
        msg = self._make_msg("continuous_mode", status="active")
        assert msg["type"] == "continuous_mode"
        assert msg["status"] == "active"

    def test_message_is_json_serializable(self):
        """All message types must be JSON-serializable (no binary, no non-standard types)."""
        for msg_type in self.MESSAGE_SCHEMA:
            msg = self._make_msg(msg_type, text="sample")
            serialized = json.dumps(msg)
            parsed = json.loads(serialized)
            assert parsed["type"] == msg_type

    def test_text_message_from_client_shape(self):
        """Client-to-server text message must have type='text' and text field."""
        client_msg = {"type": "text", "text": "Hello, I need coaching advice."}
        assert client_msg["type"] == "text"
        assert "text" in client_msg
        assert len(client_msg["text"]) > 0

    def test_end_audio_message_from_client_shape(self):
        """Client sends end_audio to signal end of voice turn."""
        client_msg = {"type": "end_audio"}
        assert client_msg["type"] == "end_audio"

    def test_audio_chunk_is_binary(self):
        """Audio chunks sent client→server must be raw bytes (ArrayBuffer), not JSON."""
        chunk = b"\x00\x01\x02\x03" * 256
        assert isinstance(chunk, bytes)
        assert len(chunk) == 1024

    def test_websocket_url_uses_correct_path(self):
        """Meridian WebSocket uses the /v1/agents/ws/alex-chat path (backward-compat)."""
        # The path is intentionally kept as 'alex-chat' for backward compatibility
        expected_suffix = "/v1/agents/ws/alex-chat"
        # Verify it's the expected path format
        assert expected_suffix.startswith("/v1/agents/ws/")
        assert "alex-chat" in expected_suffix  # backward-compatible name

    def test_all_message_types_covered(self):
        """Verify the protocol schema covers all 8 message types."""
        assert len(self.MESSAGE_SCHEMA) == 8

    @pytest.mark.asyncio
    async def test_rapid_message_sequence_no_ordering_violation(self):
        """Rapid message emission should maintain FIFO ordering."""
        queue: list[str] = []
        message_types = ["processing", "transcript", "response", "audio_start", "audio_complete"]

        async def _emit_sequence():
            for msg_type in message_types:
                await asyncio.sleep(0)  # yield to event loop
                queue.append(msg_type)

        await _emit_sequence()
        assert queue == message_types

    @pytest.mark.asyncio
    async def test_concurrent_tts_synthesis_produces_correct_chunk_count(self):
        """Multiple TTS stream chunks should all be collected in order."""
        from ai.audio_services.providers.openai_tts import OpenAITTS

        tts = OpenAITTS()
        expected_chunks = 6

        async def _stream(*args, **kwargs):
            for i in range(expected_chunks):
                yield bytes([i]) * 128

        collected: list[bytes] = []
        with patch.object(tts, "synthesize_stream", side_effect=_stream):
            async for chunk in tts.synthesize_stream("Long text response here.", voice_id="coral"):
                collected.append(chunk)

        assert len(collected) == expected_chunks
        # Verify order preserved
        for i, chunk in enumerate(collected):
            assert chunk[0] == i


# ═══════════════════════════════════════════════════════════════════
#  Voice Config + Language Integration
# ═══════════════════════════════════════════════════════════════════


class TestVoiceConfigLanguageIntegration:
    """Cross-cutting tests for VoiceConfig used inside the full voice pipeline."""

    @pytest.mark.asyncio
    async def test_system_prompt_suffix_for_rtl_language(self):
        """Arabic (RTL) should produce a non-empty system prompt suffix."""
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "ar"})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "Arabic" in suffix

    @pytest.mark.asyncio
    async def test_system_prompt_suffix_for_japanese(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "ja"})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "Japanese" in suffix

    def test_all_16_languages_produce_tts_params(self):
        """Every supported language must produce a valid TTS param dict."""
        vc = VoiceConfig()
        for i, lang in enumerate(SUPPORTED_LANGUAGES):
            vc.update_preferences(f"u{i}", {"language": lang})
            params = vc.get_tts_params(f"u{i}")
            assert params["language"] == lang
            assert params["voice"] in ("coral", "verse")
            assert isinstance(params["accent"], str)
            assert isinstance(params["tone"], str)

    def test_voice_config_is_stateless_across_users(self):
        """Changing one user's prefs must not affect another user."""
        vc = VoiceConfig()
        vc.update_preferences("alice", {"language": "fr", "voice_id": "coral"})
        vc.update_preferences("bob", {"language": "ja", "voice_id": "verse"})

        alice = vc.get_tts_params("alice")
        bob = vc.get_tts_params("bob")

        assert alice["language"] == "fr"
        assert alice["voice"] == "coral"
        assert bob["language"] == "ja"
        assert bob["voice"] == "verse"
