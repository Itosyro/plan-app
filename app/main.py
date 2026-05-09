"""FastAPI entry point + Telegram webhook integration.

Phase 1 wiring:
- spin up an aiogram ``Bot`` + ``Dispatcher`` with onboarding + text routers,
- on startup, register the Telegram webhook (`setWebhook`) with
  ``drop_pending_updates=True`` and a secret token,
- expose ``POST /tg/<secret>`` for incoming updates with double validation
  (path secret + ``X-Telegram-Bot-Api-Secret-Token`` header),
- expose ``GET /healthz`` for Render health checks.

REST API for the mini-app (``/api/*``) lands in Phase 5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from sqlmodel import select

from app.bot import build_dispatcher
from app.bot.services import is_update_processed, record_update
from app.db.base import dispose_engine, init_engine, session_scope
from app.db.models import User
from app.shared.config import Settings, get_settings
from app.shared.logging import configure_logging, get_logger
from app.workers.runner import start_inproc_scheduler, stop_inproc_scheduler


def _extract_tg_user_id(update: Update) -> int | None:
    """Return the Telegram ``from_user.id`` from an update, or ``None``.

    Walks the populated optional sub-field. Used both for logging and to
    populate ``TelegramUpdate.user_id`` (after a lookup against
    ``users.telegram_id``). See ``docs/REVIEW-2026-05-09.md::I-7``.
    """
    if update.message is not None and update.message.from_user is not None:
        return update.message.from_user.id
    if update.edited_message is not None and update.edited_message.from_user is not None:
        return update.edited_message.from_user.id
    if update.callback_query is not None and update.callback_query.from_user is not None:
        return update.callback_query.from_user.id
    if update.inline_query is not None and update.inline_query.from_user is not None:
        return update.inline_query.from_user.id
    return None


def _classify_update(update: Update) -> str:
    """Map an aiogram ``Update`` to a short string kind for logs.

    ``type(update).__name__`` is always ``"Update"`` so it tells us
    nothing — branch on the populated optional sub-field instead. See
    ``docs/REVIEW-findings.md::I-2``.
    """
    if update.message is not None:
        return "message"
    if update.edited_message is not None:
        return "edited_message"
    if update.callback_query is not None:
        return "callback_query"
    if update.inline_query is not None:
        return "inline_query"
    if update.channel_post is not None:
        return "channel_post"
    if update.edited_channel_post is not None:
        return "edited_channel_post"
    return "other"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI app.

    ``settings`` is injectable so tests can pass an in-memory SQLite URL,
    a fake bot token and an empty ``webhook_base_url`` (which suppresses
    the live ``setWebhook`` call).
    """
    settings = settings or get_settings()
    configure_logging()
    logger = get_logger(__name__)

    bot: Bot | None = None
    dp: Dispatcher = build_dispatcher()

    if settings.telegram_bot_token:
        bot = Bot(token=settings.telegram_bot_token)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        scheduler_handle: tuple[object, object] | None = None
        if settings.database_url:
            init_engine(settings.database_url)
            logger.info("db.engine.init")
        if bot is not None and settings.webhook_url:
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.telegram_webhook_secret,
                drop_pending_updates=True,
            )
            logger.info("bot.webhook.set", url=settings.webhook_url)
        if bot is not None and settings.database_url and settings.scheduler_inproc_enabled:
            task, stop = start_inproc_scheduler(
                bot,
                interval=settings.scheduler_tick_interval_seconds,
            )
            scheduler_handle = (task, stop)
            logger.info(
                "scheduler.inproc.start",
                interval=settings.scheduler_tick_interval_seconds,
            )
        try:
            yield
        finally:
            if scheduler_handle is not None:
                task, stop = scheduler_handle
                # mypy: handle is Any-typed because of the AsyncIterator boundary
                await stop_inproc_scheduler(task, stop)  # type: ignore[arg-type]
            if bot is not None:
                await bot.session.close()
            await dispose_engine()

    app = FastAPI(title="plan-app", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        """Liveness probe used by Render."""
        return {"status": "ok"}

    @app.post("/tg/{secret}", tags=["telegram"])
    async def telegram_webhook(
        secret: str,
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        """Receive an update from Telegram.

        Validates both the path secret and the secret-token header before
        feeding the update to aiogram. Idempotent on ``update_id``.
        """
        if bot is None:
            raise HTTPException(status_code=503, detail="bot not configured")
        expected = settings.telegram_webhook_secret
        if not expected or secret != expected:
            raise HTTPException(status_code=403, detail="bad path secret")
        if x_telegram_bot_api_secret_token != expected:
            raise HTTPException(status_code=403, detail="bad secret token header")

        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})

        # Идемпотентность: если этот update_id уже обработан — выходим тихо.
        async with session_scope() as session:
            if await is_update_processed(session, update.update_id):
                logger.info("webhook.duplicate", update_id=update.update_id)
                return {"ok": True}
            user_tg_id = _extract_tg_user_id(update)
            kind = _classify_update(update)
            # Look up our internal users.id so that TelegramUpdate.user_id
            # actually points at the user (not always NULL). It's nullable
            # because pre-onboarding /start hits this code path before the
            # User row exists; the dispatcher creates it later.
            # See ``docs/REVIEW-2026-05-09.md::I-7``.
            internal_user_id: int | None = None
            if user_tg_id is not None:
                result = await session.exec(select(User.id).where(User.telegram_id == user_tg_id))
                internal_user_id = result.first()
            await record_update(
                session, update_id=update.update_id, user_id=internal_user_id, kind=kind
            )
            logger.info(
                "webhook.received",
                update_id=update.update_id,
                tg_user_id=user_tg_id,
                user_id=internal_user_id,
                kind=kind,
            )

        await dp.feed_update(bot=bot, update=update)
        return {"ok": True}

    return app


app = create_app()
