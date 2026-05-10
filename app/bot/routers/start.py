"""``/start`` + ``/help`` and the onboarding FSM.

Phase 7 redesign: timezone is now picked via an inline keyboard
(CIS-popular zones + "Указать другой") so the user doesn't need to
type IANA strings. After tz is set the bot asks for a name in plain
text. The legacy text-only path (free-typed tz) is preserved as a
fallback when the user picks "Указать другой ✏️".

Exposed as ``create_router()`` so each ``build_dispatcher()`` call gets a
fresh ``Router`` instance. aiogram 3 forbids re-attaching the same router
to multiple dispatchers, which would otherwise break tests.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.courier_templates import (
    HELP,
    ONBOARDING_ALREADY_DONE,
    ONBOARDING_ASK_CUSTOM_TZ,
    ONBOARDING_ASK_NAME,
    ONBOARDING_BAD_NAME,
    ONBOARDING_BAD_TZ,
    ONBOARDING_DONE,
    ONBOARDING_GREETING,
)
from app.bot.onboarding import (
    label_for_iana,
    parse_tz_callback,
    tz_keyboard,
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

# Hard cap on display name length. Mirrors the slice in the original
# Phase 1 implementation; keep DB constraints generous (User.display_name
# is currently ``str | None`` with no explicit length cap, so this is
# purely a UX guard).
_MAX_NAME_LEN = 64


def create_router() -> Router:
    """Build a fresh ``start`` router with all handlers attached."""
    router = Router(name="start")

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        """Begin (or restart) the onboarding wizard.

        Behaviour:
        - Brand-new user → show greeting + tz keyboard.
        - Already onboarded → short re-acknowledgement with the same
          tz keyboard so they can change it without retyping. Their
          display name + existing settings are preserved (see
          ``complete_onboarding`` idempotency guarantee).
        """
        if message.from_user is None:
            return  # ignore channel-style messages without a user

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            already_onboarded = user.onboarded_at is not None
            existing_name = user.display_name or ""
            existing_tz = user.tz or ""

        # FSM enters the tz state immediately — the keyboard is the
        # primary input, but we also want the text-fallback path for
        # the unlikely case the keyboard fails to render.
        await state.set_state(Onboarding.timezone)

        if already_onboarded:
            await message.answer(
                ONBOARDING_ALREADY_DONE.format(
                    name=existing_name or "друг",
                    tz=label_for_iana(existing_tz) or "не указан",
                ),
                reply_markup=tz_keyboard(),
            )
        else:
            await message.answer(
                ONBOARDING_GREETING,
                reply_markup=tz_keyboard(),
            )
        logger.info("onboarding.start", user_id=message.from_user.id)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        """Static help message."""
        await message.answer(HELP)

    @router.callback_query(F.data.startswith("onb:tz:"))
    async def onb_tz_callback(callback: CallbackQuery, state: FSMContext) -> None:
        """Handle a timezone selection from the inline keyboard.

        - ``onb:tz:custom`` → switches to free-text input (legacy path).
        - ``onb:tz:<iana>`` → validates and persists, then asks for name.

        We always answer the callback first to clear the Telegram
        loading spinner, even on errors.
        """
        if callback.from_user is None or callback.data is None:
            await callback.answer()
            return

        payload = parse_tz_callback(callback.data)
        if payload is None:
            await callback.answer("Неверный формат.", show_alert=True)
            return

        # "Указать другой" — drop into the free-text fallback. State
        # already says ``Onboarding.timezone`` from /start, so the next
        # plain-text message lands in ``onb_timezone_text`` below.
        if payload == "custom":
            await callback.answer()
            if isinstance(callback.message, Message):
                await callback.message.answer(ONBOARDING_ASK_CUSTOM_TZ)
            logger.info("onboarding.tz_custom_requested", user_id=callback.from_user.id)
            return

        # Popular-zone path: validate and persist immediately. We don't
        # require a display name yet — user.tz can be set ahead of name
        # so re-onboarding flows (where name already exists) finish in
        # one tap.
        if not is_valid_timezone(payload):
            await callback.answer("Не узнал такой часовой пояс.", show_alert=True)
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(session, telegram_id=callback.from_user.id)
            user.tz = payload
            session.add(user)
            await session.flush()
            existing_name = user.display_name

        await state.update_data(tz=payload)
        label = label_for_iana(payload)
        await callback.answer(f"{label} — записал.")

        if existing_name:
            # Re-onboarding shortcut: name already on file → finish
            # immediately, skip the name prompt.
            async with session_scope() as session:
                user2, _ = await get_or_create_user(session, telegram_id=callback.from_user.id)
                await complete_onboarding(session, user2, display_name=existing_name, tz=payload)
            await state.clear()
            if isinstance(callback.message, Message):
                await callback.message.answer(
                    ONBOARDING_DONE.format(name=existing_name, tz=label),
                )
            logger.info(
                "onboarding.complete_re",
                user_id=callback.from_user.id,
                tz=payload,
            )
            return

        # First-time path: tz set, ask for name.
        await state.set_state(Onboarding.name)
        if isinstance(callback.message, Message):
            await callback.message.answer(ONBOARDING_ASK_NAME)
        logger.info(
            "onboarding.tz_picked",
            user_id=callback.from_user.id,
            tz=payload,
        )

    @router.message(Onboarding.timezone)
    async def onb_timezone_text(message: Message, state: FSMContext) -> None:
        """Free-text fallback after the user pressed "Указать другой ✏️".

        Skipped when the keyboard handler ran (state advances past
        ``Onboarding.timezone`` before the user gets a chance to type).
        """
        if message.from_user is None or not message.text:
            return

        tz_input = message.text.strip()
        if not is_valid_timezone(tz_input):
            await message.answer(ONBOARDING_BAD_TZ)
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(session, telegram_id=message.from_user.id)
            user.tz = tz_input
            session.add(user)
            await session.flush()
            existing_name = user.display_name

        await state.update_data(tz=tz_input)
        label = label_for_iana(tz_input)

        if existing_name:
            async with session_scope() as session:
                user2, _ = await get_or_create_user(session, telegram_id=message.from_user.id)
                await complete_onboarding(session, user2, display_name=existing_name, tz=tz_input)
            await state.clear()
            await message.answer(
                ONBOARDING_DONE.format(name=existing_name, tz=label),
            )
            logger.info(
                "onboarding.complete_re_text",
                user_id=message.from_user.id,
                tz=tz_input,
            )
            return

        await state.set_state(Onboarding.name)
        await message.answer(ONBOARDING_ASK_NAME)
        logger.info(
            "onboarding.tz_text",
            user_id=message.from_user.id,
            tz=tz_input,
        )

    @router.message(Onboarding.name)
    async def onb_name(message: Message, state: FSMContext) -> None:
        """Capture the user's display name and finish onboarding.

        At this point the user's timezone is already on disk (set by the
        keyboard or text fallback above). We only need to write the name
        and call ``complete_onboarding`` to seed ``UserSettings``.
        """
        if message.from_user is None or not message.text:
            return

        name = message.text.strip()
        if not name:
            await message.answer("Не разобрал имя. Попробуй ещё раз.")
            return
        if len(name) > _MAX_NAME_LEN:
            await message.answer(ONBOARDING_BAD_NAME)
            return

        data = await state.get_data()
        tz_iana = data.get("tz", "UTC")  # safety net; shouldn't trigger

        async with session_scope() as session:
            user, _ = await get_or_create_user(session, telegram_id=message.from_user.id)
            await complete_onboarding(session, user, display_name=name, tz=tz_iana)

        await state.clear()
        label = label_for_iana(tz_iana)
        await message.answer(ONBOARDING_DONE.format(name=name, tz=label))
        logger.info(
            "onboarding.complete",
            user_id=message.from_user.id,
            tz=tz_iana,
        )

    return router
