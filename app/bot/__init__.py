"""Telegram bot layer (aiogram 3 handlers and routers).

Phase 1 ships ``/start`` + onboarding FSM and a catch-all text handler.
Voice (Phase 2), inline-keyboards / ``/today`` (Phase 3) and ``/settings``
(Phase 3) are added later.
"""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.routers import start as start_router
from app.bot.routers import text as text_router


def build_dispatcher(storage: BaseStorage | None = None) -> Dispatcher:
    """Construct an aiogram Dispatcher with fresh Phase 1 routers attached.

    Order matters: catch-all routers (``text``) must be last so that
    command / FSM-state routers get a chance to match first.

    Each call builds new ``Router`` instances via the per-module
    ``create_router()`` factories. aiogram 3 forbids re-attaching a router
    to a second dispatcher, so module-level singletons would break tests.
    """
    dp = Dispatcher(storage=storage or MemoryStorage())
    dp.include_router(start_router.create_router())
    dp.include_router(text_router.create_router())  # catch-all — keep last
    return dp


__all__ = ["build_dispatcher"]
