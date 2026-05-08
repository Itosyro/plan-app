"""Aiogram FSM states.

Phase 1 only defines the onboarding wizard. Storage is ``MemoryStorage``
(see ``app/main.py``) — fine for single-instance Phase 1; Phase 4 will
swap to a Postgres-backed storage so state survives Render redeploys.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """States for the /start onboarding flow (имя → tz → готово)."""

    name = State()
    timezone = State()
