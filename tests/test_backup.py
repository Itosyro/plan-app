"""Tests for ``/backup`` — the server-to-server migration archive."""

from __future__ import annotations

import io
import sqlite3
import tarfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from app import backup as app_backup
from app.backup import build_backup, maybe_send_auto_backup, sqlite_path
from app.bot.courier_templates import BACKUP_FORBIDDEN, BACKUP_PRIVATE_ONLY
from app.bot.routers import commands
from app.bot.routers.commands import create_router
from app.shared.config import Settings


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite+aiosqlite:////app/data/plan.db", "/app/data/plan.db"),
        ("sqlite:///./data/plan.db", "./data/plan.db"),
        ("postgresql+psycopg://u:p@host/db", None),
        ("sqlite+aiosqlite:///:memory:", None),
        (None, None),
    ],
)
def test_sqlite_path(url: str | None, expected: str | None) -> None:
    result = sqlite_path(url)
    assert (str(result) if result is not None else None) == (
        str(Path(expected)) if expected is not None else None
    )


def test_build_backup_packs_env_and_live_database(tmp_path: Path) -> None:
    """The archive holds ``.env`` plus a readable snapshot of the DB.

    The snapshot is taken through SQLite's backup API while the source
    connection is still open, which is the whole point: on a live server
    the bot is writing when the owner asks for the archive.
    """
    db_path = tmp_path / "plan.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE task (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO task (title) VALUES ('купить хлеб')")
    conn.commit()

    env_path = tmp_path / ".env"
    # ``newline=""`` — иначе Windows подменит \n на \r\n и тест будет
    # проверять поведение платформы, а не байт-в-байт копирование.
    env_path.write_text("TELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8", newline="")

    try:
        filename, blob = build_backup(db_path, env_path)
    finally:
        conn.close()

    assert filename.startswith("plan-backup-") and filename.endswith(".tgz")

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        names = tar.getnames()
        assert sorted(names) == [".env", "data/plan.db"]
        env_member = tar.extractfile(".env")
        db_member = tar.extractfile("data/plan.db")
        assert env_member is not None and db_member is not None
        assert env_member.read().decode() == "TELEGRAM_BOT_TOKEN=123:abc\n"
        restored = tmp_path / "restored.db"
        restored.write_bytes(db_member.read())

    # The unpacked file must be a working database, not just bytes.
    check = sqlite3.connect(restored)
    try:
        assert check.execute("SELECT title FROM task").fetchall() == [("купить хлеб",)]
    finally:
        check.close()


def test_build_backup_requires_env_file(tmp_path: Path) -> None:
    """No ``.env`` → fail loudly; a half-archive would lose the keys."""
    db_path = tmp_path / "plan.db"
    sqlite3.connect(db_path).close()
    with pytest.raises(FileNotFoundError):
        build_backup(db_path, tmp_path / "missing.env")


# ── /backup handler: who is allowed to get the secrets ───────────────


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeChat:
    def __init__(self, chat_type: str) -> None:
        self.type = chat_type


class _FakeMessage:
    """Records what the handler answered with."""

    def __init__(self, user_id: int, chat_type: str = "private") -> None:
        self.from_user = _FakeUser(user_id)
        self.chat = _FakeChat(chat_type)
        self.answers: list[str] = []
        self.documents: list[tuple[str, str]] = []

    async def answer(self, text: str, **_: object) -> None:
        self.answers.append(text)

    async def answer_document(self, document: object, caption: str = "", **_: object) -> None:
        filename = getattr(document, "filename", "")
        assert isinstance(filename, str)
        self.documents.append((filename, caption))


def _backup_handler() -> Callable[..., Awaitable[None]]:
    """Pull ``cmd_backup`` out of a freshly built commands router."""
    router = create_router()
    for handler in router.message.handlers:
        if handler.callback.__name__ == "cmd_backup":
            callback: Callable[..., Awaitable[None]] = handler.callback
            return callback
    raise AssertionError("cmd_backup is not registered on the commands router")


def _settings(tmp_path: Path, owner: int | None) -> Settings:
    return Settings(
        env="test",
        owner_telegram_id=owner,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'plan.db').as_posix()}",
    )


@pytest.mark.asyncio
async def test_backup_without_owner_configured_reports_own_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset ``OWNER_TELEGRAM_ID`` → no archive, but tell them what to set."""
    monkeypatch.setattr(commands, "get_settings", lambda: _settings(tmp_path, None))
    message = _FakeMessage(user_id=555)
    await _backup_handler()(message)
    assert message.documents == []
    assert "555" in message.answers[0]


@pytest.mark.asyncio
async def test_backup_refuses_non_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stranger must never receive the bot token and the Groq keys."""
    monkeypatch.setattr(commands, "get_settings", lambda: _settings(tmp_path, 111))
    message = _FakeMessage(user_id=222)
    await _backup_handler()(message)
    assert message.documents == []
    assert message.answers == [BACKUP_FORBIDDEN]


