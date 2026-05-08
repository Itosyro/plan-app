"""Bot reply templates ("courier" voice).

Phase 1 ships a tiny seed set just for onboarding and acknowledgements.
Phase 2 will grow this to ≥ 30 phrases (≥ 5 per style) and add an LLM-based
courier — see ``docs/PROGRESS.md`` (Phase 0 closing decisions) and
``docs/PLAN.md`` § "Style of bot replies".

PII rule: templates never reference user content directly.
"""

from __future__ import annotations

from typing import Final

ONBOARDING_GREETING: Final[str] = (
    "Привет! Я твой ассистент-планировщик.\n"
    "Скидываешь голос или текст — раскладываю на задачи, заметки и напоминания.\n\n"
    "Как тебя зовут? (просто имя — например, «Юсуф»)"
)

ONBOARDING_ASK_TZ: Final[str] = (
    "Приятно, {name}!\n"
    "Какой у тебя часовой пояс? Напиши в формате IANA — например, "
    "«Europe/Moscow», «Asia/Tashkent», «Asia/Almaty».\n\n"
    "Это нужно, чтобы дайджесты и напоминания приходили в твоё время."
)

ONBOARDING_BAD_TZ: Final[str] = (
    "Не узнал такой часовой пояс. Попробуй ещё раз в формате IANA — "
    "«Europe/Moscow», «Asia/Tashkent», «Asia/Almaty». "
    "Список всех — https://nodatime.org/TimeZones."
)

ONBOARDING_DONE: Final[str] = (
    "Готово, {name}. Записал часовой пояс {tz}.\n\n"
    "Дефолты, которые поставил:\n"
    "• утренний дайджест в 08:00, вечерний — в 21:00\n"
    "• напоминания внутри дня — за 1 ч и за 15 мин до события\n"
    "• напоминания на N дней вперёд — за 1 день и за 1 час\n"
    "• критик включён в режиме «по уверенности» (порог 0.7)\n"
    "• курьер — микс шаблонов и LLM\n"
    "• «на этой неделе» = дедлайн воскресенье 23:59\n\n"
    "Всё это потом можно будет поменять в /settings (когда сделаю эту команду).\n\n"
    "AI-разбор подключу следующим шагом (Phase 2). А пока могу принимать "
    "сообщения и складывать их во входящие — попробуй написать что-нибудь."
)

TEXT_ACK_PHASE1: Final[str] = "Принял. AI-разбор подключу в Phase 2 — пока сохраняю во входящие."

HELP: Final[str] = (
    "Я — бот-планировщик. Принимаю текст и голос, раскладываю на задачи и заметки.\n\n"
    "Команды:\n"
    "/start — настройка (имя + часовой пояс)\n"
    "/help — это сообщение\n"
    "/today — задачи на сегодня\n"
    "/tomorrow — задачи на завтра\n"
    "/week — задачи на эту неделю\n"
    "/month — задачи на этот месяц\n"
    "/year — задачи на этот год\n"
    "/someday — задачи без срока\n"
    "/notes — последние заметки\n"
    "/categories — список категорий\n"
    "/settings — настройки бота"
)

NOT_ONBOARDED: Final[str] = "Похоже, мы ещё не знакомы. Напиши /start — настроим всё за минуту."
