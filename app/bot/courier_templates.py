"""Bot reply templates ("courier" voice).

Phase 1 ships a tiny seed set just for onboarding and acknowledgements.
Phase 2 will grow this to ≥ 30 phrases (≥ 5 per style) and add an LLM-based
courier — see ``docs/PROGRESS.md`` (Phase 0 closing decisions) and
``docs/PLAN.md`` § "Style of bot replies".

PII rule: templates never reference user content directly.

Onboarding rewrite (post Phase 6.x): tone is short, friendly, no
awkward placeholders. The first prompt is a timezone inline keyboard
(see ``app.bot.onboarding``), so the greeting itself is just one line
above the buttons. Name is asked **after** tz so the user is already
"in" before we ask for personal data.
"""

from __future__ import annotations

from typing import Final

# Greeting shown alongside the timezone inline-keyboard. PR-E: keep one
# emoji, drop the marketing-y bullet — it reads as a real person, not a
# kiosk.
ONBOARDING_GREETING: Final[str] = (
    "Привет 👋\n"
    "Я помогаю разбирать поток мыслей в задачи, заметки и напоминания — "
    "принимаю голосом или текстом.\n\n"
    "Для начала — выбери часовой пояс:"
)

# After timezone is set via the keyboard, ask for a name. We don't
# include the tz_label in this string (it lives in the keyboard's
# acknowledgement edit, see ``onb_tz_callback``).
ONBOARDING_ASK_NAME: Final[str] = (
    "Часовой пояс запомнил.\n\nКак к тебе обращаться? Напиши имя или ник."
)

# Fallback when user typed name longer than allowed.
ONBOARDING_BAD_NAME: Final[str] = "Чуть короче, пожалуйста — до 64 символов."

# After tz selection, if user pressed "Указать другой ✏️".
ONBOARDING_ASK_CUSTOM_TZ: Final[str] = (
    "Окей. Напиши свой часовой пояс в IANA-формате —\n"
    "например, ``Europe/Berlin`` или ``America/New_York``.\n\n"
    "Искать проще всего здесь: https://nodatime.org/TimeZones."
)

# Custom-tz validation failure (legacy ``ONBOARDING_BAD_TZ`` is kept as
# alias for back-compat with anything that imports it).
ONBOARDING_BAD_TZ: Final[str] = (
    "Не узнаю такой часовой пояс. Попробуй в IANA-формате —\n"
    "например, ``Europe/Moscow`` или ``Asia/Tashkent``."
)

# Final confirmation. Short — full settings live behind /settings.
ONBOARDING_DONE: Final[str] = (
    "Рад, что познакомились, {name}. Часовой пояс: {tz}.\n\n"
    "Итоги дня пришлю утром в 08:00 и вечером в 21:00 — это легко поменять в /settings.\n\n"
    "Скидывай мысли голосом или текстом — разложу по полкам."
)

# Re-onboarding (already onboarded, runs /start again).
ONBOARDING_ALREADY_DONE: Final[str] = (
    "Снова здорово, {name}.\n"
    "Сейчас у тебя часовой пояс {tz}.\n\n"
    "Для смены пояса нажми кнопку ниже, или просто пиши задачи как обычно."
)

TEXT_ACK_PHASE1: Final[str] = "Окей, сохранил во входящие — бот ещё учится разбирать фразы."

HELP: Final[str] = (
    "Я помогаю планировать — слушаю голосовые и текст, раскладываю на задачи и заметки.\n\n"
    "Что умею:\n"
    "/start — вернуться к настройке (часовой пояс + имя)\n"
    "/help — это сообщение\n"
    "/today — что на сегодня\n"
    "/tomorrow — что на завтра\n"
    "/week — эта неделя\n"
    "/month — этот месяц\n"
    "/year — этот год\n"
    "/someday — без срока\n"
    "/notes — последние заметки\n"
    "/categories — список категорий\n"
    "/settings — настройки"
)

NOT_ONBOARDED: Final[str] = "Мы ещё не знакомы. Нажми /start — заодно выберем часовой пояс и имя."
