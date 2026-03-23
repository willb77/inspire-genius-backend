import os
import hashlib
from typing import Optional, List, Union
from uuid import UUID
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, Response, FileResponse


from ai.agent_settings.schema import get_preference_names_by_ids
from ai.frontend_text_services.schema import (
    get_all_frontend_texts,
    get_frontend_text_by_id,
    get_frontend_texts_by_route,
    get_frontend_texts_by_selector,
    get_frontend_text_by_route_and_selector
)
from ai.frontend_text_services.req_resp_parser import FrontendTextResponse, FrontendTextListResponse
from ai.ai_agent_services.agent_utils import get_voice_gender, stream_audio_chunks, DEFAULT_ACCENT
from ai.ai_agent_services.prompts import alex_speech_instructions
from prism_inspire.core.log_config import logger
from users.response import (
    NOT_FOUND,
    SOMETHING_WENT_WRONG,
    SUCCESS_CODE,
    create_response,
)

frontend_text_routes = APIRouter(
    prefix="/frontend-text",
    tags=["Frontend Text Management"],
)

@frontend_text_routes.get("")
def get_frontend_texts(
    route_key: Optional[str] = Query(None, description="Filter by route key"),
    selector: Optional[str] = Query(None, description="Filter by selector"),
):
    """
    Get frontend texts with optional filtering.
    No authentication required.
    
    Query Parameters:
    - route_key: Filter texts by route key
    - selector: Filter texts by selector
    
    If both route_key and selector are provided, returns the specific text matching both.
    If only one is provided, returns all texts matching that criteria.
    If neither is provided, returns all frontend texts.
    """
    try:
        frontend_texts = []
        
        if route_key and selector:
            # Get specific text by both route and selector
            frontend_text = get_frontend_text_by_route_and_selector(route_key, selector)
            if frontend_text:
                frontend_texts = [frontend_text]
        elif route_key:
            # Get texts by route key
            frontend_texts = get_frontend_texts_by_route(route_key)
        elif selector:
            # Get texts by selector
            frontend_texts = get_frontend_texts_by_selector(selector)
        else:
            # Get all texts
            frontend_texts = get_all_frontend_texts()

        # Convert to response models
        text_responses = [
            FrontendTextResponse(
                id=str(text.id),
                selector=text.selector,
                routeKey=text.routeKey,
                title=text.title,
                description=text.description,
                meta_data=text.meta_data,
                comments=text.comments
            )
            for text in frontend_texts
        ]

        response_data = FrontendTextListResponse(
            frontend_texts=text_responses,
            total_count=len(text_responses)
        )

        return create_response(
            message="Frontend texts retrieved successfully",
            error_code=SUCCESS_CODE,
            status=True,
            data=response_data.dict()
        )

    except Exception as e:
        logger.error(f"Error retrieving frontend texts: {e}")
        return create_response(
            message="Failed to retrieve frontend texts",
            error_code=SOMETHING_WENT_WRONG,
            status=False,
            status_code=500
        )


