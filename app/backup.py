"""Server-to-server migration: pack ``.env`` + the SQLite file into one archive.

Self-hosted state is exactly two things — the secrets in ``.env`` and the
database file — so a backup is a ``.tar.gz`` with those two entries laid
out the way ``scripts/install.sh`` expects to unpack them over a fresh
clone: ``.env`` at the root and ``data/plan.db`` next to it.

The database is snapshotted through SQLite's online backup API, so the
copy is consistent even while the bot is writing.
"""

from __future__ import annotations

import asyncio
import io
import os
import sqlite3
import tarfile
import time
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.shared.config import Settings, get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

# ``.env`` sits at the project root (bind-mounted read-only into the
# container by docker-compose; same place ``Settings`` reads it from).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Telegram Bot API refuses documents above 50 MB.
TELEGRAM_DOCUMENT_LIMIT = 50 * 1024 * 1024


def sqlite_path(database_url: str | None) -> Path | None:
    """Return the file path behind a ``sqlite[+driver]:///…`` URL, else ``None``.

    ``sqlite+aiosqlite:////app/data/plan.db`` → ``/app/data/plan.db``;
    Postgres URLs and ``:memory:`` yield ``None`` (nothing to pack).
    """
    if not database_url:
        return None
    scheme, sep, rest = database_url.partition(":///")
    if not sep or not scheme.startswith("sqlite") or rest in ("", ":memory:"):
        return None
    return Path(rest)


def build_backup(db_path: Path, env_path: Path | None = None) -> tuple[str, bytes]:
    """Return ``(filename, tar.gz bytes)`` with ``.env`` and a DB snapshot.

    Blocking (sqlite3 + tarfile) — call via ``asyncio.to_thread`` from
    the bot. Raises ``FileNotFoundError`` if ``env_path`` is missing.
    """
    env_path = env_path if env_path is not None else ENV_FILE
    src = sqlite3.connect(db_path)
    try:
        snapshot = sqlite3.connect(":memory:")
        try:
            src.backup(snapshot)
            db_bytes = snapshot.serialize()
        finally:
            snapshot.close()
    finally:
        src.close()

    env_bytes = env_path.read_bytes()
    now = time.time()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in ((".env", env_bytes), (f"data/{db_path.name}", db_bytes)):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = int(now)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(payload))
    filename = time.strftime("plan-backup-%Y-%m-%d-%H%M.tgz", time.gmtime(now))
    return filename, buf.getvalue()


# Отметка «когда в последний раз пытались» лежит файлом рядом с базой:
# переживает пересоздание контейнера, не требует ни таблицы, ни миграции.
MARKER_NAME = ".last_backup"

# Инструкция ВНУТРИ подписи, а не ссылкой на /help: этот архив нужен
# ровно тогда, когда спросить у бота уже не получится — сервер пропал.
AUTO_BACKUP_CAPTION = (
    "🧳 Автобэкап (.env + база). Если сервер пропадёт, на новом хватит одной команды:\n"
    "curl -fsSL https://raw.githubusercontent.com/Itosyro/plan-app/main/scripts/install.sh"
    " | bash -s ИМЯ_ЭТОГО_ФАЙЛА\n\n"
    "Внутри ключи — никому не пересылай."
)


async def maybe_send_auto_backup(
    bot: Bot,
    *,
    settings: Settings | None = None,
    now: float | None = None,
) -> bool:
    """Send the owner a fresh archive if the interval has elapsed.

    Insurance for a server rented by the week: if it disappears before
    the owner remembers ``/backup``, the last automatic archive is
    already sitting in their Telegram chat. Off unless the deploy is
    self-hosted (SQLite) *and* ``OWNER_TELEGRAM_ID`` is set.

    The marker is stamped **before** sending: a permanently failing
    send (file too large, bot blocked) then retries tomorrow instead of
    every single tick.
    """
    settings = settings or get_settings()
    if settings.auto_backup_hours <= 0 or settings.owner_telegram_id is None:
        return False
    db_path = sqlite_path(settings.database_url)
    if db_path is None or not db_path.exists() or not ENV_FILE.exists():
        return False

    now = now if now is not None else time.time()
    marker = db_path.parent / MARKER_NAME
    if marker.exists() and now - marker.stat().st_mtime < settings.auto_backup_hours * 3600:
        return False
    marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), encoding="utf-8")
    # Отметка живёт во времени mtime — а его берём из того же ``now``,
    # что и сравнение выше, иначе инъекция времени в тестах врёт.
    os.utime(marker, (now, now))

    filename, blob = await asyncio.to_thread(build_backup, db_path)
    if len(blob) > TELEGRAM_DOCUMENT_LIMIT:
        logger.warning("backup.auto.too_big", size_bytes=len(blob))
        return False
    await bot.send_document(
        chat_id=settings.owner_telegram_id,
        document=BufferedInputFile(blob, filename=filename),
        caption=AUTO_BACKUP_CAPTION,
    )
    logger.info("backup.auto.sent", size_bytes=len(blob))
    return True
