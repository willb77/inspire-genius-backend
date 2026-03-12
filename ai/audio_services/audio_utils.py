import shutil
import subprocess
import asyncio
from typing import Optional

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None

def _convert_to_pcm_sync(input_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg required for reliable format conversion (install with brew/apt)")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", str(sample_rate), "-ac", str(channels),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {proc.stderr.decode(errors='ignore')}")
    return proc.stdout

async def convert_to_pcm(input_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    return await asyncio.to_thread(_convert_to_pcm_sync, input_bytes, sample_rate, channels)