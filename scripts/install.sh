#!/usr/bin/env bash
# Установка plan-app на чистый сервер одной командой.
#
#   curl -fsSL https://raw.githubusercontent.com/Itosyro/plan-app/main/scripts/install.sh | bash -s plan-backup-....tgz
#
# С архивом (его отдаёт команда /backup в боте) — переезд: .env и база
# встают на место, бот поднимается уже со всеми данными. Без архива —
# первая установка: скрипт создаёт .env из шаблона и просит вписать два
# ключа.
set -euo pipefail

REPO_URL="${PLAN_APP_REPO:-https://github.com/Itosyro/plan-app.git}"
DIR="${PLAN_APP_DIR:-$HOME/plan-app}"
BACKUP="${1:-}"

die() { printf '\n❌ %s\n' "$1" >&2; exit 1; }
say() { printf '→ %s\n' "$1"; }

command -v git >/dev/null || die "Нет git. Установи: apt install -y git"
command -v curl >/dev/null || die "Нет curl. Установи: apt install -y curl"
command -v docker >/dev/null || die "Нет docker. Установи: curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 || die "Нет плагина docker compose (docker compose version)"
docker info >/dev/null 2>&1 || die "Docker-демон не отвечает. Запусти: systemctl start docker"

# Архив резолвим ДО cd — путь пользователь дал относительно своей папки.
if [ -n "$BACKUP" ]; then
    [ -f "$BACKUP" ] || die "Файл не найден: $BACKUP (скачай его из чата с ботом и положи на сервер)"
    BACKUP="$(cd "$(dirname "$BACKUP")" && pwd)/$(basename "$BACKUP")"
fi

if [ -d "$DIR/.git" ]; then
    say "Обновляю $DIR"
    # Не смогли обновиться (правки в файлах, нет сети) — не повод падать:
    # старая версия рабочая, а данные пользователя важнее свежести кода.
    git -C "$DIR" pull --ff-only || say "обновить не вышло, продолжаю на текущей версии"
else
    say "Клонирую в $DIR"
    git clone --depth 1 "$REPO_URL" "$DIR"
fi
cd "$DIR"

if [ -n "$BACKUP" ]; then
    # Разворачиваем только ожидаемые пути: архив приходит из чата, а
    # tar с «../» в именах записал бы файлы куда угодно.
    #
    # Оглавление читаем целиком в переменную, и только потом фильтруем.
    # Два разных грабля разом: (1) на недокачанном архиве tar падает
    # здесь, ДО того как перезаписан хоть один файл; (2) вариант
    # «tar | grep -q … && die» проверку ломал — grep -q закрывает пайп
    # на первом совпадении, tar получает SIGPIPE, и под ``pipefail``
    # статус становится 141, то есть die не срабатывал ровно на тех
    # архивах, ради которых написан.
    entries="$(tar -tzf "$BACKUP")"
    bad="$(printf '%s\n' "$entries" | grep -Ev '^(\./)?(\.env|data/[A-Za-z0-9._-]+)$' || true)"
    [ -z "$bad" ] || die "В архиве посторонние файлы, распаковка отменена:
$bad"
    say "Распаковываю $BACKUP (.env + база)"
    stamp="$(date +%s)"
    if [ -f .env ]; then cp .env ".env.bak.$stamp"; fi
    # Гасим ПЕРВЫМ делом, до всякого копирования: под работающим
    # контейнером база живёт в режиме WAL, и свежие записи лежат в
    # plan.db-wal. Копия, снятая раньше остановки, их не содержит — а
    # сам WAL мы через строку удалим. Плюс запись в файл под живым
    # процессом это прямой путь к битой базе.
    docker compose down >/dev/null 2>&1 || true
    # Копию базы делаем всегда: распаковка перезаписывает файл, и без
    # копии откатиться некуда, если архив оказался не тем.
    if [ -f data/plan.db ]; then cp data/plan.db "data/plan.db.bak.$stamp"; fi
    # Хвосты WAL от ПРЕЖНЕЙ базы SQLite молча накатит на новый файл —
    # данные из архива исчезнут, а integrity_check скажет «ok».
    rm -f data/*.db-wal data/*.db-shm data/*.db-journal
    tar -xzf "$BACKUP" -C .
elif [ ! -f .env ]; then
    cp .env.server.example .env
    # Просим повторить ЭТУ ЖЕ команду, а не «docker compose up -d»:
    # ниже скрипт ещё создаёт data/ и прописывает PLAN_UID — без них
    # контейнер не сможет открыть базу.
    die "Создан $DIR/.env — впиши TELEGRAM_BOT_TOKEN и GROQ_API_KEYS (nano $DIR/.env)
   и запусти эту же команду ещё раз."
fi

grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env || die "В $DIR/.env пуст TELEGRAM_BOT_TOKEN"

# Контейнер должен работать под тем же uid, что владеет ./data и .env —
# иначе он не прочитает базу (на VPS установку часто делают из-под root).
set_env_var() {
    if grep -q "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$2|" .env
    else
        printf '%s=%s\n' "$1" "$2" >>.env
    fi
}
set_env_var PLAN_UID "$(id -u)"
set_env_var PLAN_GID "$(id -g)"
mkdir -p data
chmod 600 .env

say "Скачиваю образ"
docker compose pull
say "Запускаю"
docker compose up -d

say "Жду, пока поднимется"
for _ in $(seq 30); do
    # ``polling_alive`` в /healthz — единственный способ отличить «бот
    # работает» от «веб-сервер жив, а опрос Telegram умер». Успехом
    # считаем ТОЛЬКО ``true``: на «status ok» без этого поля скрипт
    # рапортовал бы победу о мёртвом боте.
    health="$(curl -fsS localhost:8000/healthz 2>/dev/null || true)"
    case "$health" in
        *'"polling_alive":false'*) break ;;
        *'"polling_alive":true'*)
            # aiogram ловит ЛЮБУЮ ошибку опроса и вечно ретраит, поэтому
            # живой polling ещё не значит «бот получает сообщения»:
            # неверный токен и 409 от не выключенного старого сервера
            # выглядят точно так же. Спрашиваем лог — но сперва даём
            # первому getUpdates успеть сходить и отметиться в нём.
            sleep 3
            if docker compose logs --tail 50 app 2>/dev/null | grep -q "Failed to fetch updates"; then
                docker compose logs --tail 20 app
                die "Бот не может получать сообщения — проверь токен и что старый сервер остановлен."
            fi
            printf '\n✅ Готово. Бот работает. Проверь: напиши ему в Telegram.\n'
            printf '   Логи:   cd %s && docker compose logs -f app\n' "$DIR"
            printf '   Бэкап:  команда /backup в чате с ботом\n'
            if grep -q '^MINIAPP_URL_OVERRIDE=.\+' .env; then
                # Адрес приехал из архива вместе со старым сервером и почти
                # наверняка теперь ведёт в никуда — кнопка меню откроет пустоту.
                printf '   ⚠️  В .env остался старый MINIAPP_URL_OVERRIDE — поправь под новый адрес\n'
                printf '       (после правки: docker compose up -d, не restart)\n'
            fi
            exit 0
            ;;
    esac
    sleep 2
done

docker compose logs --tail 40 app
die "Не поднялся за 60 с — лог выше. Частые причины: неверный токен, нет интернета."
