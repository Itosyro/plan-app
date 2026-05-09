"""FastAPI entry point + Telegram webhook integration.

Phase 1 wiring:
- spin up an aiogram ``Bot`` + ``Dispatcher`` with onboarding + text routers,
- on startup, register the Telegram webhook (`setWebhook`) with
  ``drop_pending_updates=True`` and a secret token,
- expose ``POST /tg/<secret>`` for incoming updates with double validation
  (path secret + ``X-Telegram-Bot-Api-Secret-Token`` header),
- expose ``GET /healthz`` for Render health checks.

Phase 5 wiring:
- mount REST routers under ``/api/*`` (``me``, ``tasks``, ``notes``,
  ``categories``, ``horizons``, ``inbox``);
- serve the built Mini-App static bundle from ``webapp/dist`` at ``/app``;
- on startup, register a ``MenuButtonWebApp`` so the bot opens the
  Mini-App from its menu icon.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from app.api.routers import categories as api_categories
from app.api.routers import horizons as api_horizons
from app.api.routers import inbox as api_inbox
from app.api.routers import me as api_me
from app.api.routers import notes as api_notes
from app.api.routers import tasks as api_tasks
from app.bot import build_dispatcher
from app.bot.services import claim_update
from app.db.base import dispose_engine, init_engine, session_scope
from app.db.models import User
from app.shared.config import Settings, get_settings
from app.shared.logging import configure_logging, get_logger
from app.workers.runner import start_inproc_scheduler, stop_inproc_scheduler

# ``webapp/dist`` is produced by the Mini-App build (`npm run build`).
# In CI / local dev without a frontend build, the directory may not
# exist; we mount it conditionally below so tests don't 500.
WEBAPP_DIST = Path(__file__).resolve().parent.parent / "webapp" / "dist"


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
        import asyncio

        scheduler_handle: tuple[asyncio.Task[None], asyncio.Event] | None = None
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
            if settings.miniapp_url:
                # ``setChatMenuButton`` is per-user and global; calling
                # it without ``chat_id`` updates the default menu so
                # every existing user sees the Mini-App entry point.
                # Telegram is permissive here — repeated calls are
                # idempotent and the bot doesn't need to be re-added.
                try:
                    await bot.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(
                            text="Открыть план",
                            web_app=WebAppInfo(url=settings.miniapp_url),
                        ),
                    )
                    logger.info("bot.menu.miniapp", url=settings.miniapp_url)
                except Exception:
                    # A bad URL or temporary 4xx must not block startup —
                    # the bot still works without a menu button. Fix
                    # MINIAPP_URL and redeploy to retry.
                    logger.exception("bot.menu.miniapp_failed")
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
                await stop_inproc_scheduler(task, stop)
            if bot is not None:
                await bot.session.close()
            await dispose_engine()

    app = FastAPI(title="plan-app", version="0.1.0", lifespan=lifespan)

    # The auth dependency reads ``Settings`` via ``Depends(get_settings)``;
    # because ``get_settings`` is ``lru_cache``-d at module level it would
    # otherwise ignore the per-app override that ``create_app`` accepts
    # (tests rely on this to inject a fake bot token). Wire an override
    # so the in-process ``settings`` always wins.
    app.dependency_overrides[get_settings] = lambda: settings

    # REST routers for the Mini-App. All routers depend on
    # ``app.api.auth.current_user`` which validates Telegram initData;
    # there is no unauthenticated path under ``/api`` other than the
    # FastAPI-generated ``/openapi.json`` (informational only).
    app.include_router(api_me.router, prefix="/api/me", tags=["me"])
    app.include_router(api_tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(api_notes.router, prefix="/api/notes", tags=["notes"])
    app.include_router(api_categories.router, prefix="/api/categories", tags=["categories"])
    app.include_router(api_horizons.router, prefix="/api/horizons", tags=["horizons"])
    app.include_router(api_inbox.router, prefix="/api/inbox", tags=["inbox"])

    # Mini-App static bundle. ``html=True`` enables SPA-style fallback
    # (any ``/app/*`` path that isn't a real file resolves to
    # ``index.html`` so client-side routing works on hard refresh).
    if WEBAPP_DIST.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(WEBAPP_DIST), html=True),
            name="webapp",
        )

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

        # Идемпотентность через атомарный INSERT: ``claim_update`` ловит
        # ``IntegrityError`` на конфликте PK, поэтому два одновременных
        # доставленных webhook'а с одним ``update_id`` не оба
        # отдиспатчатся (раньше второй падал в 500 → Telegram retry'ил
        # вечно). См. ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-5``.
        async with session_scope() as session:
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
            claimed = await claim_update(
                session,
                update_id=update.update_id,
                user_id=internal_user_id,
                kind=kind,
            )
            if not claimed:
                logger.info("webhook.duplicate", update_id=update.update_id)
                return {"ok": True}
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
