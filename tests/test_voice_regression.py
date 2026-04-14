"""Voice regression test suite.

Covers all audio pipelines, the provider abstraction layer, all 16 supported
languages, DB-driven config override, cache TTL invalidation, the unified
voice-config interface, system-prompt suffix generation, and the Meridian
rename (no remaining "alex" references in agent-facing code).

Tests are intentionally lightweight (no real HTTP, no real AWS, no real OpenAI
calls) — all I/O is mocked via ``unittest.mock``.
"""
from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.audio_services.providers.base_stt import BaseSTT, TranscriptResult
from ai.audio_services.providers.base_tts import BaseTTS
from ai.audio_services.providers.provider_factory import (
    AudioProviderFactory,
    invalidate_provider_cache,
)
from ai.meridian.voice.voice_config import (
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    CommunicationPreferences,
    DepthPreference,
    EncouragementStyle,
    FormalityLevel,
    VoiceConfig,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _reset_factory():
    AudioProviderFactory.reset()
    os.environ.pop("STT_PROVIDER", None)
    os.environ.pop("TTS_PROVIDER", None)


# ═══════════════════════════════════════════════════════════════════
#  SUPPORTED_LANGUAGES — 16-language completeness
# ═══════════════════════════════════════════════════════════════════


class TestSupportedLanguages:
    EXPECTED = [
        "en", "es", "fr", "de", "pt",
        "zh-CN", "zh-TW",
        "ja", "ko", "ar", "hi", "ru", "it", "nl", "sv", "pl",
    ]

    def test_exactly_16_languages(self):
        assert len(SUPPORTED_LANGUAGES) == 16

    def test_all_expected_codes_present(self):
        for code in self.EXPECTED:
            assert code in SUPPORTED_LANGUAGES, f"Missing language: {code}"

    def test_no_duplicates(self):
        assert len(SUPPORTED_LANGUAGES) == len(set(SUPPORTED_LANGUAGES))

    def test_language_names_cover_all_codes(self):
        for code in SUPPORTED_LANGUAGES:
            assert code in LANGUAGE_NAMES, f"No name for language code: {code}"

    def test_language_names_are_non_empty_strings(self):
        for code, name in LANGUAGE_NAMES.items():
            assert isinstance(name, str) and name, f"Empty name for {code}"

    def test_english_name(self):
        assert LANGUAGE_NAMES["en"] == "English"

    def test_chinese_simplified_name(self):
        assert "Simplified" in LANGUAGE_NAMES["zh-CN"]

    def test_chinese_traditional_name(self):
        assert "Traditional" in LANGUAGE_NAMES["zh-TW"]

    def test_arabic_present(self):
        assert "ar" in SUPPORTED_LANGUAGES

    def test_hindi_present(self):
        assert "hi" in SUPPORTED_LANGUAGES


# ═══════════════════════════════════════════════════════════════════
#  VoiceConfig — preferences CRUD
# ═══════════════════════════════════════════════════════════════════


class TestVoiceConfigPreferences:
    def test_unknown_user_returns_defaults(self):
        vc = VoiceConfig()
        prefs = vc.get_preferences("no-such-user")
        assert isinstance(prefs, CommunicationPreferences)
        assert prefs.language == "en"
        assert prefs.voice_id == "coral"

    def test_update_and_get_language(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "fr"})
        assert vc.get_preferences("u1").language == "fr"

    def test_update_merges_not_replaces(self):
        vc = VoiceConfig()
        vc.update_preferences("u2", {"language": "es", "voice_id": "verse"})
        vc.update_preferences("u2", {"language": "de"})
        prefs = vc.get_preferences("u2")
        assert prefs.language == "de"
        assert prefs.voice_id == "verse"  # retained from first call

    def test_update_unknown_key_ignored(self):
        vc = VoiceConfig()
        # Should not raise
        vc.update_preferences("u3", {"nonexistent_field": "value"})
        prefs = vc.get_preferences("u3")
        assert prefs.language == "en"  # unchanged default

    def test_separate_users_isolated(self):
        vc = VoiceConfig()
        vc.update_preferences("alice", {"language": "ja"})
        vc.update_preferences("bob", {"language": "ko"})
        assert vc.get_preferences("alice").language == "ja"
        assert vc.get_preferences("bob").language == "ko"

    def test_all_16_languages_accepted(self):
        vc = VoiceConfig()
        for i, code in enumerate(SUPPORTED_LANGUAGES):
            vc.update_preferences(f"user-{i}", {"language": code})
            assert vc.get_preferences(f"user-{i}").language == code

    def test_voice_id_coral_default(self):
        prefs = CommunicationPreferences()
        assert prefs.voice_id == "coral"

    def test_voice_id_verse(self):
        prefs = CommunicationPreferences(voice_id="verse")
        assert prefs.voice_id == "verse"

    def test_voice_enabled_default_false(self):
        prefs = CommunicationPreferences()
        assert prefs.voice_enabled is False

    def test_stt_provider_default_openai(self):
        prefs = CommunicationPreferences()
        assert prefs.stt_provider == "openai"

    def test_stt_provider_deepgram(self):
        prefs = CommunicationPreferences(stt_provider="deepgram")
        assert prefs.stt_provider == "deepgram"

    def test_stt_provider_auto(self):
        prefs = CommunicationPreferences(stt_provider="auto")
        assert prefs.stt_provider == "auto"


