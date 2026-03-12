import asyncio
import hashlib
import json
import re, os, uuid
from typing import Optional, Union, Callable, Awaitable
from datetime import datetime

from aiohttp import ClientError
from fastapi import Request, WebSocket, WebSocketDisconnect, logger
from google.genai import types

from ai.ai_agent_services.ai_tools import AssistantQuery
from ai.ai_agent_services.prompts import (
    alex_speech_instructions,
    assistant_query_prompt,
)
from prism_inspire.core.ai_client import genai_client, openai, openai_client
from prism_inspire.core.file_utils import S3_BUCKET, S3FileHandler

# Default constants
DEFAULT_ACCENT = "US/English"


def get_device_id(client: Union[WebSocket, Request]) -> str:
    """Generate device ID from client IP and user agent using secure hashing"""
    # Handle both WebSocket and Request uniformly by checking attributes
    client_addr = getattr(client, "client", None)
    client_ip = (
        client_addr.host
        if client_addr and getattr(client_addr, "host", None)
        else "unknown"
    )
    user_agent = (
        client.headers.get("user-agent", "unknown")
        if getattr(client, "headers", None)
        else "unknown"
    )

    client_ip = str(client_ip).replace("_", "-") if client_ip else "unknown"
    user_agent = str(user_agent).replace("_", "-") if user_agent else "unknown"

    device_string = f"{client_ip}_{user_agent}"
    return hashlib.sha256(device_string.encode()).hexdigest()[:32]


async def audio_transcription(audio_file):
    """
    Handles the transcription of audio data by sending it to the transcription service.
    """
    file = open(audio_file, "rb")
    try:
        transcription = await openai.audio.transcriptions.create(
            model="gpt-4o-transcribe", file=file, response_format="text"
        )
        if isinstance(transcription, str) and transcription.strip():
            return transcription
        elif isinstance(transcription, dict) and "text" in transcription:
            return transcription["text"]
        else:
            return "Error: Empty or invalid transcription result"
    except Exception as e:
        print(f"Error: {e}")
        raise Exception(f"Can you please repeat that?")
    finally:
        file.close()


async def generate_and_stream_response(
    websocket: WebSocket,
    user_input: str,
    system: str,
    chat_history=None,
    accent=DEFAULT_ACCENT,
    tone="Warm",
    voice="coral",
    save_callback: Optional[Callable[[str, bytes, str], Awaitable[None]]] = None,
):
    """
    Generate response and stream audio simultaneously for minimal latency
    """
    try:
        messages = [{"role": "system", "content": system}]
        if chat_history:
            messages.extend(chat_history)

        messages.append(
            {"role": "user", "content": [{"type": "text", "text": user_input}]}
        )

        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0.9,
            max_tokens=1500,
        )
        response_text = response.choices[0].message.content

        await websocket.send_text(json.dumps({"type": "audio_start", "format": "pcm"}))

        await websocket.send_text(
            json.dumps(
                {
                    "type": "response_chunk",
                    "content": response_text,
                    "full_text": response_text,
                }
            )
        )

        audio_bytes: Optional[bytes] = None
        audio_filename: Optional[str] = None
        audio_bytes = await stream_and_capture_sentence_audio(
            websocket,
            response_text,
            instructions=alex_speech_instructions,
            accent=accent,
            tone=tone,
            voice=voice,
            response_format="pcm",
        )
        utc_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        audio_filename = f"{utc_ts}" if audio_bytes else None

        if save_callback:
            try:
                asyncio.create_task(save_callback(response_text, audio_bytes, audio_filename))
            except Exception:
                # swallow scheduling errors; actual save_callback should handle its own errors/logging
                pass
            
        await websocket.send_text(
            json.dumps({"type": "response", "text": response_text})
        )

        await websocket.send_text(json.dumps({"type": "audio_complete"}))

        return response_text, audio_bytes, audio_filename

    except Exception as e:
        print(f"Error in generate_and_stream_response: {e}")
        await websocket.send_text(
            json.dumps(
                {"type": "error", "message": f"Error generating response: {str(e)}"}
            )
        )
        return "I apologize, but I'm having trouble processing your request right now.", None, None


async def stream_sentence_audio(
    websocket: WebSocket,
    sentence: str,
    voice="coral",
    instructions=alex_speech_instructions,
    accent=DEFAULT_ACCENT,
    tone="Warm",
):
    """
    Stream audio for a single sentence
    """
    try:
        async with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            instructions=instructions.format(accent=accent, tone=tone),
            input=sentence,
            response_format="pcm",
            speed=1,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=65536):  # 64KB chunks
                if chunk:
                    await websocket.send_bytes(chunk)
                    print(f"Sent audio chunk of size {len(chunk)} bytes")
                    await asyncio.sleep(0.001)
    except Exception as e:
        print(f"Error streaming sentence audio: {e}")

