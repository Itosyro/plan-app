"""Tests for the edit-intent → create fallback (false-positive recovery).

Real symptom (2026-06-04): user said something like «отправить курсовые
учительнице»; the intent detector classified it as an edit-intent;
``find_tasks_by_query`` returned nothing; the bot dead-ended with
«Не нашёл задачу X…» and the user's actual task — to CREATE a new item —
was silently dropped.

After the fix, ``execute_edit`` raises :class:`EditTargetNotFound` when
its target task cannot be resolved, and the pipeline catches it and
falls through to the splitter+classifier create-path with the original
text.
"""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import EditIntent
from app.bot.edit_executor import EditTargetNotFound, execute_edit
from app.bot.services import get_or_create_user


@pytest.mark.asyncio
async def test_execute_edit_raises_when_target_missing(session: AsyncSession) -> None:
    """The executor must raise EditTargetNotFound (not return a dead-end
    string) so the pipeline can fall through to create."""
    user, _ = await get_or_create_user(session, telegram_id=5101)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(
        intent="rename",
        task_query="курсовые отправки учительницы",
        new_title="курсовые",
        confidence=0.7,
    )

    with pytest.raises(EditTargetNotFound) as exc_info:
        await execute_edit(intent, user.id)

    assert exc_info.value.query == "курсовые отправки учительницы"
    assert exc_info.value.original_intent == "rename"


@pytest.mark.asyncio
async def test_execute_edit_raises_for_empty_query_with_no_last_task(
    session: AsyncSession,
) -> None:
    """Empty task_query AND no last-task anaphora → also a false positive.

    The detector is grasping at straws; the pipeline should retry as
    create with the user's original full text.
    """
    user, _ = await get_or_create_user(session, telegram_id=5102)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="set_due", task_query="", new_due_raw="в 15:00", confidence=0.6)

    with pytest.raises(EditTargetNotFound):
        await execute_edit(intent, user.id)


@pytest.mark.asyncio
async def test_execute_edit_does_not_raise_when_target_found(
    session: AsyncSession,
) -> None:
    """Sanity: the happy path is unchanged — we still return a normal
    reply tuple when the task is found and renamed."""
    from app.ai.schemas import ClassifierResult
    from app.bot.services import persist_classification

    user, _ = await get_or_create_user(session, telegram_id=5103)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Учёба",
        horizon="today",
        priority="medium",
        is_task=True,
        title="отчёт",
        confidence=0.9,
    )
    await persist_classification(session, user_id=user.id, cr=cr, due_at=None, inbox_id=None)
    await session.commit()

    intent = EditIntent(
        intent="rename", task_query="отчёт", new_title="квартальный отчёт", confidence=0.9
    )
    reply, _kb = await execute_edit(intent, user.id)
    assert "квартальный отчёт" in reply
