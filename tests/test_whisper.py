"""Tests for Whisper transcription. All Groq calls mocked via respx."""

from __future__ import annotations

import pytest
import respx

from app.ai.router import GroqKeyRouter
from app.ai.whisper import transcribe_voice

_FAKE_KEYS = ["gsk_test_key_1"]


def _mock_whisper(text: str) -> None:
    """Mock Groq audio transcription endpoint returning plain text."""
    respx.post("https://api.groq.com/openai/v1/audio/transcriptions").mock(
        return_value=respx.MockResponse(200, text=text),
    )


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_voice_basic() -> None:
    """Basic transcription returns expected text."""
    _mock_whisper("утром пробежка пять километров потом совещание в одиннадцать")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await transcribe_voice(router, b"\x00" * 100)
    assert "пробежка" in result
    assert "совещание" in result


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_voice_empty() -> None:
    """Empty audio returns empty string."""
    _mock_whisper("")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await transcribe_voice(router, b"\x00" * 50)
    assert result == ""


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_voice_whitespace() -> None:
    """Whisper returning only whitespace is stripped."""
    _mock_whisper("   \n  ")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await transcribe_voice(router, b"\x00" * 50)
    assert result == ""


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_voice_short_phrase() -> None:
    """Short phrase transcription works."""
    _mock_whisper("купить хлеб")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await transcribe_voice(router, b"\x00" * 30)
    assert result == "купить хлеб"


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_voice_custom_filename() -> None:
    """Custom filename is passed through to API."""
    _mock_whisper("тест голосового")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await transcribe_voice(router, b"\x00" * 30, filename="message.oga")
    assert result == "тест голосового"
