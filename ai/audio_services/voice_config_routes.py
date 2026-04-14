"""Voice provider configuration endpoints — super-admin only.

GET  /v1/admin/voice-config  — retrieve current STT/TTS provider settings
PUT  /v1/admin/voice-config  — update STT/TTS provider settings
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role, log_access
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
)
from ai.audio_services.system_config_model import SystemConfig
from ai.audio_services.providers.provider_factory import invalidate_provider_cache

voice_config_routes = APIRouter(prefix="/admin/voice-config", tags=["Voice Configuration"])

VALID_STT_PROVIDERS = {"openai", "deepgram", "auto"}
VALID_TTS_PROVIDERS = {"openai"}

_STT_CONFIG_KEY = "stt_provider"
_TTS_CONFIG_KEY = "tts_provider"


class VoiceConfigUpdate(BaseModel):
    stt_provider: str | None = None
    tts_provider: str | None = None


@voice_config_routes.get("")
def get_voice_config(
    user_data: dict = Depends(require_role("super-admin")),
):
    """Retrieve current voice provider configuration."""
    session = ScopedSession()
    try:
        log_access(user_data, "voice_config", action="get")

        stt_row = session.query(SystemConfig).filter(SystemConfig.key == _STT_CONFIG_KEY).first()
        tts_row = session.query(SystemConfig).filter(SystemConfig.key == _TTS_CONFIG_KEY).first()

        stt_provider = stt_row.value if stt_row else os.environ.get("STT_PROVIDER", "openai")
        tts_provider = tts_row.value if tts_row else os.environ.get("TTS_PROVIDER", "openai")

        return create_response(
            message="Voice configuration retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "stt_provider": stt_provider,
                "tts_provider": tts_provider,
                "valid_stt_providers": sorted(VALID_STT_PROVIDERS),
                "valid_tts_providers": sorted(VALID_TTS_PROVIDERS),
                "stt_updated_at": stt_row.updated_at.isoformat() if stt_row else None,
                "tts_updated_at": tts_row.updated_at.isoformat() if tts_row else None,
                "stt_updated_by": stt_row.updated_by if stt_row else None,
                "tts_updated_by": tts_row.updated_by if tts_row else None,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving voice config: {e}")
        return create_response(
            message="Failed to retrieve voice configuration",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@voice_config_routes.put("")
def update_voice_config(
    body: VoiceConfigUpdate,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Update voice provider configuration."""
    if body.stt_provider is not None and body.stt_provider not in VALID_STT_PROVIDERS:
        return create_response(
            message=f"Invalid STT provider '{body.stt_provider}'. Valid: {sorted(VALID_STT_PROVIDERS)}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )
    if body.tts_provider is not None and body.tts_provider not in VALID_TTS_PROVIDERS:
        return create_response(
            message=f"Invalid TTS provider '{body.tts_provider}'. Valid: {sorted(VALID_TTS_PROVIDERS)}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    updated_by = user_data.get("sub") or user_data.get("email")
    session = ScopedSession()
    try:
        log_access(user_data, "voice_config", action="update")

        now = datetime.now(timezone.utc)
        updated_keys: list[str] = []

        for config_key, new_value in [
            (_STT_CONFIG_KEY, body.stt_provider),
            (_TTS_CONFIG_KEY, body.tts_provider),
        ]:
            if new_value is None:
                continue

            row = session.query(SystemConfig).filter(SystemConfig.key == config_key).first()
            if row:
                row.value = new_value
                row.updated_by = updated_by
                row.updated_at = now
            else:
                session.add(SystemConfig(
                    key=config_key,
                    value=new_value,
                    updated_by=updated_by,
                    updated_at=now,
                    created_at=now,
                ))
            updated_keys.append(config_key)

        session.commit()

        # Invalidate cached provider instances so next request re-reads the DB
        invalidate_provider_cache()

        return create_response(
            message="Voice configuration updated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "updated_keys": updated_keys,
                "stt_provider": body.stt_provider,
                "tts_provider": body.tts_provider,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating voice config: {e}")
        return create_response(
            message="Failed to update voice configuration",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
