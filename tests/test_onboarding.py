"""Tests for the Phase 7 onboarding redesign.

Covers ``app/bot/onboarding.py`` (timezone keyboard helpers) and the
new ``/start`` flow in ``app/bot/routers/start.py`` (callback path
where user picks a tz button instead of typing IANA).
"""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.onboarding import (
    CUSTOM_TZ_CALLBACK,
    POPULAR_TIMEZONES,
    label_for_iana,
    parse_tz_callback,
    tz_keyboard,
)
from app.bot.services import (
    complete_onboarding,
    get_or_create_user,
    is_valid_timezone,
)
from app.db.models import User

# ── tz_keyboard / label / parse helpers ──────────────────────────────


def test_popular_timezones_all_iana_valid() -> None:
    """Each popular timezone must round-trip through ``zoneinfo`` —
    otherwise the button would error on tap. Cheap check, big payoff
    if we ever add a typo."""
    for label, iana in POPULAR_TIMEZONES:
        assert is_valid_timezone(iana), f"{label} → {iana} is not a known IANA tz"


def test_popular_timezones_no_duplicates() -> None:
    """Each IANA value should appear only once. Labels can theoretically
    repeat (different city, same offset), but the IANA list must be
    unique so the keyboard doesn't show two buttons that do the same
    thing."""
    ianas = [iana for _, iana in POPULAR_TIMEZONES]
    assert len(ianas) == len(set(ianas))


def test_tz_keyboard_layout() -> None:
    """Keyboard must be 3 columns × N rows + a final wide row for
    "Указать другой ✏️" so the user can fall back to free text."""
    kb = tz_keyboard()
    assert kb.inline_keyboard, "keyboard must not be empty"

    # Last row is always the "custom" fallback — single button.
    last_row = kb.inline_keyboard[-1]
    assert len(last_row) == 1
    assert last_row[0].callback_data == CUSTOM_TZ_CALLBACK
    assert "✏" in last_row[0].text  # emoji preserved

    # All other rows are tz buttons, ≤ 3 wide.
    for row in kb.inline_keyboard[:-1]:
        assert 1 <= len(row) <= 3
        for btn in row:
            assert btn.callback_data is not None
            assert btn.callback_data.startswith("onb:tz:")
            assert btn.callback_data != CUSTOM_TZ_CALLBACK


def test_tz_keyboard_callback_data_under_64_bytes() -> None:
    """Telegram caps callback_data at 64 bytes UTF-8. The longest IANA
    string in our list is well within that, but pin the invariant so
    a future addition (e.g. ``America/Argentina/Buenos_Aires``) doesn't
    silently break tap handling."""
    kb = tz_keyboard()
    for row in kb.inline_keyboard:
        for btn in row:
            data = btn.callback_data or ""
            assert len(data.encode("utf-8")) <= 64, f"too long: {data!r}"


def test_label_for_iana_known() -> None:
    assert label_for_iana("Europe/Moscow") == "Москва"
    assert label_for_iana("Asia/Tashkent") == "Ташкент"


def test_label_for_iana_unknown_returns_iana() -> None:
    """Unknown IANA strings (custom-tz path) round-trip through unchanged."""
    assert label_for_iana("America/Argentina/Buenos_Aires") == "America/Argentina/Buenos_Aires"
    assert label_for_iana("UTC") == "UTC"


def test_parse_tz_callback_known_iana() -> None:
    assert parse_tz_callback("onb:tz:Europe/Moscow") == "Europe/Moscow"
    assert parse_tz_callback("onb:tz:Asia/Almaty") == "Asia/Almaty"


def test_parse_tz_callback_custom() -> None:
    assert parse_tz_callback("onb:tz:custom") == "custom"


def test_parse_tz_callback_malformed() -> None:
    """Defensive: anything that doesn't match the expected prefix returns
    ``None`` so the handler can show "неверный формат" instead of
    crashing on a slice. Mirrors the parse_task_callback pattern from
    ``callbacks.py`` (R-NEW-I-1 regression)."""
    assert parse_tz_callback("") is None
    assert parse_tz_callback("not:a:onb") is None
    assert parse_tz_callback("onb:tz:") is None
    assert parse_tz_callback("task:done:42") is None


# ── re-onboarding idempotency through the new flow ────────────────────


@pytest.mark.asyncio
async def test_re_onboarding_preserves_name_and_settings(
    session: AsyncSession,
) -> None:
    """When a user re-runs ``/start`` and just retaps a tz button, their
    existing display_name + UserSettings tweaks survive.

    The new flow's "skip name prompt" shortcut for re-onboarded users
    funnels through the same ``complete_onboarding`` idempotency
    guarantee that lives in ``app/bot/services/users.py``. This test
    pins that the shortcut works end-to-end without resetting either.
    """
    user, _ = await get_or_create_user(session, telegram_id=999)
    await session.commit()
    settings = await complete_onboarding(session, user, display_name="Юсуф", tz="Europe/Moscow")
    settings.critic_mode = "always"
    settings.morning_digest_at = "09:30"
    session.add(settings)
    await session.commit()

    # Simulate the re-onboarding shortcut: only update tz, reuse name.
    user2 = (await session.exec(select(User).where(User.telegram_id == 999))).first()
    assert user2 is not None
    assert user2.display_name == "Юсуф"  # name still on file
    settings2 = await complete_onboarding(
        session,
        user2,
        display_name=user2.display_name or "",
        tz="Asia/Tashkent",
    )
    await session.commit()

    fetched = (await session.exec(select(User).where(User.telegram_id == 999))).first()
    assert fetched is not None
    assert fetched.display_name == "Юсуф"  # unchanged
    assert fetched.tz == "Asia/Tashkent"  # tz updated
    assert settings2.critic_mode == "always"  # tweak preserved
    assert settings2.morning_digest_at == "09:30"  # tweak preserved
