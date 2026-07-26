"""Аудит 2026-07-26: edit-ветки парсят время в таймзоне пользователя.

Раньше ``_execute_set_due`` / ``_execute_reorder_time`` /
``_execute_set_reminder`` звали ``dateparser.parse`` без TIMEZONE — на
UTC-сервере «завтра в 10» для москвича сохранялось как 10:00 UTC, и
напоминание приходило в 13:00 МСК. Теперь все три ветки идут через
``parse_user_datetime`` (см. ``app/ai/time_resolver.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    _execute_set_due,
    _execute_set_reminder,
)
from app.bot.services import get_or_create_user, persist_classification
from app.db.models import Reminder, Task, UserSettings


def _cr(title: str = "Позвонить маме") -> ClassifierResult:
    return ClassifierResult(
        category_name="Семья",
        horizon="today",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title=title,
    )


async def _seed_msk_user_with_task(session: AsyncSession) -> tuple[int, int]:
    """User in Europe/Moscow + one task; returns (user_id, task_id)."""
    user, _ = await get_or_create_user(session, telegram_id=777001)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    row = await persist_classification(
        session, user_id=user.id, cr=_cr(), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task) and row.id is not None
    await session.commit()
    return user.id, row.id


@pytest.mark.asyncio
async def test_set_due_stores_user_local_time_as_utc(session: AsyncSession) -> None:
    user_id, task_id = await _seed_msk_user_with_task(session)

    intent = EditIntent(
        intent="set_due", task_query="маме", new_due_raw="завтра в 10", confidence=0.9
    )
    reply, _snap = await _execute_set_due(task_id, user_id, intent)
    assert "10:00" in reply  # подтверждение — в локальном времени юзера

    task = (await session.exec(select(Task).where(Task.id == task_id))).one()
    assert task.due_at is not None
    # 10:00 МСК = 07:00 UTC. Старый код записал бы 10:00 UTC.
    assert task.due_at.hour == 7


@pytest.mark.asyncio
async def test_set_reminder_fires_at_user_local_time(session: AsyncSession) -> None:
    user_id, task_id = await _seed_msk_user_with_task(session)

    intent = EditIntent(
        intent="set_reminder", task_query="маме", new_due_raw="завтра в 9", confidence=0.9
    )
    reply, _snap = await _execute_set_reminder(task_id, user_id, intent)
    # Подтверждение показывает время в зоне юзера — как он и сказал.
    assert "9:00" in reply or "09:00" in reply

    reminder = (
        await session.exec(
            select(Reminder).where(Reminder.task_id == task_id, Reminder.status == "pending")
        )
    ).one()
    # «Завтра» отсчитывается от ЛОКАЛЬНОЙ даты пользователя, поэтому и
    # ожидание строим в его зоне, а потом переводим в naive-UTC. Считать
    # «завтра» по UTC нельзя: между 21:00 и 24:00 UTC в Москве уже
    # следующие сутки, и тест падал бы каждый вечер — ровно тот сдвиг
    # суток, против которого написан сам фикс.
    msk = ZoneInfo("Europe/Moscow")
    tomorrow_local = (datetime.now(msk) + timedelta(days=1)).date()
    expected = (
        datetime.combine(tomorrow_local, time(9, 0), tzinfo=msk)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    # 09:00 МСК = 06:00 UTC; старый код поставил бы 09:00 UTC (12:00 МСК).
    assert reminder.fire_at == expected


@pytest.mark.asyncio
async def test_set_reminder_uses_user_evening_anchor(session: AsyncSession) -> None:
    """«напомни вечером» must respect ``UserSettings.evening_anchor``.

    M-6 сделал якоря утра/вечера настраиваемыми, но только на surface
    первичного разбора (``resolve_time``). Голосовая правка шла через
    ``parse_user_datetime``, который якоря игнорировал, — юзер с
    evening_anchor="21:00" получал дефолтные 19:00.
    """
    user_id, task_id = await _seed_msk_user_with_task(session)
    session.add(UserSettings(user_id=user_id, evening_anchor="21:00"))
    await session.commit()

    intent = EditIntent(
        intent="set_reminder", task_query="маме", new_due_raw="вечером", confidence=0.9
    )
    reply, _snap = await _execute_set_reminder(task_id, user_id, intent)
    assert "21:00" in reply

    reminder = (
        await session.exec(
            select(Reminder).where(Reminder.task_id == task_id, Reminder.status == "pending")
        )
    ).one()
    # 21:00 МСК = 18:00 UTC (naive-UTC в БД).
    assert reminder.fire_at.hour == 18


@pytest.mark.asyncio
async def test_set_due_falls_back_to_default_anchor_without_settings(
    session: AsyncSession,
) -> None:
    """Без строки ``UserSettings`` якоря остаются дефолтными (19:00)."""
    user_id, task_id = await _seed_msk_user_with_task(session)

    intent = EditIntent(intent="set_due", task_query="маме", new_due_raw="вечером", confidence=0.9)
    reply, _snap = await _execute_set_due(task_id, user_id, intent)
    assert "19:00" in reply