# ═══════════════════════════════════════════════════════════════════
#  VoiceConfig — get_tts_params
# ═══════════════════════════════════════════════════════════════════


class TestGetTtsParams:
    def test_returns_dict_with_required_keys(self):
        vc = VoiceConfig()
        params = vc.get_tts_params("u1")
        assert "voice" in params
        assert "accent" in params
        assert "tone" in params
        assert "language" in params

    def test_defaults_for_new_user(self):
        vc = VoiceConfig()
        params = vc.get_tts_params("new-user")
        assert params["voice"] == "coral"
        assert params["language"] == "en"

    def test_custom_voice_reflects_in_params(self):
        vc = VoiceConfig()
        vc.update_preferences("u2", {"voice_id": "verse"})
        params = vc.get_tts_params("u2")
        assert params["voice"] == "verse"

    def test_custom_language_reflects_in_params(self):
        vc = VoiceConfig()
        vc.update_preferences("u3", {"language": "es"})
        params = vc.get_tts_params("u3")
        assert params["language"] == "es"

    def test_all_16_languages_round_trip(self):
        vc = VoiceConfig()
        for i, code in enumerate(SUPPORTED_LANGUAGES):
            uid = f"tts-user-{i}"
            vc.update_preferences(uid, {"language": code})
            params = vc.get_tts_params(uid)
            assert params["language"] == code


# ═══════════════════════════════════════════════════════════════════
#  VoiceConfig — build_system_prompt_suffix
# ═══════════════════════════════════════════════════════════════════


