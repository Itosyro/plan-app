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

# Greeting shown alongside the timezone inline-keyboard.
ONBOARDING_GREETING: Final[str] = (
    "Привет 👋\n"
    "Я разбираю твои голосовые и текстовые мысли в задачи, "
    "заметки и напоминания.\n\n"
    "Сначала — часовой пояс. Выбери свой:"
)

# After timezone is set via the keyboard, ask for a name. We don't
# include the tz_label in this string (it lives in the keyboard's
# acknowledgement edit, see ``onb_tz_callback``).
ONBOARDING_ASK_NAME: Final[str] = "Готово.\n\nКак к тебе обращаться? Напиши имя или ник."

# Fallback when user typed name longer than allowed.
ONBOARDING_BAD_NAME: Final[str] = "Слишком длинное. До 64 символов, пожалуйста."

# After tz selection, if user pressed "Указать другой ✏️".
ONBOARDING_ASK_CUSTOM_TZ: Final[str] = (
    "Окей. Напиши свой часовой пояс в IANA-формате —\n"
    "например, ``Europe/Berlin`` или ``America/New_York``.\n\n"
    "Список всех — https://nodatime.org/TimeZones."
)

# Custom-tz validation failure (legacy ``ONBOARDING_BAD_TZ`` is kept as
# alias for back-compat with anything that imports it).
ONBOARDING_BAD_TZ: Final[str] = (
    "Не узнал такой часовой пояс. Попробуй ещё раз в IANA-формате —\n"
    "например, ``Europe/Moscow`` или ``Asia/Tashkent``."
)

# Final confirmation. Short — full settings live behind /settings.
ONBOARDING_DONE: Final[str] = (
    "Готово, {name}. Часовой пояс — {tz}.\n\n"
    "Дайджесты: утром в 08:00, вечером в 21:00.\n"
    "Поменять — /settings.\n\n"
    "Скидывай мысли — голосом или текстом."
)

# Re-onboarding (already onboarded, runs /start again).
ONBOARDING_ALREADY_DONE: Final[str] = (
    "Уже знакомы, {name}.\n"
    "Часовой пояс: {tz}.\n\n"
    "Поменять часовой пояс — нажми кнопку. "
    "Или просто пиши задачи как обычно."
)

TEXT_ACK_PHASE1: Final[str] = "Принял. AI-разбор подключу в Phase 2 — пока сохраняю во входящие."

HELP: Final[str] = (
    "Я — бот-планировщик. Принимаю текст и голос, раскладываю на задачи и заметки.\n\n"
    "📋 Просмотр:\n"
    "/today — задачи на сегодня\n"
    "/tomorrow — задачи на завтра\n"
    "/week — задачи на эту неделю\n"
    "/month — задачи на этот месяц\n"
    "/year — задачи на этот год\n"
    "/someday — задачи без срока\n"
    "/notes — последние заметки\n"
    "/categories — список категорий\n\n"
    "⚡ Быстрый ввод:\n"
    "/add <текст> — добавить задачу/мысль через AI-разбор\n"
    "/done <название> — отметить задачу выполненной\n"
    "/del <название> — удалить задачу\n"
    "/move <название> <горизонт> — перенести задачу\n"
    "/postpone <название> <горизонт> — синоним /move\n\n"
    "Горизонты: today/сегодня, tomorrow/завтра, week/неделя,\n"
    "month/месяц, year/год, someday/потом\n\n"
    "⚙️ Прочее:\n"
    "/start — настройка (часовой пояс + имя)\n"
    "/help — это сообщение\n"
    "/settings — настройки бота"
)

NOT_ONBOARDED: Final[str] = "Похоже, мы ещё не знакомы. Напиши /start — настроим всё за минуту."
