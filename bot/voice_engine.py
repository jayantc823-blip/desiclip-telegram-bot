"""Async Hindi speech generation using Microsoft's public Edge TTS service."""
import asyncio
import logging
from pathlib import Path
import edge_tts

log = logging.getLogger(__name__)

async def synthesize(text: str, destination: Path, voice: str = "hi-IN-MadhurNeural", rate: str = "+14%", pitch: str = "+5Hz"):
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(destination))
        return destination
    except Exception as exc:
        log.warning("Edge TTS failed; clip will use original audio: %s", exc)
        return None