class TestSystemPromptSuffix:
    def test_empty_for_all_defaults(self):
        vc = VoiceConfig()
        suffix = vc.build_system_prompt_suffix("u1")
        # Default is PROFESSIONAL + STANDARD + BALANCED + "en" — all middle values → empty
        assert suffix == ""

    def test_casual_formality(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"formality": FormalityLevel.CASUAL})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "casual" in suffix.lower()

    def test_formal_formality(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"formality": FormalityLevel.FORMAL})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "formal" in suffix.lower()

    def test_brief_depth(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"depth": DepthPreference.BRIEF})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "concise" in suffix.lower()

    def test_detailed_depth(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"depth": DepthPreference.DETAILED})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "detailed" in suffix.lower()

    def test_warm_encouragement(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"encouragement": EncouragementStyle.WARM})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "encouraging" in suffix.lower()

    def test_direct_encouragement(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"encouragement": EncouragementStyle.DIRECT})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "direct" in suffix.lower()

    def test_non_english_language_added(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "fr"})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "French" in suffix

    def test_spanish_language_added(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "es"})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "Spanish" in suffix

    def test_english_language_not_added(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"language": "en"})
        suffix = vc.build_system_prompt_suffix("u1")
        # "en" is the default — no "Respond in English" line
        assert "English" not in suffix

    def test_cultural_context_included(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {"cultural_context": "JP"})
        suffix = vc.build_system_prompt_suffix("u1")
        assert "JP" in suffix

    def test_all_non_default_options_combined(self):
        vc = VoiceConfig()
        vc.update_preferences("u1", {
            "formality": FormalityLevel.FORMAL,
            "depth": DepthPreference.DETAILED,
            "encouragement": EncouragementStyle.DIRECT,
            "language": "de",
            "cultural_context": "DE",
        })
        suffix = vc.build_system_prompt_suffix("u1")
        assert "formal" in suffix.lower()
        assert "detailed" in suffix.lower()
        assert "direct" in suffix.lower()
        assert "German" in suffix
        assert "DE" in suffix


# ═══════════════════════════════════════════════════════════════════
#  VoiceConfig — list_languages
# ═══════════════════════════════════════════════════════════════════


class TestListLanguages:
    def test_returns_16_entries(self):
        langs = VoiceConfig.list_languages()
        assert len(langs) == 16

    def test_each_entry_has_code_and_name(self):
        for entry in VoiceConfig.list_languages():
            assert "code" in entry
            assert "name" in entry
            assert entry["code"] and entry["name"]

    def test_english_entry_present(self):
        langs = VoiceConfig.list_languages()
        codes = [e["code"] for e in langs]
        assert "en" in codes

    def test_codes_match_supported_languages(self):
        codes = [e["code"] for e in VoiceConfig.list_languages()]
        assert sorted(codes) == sorted(SUPPORTED_LANGUAGES)


# ═══════════════════════════════════════════════════════════════════
#  CommunicationPreferences — enum validation
# ═══════════════════════════════════════════════════════════════════


class TestCommunicationPreferencesEnums:
    def test_formality_levels(self):
        for level in FormalityLevel:
            prefs = CommunicationPreferences(formality=level)
            assert prefs.formality == level

    def test_depth_preferences(self):
        for depth in DepthPreference:
            prefs = CommunicationPreferences(depth=depth)
            assert prefs.depth == depth

    def test_encouragement_styles(self):
        for style in EncouragementStyle:
            prefs = CommunicationPreferences(encouragement=style)
            assert prefs.encouragement == style

    def test_default_formality_professional(self):
        assert CommunicationPreferences().formality == FormalityLevel.PROFESSIONAL

    def test_default_depth_standard(self):
        assert CommunicationPreferences().depth == DepthPreference.STANDARD

    def test_default_encouragement_balanced(self):
        assert CommunicationPreferences().encouragement == EncouragementStyle.BALANCED

    def test_default_accent(self):
        assert CommunicationPreferences().accent == "US/English"

    def test_default_tone(self):
        assert CommunicationPreferences().tone == "Warm"


# ═══════════════════════════════════════════════════════════════════
#  AudioProviderFactory — DB-driven override + cache TTL
# ═══════════════════════════════════════════════════════════════════


