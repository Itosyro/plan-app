"""Tests for the self-hosted deploy path (own VPS, no managed services).

Три обещания, которые делает ``docs/SELF-HOSTING.md``, и каждое ломается
незаметно, если его не закрепить тестом:

1. ``BOT_MODE=polling`` действительно поднимает long-polling и НЕ трогает
   webhook-регистрацию (иначе бот молча не получает сообщений);
2. перед стартом polling'а webhook снимается — пока он зарегистрирован,
   Telegram отвечает на ``getUpdates`` ошибкой 409;
3. ``AUTO_MIGRATE=true`` доводит схему до ``head`` на старте, иначе
   «docker compose up» упирается в пустую базу.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.main import create_app
from app.shared.config import Settings

_FAKE_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class _SpyBot:
    """Records the lifecycle calls the lifespan makes on the Bot."""

    def __init__(self) -> None:
        self.deleted_webhook = False
        self.set_webhook_calls = 0
        self.menu_calls = 0

    async def delete_webhook(self, **kwargs: Any) -> None:
        self.deleted_webhook = True

    async def set_webhook(self, **kwargs: Any) -> None:
        self.set_webhook_calls += 1

    async def set_chat_menu_button(self, **kwargs: Any) -> None:
        self.menu_calls += 1

    @property
    def session(self) -> Any:
        class _S:
            async def close(self) -> None:
                return None

        return _S()


class _SpyDispatcher:
    def __init__(self) -> None:
        self.polling_started = False
        self.stopped = False

    async def start_polling(self, bot: Any, **kwargs: Any) -> None:
        self.polling_started = True
        # Реальный ``start_polling`` не возвращается, пока его не
        # остановят; имитируем это, иначе тест не отличит запуск от
        # мгновенного выхода.
        import asyncio

        await asyncio.Event().wait()

    async def stop_polling(self) -> None:
        self.stopped = True

    async def feed_update(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def polling_app(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, _SpyBot, _SpyDispatcher]:
    """Build an app in polling mode with the Bot/Dispatcher spied on."""
    spy_bot = _SpyBot()
    spy_dp = _SpyDispatcher()
    monkeypatch.setattr("app.main.Bot", lambda **kwargs: spy_bot)
    monkeypatch.setattr("app.main.build_dispatcher", lambda: spy_dp)
    settings = Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_FAKE_BOT_TOKEN,
        bot_mode="polling",
        webhook_base_url=None,
        database_url=None,
    )
    return create_app(settings=settings), spy_bot, spy_dp


def test_polling_mode_starts_long_polling(
    polling_app: tuple[Any, _SpyBot, _SpyDispatcher],
) -> None:
    """BOT_MODE=polling запускает polling и не регистрирует webhook."""
    app, spy_bot, spy_dp = polling_app
    with TestClient(app):
        pass
    assert spy_dp.polling_started is True
    assert spy_bot.set_webhook_calls == 0


def test_polling_mode_clears_any_registered_webhook(
    polling_app: tuple[Any, _SpyBot, _SpyDispatcher],
) -> None:
    """Webhook снимается до старта polling'а — иначе getUpdates даёт 409."""
    app, spy_bot, _spy_dp = polling_app
    with TestClient(app):
        pass
    assert spy_bot.deleted_webhook is True


def test_polling_is_stopped_on_shutdown(
    polling_app: tuple[Any, _SpyBot, _SpyDispatcher],
) -> None:
    """Остановка приложения гасит polling — иначе контейнер не завершится."""
    app, _spy_bot, spy_dp = polling_app
    with TestClient(app):
        pass
    assert spy_dp.stopped is True


def test_webhook_mode_is_still_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Управляемый деплой не должен молча переехать на polling."""
    spy_bot = _SpyBot()
    spy_dp = _SpyDispatcher()
    monkeypatch.setattr("app.main.Bot", lambda **kwargs: spy_bot)
    monkeypatch.setattr("app.main.build_dispatcher", lambda: spy_dp)
    settings = Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_FAKE_BOT_TOKEN,
        telegram_webhook_secret="s3cret",
        webhook_base_url="https://example.test",
        database_url=None,
    )
    assert settings.bot_mode == "webhook"
    with TestClient(create_app(settings=settings)):
        pass
    assert spy_dp.polling_started is False
    assert spy_bot.set_webhook_calls == 1


def test_auto_migrate_builds_the_schema_on_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUTO_MIGRATE=true поднимает схему на пустом файле SQLite.

    Это обещание «docker compose up — и работает»: без него первый
    запуск упирается в базу без таблиц.
    """
    spy_bot = _SpyBot()
    spy_dp = _SpyDispatcher()
    monkeypatch.setattr("app.main.Bot", lambda **kwargs: spy_bot)
    monkeypatch.setattr("app.main.build_dispatcher", lambda: spy_dp)

    db_file = tmp_path / "plan.db"
    settings = Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_FAKE_BOT_TOKEN,
        bot_mode="polling",
        auto_migrate=True,
        webhook_base_url=None,
        database_url=f"sqlite+aiosqlite:///{db_file}",
    )
    with TestClient(create_app(settings=settings)):
        pass

    assert db_file.exists()
    sync_engine = create_engine(f"sqlite:///{db_file}")
    try:
        tables = set(inspect(sync_engine).get_table_names())
    finally:
        sync_engine.dispose()
    # Ключевые таблицы + отметка Alembic, что миграции реально прогнаны.
    assert {"users", "tasks", "reminders", "alembic_version"} <= tables


def test_dockerfile_from_lines_are_parseable() -> None:
    """``FROM`` принимает один или три аргумента — не больше.

    Хвостовой комментарий после ``AS name`` («# 20-alpine») делает
    строку пятиаргументной, и образ не собирается вообще. Это лежало в
    репозитории незамеченным, потому что управляемый деплой собирает не
    из Dockerfile — поймали только когда self-hosting сделал сборку
    обязательной. Тест дешёвый, а класс поломки тихий.
    """
    dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
    for lineno, line in enumerate(dockerfile.read_text().splitlines(), start=1):
        if not line.startswith("FROM"):
            continue
        parts = line.split()
        assert len(parts) in (2, 4), (
            f"Dockerfile:{lineno} — FROM с {len(parts)} аргументами: {line}"
        )
        if len(parts) == 4:
            assert parts[2].upper() == "AS", f"Dockerfile:{lineno} — ожидался AS: {line}"