async def stream_and_capture_sentence_audio(
    websocket: WebSocket,
    sentence: str,
    voice="coral",
    instructions=alex_speech_instructions,
    accent=DEFAULT_ACCENT,
    tone="Warm",
    response_format="pcm",
):
    """
    Stream audio chunks to websocket and capture full audio bytes to return.
    Returns bytes object (may be empty on failure).
    """
    buf = bytearray()
    try:
        async with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            instructions=instructions.format(accent=accent, tone=tone),
            input=sentence,
            response_format=response_format,
            speed=1,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=65536):
                if chunk:
                    buf.extend(chunk)
                    await websocket.send_bytes(chunk)
                    await asyncio.sleep(0.001)
    except Exception as e:
        print(f"Error streaming+capturing sentence audio: {e}")
    return bytes(buf)


async def stream_audio_chunks(sentence: str, voice="coral", instructions=alex_speech_instructions,
                               accent=DEFAULT_ACCENT, tone="Warm"):
    """
    Async generator that yields TTS audio chunks from OpenAI API.
    """
    try:
        async with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            instructions=instructions.format(accent=accent, tone=tone),
            input=sentence,
            response_format="wav",   # Could be "wav" if you want an audio container
            speed=1,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=65536):
                if chunk:
                    yield chunk
                    await asyncio.sleep(0.001)
    except Exception as e:
        print(f"Error while generating TTS: {e}")


async def get_assistant_helper(
    user_input: str,
    system_prompt: str = assistant_query_prompt,
    response_format=AssistantQuery,
) -> AssistantQuery:
    """
    Generate structured output using the AssistantQuery tool
    """
    try:
        messages = [{"role": "system", "content": system_prompt}]

        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": "User Query: " + user_input}],
            }
        )

        response = openai_client.beta.chat.completions.parse(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0.8,
            max_tokens=1500,
            response_format=response_format,
        )
        return response.choices[0].message.parsed

    except Exception as e:
        print(f"Error in generate_structured_output: {e}")
        # Return an AssistantQuery instance instead of a plain dict so the type hint is always satisfied.
        return AssistantQuery(
            other_user_information=False,
            target_users=None,
            refined_query=[f"Error generating structured output: {str(e)}"],
        )


def parse_audio_mime_type(mime_type: str) -> dict:
    """Parse audio mime type to extract parameters like sample rate and bits per sample."""
    # Default values for common audio formats
    defaults = {
        "rate": 24000,  # Default sample rate
        "bits_per_sample": 16,  # Default bits per sample
    }

    # Extract parameters from mime type if present
    # Example: audio/pcm;rate=24000;encoding=linear16
    if ";" in mime_type:
        parts = mime_type.split(";")
        for part in parts[1:]:
            if "rate=" in part:
                rate_match = re.search(r"rate=(\d+)", part)
                if rate_match:
                    defaults["rate"] = int(rate_match.group(1))
            elif "encoding=" in part and "16" in part:
                defaults["bits_per_sample"] = 16
            elif "encoding=" in part and "24" in part:
                defaults["bits_per_sample"] = 24

    return defaults


def convert_to_pcm(audio_data: bytes, mime_type: str) -> bytes:
    """Convert audio data to PCM format if needed."""
    if "pcm" in mime_type.lower():
        return audio_data

    # For WAV format, extract PCM data (skip header)
    if "wav" in mime_type.lower():
        # WAV header is typically 44 bytes
        if len(audio_data) > 44:
            return audio_data[44:]

    # For other formats, return as-is and let the client handle it
    return audio_data


async def get_assistant_helper_gemini(
    user_input, system_prompt: str = assistant_query_prompt, response_format=AssistantQuery
):
    """
    Generate structured output using the AssistantQuery tool with Gemini
    """
    try:
        # Handle both string and bytes input
        if isinstance(user_input, bytes):
            user_part = types.Part.from_bytes(
                data=user_input,
                mime_type="audio/mp3",
            )
        user_part = types.Part.from_text(text=f"User Query : {user_input}")

        contents = [
            types.Content(
                role="user",
                parts=[user_part],
            )
        ]

        generate_content_config = types.GenerateContentConfig(
            system_instruction=[
                types.Part.from_text(text=system_prompt),
            ],
            thinking_config=types.ThinkingConfig(
                thinking_level="MINIMAL",
            ),
            temperature=0.8,
            max_output_tokens=1500,
            response_mime_type="application/json",
            response_schema=response_format,
        )
        response = genai_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=generate_content_config,
        )
        print(f"Generated response: {response.text}")

        return response.parsed

    except Exception as e:
        print(f"Error in get_assistant_helper_gemini: {e}")
        # Return an AssistantQuery instance instead of a plain dict so the type hint is always satisfied.
        return AssistantQuery(
            other_user_information=False,
            target_users=None,
            refined_query=[f"Error generating structured output: {str(e)}"],
        )


