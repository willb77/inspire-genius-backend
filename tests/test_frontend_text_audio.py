"""Regression tests for frontend_text_service audio endpoints.

Covers:
- /audio-preview: still works identically, calls through provider abstraction
- /{text_id}/audio-stream: still works, emits deprecation warning, X-Deprecated header
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_async_gen(chunks):
    """Return an async generator that yields the given chunks."""
    async def _gen():
        for chunk in chunks:
            yield chunk
    return _gen()


# ---------------------------------------------------------------------------
# Unit tests — audio-preview endpoint logic
# ---------------------------------------------------------------------------

class TestAudioPreviewLogic:
    """Test coach audio preview: provider abstraction, caching, output format."""

    def test_cache_key_is_sorted_by_tone_ids(self):
        """MD5 cache key must be identical regardless of tone_ids input order."""
        text = "Welcome to Inspire Genius. I am here to assist you with your needs."
        accent_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        gender_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        tone_id_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
        tone_id_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")

        def compute_key(tone_ids):
            sorted_tones = sorted([str(t) for t in tone_ids])
            voice = "coral"
            raw = f"{text}_{accent_id}_{','.join(sorted_tones)}_{gender_id}_{voice}"
            return hashlib.md5(raw.encode("utf-8")).hexdigest()

        key_ab = compute_key([tone_id_1, tone_id_2])
        key_ba = compute_key([tone_id_2, tone_id_1])
        assert key_ab == key_ba, "Cache key must be order-independent for tone_ids"

    @pytest.mark.asyncio
    async def test_audio_preview_uses_stream_audio_chunks(self, tmp_path):
        """audio-preview calls stream_audio_chunks, which delegates to provider_factory."""
        fake_audio = b"\x00\x01" * 100

        from ai.frontend_text_services import frontend_text_service as svc

        # Patch get_preference_names_by_ids and get_voice_gender
        pref_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_preference_names_by_ids",
            return_value={"accent": "American", "tones": ["Warm"], "gender": "female"},
        )
        voice_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_voice_gender",
            return_value="coral",
        )
        # Patch stream_audio_chunks to yield fake audio
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([fake_audio]),
        )
        # Redirect audio_cache_dir to tmp_path
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with pref_patch, voice_patch, stream_patch as mock_stream, cwd_patch:
            accent_id = uuid.uuid4()
            tone_ids = [uuid.uuid4()]
            gender_id = uuid.uuid4()

            result = await svc.preview_audio(
                accent_id=accent_id,
                tone_ids=tone_ids,
                gender_id=gender_id,
            )

        # stream_audio_chunks was called once
        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args[1]
        assert call_kwargs["accent"] == "American"
        assert call_kwargs["tone"] == "Warm"
        assert call_kwargs["voice"] == "coral"

        # Response is a FileResponse with PCM media type
        assert result.media_type == "audio/pcm"

    @pytest.mark.asyncio
    async def test_audio_preview_cache_hit_skips_generation(self, tmp_path):
        """audio-preview returns cached file without calling stream_audio_chunks."""
        fake_audio = b"\xff\xfe" * 50

        # Pre-populate cache
        text = "Welcome to Inspire Genius. I am here to assist you with your needs."
        accent_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        gender_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        tone_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        voice = "coral"
        sorted_tones = [str(tone_id)]
        cache_key = f"{text}_{accent_id}_{','.join(sorted_tones)}_{gender_id}_{voice}"
        content_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()

        cache_dir = os.path.join(str(tmp_path), "audio_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cached_file = os.path.join(cache_dir, f"preview_audio_{content_hash}.pcm")
        with open(cached_file, "wb") as f:
            f.write(fake_audio)

        from ai.frontend_text_services import frontend_text_service as svc

        pref_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_preference_names_by_ids",
            return_value={"accent": "American", "tones": ["Warm"], "gender": "female"},
        )
        voice_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_voice_gender",
            return_value="coral",
        )
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with pref_patch, voice_patch, stream_patch as mock_stream, cwd_patch:
            result = await svc.preview_audio(
                accent_id=accent_id,
                tone_ids=[tone_id],
                gender_id=gender_id,
            )

        # stream_audio_chunks should NOT have been called — cache hit
        mock_stream.assert_not_called()
        assert result.headers.get("X-Cache-Status") == "HIT"

    @pytest.mark.asyncio
    async def test_audio_preview_cache_miss_sets_miss_header(self, tmp_path):
        """Cache miss sets X-Cache-Status: MISS."""
        fake_audio = b"\x00\x01" * 10

        from ai.frontend_text_services import frontend_text_service as svc

        pref_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_preference_names_by_ids",
            return_value={"accent": "British", "tones": ["Professional"], "gender": "male"},
        )
        voice_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_voice_gender",
            return_value="verse",
        )
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([fake_audio]),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with pref_patch, voice_patch, stream_patch, cwd_patch:
            result = await svc.preview_audio(
                accent_id=uuid.uuid4(),
                tone_ids=[uuid.uuid4()],
                gender_id=uuid.uuid4(),
            )

        assert result.headers.get("X-Cache-Status") == "MISS"

    @pytest.mark.asyncio
    async def test_audio_preview_empty_audio_raises_500(self, tmp_path):
        """Empty TTS output raises HTTP 500."""
        from fastapi import HTTPException
        from ai.frontend_text_services import frontend_text_service as svc

        pref_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_preference_names_by_ids",
            return_value={"accent": "American", "tones": ["Warm"], "gender": "female"},
        )
        voice_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_voice_gender",
            return_value="coral",
        )
        # Return empty generator — no audio produced
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([]),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with pref_patch, voice_patch, stream_patch, cwd_patch:
            with pytest.raises(HTTPException) as exc_info:
                await svc.preview_audio(
                    accent_id=uuid.uuid4(),
                    tone_ids=[uuid.uuid4()],
                    gender_id=uuid.uuid4(),
                )

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Unit tests — /{text_id}/audio-stream deprecation
# ---------------------------------------------------------------------------

class _FakeFrontendText:
    def __init__(self, title="Test Title", description="Test description body"):
        self.title = title
        self.description = description


class TestTourNarrationDeprecation:
    """Tour narration endpoint must still work but must emit deprecation signals."""

    @pytest.mark.asyncio
    async def test_deprecation_warning_logged(self, tmp_path):
        """Endpoint calls logger.warning() with a DEPRECATED message on every call.

        Note: prism_inspire.core.log_config is stubbed in conftest, so `logger` in
        the service module is a MagicMock.  We assert the mock was called with the
        right message rather than using caplog (which only captures real loggers).
        """
        from ai.frontend_text_services import frontend_text_service as svc

        text_id = uuid.uuid4()
        fake_audio = b"\xaa\xbb" * 20

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=_FakeFrontendText(),
        )
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([fake_audio]),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        mock_logger = MagicMock()
        logger_patch = patch(
            "ai.frontend_text_services.frontend_text_service.logger",
            mock_logger,
        )

        with db_patch, stream_patch, cwd_patch, logger_patch:
            await svc.stream_frontend_text_audio(text_id=text_id)

        # logger.warning must have been called at least once
        assert mock_logger.warning.called, "Expected logger.warning() to be called"
        # The first positional arg (format string) must contain "DEPRECATED"
        first_call_args = mock_logger.warning.call_args_list[0][0]
        assert first_call_args, "warning() must receive arguments"
        assert "DEPRECATED" in first_call_args[0], (
            f"Expected 'DEPRECATED' in warning message, got: {first_call_args[0]!r}"
        )
        assert "VoiceDeskAI" in first_call_args[0], (
            f"Expected 'VoiceDeskAI' in warning message, got: {first_call_args[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_x_deprecated_header_on_cache_miss(self, tmp_path):
        """Cache miss response includes X-Deprecated: true header."""
        from ai.frontend_text_services import frontend_text_service as svc

        text_id = uuid.uuid4()
        fake_audio = b"\xcc\xdd" * 15

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=_FakeFrontendText(),
        )
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([fake_audio]),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with db_patch, stream_patch, cwd_patch:
            result = await svc.stream_frontend_text_audio(text_id=text_id)

        assert result.headers.get("X-Deprecated") == "true"

    @pytest.mark.asyncio
    async def test_x_deprecated_header_on_cache_hit(self, tmp_path):
        """Cache hit response also includes X-Deprecated: true header."""
        from ai.frontend_text_services import frontend_text_service as svc

        text_id = uuid.uuid4()
        title = "Cached Title"
        description = "Cached description"
        text_to_speak = f"{title}\n{description}"
        content_hash = hashlib.md5(text_to_speak.encode("utf-8")).hexdigest()

        # Pre-populate cache
        cache_dir = os.path.join(str(tmp_path), "audio_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cached_file = os.path.join(cache_dir, f"frontend_text_{text_id}_{content_hash}.pcm")
        with open(cached_file, "wb") as f:
            f.write(b"\xee\xff" * 10)

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=_FakeFrontendText(title=title, description=description),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with db_patch, cwd_patch:
            result = await svc.stream_frontend_text_audio(text_id=text_id)

        assert result.headers.get("X-Deprecated") == "true"

    @pytest.mark.asyncio
    async def test_tour_narration_still_functional(self, tmp_path):
        """Deprecation must not break audio generation — endpoint returns PCM FileResponse."""
        from ai.frontend_text_services import frontend_text_service as svc

        text_id = uuid.uuid4()
        fake_audio = b"\x11\x22" * 30

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=_FakeFrontendText(title="Tour Step 1", description="Welcome"),
        )
        stream_patch = patch(
            "ai.frontend_text_services.frontend_text_service.stream_audio_chunks",
            return_value=_make_async_gen([fake_audio]),
        )
        cwd_patch = patch("os.getcwd", return_value=str(tmp_path))

        with db_patch, stream_patch, cwd_patch:
            result = await svc.stream_frontend_text_audio(text_id=text_id)

        assert result.media_type == "audio/pcm"

    @pytest.mark.asyncio
    async def test_tour_narration_404_when_text_not_found(self):
        """Returns 404 when frontend text is missing — deprecation does not mask errors."""
        from fastapi import HTTPException
        from ai.frontend_text_services import frontend_text_service as svc

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=None,
        )

        with db_patch:
            with pytest.raises(HTTPException) as exc_info:
                await svc.stream_frontend_text_audio(text_id=uuid.uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_tour_narration_400_when_no_text_content(self):
        """Returns 400 when frontend text has no title/description."""
        from fastapi import HTTPException
        from ai.frontend_text_services import frontend_text_service as svc

        db_patch = patch(
            "ai.frontend_text_services.frontend_text_service.get_frontend_text_by_id",
            return_value=_FakeFrontendText(title="", description=""),
        )

        with db_patch:
            with pytest.raises(HTTPException) as exc_info:
                await svc.stream_frontend_text_audio(text_id=uuid.uuid4())

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Provider abstraction integration — stream_audio_chunks delegation
# ---------------------------------------------------------------------------

def _can_import_agent_utils() -> bool:
    """Return True if agent_utils can be imported without errors."""
    try:
        import ai.ai_agent_services.agent_utils  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _can_import_agent_utils(),
    reason="agent_utils dependencies (google.genai, prism_inspire.core.ai_client) "
           "not available in this test environment",
)
class TestStreamAudioChunksDelegation:
    """Verify stream_audio_chunks calls provider_factory.get_tts(), not OpenAI directly."""

    @pytest.mark.asyncio
    async def test_stream_audio_chunks_calls_provider_factory(self):
        """stream_audio_chunks must delegate to AudioProviderFactory.get_tts()."""
        fake_chunk = b"\xde\xad\xbe\xef"

        mock_tts = MagicMock()
        mock_tts.synthesize_stream = MagicMock(
            return_value=_make_async_gen([fake_chunk])
        )

        # AudioProviderFactory is lazily imported INSIDE stream_audio_chunks(), so
        # patch it at the source location rather than as a module-level attribute.
        factory_patch = patch(
            "ai.audio_services.providers.provider_factory.AudioProviderFactory.get_tts",
            return_value=mock_tts,
        )

        with factory_patch as mock_get_tts:
            from ai.ai_agent_services.agent_utils import stream_audio_chunks
            chunks = []
            async for chunk in stream_audio_chunks(
                sentence="Hello world",
                voice="coral",
                accent="American",
                tone="Warm",
            ):
                chunks.append(chunk)

        mock_get_tts.assert_called_once()
        assert chunks == [fake_chunk]

    @pytest.mark.asyncio
    async def test_stream_audio_chunks_passes_voice_params(self):
        """Accent, tone, and voice_id must be forwarded to the TTS provider."""
        fake_chunk = b"\x01\x02"
        captured_kwargs = {}

        async def mock_synth_stream(text, voice_id="coral", **kwargs):
            captured_kwargs.update(kwargs)
            captured_kwargs["voice_id"] = voice_id
            yield fake_chunk

        mock_tts = MagicMock()
        mock_tts.synthesize_stream = mock_synth_stream

        # AudioProviderFactory is lazily imported inside stream_audio_chunks()
        factory_patch = patch(
            "ai.audio_services.providers.provider_factory.AudioProviderFactory.get_tts",
            return_value=mock_tts,
        )

        with factory_patch:
            from ai.ai_agent_services.agent_utils import stream_audio_chunks
            async for _ in stream_audio_chunks(
                sentence="Test sentence",
                voice="verse",
                accent="British",
                tone="Professional",
            ):
                pass

        assert captured_kwargs.get("voice_id") == "verse"
        assert captured_kwargs.get("accent") == "British"
        assert captured_kwargs.get("tone") == "Professional"
