"""``/start`` + ``/help`` and the onboarding FSM (имя → tz → дефолты).

Exposed as ``create_router()`` so each ``build_dispatcher()`` call gets a
fresh ``Router`` instance. aiogram 3 forbids re-attaching the same router
to multiple dispatchers, which would otherwise break tests.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.courier_templates import (
    HELP,
    ONBOARDING_ASK_TZ,
    ONBOARDING_BAD_TZ,
    ONBOARDING_DONE,
    ONBOARDING_GREETING,
)
from app.bot.services import (
    complete_onboarding,
    get_or_create_user,
    is_valid_timezone,
)
from app.bot.states import Onboarding
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)


def create_router() -> Router:
    """Build a fresh ``start`` router with all handlers attached."""
    router = Router(name="start")

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        """Begin (or restart) the onboarding wizard."""
        if message.from_user is None:
            return  # ignore channel-style messages without a user

        async with session_scope() as session:
            await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )

        await state.set_state(Onboarding.name)
        await message.answer(ONBOARDING_GREETING)
        logger.info("onboarding.start", user_id=message.from_user.id)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        """Static help message."""
        await message.answer(HELP)

    @router.message(Onboarding.name)
    async def onb_name(message: Message, state: FSMContext) -> None:
        """Capture the user's display name and ask for a timezone."""
        if message.from_user is None or not message.text:
            return

        name = message.text.strip()[:64]
        if not name:
            await message.answer("Не разобрал имя. Попробуй ещё раз.")
            return

        await state.update_data(display_name=name)
        await state.set_state(Onboarding.timezone)
        await message.answer(ONBOARDING_ASK_TZ.format(name=name))
        logger.info("onboarding.name_captured", user_id=message.from_user.id)

    @router.message(Onboarding.timezone)
    async def onb_timezone(message: Message, state: FSMContext) -> None:
        """Validate the timezone, write defaults, and exit the FSM."""
        if message.from_user is None or not message.text:
            return

        tz_input = message.text.strip()
        if not is_valid_timezone(tz_input):
            await message.answer(ONBOARDING_BAD_TZ)
            return

        data = await state.get_data()
        display_name = data.get("display_name", "")

        async with session_scope() as session:
            user, _ = await get_or_create_user(session, telegram_id=message.from_user.id)
            await complete_onboarding(session, user, display_name=display_name, tz=tz_input)

        await state.clear()
        await message.answer(ONBOARDING_DONE.format(name=display_name, tz=tz_input))
        logger.info("onboarding.complete", user_id=message.from_user.id, tz=tz_input)

    return router
