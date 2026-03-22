from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse,HTMLResponse
from prism_inspire.core.file_utils import S3_BUCKET, S3FileHandler, file_handler
import asyncio, io, os, wave, json, urllib.parse, boto3
from prism_inspire.core.log_config import logger
from botocore.exceptions import ClientError, BotoCoreError
from prism_inspire.db.session import ScopedSession
from ai.file_services.schema import get_audio_file_path_by_message_id
from typing import Optional
from users.decorators import require_super_admin_role

audio_service = APIRouter(tags=["Audio Service"])

@audio_service.get("/audio/download_by_key")
async def download_by_key(key: str = Query(...)):
    if not key:
        raise HTTPException(status_code=400, detail="missing 'key' parameter")

    bucket = S3_BUCKET or os.getenv("S3_BUCKET_NAME")
    if not bucket:
        logger.error("S3 bucket not configured")
        raise HTTPException(status_code=500, detail="S3 bucket not configured on server")

    client = file_handler.s3_client

    def _get_obj(bkt: str, k: str):
        return client.get_object(Bucket=bkt, Key=k)

    try:
        obj = await asyncio.to_thread(_get_obj, bucket, key)

        if not obj or "Body" not in obj or obj["Body"] is None:
            logger.error("S3 get_object returned no Body for key=%s (obj=%s)", key, obj)
            raise HTTPException(status_code=404, detail="Object not found")
        def _read_body(stream_obj):
            data = stream_obj.read()
            try:
                stream_obj.close()
            except Exception:
                pass
            return data

        body = await asyncio.to_thread(_read_body, obj["Body"])

        if not body:
            raise HTTPException(status_code=404, detail="Object body is empty")

        # Prefer ContentType from S3, but coerce PCM keys to audio/pcm
        s3_ct = (obj.get("ContentType") or "application/octet-stream")
        filename = (os.path.basename(key) if key else "download.bin")

        # If key looks like PCM, serve as audio/pcm and ensure .pcm filename
        if key.lower().endswith(".pcm") or ("pcm" in s3_ct.lower()):
            content_type = "audio/pcm"
            if not filename.lower().endswith(".pcm"):
                filename = os.path.splitext(filename)[0] + ".pcm"
        elif body[:4] == b"RIFF" or "wav" in s3_ct.lower():
            content_type = "audio/wav"
            if not filename.lower().endswith(".wav"):
                filename = os.path.splitext(filename)[0] + ".wav"
        else:
            content_type = s3_ct

        # Build response headers to mirror S3 / frontend endpoint behavior
        cache_control = obj.get("CacheControl") or "public,max-age=86400"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(body)),
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Cache-Control": cache_control,
        }
        etag = obj.get("ETag")
        if etag:
            headers["ETag"] = str(etag)
        last_mod = obj.get("LastModified")
        if last_mod:
            try:
                headers["Last-Modified"] = last_mod.strftime("%a, %d %b %Y %H:%M:%S GMT")
            except Exception:
                headers["Last-Modified"] = str(last_mod)

        return StreamingResponse(io.BytesIO(body), media_type=content_type, headers=headers)

    except ClientError as e:
        # unified ClientError handling
        code = e.response.get("Error", {}).get("Code")
        logger.exception("S3 ClientError for key=%s: %s", key, e)
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Object not found")
        raise HTTPException(status_code=502, detail=f"S3 error: {code or str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error downloading S3 object %s: %s", key, e)
        raise HTTPException(status_code=500, detail=str(e))
    
@audio_service.get("/S3_objects")
def list_objects(
    user_data: dict = Depends(require_super_admin_role()),
):
    """
    List the Objects in the S3 Bucket.
    """

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("S3_BUCKET_NAME")


    if not access_key or not secret_key or not bucket:
        raise HTTPException(status_code=500, detail="S3 credentials or bucket not configured in environment")

    client = getattr(file_handler, "s3_client", None)
    if not client:
        client_kwargs = {"aws_access_key_id": access_key, "aws_secret_access_key": secret_key}
        region = os.getenv("AWS_REGION") or os.getenv("S3_REGION")
        if region:
            client_kwargs["region_name"] = region
        client = boto3.client("s3", **client_kwargs)
    try:
        resp = client.list_objects_v2(Bucket=bucket)
        items = [obj["Key"] for obj in resp.get("Contents", [])]
        return {"bucket": bucket, "keys": items}
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=502, detail=f"S3 list_objects failed: {e}")


