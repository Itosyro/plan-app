"""Router for voice messages.

Phase 2.3a: download voice file from Telegram, transcribe via Groq Whisper,
then run the same pipeline as text (split → time → classify → persist → reply).
Phase 2.3c: reply via Courier instead of deterministic text.
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import Message

from app.ai.whisper import transcribe_voice
from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.routers.text import _get_router, _run_pipeline
from app.bot.services import get_or_create_user, get_user_settings, log_ai_run, store_inbox_voice
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)

MAX_VOICE_SIZE = 20 * 1024 * 1024  # 20 MB — Telegram limit for voice


async def _download_voice(message: Message) -> bytes | None:
    """Download voice file bytes from Telegram."""
    if message.voice is None or message.bot is None:
        return None
    file = await message.bot.get_file(message.voice.file_id)
    if file.file_path is None:
        return None
    bio = await message.bot.download_file(file.file_path)
    if bio is None:
        return None
    return bio.read()


def create_router() -> Router:
    """Build a fresh ``voice`` router."""
    router = Router(name="voice")

    @router.message(F.voice)
    async def handle_voice(message: Message) -> None:
        """Transcribe voice, run full pipeline, reply."""
        if message.from_user is None or message.voice is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            if user.id is None:
                return
            user_id = user.id
            user_tz = user.tz
            settings = await get_user_settings(session, user.id)
            critic_mode = settings.critic_mode if settings else "confidence"
            critic_threshold = settings.critic_confidence_threshold if settings else 0.7
            courier_mode = settings.response_style_source if settings else "mix"
            courier_style = "neutral"

        groq_router = _get_router()
        if groq_router is None:
            await message.answer("AI-разбор временно недоступен — сохраняю во входящие.")
            return

        if message.voice.file_size and message.voice.file_size > MAX_VOICE_SIZE:
            await message.answer("Голосовое слишком большое (макс. 20 МБ).")
            return

        await message.answer("🎤 Расшифровываю голосовое…")

        from_user_id = message.from_user.id
        msg_id = message.message_id

        async def _background() -> None:
            try:
                audio_bytes = await _download_voice(message)
                if audio_bytes is None:
                    await message.answer("Не удалось скачать голосовое.")
                    return

                transcript = await transcribe_voice(groq_router, audio_bytes)

                if not transcript or len(transcript.strip()) < 2:
                    await message.answer("Не удалось распознать речь — попробуй ещё раз.")
                    return

                # Store inbox entry with transcript
                async with session_scope() as session:
                    entry = await store_inbox_voice(
                        session,
                        user_id=user_id,
                        transcript=transcript,
                        telegram_message_id=msg_id,
                    )
                    inbox_id = entry.id

                    await log_ai_run(
                        session,
                        user_id=user_id,
                        inbox_id=inbox_id,
                        stage="whisper",
                        model="whisper-large-v3",
                        key_index=groq_router.current_key_id,
                    )

                logger.info(
                    "voice.transcribed",
                    tg_user_id=from_user_id,
                    transcript_len=len(transcript),
                )

                reply = await _run_pipeline(
                    groq_router,
                    transcript,
                    from_user_id,
                    user_id,
                    user_tz,
                    inbox_id,
                    critic_mode=critic_mode,
                    confidence_threshold=critic_threshold,
                    courier_mode=courier_mode,
                    courier_style=courier_style,
                )
                await message.answer(reply)

            except Exception:
                logger.exception(
                    "voice.pipeline_error",
                    tg_user_id=from_user_id,
                )
                await message.answer("Ошибка при обработке голосового — попробуй ещё раз.")

        task = asyncio.create_task(_background())
        task.add_done_callback(
            lambda t: t.result() if not t.cancelled() else None,
        )

    return router
