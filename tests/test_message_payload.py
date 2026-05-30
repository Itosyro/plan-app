"""Unit tests for app/bot/routers/_message_payload.py.

These tests use lightweight stand-in dataclasses instead of real aiogram
Message objects — no aiogram or Groq imports required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.bot.routers._message_payload import (
    TextPayload,
    VoicePayload,
    is_short_instruction,
    resolve_effective_payload,
)

# ---------------------------------------------------------------------------
# Minimal stand-in objects (no aiogram dependency)
# ---------------------------------------------------------------------------


@dataclass
class _Voice:
    file_id: str = "voice_file_id"
    file_size: int = 1024
    duration: int = 10  # seconds — long enough that we'd transcribe it


@dataclass
class _FakeMessage:
    """Minimal stand-in for aiogram.types.Message."""

    text: str | None = None
    caption: str | None = None
    voice: _Voice | None = None
    audio: Any = None
    reply_to_message: _FakeMessage | None = None
    forward_origin: Any = None  # set on forwarded messages
    bot: Any = None
    message_id: int = 1
    from_user: Any = None
    chat: Any = None


# ---------------------------------------------------------------------------
# is_short_instruction
# ---------------------------------------------------------------------------


class TestIsShortInstruction:
    def test_empty_string(self) -> None:
        assert is_short_instruction("") is True

    def test_whitespace_only(self) -> None:
        assert is_short_instruction("   ") is True

    def test_keyword_exact(self) -> None:
        assert is_short_instruction("разбери") is True

    def test_keyword_with_leading_space(self) -> None:
        assert is_short_instruction("  Разбери это пожалуйста") is True

    def test_keyword_mixed_case(self) -> None:
        assert is_short_instruction("РАЗБЕРИ") is True

    def test_keyword_сделай_задачи(self) -> None:
        assert is_short_instruction("сделай задачи") is True

    def test_keyword_разложи(self) -> None:
        assert is_short_instruction("разложи") is True

    def test_keyword_посмотри(self) -> None:
        assert is_short_instruction("посмотри") is True

    def test_keyword_что_это(self) -> None:
        assert is_short_instruction("что это") is True

    def test_negative_купи_хлеб(self) -> None:
        assert is_short_instruction("Купи хлеб") is False

    def test_negative_meeting(self) -> None:
        assert is_short_instruction("Завтра встреча с Анной в 15:00") is False

    def test_negative_long_instruction_lookalike(self) -> None:
        # Longer than _MAX_INSTRUCTION_LEN — should NOT be treated as instruction.
        long_text = (
            "разбери пожалуйста вот это длинное сообщение которое явно длиннее сорока символов"
        )
        assert is_short_instruction(long_text) is False

    def test_negative_substantial_text_no_keyword(self) -> None:
        assert is_short_instruction("Встреча в 15:00") is False


# ---------------------------------------------------------------------------
# Stub helpers for resolve_effective_payload
# ---------------------------------------------------------------------------

_FAKE_TRANSCRIPT = "transcribed voice text"
_FAKE_BYTES = b"audio bytes"


async def _stub_download_ok(message: _FakeMessage) -> bytes | None:  # type: ignore[override]
    voice = getattr(message, "voice", None) or getattr(message, "audio", None)
    if voice is None:
        return None
    return _FAKE_BYTES


async def _stub_download_fail(message: _FakeMessage) -> bytes | None:  # type: ignore[override]
    return None


async def _stub_transcribe(groq_router: Any, audio_bytes: bytes) -> str:
    return _FAKE_TRANSCRIPT


_TARGET_TRANSCRIPT = "купить хлеб и молоко завтра в супермаркете"


class _ScriptedTranscriber:
    """Returns different transcripts on successive calls — simulates
    transcribing the own short instruction first, then the reply target."""

    def __init__(self, *transcripts: str) -> None:
        self._queue: list[str] = list(transcripts)

    async def __call__(self, groq_router: Any, audio_bytes: bytes) -> str:
        return self._queue.pop(0) if self._queue else _FAKE_TRANSCRIPT


# ---------------------------------------------------------------------------
# resolve_effective_payload tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResolveEffectivePayload:
    async def test_own_substantial_text_returns_text_payload(self) -> None:
        """A message with substantial own text → TextPayload with that text."""
        msg = _FakeMessage(text="Встреча завтра в 15:00")
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == "Встреча завтра в 15:00"

    async def test_own_voice_returns_voice_payload(self) -> None:
        """A message with own voice → VoicePayload after transcription."""
        msg = _FakeMessage(voice=_Voice())
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        assert result.transcript == _FAKE_TRANSCRIPT

    async def test_reply_empty_own_text_text_reply_to(self) -> None:
        """Reply with empty own text + text reply target → TextPayload from target."""
        replied = _FakeMessage(text="Встреча с командой завтра в 10:00 в офисе")
        msg = _FakeMessage(text="разбери", reply_to_message=replied)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == replied.text

    async def test_reply_empty_own_text_voice_reply_to(self) -> None:
        """Reply with empty own text + voice reply target → VoicePayload (transcribed)."""
        replied = _FakeMessage(voice=_Voice(file_id="replied_voice"))
        msg = _FakeMessage(text="", reply_to_message=replied)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        assert result.transcript == _FAKE_TRANSCRIPT

    async def test_reply_with_substantial_own_text_uses_own_text(self) -> None:
        """Reply with substantial own text → own text wins, reply target ignored."""
        replied = _FakeMessage(text="Это другой текст что не должен использоваться")
        msg = _FakeMessage(
            text="Встреча в 14:00 завтра в кафе у метро",
            reply_to_message=replied,
        )
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == msg.text

    async def test_non_reply_empty_text_no_voice_returns_none(self) -> None:
        """Plain message with empty text and no voice → None."""
        msg = _FakeMessage(text="")
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert result is None

    async def test_non_reply_whitespace_text_no_voice_returns_none(self) -> None:
        """Plain message with whitespace-only text and no voice → None."""
        msg = _FakeMessage(text="   ")
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert result is None

    async def test_forwarded_voice_treated_as_own_voice(self) -> None:
        """Forwarded voice message (forward_origin set, own voice populated) → VoicePayload."""
        msg = _FakeMessage(
            voice=_Voice(file_id="fwd_voice"),
            forward_origin=object(),  # non-None signals forward
        )
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        assert result.transcript == _FAKE_TRANSCRIPT

    async def test_forwarded_text_treated_as_own_text(self) -> None:
        """Forwarded text message (forward_origin set, own text populated) → TextPayload."""
        msg = _FakeMessage(
            text="Задача: подготовить отчёт к пятнице",
            forward_origin=object(),
        )
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == msg.text

    async def test_reply_to_empty_target_returns_none(self) -> None:
        """Reply to a message that has no text and no voice → None."""
        replied = _FakeMessage(text=None, voice=None)
        msg = _FakeMessage(text="разбери", reply_to_message=replied)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert result is None

    async def test_download_fails_returns_none(self) -> None:
        """If voice download fails, resolver returns None rather than crashing."""
        msg = _FakeMessage(voice=_Voice())
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_fail,  # type: ignore[arg-type]
        )
        assert result is None

    async def test_caption_used_when_text_absent(self) -> None:
        """If message has no .text but has .caption, caption is used."""
        msg = _FakeMessage(text=None, caption="Встреча завтра в 9 утра в офисе")
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == "Встреча завтра в 9 утра в офисе"

    async def test_reply_caption_used_when_target_has_no_text(self) -> None:
        """Reply target with caption (no text) → TextPayload from caption."""
        replied = _FakeMessage(text=None, caption="Фото с встречи — запиши в задачи")
        msg = _FakeMessage(text="разбери", reply_to_message=replied)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=_stub_transcribe,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, TextPayload)
        assert result.text == replied.caption


# ---------------------------------------------------------------------------
# looks_like_reply_to_voice (cheap pre-flight; no network)
# ---------------------------------------------------------------------------


from app.bot.routers._message_payload import looks_like_reply_to_voice  # noqa: E402


class TestLooksLikeReplyToVoice:
    def test_reply_to_voice_with_instruction(self) -> None:
        replied = _FakeMessage(voice=_Voice())
        msg = _FakeMessage(text="разбери", reply_to_message=replied)
        assert looks_like_reply_to_voice(msg) is True  # type: ignore[arg-type]

    def test_reply_to_voice_with_empty_body(self) -> None:
        replied = _FakeMessage(voice=_Voice())
        msg = _FakeMessage(text="", reply_to_message=replied)
        assert looks_like_reply_to_voice(msg) is True  # type: ignore[arg-type]

    def test_reply_to_text_returns_false(self) -> None:
        replied = _FakeMessage(text="Какой-то текст")
        msg = _FakeMessage(text="разбери", reply_to_message=replied)
        assert looks_like_reply_to_voice(msg) is False  # type: ignore[arg-type]

    def test_substantial_own_text_returns_false(self) -> None:
        """If the user wrote substantial content themselves, we don't
        plan to transcribe the reply target — even if it's a voice."""
        replied = _FakeMessage(voice=_Voice())
        msg = _FakeMessage(text="Купить молоко и хлеб завтра", reply_to_message=replied)
        assert looks_like_reply_to_voice(msg) is False  # type: ignore[arg-type]

    def test_no_reply_returns_false(self) -> None:
        msg = _FakeMessage(text="разбери")
        assert looks_like_reply_to_voice(msg) is False  # type: ignore[arg-type]

    def test_own_voice_returns_false(self) -> None:
        """A direct voice message hits the voice router, not text — so
        even if it has a reply target, we don't flag for text-side
        transcription."""
        replied = _FakeMessage(voice=_Voice())
        msg = _FakeMessage(voice=_Voice(), reply_to_message=replied)
        assert looks_like_reply_to_voice(msg) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Voice-on-voice reply (own voice that's actually an instruction trigger)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVoiceOnVoiceReply:
    """When the user replies to a prior voice WITH a new voice (rather
    than a typed «разбери»), we should still route to the reply target.

    Two code paths cover this — a short ``duration`` skips the first
    Whisper call entirely as an optimisation, while a longer-than-3s
    own voice gets transcribed but routed by ``is_short_instruction``."""

    async def test_short_duration_skips_own_transcription(self) -> None:
        """duration ≤ 3s + reply-to-voice → take the reply target directly,
        save one Whisper round-trip."""
        replied = _FakeMessage(voice=_Voice(duration=12))
        own_voice = _Voice(duration=2)
        msg = _FakeMessage(voice=own_voice, reply_to_message=replied)

        # Scripted transcriber asserts we only ever ask Whisper once
        # (for the reply target, not the short own voice).
        scripted = _ScriptedTranscriber(_TARGET_TRANSCRIPT)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=scripted,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        assert result.transcript == _TARGET_TRANSCRIPT
        # One call left unconsumed → exactly one transcribe call happened.
        assert scripted._queue == []

    async def test_long_own_voice_with_instruction_routes_to_reply(self) -> None:
        """duration > 3s but transcript is an instruction → reply target wins."""
        replied = _FakeMessage(voice=_Voice(duration=15))
        own_voice = _Voice(duration=5)  # > 3s, so we don't skip
        msg = _FakeMessage(voice=own_voice, reply_to_message=replied)

        scripted = _ScriptedTranscriber("разбери", _TARGET_TRANSCRIPT)
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=scripted,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        assert result.transcript == _TARGET_TRANSCRIPT

    async def test_long_own_voice_with_content_keeps_own_transcript(self) -> None:
        """duration > 3s and own transcript is substantial → own wins,
        reply target is ignored (matches the text-side semantic)."""
        replied = _FakeMessage(voice=_Voice(duration=15))
        own_voice = _Voice(duration=8)
        msg = _FakeMessage(voice=own_voice, reply_to_message=replied)

        scripted = _ScriptedTranscriber(
            "ещё купить помидоры и оливковое масло на завтра",
            _TARGET_TRANSCRIPT,
        )
        result = await resolve_effective_payload(
            msg,  # type: ignore[arg-type]
            transcribe=scripted,
            download_voice=_stub_download_ok,  # type: ignore[arg-type]
        )
        assert isinstance(result, VoicePayload)
        # Own substantial transcript wins; reply target was never fetched.
        assert "помидоры" in result.transcript
        assert _TARGET_TRANSCRIPT not in result.transcript