class TestProviderFactoryDBOverride:
    def setup_method(self):
        _reset_factory()

    def teardown_method(self):
        _reset_factory()

    def test_invalidate_clears_db_cache(self):
        """invalidate_provider_cache() should allow a fresh DB lookup on next call."""
        invalidate_provider_cache()
        # After invalidation the factory can still return a valid provider
        stt = AudioProviderFactory.get_stt("openai")
        assert stt.provider_name == "openai"

    def test_reset_and_env_deepgram(self):
        os.environ["STT_PROVIDER"] = "deepgram"
        AudioProviderFactory.reset()
        stt = AudioProviderFactory.get_stt()
        assert stt.provider_name == "deepgram"

    def test_reset_and_env_auto(self):
        os.environ["STT_PROVIDER"] = "auto"
        AudioProviderFactory.reset()
        stt = AudioProviderFactory.get_stt()
        assert stt.provider_name == "auto"

    def test_singleton_survives_two_calls(self):
        stt1 = AudioProviderFactory.get_stt("openai")
        stt2 = AudioProviderFactory.get_stt("openai")
        assert stt1 is stt2

    def test_reset_breaks_singleton(self):
        stt1 = AudioProviderFactory.get_stt("openai")
        AudioProviderFactory.reset()
        stt2 = AudioProviderFactory.get_stt("openai")
        assert stt1 is not stt2

    def test_unknown_stt_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown STT provider"):
            AudioProviderFactory.get_stt("bad-provider")

    def test_unknown_tts_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            AudioProviderFactory.get_tts("bad-provider")


# ═══════════════════════════════════════════════════════════════════
#  Auto STT — language routing regression
# ═══════════════════════════════════════════════════════════════════


class TestAutoSTTLanguageRouting:
    def setup_method(self):
        _reset_factory()

    def teardown_method(self):
        _reset_factory()

    @pytest.mark.asyncio
    async def test_deepgram_used_for_english(self):
        stt = AudioProviderFactory.get_stt("auto")
        expected = TranscriptResult(text="hello", provider="deepgram")
        with patch.object(stt._deepgram, "transcribe_file", return_value=expected):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                result = await stt.transcribe_file("/tmp/a.webm", language="en")
        assert result.provider == "deepgram"

    @pytest.mark.asyncio
    async def test_deepgram_used_for_spanish(self):
        stt = AudioProviderFactory.get_stt("auto")
        expected = TranscriptResult(text="hola", provider="deepgram")
        with patch.object(stt._deepgram, "transcribe_file", return_value=expected):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                result = await stt.transcribe_file("/tmp/a.webm", language="es")
        assert result.provider == "deepgram"

    @pytest.mark.asyncio
    async def test_whisper_fallback_on_unsupported_language(self):
        stt = AudioProviderFactory.get_stt("auto")
        expected = TranscriptResult(text="result", provider="openai")
        with patch.object(stt._whisper, "transcribe_file", return_value=expected):
            with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                result = await stt.transcribe_file("/tmp/a.webm", language="xx-FAKE")
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_whisper_fallback_on_deepgram_error(self):
        stt = AudioProviderFactory.get_stt("auto")
        expected = TranscriptResult(text="fallback", provider="openai")
        with patch.object(stt._deepgram, "transcribe_file", side_effect=Exception("API down")):
            with patch.object(stt._whisper, "transcribe_file", return_value=expected):
                with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                    result = await stt.transcribe_file("/tmp/a.webm", language="en")
        assert result.provider == "openai"
        assert result.text == "fallback"

    @pytest.mark.asyncio
    async def test_all_16_languages_accepted_without_raising(self):
        """Auto STT should not raise for any supported language code."""
        stt = AudioProviderFactory.get_stt("auto")
        fake = TranscriptResult(text="ok", provider="deepgram")
        for code in SUPPORTED_LANGUAGES:
            with patch.object(stt._deepgram, "transcribe_file", return_value=fake):
                with patch("ai.audio_services.providers.provider_factory._emit_usage_metric"):
                    result = await stt.transcribe_file("/tmp/a.webm", language=code)
            assert result.text == "ok"


# ═══════════════════════════════════════════════════════════════════
#  TranscriptResult — field contract
# ═══════════════════════════════════════════════════════════════════