###########################################  WebSocket Audio Playback  ###########################################

def _resolve_audio_path(message_id: str) -> str | None:
    """
    Resolve audio file path for a given message_id.
    Prefer project's helper if available, otherwise fallback to common tmp path.
    """
    if get_audio_file_path_by_message_id:
        try:
            p = get_audio_file_path_by_message_id(message_id)
            if p:
                return p
        except Exception as e:
            logger.error(f"audio_service: helper get_audio_file_path_by_message_id error: {e}")

    candidates = [
        f"/tmp/audio/{message_id}.wav",
        f"/tmp/audio/{message_id}.mp3",
        f"/var/tmp/audio/{message_id}.wav",
        f"./audio_output/{message_id}.wav",
        f"./audio_output/{message_id}.mp3",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


async def _stream_file_in_chunks(ws: WebSocket, file_path: str, chunk_size: int = 65536):
    """
    Async streaming of binary file in chunks to websocket.
    Sends a small JSON metadata message first, then binary chunks, then an 'end' text message.
    """
    try:
        await ws.send_text(json.dumps({"type": "audio_start", "file": os.path.basename(file_path)}))
    except Exception:
        logger.error(f"audio_service: failed to send audio_start for {file_path}")

    loop = asyncio.get_running_loop()
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = await loop.run_in_executor(None, f.read, chunk_size)
                if not chunk:
                    break
                await ws.send_bytes(chunk)
    except Exception as e:
        logger.error(f"audio_service: error streaming file {file_path}: {e}")
        try:
            await ws.send_text(json.dumps({"type": "audio_error", "message": str(e)}))
        except Exception:
            pass
        raise

    try:
        await ws.send_text(json.dumps({"type": "audio_end"}))
    except Exception:
        pass

@audio_service.websocket("/audio/ws/play_message/{message_id}")
async def audio_playback(ws: WebSocket, message_id: str):
    # Allow client to override the path param using query param 'id' or 'message_id'
    query_string = ws.scope.get("query_string", b"").decode()
    if query_string:
        try:
            qs = urllib.parse.parse_qs(query_string)
            qid = (qs.get("id") or qs.get("message_id") or [None])[0]
            if qid:
                message_id = qid
        except Exception:
            pass

    try:
        await ws.accept()
    except Exception as e:
        logger.error(f"[audio-service-{message_id}] WebSocket accept failed: {e}")
        try:
            await ws.close()
        except Exception:
            pass
        return

    try:
        # Wait briefly for an init message (so FE can send init payload after open).
        # If none arrives within timeout, continue using the path message_id.
        init_payload = None
        try:
            init_msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
            text = init_msg.get("text")
            if text:
                try:
                    parsed = json.loads(text)
                    if parsed.get("type") == "init":
                        init_payload = parsed
                    elif "message_id" in parsed:
                        init_payload = parsed
                except Exception:
                    init_payload = None
        except asyncio.TimeoutError:
            init_payload = None
        except Exception:
            init_payload = None

        if init_payload:
            # override message_id if provided in init payload
            msg_id_from_payload = init_payload.get("message_id") or init_payload.get("id")
            if msg_id_from_payload:
                message_id = msg_id_from_payload

        # Resolve file and stream
        file_path = _resolve_audio_path(message_id)
        if not file_path:
            try:
                await ws.send_text(json.dumps({"type": "audio_error", "message": "audio_not_found"}))
            except Exception:
                pass
            await ws.close()
            return

        # Stream and close when done
        await _stream_file_in_chunks(ws, file_path)

    except WebSocketDisconnect:
        logger.info(f"[audio-service-{message_id}] WebSocket disconnected by client.")
    except Exception as e:
        logger.error(f"[audio-service-{message_id}] Error: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass
        logger.info(f"[audio-service-{message_id}] Connection closed.")