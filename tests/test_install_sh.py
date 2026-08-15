"""End-to-end tests for ``scripts/install.sh`` — the one-command self-hosted install.

Only the external commands are faked: ``git``/``docker``/``curl`` are
``#!/bin/sh`` stubs on a ``PATH`` prefix that log their argv. Everything the
script itself decides — the tar allow-list, ``.env`` handling, the
``PLAN_UID``/``PLAN_GID`` rewrite, when compose may start — really runs
under bash.
"""

from __future__ import annotations

import io
import os
import shutil
import sqlite3
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from app.backup import build_backup

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "install.sh"
EXAMPLE_ENV = ROOT / ".env.server.example"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash is required to run scripts/install.sh"
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _bash() -> str:
    """Return the bash to run the script with — Git Bash on Windows, ``bash`` elsewhere.

    On Windows ``shutil.which("bash")`` finds WSL's bash first, and WSL
    cannot open a script by its ``C:/...`` path. Git Bash ships next to
    ``git.exe`` and understands such paths.
    """
    git = shutil.which("git")
    roots = [Path(git).parents[1]] if git else []
    for candidate in [
        root / "bin" / "bash.exe" for root in [*roots, Path(r"C:\Program Files\Git")]
    ]:
        if candidate.is_file():
            return str(candidate)
    return "bash"


BASH = _bash()

# Каталог со стабами ($1) встаёт в начало PATH изнутри bash, а не через env:
# Git Bash при старте переписывает PATH и дописывает в начало свои
# /mingw64/bin и /usr/bin — а там лежат настоящие git и curl. ``cd && pwd``
# заодно приводит путь к тому виду, который понимает сам bash.
_PATH_PRELUDE = 'PATH="$(cd "$1" && pwd):$PATH"; shift; exec bash "$@"'