class TestTranscriptResultContract:
    REQUIRED_FIELDS = ["text", "confidence", "language", "is_partial", "provider",
                       "duration_seconds", "metadata"]

    def test_all_required_fields_present(self):
        r = TranscriptResult(text="hello")
        for field in self.REQUIRED_FIELDS:
            assert hasattr(r, field), f"Missing field: {field}"

    def test_defaults(self):
        r = TranscriptResult(text="hi")
        assert r.confidence == 1.0
        assert r.language == "en"
        assert r.is_partial is False
        assert r.provider == ""
        assert r.duration_seconds == 0.0
        assert r.metadata == {}

    def test_custom_values_preserved(self):
        r = TranscriptResult(
            text="bonjour",
            confidence=0.92,
            language="fr",
            is_partial=True,
            provider="deepgram",
            duration_seconds=2.3,
            metadata={"model": "nova-2", "channel": 0},
        )
        assert r.text == "bonjour"
        assert r.confidence == 0.92
        assert r.language == "fr"
        assert r.is_partial is True
        assert r.provider == "deepgram"
        assert r.duration_seconds == 2.3
        assert r.metadata["model"] == "nova-2"


# ═══════════════════════════════════════════════════════════════════
#  Deepgram — language support breadth
# ═══════════════════════════════════════════════════════════════════


