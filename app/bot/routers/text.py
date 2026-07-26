"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 added the Splitter.
Phase 2.2 adds the full pipeline: split → time → classify → persist → reply.
Phase 2.3 adds the Critic (conditional review of classifier output).
Phase 2.3c replaces the deterministic reply with Courier.
Phase 2.3d adds reorder detection (move task to a different horizon).
WS3: accept replies/forwards of voice or text as pipeline input.

The pipeline body itself lives in ``app/bot/routers/_pipeline.py`` — this
file is just the aiogram glue. See ``docs/REVIEW-2026-05-09.md::I-4``.
"""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import F, Router
from aiogram.types import Message

from app.ai.whisper import transcribe_voice
from app.bot import reactions
from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.quote_replies import reply_to
from app.bot.rate_limit import get_rate_limiter
from app.bot.routers._message_payload import (
    TextPayload,
    VoicePayload,
    looks_like_reply_to_voice,
    resolve_effective_payload,
)
from app.bot.routers._pipeline import (
    get_groq_router,
    log_task_exception,
    run_pipeline,
)
from app.bot.routers.voice import _download_voice
from app.bot.services import (
    get_or_create_user,
    get_user_settings,
    log_ai_run,
    store_inbox_text,
    store_inbox_voice,
)
from app.bot.streaming import stream_reply
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)


def create_router() -> Router:
    """Build a fresh ``text`` router (catch-all)."""
    router = Router(name="text")

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Persist incoming text (or resolved reply/forward), run full pipeline, reply."""
        if message.from_user is None or message.text is None:
            return

        # Throttle the expensive LLM pipeline per user (CRIT-2). Cheap
        # in-memory check before we touch the DB or Groq.
        if not get_rate_limiter().allow(message.from_user.id):
            logger.info("ratelimit.text_throttled", tg_user_id=message.from_user.id)
            await message.answer(
                "Слишком много сообщений подряд — дай мне пару секунд разгрести. Попробуй ещё раз чуть позже."
            )
            return

        # Проверяем онбординг ДО плейсхолдера и до resolve (mirrors
        # voice.py): иначе неонборженный юзер навсегда видел «⏳ Разбираю…»,
        # а reply-на-голосовое ещё и впустую тратил Whisper.
        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return

        groq_router = get_groq_router()

        # Acknowledge the message *before* any potentially-slow work so
        # the user gets immediate feedback. If this is a reply to a voice
        # message, the resolver below will spend a few seconds on Whisper —
        # without the early placeholder the user sees nothing happening.
        chat_id = message.chat.id
        user_message_id = message.message_id
        if message.bot is not None:
            await reactions.set_reaction(message.bot, chat_id, user_message_id, reactions.RECEIVE)
        will_transcribe = looks_like_reply_to_voice(message)
        placeholder = await message.answer(
            "🎤 Расшифровываю голосовое…" if will_transcribe else "⏳ Разбираю…",
            reply_parameters=reply_to(chat_id=chat_id, message_id=user_message_id),
        )

        # Resolve the effective payload *before* the DB session so we can
        # store the actual content (not the instruction trigger) in inbox.
        # For reply-to-voice this calls Whisper — and the early placeholder
        # above is already on screen so the user sees progress.
        # Resolver can raise: Whisper rate-limit cascade
        # (GroqKeysExhaustedError), per-call timeout, download failure.
        # Without a try/except here the placeholder would hang forever
        # on "🎤 Расшифровываю…" and the user has no feedback — which is
        # the exact UX bug they reported (\"переотвечаю на гс — не разбирает\").
        try:
            payload = await resolve_effective_payload(
                message,
                transcribe=transcribe_voice,  # type: ignore[arg-type]
                download_voice=_download_voice,
                groq_router=groq_router,
            )
        except Exception:
            logger.exception(
                "text.resolve_failed",
                tg_user_id=message.from_user.id,
                will_transcribe=will_transcribe,
            )
            if message.bot is not None:
                await reactions.set_reaction(message.bot, chat_id, user_message_id, reactions.ERROR)
            with contextlib.suppress(Exception):
                await placeholder.edit_text(
                    "Не получилось расшифровать реплай-голосовое — попробуй ещё раз "
                    "через минуту или перешли его снова."
                    if will_transcribe
                    else "Ошибка при разборе — попробуй ещё раз."
                )
            return

        if payload is None:
            try:
                await placeholder.edit_text(
                    "Не нашёл, на что ты отвечаешь — перешли голосовое или текст ещё раз."
                )
            except Exception:
                await message.answer(
                    "Не нашёл, на что ты отвечаешь — перешли голосовое или текст ещё раз."
                )
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            assert user.id is not None

            # Store the *resolved* payload so the audit trail reflects what
            # actually went through the LLM pipeline.
            if isinstance(payload, TextPayload):
                entry = await store_inbox_text(
                    session,
                    user_id=user.id,
                    raw_text=payload.text,
                    telegram_message_id=message.message_id,
                )
            elif isinstance(payload, VoicePayload):
                # VoicePayload — we already have the transcript from Whisper.
                entry = await store_inbox_voice(
                    session,
                    user_id=user.id,
                    transcript=payload.transcript,
                    telegram_message_id=message.message_id,
                )
                if groq_router is not None:
                    from app.ai.models import get_models

                    await log_ai_run(
                        session,
                        user_id=user.id,
                        inbox_id=entry.id,
                        stage="whisper",
                        model=get_models().whisper,
                        key_index=groq_router.current_key_id,
                    )

            user_id = user.id
            user_tz = user.tz
            inbox_id = entry.id
            settings = await get_user_settings(session, user.id)
            critic_mode = settings.critic_mode if settings else "confidence"
            critic_threshold = settings.critic_confidence_threshold if settings else 0.7
            courier_mode = settings.response_style_source if settings else "mix"
            courier_style = settings.courier_template_style if settings else "neutral"
            default_offsets: dict[str, list[int]] | None = (
                {k: list(v) for k, v in settings.default_reminder_offsets.items()}
                if settings
                else None
            )
            morning_anchor = settings.morning_anchor if settings else "09:00"
            evening_anchor = settings.evening_anchor if settings else "19:00"
            concretize_tasks = settings.concretize_tasks if settings else False
            review_enabled = settings.review_enabled if settings else True

        effective_text = payload.text if isinstance(payload, TextPayload) else payload.transcript
        logger.info(
            "inbox.text_stored",
            user_id=message.from_user.id,
            text_len=len(effective_text),
            payload_kind="text" if isinstance(payload, TextPayload) else "voice_transcript",
        )

        if groq_router is None:
            try:
                await placeholder.edit_text("AI-разбор временно недоступен — сохраняю во входящие.")
            except Exception:
                await message.answer("AI-разбор временно недоступен — сохраняю во входящие.")
            return

        from_user_id = message.from_user.id

        # If we already transcribed a reply-target voice, the placeholder
        # currently shows "🎤 Расшифровываю…" — swap to the pipeline copy
        # so the user knows we've moved on to the actual parsing stage.
        # Best-effort: a failed edit is purely cosmetic.
        if will_transcribe:
            try:
                await placeholder.edit_text("⏳ Разбираю…")
            except Exception:
                logger.debug("pipeline.placeholder_handoff_failed", exc_info=True)

        async def _on_stage(stage_text: str) -> None:
            # Live-draft: edit the placeholder with a progress line while
            # the pipeline works. Best-effort — a failed edit (429/no-op)
            # must never break the pipeline.
            try:
                await placeholder.edit_text(stage_text)
            except Exception:
                logger.debug("pipeline.stage_edit_failed", exc_info=True)

        pipeline_text = effective_text

        async def _background() -> None:
            try:
                reply, keyboard = await run_pipeline(
                    groq_router,
                    pipeline_text,
                    from_user_id,
                    user_id,
                    user_tz,
                    inbox_id,
                    critic_mode=critic_mode,
                    confidence_threshold=critic_threshold,
                    courier_mode=courier_mode,
                    courier_style=courier_style,
                    default_reminder_offsets=default_offsets,
                    morning_anchor=morning_anchor,
                    evening_anchor=evening_anchor,
                    concretize_tasks=concretize_tasks,
                    review_enabled=review_enabled,
                    on_stage=_on_stage,
                )
                await stream_reply(
                    placeholder,
                    reply,
                    bot=message.bot,
                    reply_markup=keyboard,
                )
                if message.bot is not None:
                    await reactions.set_reaction(
                        message.bot, chat_id, user_message_id, reactions.SUCCESS
                    )
            except Exception:
                logger.exception(
                    "pipeline.error",
                    tg_user_id=from_user_id,
                    text_len=len(pipeline_text),
                )
                if message.bot is not None:
                    await reactions.set_reaction(
                        message.bot, chat_id, user_message_id, reactions.ERROR
                    )
                try:
                    await placeholder.edit_text(
                        "Ошибка при разборе — сохранил во входящие, разберу позже."
                    )
                except Exception:
                    await message.answer(
                        "Ошибка при разборе — сохранил во входящие, разберу позже."
                    )

        task = asyncio.create_task(_background())
        task.add_done_callback(log_task_exception)

    return router