@pytest.mark.asyncio
async def test_backup_sends_archive_to_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner gets a document whose name matches the install hint."""
    sqlite3.connect(tmp_path / "plan.db").close()
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8", newline="")
    monkeypatch.setattr(app_backup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(commands, "get_settings", lambda: _settings(tmp_path, 111))

    message = _FakeMessage(user_id=111)
    await _backup_handler()(message)

    assert message.answers == []
    assert len(message.documents) == 1
    filename, caption = message.documents[0]
    assert filename.endswith(".tgz")
    # The caption is the migration instruction — it must name the very
    # file the user just received, or the copy-pasted command fails.
    assert filename in caption


@pytest.mark.asyncio
async def test_backup_refuses_group_chats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even for the owner: a reply in a group shows the keys to everyone."""
    sqlite3.connect(tmp_path / "plan.db").close()
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8", newline="")
    monkeypatch.setattr(app_backup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(commands, "get_settings", lambda: _settings(tmp_path, 111))

    message = _FakeMessage(user_id=111, chat_type="supergroup")
    await _backup_handler()(message)

    assert message.documents == []
    assert message.answers == [BACKUP_PRIVATE_ONLY]


@pytest.mark.asyncio
async def test_backup_reports_failure_instead_of_going_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup that can't be built must say so — silence reads as success."""
    sqlite3.connect(tmp_path / "plan.db").close()
    monkeypatch.setattr(app_backup, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setattr(commands, "get_settings", lambda: _settings(tmp_path, 111))

    message = _FakeMessage(user_id=111)
    await _backup_handler()(message)

    assert message.documents == []
    assert len(message.answers) == 1
    assert "data/plan.db" in message.answers[0]


# ── auto-backup: insurance for a server rented by the week ───────────


class _RecordingBot:
    def __init__(self) -> None:
        self.sent: list[int] = []
        self.captions: list[str] = []

    async def send_document(
        self, *, chat_id: int, document: object = None, caption: str = "", **_: object
    ) -> None:
        self.sent.append(chat_id)
        self.captions.append(caption)


@pytest.fixture
def _sqlite_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A self-hosted-looking install: a real DB file and a real ``.env``."""
    sqlite3.connect(tmp_path / "plan.db").close()
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8", newline="")
    monkeypatch.setattr(app_backup, "ENV_FILE", tmp_path / ".env")
    return tmp_path


@pytest.mark.asyncio
async def test_auto_backup_sends_once_per_interval(
    _sqlite_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First tick sends; the next tick an hour later stays quiet."""
    settings = _settings(_sqlite_home, 111)
    bot = _RecordingBot()

    now = 1_000_000.0
    assert await maybe_send_auto_backup(bot, settings=settings, now=now) is True
    assert bot.sent == [111]
    # Подпись — единственная инструкция, доступная когда сервера уже нет:
    # в ней должно стоять реальное имя файла, а не плейсхолдер.
    assert "plan-backup-" in bot.captions[0]
    assert ".tgz" in bot.captions[0]

    assert await maybe_send_auto_backup(bot, settings=settings, now=now + 3600) is False
    assert bot.sent == [111]

    # A day later the interval has elapsed → a fresh copy goes out.
    assert await maybe_send_auto_backup(bot, settings=settings, now=now + 25 * 3600) is True
    assert bot.sent == [111, 111]


@pytest.mark.asyncio
async def test_auto_backup_off_without_owner_or_when_disabled(_sqlite_home: Path) -> None:
    """No owner → nowhere to send. ``auto_backup_hours=0`` → opted out."""
    bot = _RecordingBot()
    assert await maybe_send_auto_backup(bot, settings=_settings(_sqlite_home, None)) is False

    off = Settings(
        env="test",
        owner_telegram_id=111,
        auto_backup_hours=0,
        database_url=f"sqlite+aiosqlite:///{(_sqlite_home / 'plan.db').as_posix()}",
    )
    assert await maybe_send_auto_backup(bot, settings=off) is False
    assert bot.sent == []


@pytest.mark.asyncio
async def test_auto_backup_skipped_on_managed_postgres(tmp_path: Path) -> None:
    """Managed deploy has no SQLite file to pack — must not crash."""
    bot = _RecordingBot()
    settings = Settings(
        env="test",
        owner_telegram_id=111,
        database_url="postgresql+psycopg://u:p@host/db",
    )
    assert await maybe_send_auto_backup(bot, settings=settings) is False
    assert bot.sent == []