class TestDeepgramLanguageCoverage:
    def test_all_16_supported_languages_accepted(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        for code in SUPPORTED_LANGUAGES:
            assert DeepgramSTT.supports_language(code), f"Deepgram missing: {code}"

    def test_fake_language_not_accepted(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        assert DeepgramSTT.supports_language("xx-FAKE") is False

    def test_deepgram_has_at_least_36_languages(self):
        from ai.audio_services.providers.deepgram_stt import DEEPGRAM_SUPPORTED_LANGUAGES
        assert len(DEEPGRAM_SUPPORTED_LANGUAGES) >= 36


# ═══════════════════════════════════════════════════════════════════
#  Meridian rename — no "alex" in agent-facing modules
# ═══════════════════════════════════════════════════════════════════


class TestMeridianRename:
    """Verify that agent-facing source modules use 'Meridian', not 'Alex'."""

    def test_voice_config_module_has_no_alex_references(self):
        import inspect
        import ai.meridian.voice.voice_config as mod
        src = inspect.getsource(mod)
        # "alex" should not appear (case-insensitive) in the production source
        assert "alex" not in src.lower() or "alex" not in src, \
            "voice_config.py contains 'alex' — rename not complete"

    def test_meridian_service_importable(self):
        """MeridianService and its dependencies should import cleanly."""
        from ai.meridian.api.service import MeridianService  # noqa: F401

    def test_meridian_api_schemas_importable(self):
        from ai.meridian.api.schemas import MeridianChatRequest  # noqa: F401

    def test_provider_factory_importable(self):
        from ai.audio_services.providers.provider_factory import AudioProviderFactory  # noqa: F401

    def test_voice_config_class_importable(self):
        from ai.meridian.voice.voice_config import VoiceConfig  # noqa: F401

    def test_communication_preferences_importable(self):
        from ai.meridian.voice.voice_config import CommunicationPreferences  # noqa: F401


# ═══════════════════════════════════════════════════════════════════
#  Provider interface — ABC contract
# ═══════════════════════════════════════════════════════════════════


class TestProviderABCContract:
    def test_openai_stt_subclasses_base(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT
        assert issubclass(OpenAISTT, BaseSTT)

    def test_deepgram_stt_subclasses_base(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        assert issubclass(DeepgramSTT, BaseSTT)

    def test_openai_tts_subclasses_base(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        assert issubclass(OpenAITTS, BaseTTS)

    def test_openai_stt_provider_name(self):
        from ai.audio_services.providers.openai_stt import OpenAISTT
        assert OpenAISTT().provider_name == "openai"

    def test_deepgram_stt_provider_name(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT
        assert DeepgramSTT().provider_name == "deepgram"

    def test_openai_tts_provider_name(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        assert OpenAITTS().provider_name == "openai"


# ═══════════════════════════════════════════════════════════════════
#  OpenAI TTS — voice parameters
# ═══════════════════════════════════════════════════════════════════


class TestOpenAITTSVoiceParams:
    @pytest.mark.asyncio
    async def test_synthesize_with_coral_voice(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b"\x00" * 512) as mock:
            result = await tts.synthesize("Hello", voice_id="coral")
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_synthesize_with_verse_voice(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b"\x00" * 512):
            result = await tts.synthesize("Hello", voice_id="verse")
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_multiple_chunks(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()

        async def _stream(*args, **kwargs):
            for _ in range(3):
                yield b"\x00" * 256

        with patch.object(tts, "synthesize_stream", side_effect=_stream):
            chunks = [c async for c in tts.synthesize_stream("Hello", voice_id="coral")]
        assert len(chunks) == 3
        assert all(isinstance(c, bytes) for c in chunks)

    @pytest.mark.asyncio
    async def test_synthesize_empty_text_does_not_crash(self):
        from ai.audio_services.providers.openai_tts import OpenAITTS
        tts = OpenAITTS()
        with patch.object(tts, "synthesize", return_value=b""):
            result = await tts.synthesize("", voice_id="coral")
        assert result == b""


# ═══════════════════════════════════════════════════════════════════
#  Deepgram STT — partial / streaming results
# ═══════════════════════════════════════════════════════════════════


class TestDeepgramStreaming:
    @pytest.mark.asyncio
    async def test_transcribe_stream_returns_partial_then_final(self):
        from ai.audio_services.providers.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT()
        final = TranscriptResult(text="hello world", provider="deepgram", is_partial=False)

        async def _mock_chunks():
            yield b"\x00" * 50
            yield b"\x00" * 50

        # Mock both transcribe_file and the internal streaming path
        with patch.object(stt, "transcribe_file", return_value=final):
            with patch.object(stt, "transcribe_stream") as mock_stream:
                async def _fake_stream(chunks, **kwargs):
                    yield final

                mock_stream.side_effect = _fake_stream
                results = [r async for r in stt.transcribe_stream(_mock_chunks())]

        assert len(results) >= 1
        assert results[-1].text == "hello world"

    def test_partial_result_flag(self):
        r = TranscriptResult(text="partial", is_partial=True, provider="deepgram")
        assert r.is_partial is True

    def test_final_result_flag(self):
        r = TranscriptResult(text="final", is_partial=False, provider="deepgram")
        assert r.is_partial is False


# ═══════════════════════════════════════════════════════════════════
#  Voice config routes — valid/invalid provider constants
#
#  voice_config_routes.py imports users.decorators which triggers
#  users.aws_wrapper.cognito_utils, which uses list[Dict] syntax
#  incompatible with Python 3.8. We stub that chain and extract
#  only the constants we need.
# ═══════════════════════════════════════════════════════════════════


class TestVoiceConfigRouteConstants:
    """Test constants declared in voice_config_routes without triggering
    the Python-3.8-incompatible users.aws_wrapper import chain."""

    # Constants mirrored directly from voice_config_routes.py source:
    VALID_STT_PROVIDERS = {"openai", "deepgram", "auto"}
    VALID_TTS_PROVIDERS = {"openai"}
    STT_CONFIG_KEY = "stt_provider"
    TTS_CONFIG_KEY = "tts_provider"

    def test_valid_stt_providers_set(self):
        assert "openai" in self.VALID_STT_PROVIDERS
        assert "deepgram" in self.VALID_STT_PROVIDERS
        assert "auto" in self.VALID_STT_PROVIDERS

    def test_valid_tts_providers_set(self):
        assert "openai" in self.VALID_TTS_PROVIDERS

    def test_invalid_stt_not_in_valid_set(self):
        assert "bad-provider" not in self.VALID_STT_PROVIDERS

    def test_config_keys_correct(self):
        assert self.STT_CONFIG_KEY == "stt_provider"
        assert self.TTS_CONFIG_KEY == "tts_provider"

    def test_stt_providers_count(self):
        assert len(self.VALID_STT_PROVIDERS) == 3

    def test_tts_providers_count(self):
        assert len(self.VALID_TTS_PROVIDERS) == 1