@frontend_text_routes.get("/audio-preview")
async def preview_audio(
    accent_id: UUID = Query(..., description="Accent preference UUID (required)"),
    tone_ids: Union[list[UUID], str] = Query(..., description="List of tone preference UUIDs (required)"),
    gender_id: UUID = Query(..., description="Gender preference UUID (required)"),
):
    """
    Generate preview audio with custom accent, tone, and voice.

    Query Parameters:
    - accent_id: UUID of the accent preference (required)
    - tone_ids: List of tone UUIDs (required)
    - gender_id: UUID of the gender preference (required)
    """
    try:
        if isinstance(tone_ids, str):
            tone_ids = [UUID(t.strip()) for t in tone_ids.split(',') if t.strip()]

        text = "Welcome to Inspire Genius. I am here to assist you with your needs."

        # Get preference names by IDs
        pref_names = get_preference_names_by_ids(accent_id, tone_ids, gender_id)

        # Extract preference values
        accent = pref_names.get("accent") or DEFAULT_ACCENT
        tone = pref_names.get("tones")
        if isinstance(tone, list):
            tone = ", ".join(tone) if tone else "Warm"
        else:
            tone = tone or "Warm"

        # Determine voice based on gender
        gender = pref_names.get("gender") or "female"
        voice = get_voice_gender(gender.lower() if gender else "female")

        # Create cache directory
        audio_cache_dir = os.path.join(os.getcwd(), "audio_cache")
        os.makedirs(audio_cache_dir, exist_ok=True)

        # Sort tone IDs for consistent caching regardless of input order
        sorted_tone_ids = sorted([str(tid) for tid in tone_ids])

        # Generate cache filename with content hash (includes all parameters)
        # Using sorted tone IDs ensures same cache hit even if tone order differs
        cache_key = f"{text}_{accent_id}_{','.join(sorted_tone_ids)}_{gender_id}_{voice}"
        content_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        audio_filename = f"preview_audio_{content_hash}.pcm"
        audio_filepath = os.path.join(audio_cache_dir, audio_filename)

        # Check if audio file already exists in cache
        if os.path.exists(audio_filepath):
            logger.info(f"Using cached preview audio: {audio_filepath}")
            return FileResponse(
                path=audio_filepath,
                media_type="audio/pcm",
                filename=f"preview_audio_{content_hash}.pcm",
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Content-Type-Options": "nosniff",
                    "X-Cache-Status": "HIT"
                }
            )

        logger.info(f"Generating preview audio - Text: {text[:50]}..., Accent: {accent}, Tone: {tone}, Voice: {voice}")

        # Generate audio using stream_audio_chunks
        audio_content = b""
        async for chunk in stream_audio_chunks(
            sentence=text,
            instructions=alex_speech_instructions,
            accent=accent,
            tone=tone,
            voice=voice
        ):
            if chunk:
                audio_content += chunk

        if not audio_content:
            raise HTTPException(status_code=500, detail="Failed to generate audio - no content")

        # Save to cache
        with open(audio_filepath, 'wb') as f:
            f.write(audio_content)

        logger.info(f"Generated and cached preview audio, size: {len(audio_content)} bytes")

        return FileResponse(
            path=audio_filepath,
            media_type="audio/pcm",
            filename=f"preview_audio_{content_hash}.pcm",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Content-Type-Options": "nosniff",
                "X-Cache-Status": "MISS"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating preview audio: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")


@frontend_text_routes.get("/{text_id}")
def get_frontend_text_by_id_api(text_id: UUID):
    """
    Get a specific frontend text by ID.
    No authentication required.
    """
    try:
        frontend_text = get_frontend_text_by_id(text_id)
        
        if not frontend_text:
            return create_response(
                message="Frontend text not found",
                error_code=NOT_FOUND,
                status=False,
                status_code=404
            )

        text_response = FrontendTextResponse(
            id=str(frontend_text.id),
            selector=frontend_text.selector,
            routeKey=frontend_text.routeKey,
            title=frontend_text.title,
            description=frontend_text.description,
            meta_data=frontend_text.meta_data,
            comments=frontend_text.comments
        )

        return create_response(
            message="Frontend text retrieved successfully",
            error_code=SUCCESS_CODE,
            status=True,
            data={"frontend_text": text_response.dict()}
        )

    except Exception as e:
        logger.error(f"Error retrieving frontend text by ID {text_id}: {e}")
        return create_response(
            message="Failed to retrieve frontend text",
            error_code=SOMETHING_WENT_WRONG,
            status=False,
            status_code=500
        )


@frontend_text_routes.get(
    "/{text_id}/audio-stream",
    responses={
        200: {
            "description": "Direct audio response in PCM format",
            "content": {
                "audio/pcm": {
                    "schema": {
                        "type": "string",
                        "format": "binary"
                    }
                }
            },
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment filename for the audio file",
                    "schema": {"type": "string"}
                }
            }
        },
        404: {"description": "Frontend text not found"},
        400: {"description": "No text content available for audio generation"},
        500: {"description": "Failed to generate audio"}
    },
    summary="Generate audio for frontend text",
    description="""
    Generates audio (PCM format) for a frontend text by ID.
    
    The endpoint combines the title and description of the frontend text with a newline separator
    and converts it to speech using text-to-speech technology.
    
    **Response Format**: 
    - Media Type: `audio/pcm`
    - Encoding: 16-bit PCM
    - Sample Rate: 24kHz
    - Direct response (not streamed)
    
    **Usage Notes**:
    - This endpoint returns complete audio data
    - No authentication required
    - Suitable for download or immediate playback
    - Works well with Swagger UI testing
    
    **Browser Compatibility**:
    - Modern browsers support PCM audio
    - Consider using Web Audio API for playback
    """
)
async def stream_frontend_text_audio(text_id: UUID):
    """
    Generate audio for a frontend text by ID.
    Combines title and description with newline separator.
    No authentication required.
    """
    try:
        # Get the frontend text from database
        frontend_text = get_frontend_text_by_id(text_id)
        
        if not frontend_text:
            raise HTTPException(status_code=404, detail="Frontend text not found")

        # Prepare the text to be spoken: title + \n + description
        text_to_speak = ""
        if frontend_text.title:
            text_to_speak += frontend_text.title
        if frontend_text.description:
            if text_to_speak:
                text_to_speak += "\n"
            text_to_speak += frontend_text.description
        
        if not text_to_speak.strip():
            raise HTTPException(status_code=400, detail="No text content available for audio generation")

        # Create audio cache directory in project root
        audio_cache_dir = os.path.join(os.getcwd(), "audio_cache")
        os.makedirs(audio_cache_dir, exist_ok=True)
        
        # Generate filename based on content hash for consistency
        content_hash = hashlib.md5(text_to_speak.encode('utf-8')).hexdigest()
        audio_filename = f"frontend_text_{text_id}_{content_hash}.pcm"
        audio_filepath = os.path.join(audio_cache_dir, audio_filename)
        
        # Check if audio file already exists
        if os.path.exists(audio_filepath):
            logger.info(f"Using cached audio for frontend text {text_id}: {audio_filepath}")
            return FileResponse(
                path=audio_filepath,
                media_type="audio/pcm",
                filename=f"frontend_text_{text_id}_audio.pcm",
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                    "X-Content-Type-Options": "nosniff"
                }
            )
        
        logger.info(f"Generating new audio for frontend text {text_id}: {text_to_speak[:100]}...")
        
        # Generate audio using the stream_audio_chunks function
        audio_content = b""
        async for chunk in stream_audio_chunks(
            sentence=text_to_speak,
            instructions=alex_speech_instructions,
            accent=DEFAULT_ACCENT,
            tone="Warm"
        ):
            if chunk:
                audio_content += chunk
        
        # Save audio to cache file
        with open(audio_filepath, 'wb') as f:
            f.write(audio_content)
        
        logger.info(f"Generated and cached audio for text {text_id}, size: {len(audio_content)} bytes, saved to: {audio_filepath}")
        
        # Return the cached file
        return FileResponse(
            path=audio_filepath,
            media_type="audio/pcm",
            filename=f"frontend_text_{text_id}_audio.pcm",
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                "X-Content-Type-Options": "nosniff"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating audio for frontend text {text_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate audio")