async def generate_and_stream_gemini_res(
    websocket: WebSocket,
    user_input: str,
    system: str,
    chat_history=None,
    accent=DEFAULT_ACCENT,
    tone="Warm",
    mute=False,
    voice="coral",
    save_callback=None,
):
    """
    Generate response and stream audio simultaneously for minimal latency using Gemini
    """
    try:
        # Build conversation history
        contents = []
        # Add chat history if available
        if chat_history:
            for message in chat_history:
                role = "user" if message["role"] == "user" else "model"
                content_text = message["content"]
                if isinstance(content_text, list):
                    # Extract text from content array
                    content_text = (
                        content_text[0]["text"]
                        if content_text and "text" in content_text[0]
                        else ""
                    )

                contents.append(
                    types.Content(
                        role=role,
                        parts=[
                            types.Part.from_text(text=content_text),
                        ],
                    )
                )

        # Add current user input
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_input),
                ],
            )
        )

        generate_content_config = types.GenerateContentConfig(
            system_instruction=[
                types.Part.from_text(text=system),
            ],
            thinking_config=types.ThinkingConfig(
                thinking_level="MEDIUM",
            ),
            temperature=0.9,
            max_output_tokens=1500,
        )

        response = genai_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=generate_content_config,
        )

        response_text = response.text
        print(f"Generated response: {response_text}")

        # Save response to database immediately after generation, before streaming audio
        if save_callback:
            utc_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            audio_fname = f"{utc_ts}" if audio_bytes else None
            await save_callback(
                response_text,
                audio_bytes if not mute else None,
                audio_fname
            )
            print(f"Saved response to database immediately after generation")

        await websocket.send_text(json.dumps({"type": "audio_start", "format": "pcm"}))

        await websocket.send_text(
            json.dumps(
                {
                    "type": "response_chunk",
                    "content": response_text,
                    "full_text": response_text,
                }
            )
        )
        if not mute:
            audio_bytes = await stream_and_capture_sentence_audio(
                websocket,
                response_text,
                instructions=alex_speech_instructions,
                accent=accent,
                tone=tone,
                voice=voice,
                response_format="pcm",
            )
            utc_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            audio_filename = f"{utc_ts}" if audio_bytes else None

        await websocket.send_text(
            json.dumps({"type": "response", "text": response_text})
        )

        await websocket.send_text(json.dumps({"type": "audio_complete"}))

        if save_callback:
                try:
                    asyncio.create_task(save_callback(response_text, audio_bytes if 'audio_bytes' in locals() else None, audio_filename))
                except Exception:
                    logger.exception("Failed scheduling save_callback for gemini response")

        return response_text

    except Exception as e:
        print(f"Error in generate_and_stream_gemini_res: {e}")
        await websocket.send_text(
            json.dumps(
                {"type": "error", "message": f"Error generating response: {str(e)}"}
            )
        )
        return "I apologize, but I'm having trouble processing your request right now."


async def stream_gemini_audio(
    websocket: WebSocket,
    sentence: str,
    voice="Zephyr",
    instructions=None,
    accent=DEFAULT_ACCENT,
    tone="Warm",
):
    """
    Stream audio for a single sentence using Google Generative AI
    """
    prompt = (
        "instructions: " + instructions.format(accent=accent, tone=tone)
        if instructions
        else ""
    )
    prompt += f"\n\n{sentence}" if sentence else ""
    try:
        model = "gemini-2.5-flash-preview-tts"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=0.9,
            response_modalities=[
                "audio",
            ],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )

        # Stream audio chunks directly to websocket
        for chunk in genai_client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if (
                chunk.candidates is None
                or chunk.candidates[0].content is None
                or chunk.candidates[0].content.parts is None
            ):
                continue

            # Check if this chunk contains audio data
            if (
                chunk.candidates[0].content.parts[0].inline_data
                and chunk.candidates[0].content.parts[0].inline_data.data
            ):

                inline_data = chunk.candidates[0].content.parts[0].inline_data
                audio_data = inline_data.data
                print(f"Received audio chunk of size {len(audio_data)} bytes")
                await websocket.send_bytes(audio_data)
                print(f"Sent audio chunk of size {len(audio_data)} bytes")
            else:
                if hasattr(chunk, "text") and chunk.text:
                    print(f"Text response: {chunk.text}")

    except Exception as e:
        print(f"Error streaming gemini audio: {e}")


def get_voice_gender(gender: str) -> str:
    """Map gender to OpenAI TTS voice names."""
    if gender == "male":
        return "verse"
    if gender == "female":
        return "coral"

