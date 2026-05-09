"""UserSettings queries, mutations, and allow-lists."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import User, UserSettings
from app.shared.logging import get_logger

from .users import is_valid_timezone

logger = get_logger(__name__)


async def get_user_settings(
    session: AsyncSession,
    user_id: int,
) -> UserSettings | None:
    """Return the user's settings row, or None if not onboarded yet."""
    result = await session.exec(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    return result.first()


REMINDER_PRESETS: dict[str, dict[str, list[int]]] = {
    "minimal": {"same_day": [15], "multi_day": [60]},
    "default": {"same_day": [60, 15], "multi_day": [1440, 60]},
    "extra": {"same_day": [180, 60, 15], "multi_day": [1440, 240, 60]},
}

# Allowed values for each user-editable setting field. Mirrors the options
# rendered by ``app/bot/routers/settings.py::SETTING_OPTIONS`` and is the
# authoritative validation gate at the service layer — a malformed callback
# (replayed, edited, or maliciously crafted) is rejected before it touches
# the database.
ALLOWED_SETTING_VALUES: dict[str, frozenset[str]] = {
    "critic_mode": frozenset({"always", "confidence", "never"}),
    "morning_digest_at": frozenset({"07:00", "08:00", "09:00", "10:00"}),
    "evening_digest_at": frozenset({"20:00", "21:00", "22:00", "23:00"}),
    # Vocabulary must match ``app/ai/courier.py::generate_courier_reply``'s
    # ``mode`` parameter — pre-2026-05-09 the UI shipped
    # ``formal``/``casual``/``mix`` which silently fell through both
    # branches in courier.py and degenerated to ``template_only`` for
    # the first two. See ``docs/REVIEW-2026-05-09.md::C-1``.
    "response_style_source": frozenset({"template_only", "llm_only", "mix"}),
    # Vocabulary must match the keys of ``app/ai/courier.py::TEMPLATES``.
    "courier_template_style": frozenset(
        {"neutral", "formal_master", "friendly", "playful", "terse", "respectful"},
    ),
    "week_due_semantic": frozenset({"deadline_sunday", "deadline_saturday", "spread_evenly"}),
}


def reminder_preset_from_offsets(offsets: dict[str, list[int]] | dict[str, object]) -> str:
    """Return the preset name matching ``offsets`` (custom if no match)."""
    raw_same = offsets.get("same_day") or []
    raw_multi = offsets.get("multi_day") or []
    same = list(raw_same) if isinstance(raw_same, list) else []
    multi = list(raw_multi) if isinstance(raw_multi, list) else []
    for name, preset in REMINDER_PRESETS.items():
        if preset["same_day"] == same and preset["multi_day"] == multi:
            return name
    return "custom"


async def update_user_settings(
    session: AsyncSession,
    user_id: int,
    field: str,
    value: str,
) -> UserSettings | None:
    """Update a single setting and return the latest UserSettings row.

    Most fields live on ``UserSettings``. Two virtual fields are handled
    specially:

    * ``tz`` — written to ``User.tz`` (after ``is_valid_timezone`` check).
    * ``reminder_preset`` — expanded via ``REMINDER_PRESETS`` and written
      to ``UserSettings.default_reminder_offsets``.
    """
    settings = await get_user_settings(session, user_id)
    if settings is None:
        return None

    if field == "tz":
        if not is_valid_timezone(value):
            return None
        user_result = await session.exec(select(User).where(User.id == user_id))
        user = user_result.first()
        if user is None:
            return None
        user.tz = value
        session.add(user)
        await session.flush()
        logger.info("settings.updated", user_id=user_id, field=field, value=value)
        return settings

    if field == "reminder_preset":
        preset = REMINDER_PRESETS.get(value)
        if preset is None:
            return None
        settings.default_reminder_offsets = dict(preset)
        session.add(settings)
        await session.flush()
        logger.info("settings.updated", user_id=user_id, field=field, value=value)
        return settings

    if field not in ALLOWED_SETTING_VALUES or value not in ALLOWED_SETTING_VALUES[field]:
        return None

    if field == "critic_mode":
        settings.critic_mode = value
    elif field == "morning_digest_at":
        settings.morning_digest_at = value
    elif field == "evening_digest_at":
        settings.evening_digest_at = value
    elif field == "response_style_source":
        settings.response_style_source = value
    elif field == "courier_template_style":
        settings.courier_template_style = value
    elif field == "week_due_semantic":
        settings.week_due_semantic = value
    else:  # pragma: no cover - exhaustive above
        return None
    session.add(settings)
    await session.flush()
    logger.info("settings.updated", user_id=user_id, field=field, value=value)
    return settings
