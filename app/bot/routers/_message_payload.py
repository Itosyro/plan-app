"""Resolve the *effective* content payload for a message.

Handles three surfaces:
1. Plain message with its own text / voice  → use it directly.
2. Reply to another message with empty/instruction-only body → borrow the
   replied-to message's text or voice.
3. Forwarded message → Telegram populates ``.text`` / ``.voice`` on the
   forwarding message itself, so it is treated exactly like case 1 — no
   special handling needed.

The public API is:

    payload = await resolve_effective_payload(
        message,
        transcribe=transcribe_voice,   # injected so tests can stub it
        download_voice=_download_voice, # injected likewise
    )
    if payload is None:
        # nothing parseable — send a friendly error
    elif isinstance(payload, TextPayload):
        run_pipeline(groq_router, payload.text, ...)
    elif isinstance(payload, VoicePayload):
        run_pipeline(groq_router, payload.transcript, ...)

See WS3 in the sprint plan.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Message

# ---------------------------------------------------------------------------
# Instruction-keyword detection
# ---------------------------------------------------------------------------

#: Lowercased trigger words / phrases that signal "process the referred
#: message, not me".  Keep entries short — ``is_short_instruction`` does a
#: *contains* check so "разбери это пожалуйста" matches "разбери".
INSTRUCTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "разбери",
        "разложи",
        "сделай задачи",
        "сделай задачу",
        "что это",
        "посмотри",
        "обработай",
        "распарси",
        "парсани",
        "добавь",
        "запиши",
        "занеси",
    }
)

#: Own-content minimum to NOT fall through to the reply target.
#: 8 characters → short instructions like "разбери" (7 chars) fall through,
#: real content like "Встреча в 15:00" (15 chars) stays on its own path.
_MIN_SUBSTANTIAL_TEXT = 8

#: Upper bound on the *own* message length that we're even willing to treat
#: as an instruction.  A 25-char text could still be "Разбери это пожалуйста" —
#: we don't want to accidentally swallow longer prose.
_MAX_INSTRUCTION_LEN = 40


def _normalize(text: str) -> str:
    """Lowercase + strip leading/trailing whitespace + collapse internal spaces."""
    text = unicodedata.normalize("NFC", text).lower().strip()
    return re.sub(r"\s+", " ", text)


def is_short_instruction(text: str) -> bool:
    """Return *True* if *text* looks like an instruction to process a referred
    message rather than content in its own right.

    Positive cases:
    - Empty / whitespace-only string.
    - Text that is ≤ ``_MAX_INSTRUCTION_LEN`` chars AND whose normalised form
      *starts with* or *is contained in* one of ``INSTRUCTION_KEYWORDS``.

    Negative cases:
    - Anything with ≥ ``_MIN_SUBSTANTIAL_TEXT`` non-whitespace chars that
      does not match a keyword (e.g. "Купи хлеб", "Встреча в 15:00").
    """
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) > _MAX_INSTRUCTION_LEN:
        return False
    norm = _normalize(stripped)
    return any(norm == kw or norm.startswith(kw) or kw in norm for kw in INSTRUCTION_KEYWORDS)


# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextPayload:
    """Resolved text ready for the pipeline."""

    text: str


@dataclass(frozen=True, slots=True)
class VoicePayload:
    """Resolved voice transcript ready for the pipeline."""

    transcript: str


Payload = TextPayload | VoicePayload


# ---------------------------------------------------------------------------
# Cheap pre-flight check (no network)
# ---------------------------------------------------------------------------


def looks_like_reply_to_voice(message: Message) -> bool:
    """Return True if this message is a reply with an empty/instruction body
    and the replied-to message is voice/audio.

    Used by the text router to *predict* whether ``resolve_effective_payload``
    will spend time on Whisper, so it can post a tailored
    "🎤 Расшифровываю реплай-голосовое…" placeholder before the
    transcription starts. Purely string + attribute inspection — no
    network, no DB.
    """
    own_voice = getattr(message, "voice", None) or getattr(message, "audio", None)
    if own_voice is not None:
        return False  # own voice path is handled by the voice router
    own_text: str = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    if own_text and not is_short_instruction(own_text):
        return False
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return False
    reply_voice = getattr(reply, "voice", None) or getattr(reply, "audio", None)
    return reply_voice is not None


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

# Type aliases for the injected callables so callers and tests are explicit.
TranscribeFn = Callable[[object, bytes], Awaitable[str]]
DownloadFn = Callable[["Message"], Awaitable[bytes | None]]


async def resolve_effective_payload(
    message: Message,
    *,
    transcribe: TranscribeFn,
    download_voice: DownloadFn,
    groq_router: object | None = None,
) -> Payload | None:
    """Return the effective payload for *message*, or *None* if nothing parseable.

    Decision tree
    -------------
    1. If the message has its own voice → VoicePayload (download + transcribe).
    2. If the message has substantial text (≥ ``_MIN_SUBSTANTIAL_TEXT`` chars
       and not an instruction) → TextPayload.
    3. Otherwise, if the message is a *reply*:
       a. replied-to has voice → download + transcribe → VoicePayload.
       b. replied-to has text/caption → TextPayload.
       c. nothing parseable in reply target → None.
    4. No reply and no own content → None.

    Forwarded messages arrive with ``.forward_origin`` set *and* with
    ``.voice`` / ``.text`` populated on the message itself, so they are
    handled by steps 1–2 transparently (no special branch needed).

    ``groq_router`` is passed through to ``transcribe`` as the first
    positional argument (matching the real ``transcribe_voice`` signature).
    The injected callable therefore has signature
    ``(groq_router, audio_bytes) -> Awaitable[str]``.
    """
    own_voice = getattr(message, "voice", None) or getattr(message, "audio", None)
    own_text: str = getattr(message, "text", None) or getattr(message, "caption", None) or ""

    # ── Step 1: own voice ──────────────────────────────────────────────────
    if own_voice is not None:
        audio_bytes = await download_voice(message)
        if audio_bytes is None:
            return None
        transcript = await transcribe(groq_router, audio_bytes)
        return VoicePayload(transcript=transcript)

    # ── Step 2: own substantial text ──────────────────────────────────────
    if own_text and not is_short_instruction(own_text):
        return TextPayload(text=own_text)

    # ── Step 3: fall back to reply target ─────────────────────────────────
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return None

    reply_voice = getattr(reply, "voice", None) or getattr(reply, "audio", None)
    reply_text: str = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""

    if reply_voice is not None:
        audio_bytes = await download_voice(reply)
        if audio_bytes is None:
            return None
        transcript = await transcribe(groq_router, audio_bytes)
        return VoicePayload(transcript=transcript)

    if reply_text:
        return TextPayload(text=reply_text)

    return None
