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

from app.shared.config import get_settings

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
    "например, Europe/Berlin или America/New_York.\n\n"
    "Искать проще всего здесь: https://nodatime.org/TimeZones."
)

# Custom-tz validation failure (legacy ``ONBOARDING_BAD_TZ`` is kept as
# alias for back-compat with anything that imports it).
ONBOARDING_BAD_TZ: Final[str] = (
    "Не узнаю такой часовой пояс. Попробуй в IANA-формате —\n"
    "например, Europe/Moscow или Asia/Tashkent."
)

# Final confirmation. Short — full settings live behind /settings.
ONBOARDING_DONE: Final[str] = (
    "Рад, что познакомились, {name}. Часовой пояс: {tz}.\n\n"
    "Итоги дня пришлю утром в 08:00 и вечером в 21:00 — это легко поменять в /settings.\n\n"
    "Скидывай мысли голосом или текстом — разложу по полкам.\n\n"
    "Весь список целиком живёт в приложении — кнопка «Открыть план» рядом с полем ввода."
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
    "/reminders — что я собираюсь напомнить (там же можно отменить)\n"
    "/categories — список категорий\n"
    "/settings — настройки\n"
    "/backup — архив с данными для переезда на другой сервер (только владельцу)\n\n"
    "Ещё есть приложение — весь твой список задач и заметок целиком: "
    "можно листать, править и отмечать сделанное. "
    "Открывается кнопкой «Открыть план» рядом с полем ввода.\n\n"
    "«Входящие» — вкладка в этом приложении. Туда я складываю сообщения, "
    "в разборе которых не уверен, — чтобы ты глянул и поправил."
)


# На своём VPS Mini-App обычно не поднят (нужен публичный HTTPS), и тогда
# ``app/main.py`` не ставит кнопку меню — обещать «Открыть план» нельзя.
# Абзац про приложение опознаём по корню «приложени»: в текстах выше все
# такие абзацы — ровно про Mini-App и только про него.
def miniapp_aware(text: str) -> str:
    """Return ``text`` with the Mini-App paragraphs dropped when it isn't configured."""
    if get_settings().miniapp_url is not None:
        return text
    return "\n\n".join(part for part in text.split("\n\n") if "приложени" not in part)


def app_or(with_app: str, without_app: str) -> str:
    """Pick the phrasing that matches this deploy.

    For one-liners where the Mini-App clause can't just be cut out of the
    sentence — «загляни во «Входящие»» is a dead end when there is no app
    to open, so those texts need their own wording, not a truncation.
    """
    return with_app if get_settings().miniapp_url is not None else without_app


NOT_ONBOARDED: Final[str] = "Мы ещё не знакомы. Нажми /start — заодно выберем часовой пояс и имя."

# /backup — перенос на другой сервер. Команда только для владельца:
# в архиве лежит .env с токеном бота и ключами Groq.
BACKUP_NOT_CONFIGURED: Final[str] = (
    "Бэкап отключён: в .env на сервере не задан OWNER_TELEGRAM_ID.\n"
    "Твой Telegram ID: {tg_id}. Добавь строку OWNER_TELEGRAM_ID={tg_id} и перезапусти бота "
    "(docker compose up -d)."
)
BACKUP_FORBIDDEN: Final[str] = "Эта команда только для владельца бота."
BACKUP_PRIVATE_ONLY: Final[str] = (
    "Только в личке: в архиве лежат ключи, в группе их увидели бы все. Напиши мне /backup лично."
)
BACKUP_FAILED: Final[str] = (
    "Не смог собрать архив: {error}\n"
    "База и ключи на месте — забери их с сервера руками: data/plan.db и .env."
)
BACKUP_NOT_SQLITE: Final[str] = (
    "Бэкап работает только на своём сервере (база — файл SQLite). "
    "Здесь база внешняя — выгружай её средствами провайдера."
)
BACKUP_TOO_BIG: Final[str] = (
    "Архив весит {mb} МБ — Telegram пропускает документы до 50 МБ. "
    "Забери файл базы с сервера напрямую: data/plan.db (плюс .env)."
)
BACKUP_CAPTION: Final[str] = (
    "🧳 Внутри — .env (ключи) и база. Перенос на новый сервер:\n"
    "1. На старом: docker compose down\n"
    "2. Скинь этот файл на новый сервер\n"
    "3. Там одна команда:\n"
    "curl -fsSL https://raw.githubusercontent.com/Itosyro/plan-app/main/scripts/install.sh"
    " | bash -s {filename}\n\n"
    "Это снимок на сейчас: всё, что напишешь после этого сообщения, "
    "на новый сервер не переедет.\n"
    "Файл содержит секреты — удали это сообщение, когда закончишь."
)

# Пайплайн упал уже ПОСЛЕ того, как сообщение легло в inbox. Ничего не
# потеряно, но и «разберу позже» обещать нельзя — повторного разбора в
# продукте нет. Поэтому текст говорит ровно две вещи: где лежит и что
# можно сделать. Отправитель обязан сам выставить ``needs_review``,
# иначе записи не будет в «Входящих» Mini-App и текст станет ложью.
PIPELINE_FAILED: Final[str] = (
    "Не получилось разобрать — но сообщение не потерялось: "
    "оно лежит во «Входящих» в приложении.\n"
    "Загляни туда или пришли его мне ещё раз."
)

# Тот же смысл там, где мини-аппа нет: «Входящие» открыть негде, поэтому
# единственное честное действие — прислать сообщение ещё раз.
PIPELINE_FAILED_NO_APP: Final[str] = (
    "Не получилось разобрать — но сообщение не потерялось, оно сохранено целиком.\n"
    "Пришли его мне ещё раз — попробую снова."
)


def pipeline_failed() -> str:
    """Return the pipeline-failure text matching this deploy."""
    return app_or(PIPELINE_FAILED, PIPELINE_FAILED_NO_APP)