def _stub(path: Path, body: str) -> None:
    """Write an executable ``#!/bin/sh`` stub (LF endings — CRLF breaks the shebang)."""
    path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _archive(tmp_path: Path, env_text: str) -> Path:
    """Build a real ``/backup`` archive (temp sqlite db + temp ``.env``) on disk."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "live"
    src.mkdir()
    db_path = src / "plan.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE task (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO task (title) VALUES ('купить хлеб')")
    conn.commit()
    conn.close()
    env_path = src / ".env"
    # ``newline=""`` — иначе Windows подменит \n на \r\n и мы будем сравнивать
    # поведение платформы, а не байты, которые прошли через архив.
    env_path.write_text(env_text, encoding="utf-8", newline="")

    filename, blob = build_backup(db_path, env_path)
    archive = tmp_path / filename
    archive.write_bytes(blob)
    return archive


@pytest.fixture
def install_dir(tmp_path: Path) -> Path:
    """Where the script installs — its parent is the target of a ``../`` escape."""
    return tmp_path / "srv" / "plan-app"


@pytest.fixture
def cmd_log(tmp_path: Path) -> Path:
    """Argv of every stubbed external command, one per line."""
    return tmp_path / "cmd.log"


@pytest.fixture
def run_install(tmp_path: Path, install_dir: Path, cmd_log: Path) -> Runner:
    """Return a callable running install.sh against stubbed git/docker/curl."""
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    for name in (".env.server.example", "docker-compose.yml"):
        shutil.copy(ROOT / name, repo / name)

    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    log = cmd_log.as_posix()
    # git clone <repo> <dir> — раскладываем копию «репозитория» в <dir>
    # (последний аргумент), остальные подкоманды просто отмечаются в логе.
    _stub(
        stub_bin / "git",
        f"printf 'git %s\\n' \"$*\" >>'{log}'\n"
        '[ "$1" = clone ] || exit 0\n'
        'for a in "$@"; do dst="$a"; done\n'
        f'mkdir -p "$dst" && cp -a \'{repo.as_posix()}/.\' "$dst/"\n',
    )
    # info / compose version / pull / up -d / logs — всё успешно.
    _stub(stub_bin / "docker", f"printf 'docker %s\\n' \"$*\" >>'{log}'\n")
    # healthz отвечает сразу и телом, похожим на настоящее: скрипт ждёт
    # именно ``polling_alive``, пустой ответ гонял бы его все 30 кругов.
    _stub(
        stub_bin / "curl",
        f"printf 'curl %s\\n' \"$*\" >>'{log}'\n"
        'printf \'{"status":"ok","env":"production","polling_alive":true}\'\n',
    )
    install_dir.parent.mkdir(parents=True)

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "-c", _PATH_PRELUDE, "bash", stub_bin.as_posix(), SCRIPT.as_posix(), *args],
            env={
                **os.environ,
                "PLAN_APP_DIR": install_dir.as_posix(),
                "PLAN_APP_REPO": "https://example.invalid/plan-app.git",
            },
            capture_output=True,
            text=True,
            # Скрипт говорит по-русски в UTF-8, а локаль Windows — нет.
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    return run


def test_migration_unpacks_env_and_database(
    run_install: Runner, install_dir: Path, cmd_log: Path, tmp_path: Path
) -> None:
    """With an archive: ``.env`` + ``data/plan.db`` land in place and compose starts."""
    archive = _archive(tmp_path, "TELEGRAM_BOT_TOKEN=123:abc\n")

    result = run_install(archive.as_posix())

    assert result.returncode == 0, result.stderr
    with tarfile.open(archive) as tar:
        packed_db = tar.extractfile("data/plan.db")
        assert packed_db is not None
        assert (install_dir / "data" / "plan.db").read_bytes() == packed_db.read()
    # Байт в байт, плюс дописанные в конец PLAN_UID/PLAN_GID.
    assert (install_dir / ".env").read_bytes().startswith(b"TELEGRAM_BOT_TOKEN=123:abc\n")
    assert "compose up -d" in cmd_log.read_text(encoding="utf-8")


def test_archive_with_parent_path_is_rejected(
    run_install: Runner, install_dir: Path, cmd_log: Path, tmp_path: Path
) -> None:
    """A tarball carrying ``../evil`` must not be unpacked at all."""
    archive = tmp_path / "evil.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, payload in ((".env", b"TELEGRAM_BOT_TOKEN=123:abc\n"), ("../evil", b"pwned")):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

    result = run_install(archive.as_posix())

    assert result.returncode != 0
    assert "посторонние файлы" in result.stderr
    assert not (install_dir.parent / "evil").exists()
    assert not (install_dir / ".env").exists()
    assert "compose up" not in cmd_log.read_text(encoding="utf-8")


def test_fresh_install_creates_env_and_stops(
    run_install: Runner, install_dir: Path, cmd_log: Path
) -> None:
    """No archive, no ``.env``: seed it from the example and stop for the keys."""
    result = run_install()

    assert result.returncode != 0
    assert (install_dir / ".env").read_bytes() == EXAMPLE_ENV.read_bytes()
    assert "TELEGRAM_BOT_TOKEN" in result.stderr
    assert "compose up" not in cmd_log.read_text(encoding="utf-8")


def test_guard_holds_for_an_archive_bigger_than_the_pipe_buffer(
    run_install: Runner, install_dir: Path, cmd_log: Path, tmp_path: Path
) -> None:
    """The allow-list must not depend on how much fits in a pipe.

    With ``tar -tzf … | grep -q … && die`` the guard silently inverted on
    any archive whose listing exceeded ~64 KiB: grep exited at the first
    stray name, tar died of SIGPIPE, and under ``pipefail`` the pipeline
    went non-zero — so ``die`` never ran. A planted
    ``docker-compose.override.yml`` would then be extracted and merged by
    the ``docker compose up`` two lines later.
    """
    archive = tmp_path / "big.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, payload in [
            (".env", b"TELEGRAM_BOT_TOKEN=123:abc\n"),
            ("docker-compose.override.yml", b"services: {app: {entrypoint: [sh, -c, pwned]}}\n"),
            *((f"data/pad-{i}.txt", b"") for i in range(20_000)),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

    result = run_install(archive.as_posix())

    assert result.returncode != 0
    assert "посторонние файлы" in result.stderr
    assert not (install_dir / "docker-compose.override.yml").exists()
    assert "compose up" not in cmd_log.read_text(encoding="utf-8")


def test_truncated_archive_does_not_touch_the_existing_database(
    run_install: Runner, install_dir: Path, tmp_path: Path
) -> None:
    """An interrupted download must abort before anything is overwritten.

    The listing used to be validated inside a pipe whose failure was
    swallowed, so a half-downloaded archive passed the check and tar
    then wrote garbage over the live database — old data gone, new data
    corrupt, no copy of either.
    """
    good = _archive(tmp_path, "TELEGRAM_BOT_TOKEN=123:abc\n")
    truncated = tmp_path / "half.tgz"
    truncated.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 2])

    # Первый прогон создаёт установку с «живой» базой.
    assert run_install(good.as_posix()).returncode == 0
    live = install_dir / "data" / "plan.db"
    before = live.read_bytes()

    result = run_install(truncated.as_posix())

    assert result.returncode != 0
    assert live.read_bytes() == before


def test_restore_keeps_a_copy_of_the_previous_database(
    run_install: Runner, install_dir: Path, tmp_path: Path
) -> None:
    """Restoring over an existing install leaves the old DB recoverable."""
    first = _archive(tmp_path / "one", "TELEGRAM_BOT_TOKEN=123:abc\n")
    second = _archive(tmp_path / "two", "TELEGRAM_BOT_TOKEN=999:xyz\n")

    assert run_install(first.as_posix()).returncode == 0
    previous = (install_dir / "data" / "plan.db").read_bytes()

    assert run_install(second.as_posix()).returncode == 0

    backups = list((install_dir / "data").glob("plan.db.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == previous


def test_stale_plan_uid_is_replaced_not_appended(
    run_install: Runner, install_dir: Path, tmp_path: Path
) -> None:
    """A uid from the old server is overwritten with this machine's id once."""
    archive = _archive(tmp_path, "PLAN_UID=4242\nTELEGRAM_BOT_TOKEN=123:abc\n")

    assert run_install(archive.as_posix()).returncode == 0

    uid = subprocess.run(
        [BASH, "-c", "id -u"], capture_output=True, text=True, check=True
    ).stdout.strip()
    lines = (install_dir / ".env").read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if line.startswith("PLAN_UID=")] == [f"PLAN_UID={uid}"]


def test_missing_archive_aborts_before_clone(
    run_install: Runner, install_dir: Path, cmd_log: Path, tmp_path: Path
) -> None:
    """A typo in the archive path stops the install before it touches anything."""
    result = run_install((tmp_path / "nope.tgz").as_posix())

    assert result.returncode != 0
    assert "nope.tgz" in result.stderr
    assert not install_dir.exists()
    log = cmd_log.read_text(encoding="utf-8")
    assert "clone" not in log
    assert "compose up" not in log
