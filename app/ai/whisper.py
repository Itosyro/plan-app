"""Whisper — transcribe voice messages via Groq Whisper API.

Uses ``whisper-large-v3`` for maximum accuracy on Russian speech.
The caller downloads the Telegram voice file and passes raw bytes.
"""

from __future__ import annotations

import time

from groq import AsyncGroq

from app.ai.router import GroqKeyRouter
from app.shared.logging import get_logger

logger = get_logger(__name__)

WHISPER_MODEL = "whisper-large-v3"


async def transcribe_voice(
    router: GroqKeyRouter,
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
) -> str:
    """Transcribe *audio_bytes* to text via Groq Whisper.

    Returns the transcribed text (may be empty for silence / noise).
    """
    client = AsyncGroq(api_key=router.current_key)

    t0 = time.monotonic()
    result = await client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, audio_bytes),
        language="ru",
        response_format="text",
        temperature=0.0,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    text = str(result).strip()

    logger.info(
        "whisper.done",
        text_len=len(text),
        audio_bytes=len(audio_bytes),
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return text
