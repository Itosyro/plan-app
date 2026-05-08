"""Database layer: SQLModel models, async session factory.

Phase 1 ships ``User``, ``UserSettings``, ``InboxEntry``, ``TelegramUpdate``.
Phase 2 will add domain models (``Category``, ``Horizon``, ``Task``,
``Note``, ``AiRun``, ...).
"""

from __future__ import annotations

from app.db.base import (
    dispose_engine,
    get_engine,
    get_sessionmaker,
    init_engine,
    session_scope,
)
from app.db.models import InboxEntry, TelegramUpdate, User, UserSettings

__all__ = [
    "InboxEntry",
    "TelegramUpdate",
    "User",
    "UserSettings",
    "dispose_engine",
    "get_engine",
    "get_sessionmaker",
    "init_engine",
    "session_scope",
]
