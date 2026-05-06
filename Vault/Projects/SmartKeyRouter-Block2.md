# Блок 2 — KeyPool + FailureTracker

**Статус:** ⏳ В работе
**Дата старта:** 2026-05-05
**Исполнитель:** agent-2 (claude-code)

## Задача
Управление ключами и отслеживание ошибок с thread-safety.

## Файлы на выходе
- `smartkeyrouter/key_pool.py` — KeyPool
- `smartkeyrouter/failure_tracker.py` — FailureTracker
- `smartkeyrouter/tests/test_key_pool.py`
- `smartkeyrouter/tests/test_failure_tracker.py`

## KeyPool — требования

**Стратегии выбора ключа:**
- `round_robin` — по кругу (key1→key2→key3→key1)
- `random` — случайный из доступных
- `sequential` — с начала, следующий только если на cooldown

**Методы:**
- `get_next_key() → str | None` — следующий доступный
- `mark_failed(key, error_code)` — записать ошибку
- `mark_success(key)` — сбросить счётчик
- `get_status() → dict` — статус всех ключей (маска: 8 символов + "...")

## FailureTracker — требования

**ОБЯЗАТЕЛЬНО thread-safe:** `threading.Lock()`

**Данные на ключ:**
- fail_count: int
- last_error_code: int
- cooldown_until: datetime
- total_requests: int
- total_failures: int

**Логика cooldown:**
- Retry-After header → cooldown = now + Retry-After
- Exponential backoff: base=1с → 1, 2, 4, 8, 16... (max 600с)
- 401/403 → бесконечность (ключ invalid навсегда)
- 500/502/503 → 30 секунд фиксированно

**Методы:**
- `record_failure(key, error_code, retry_after=None)`
- `record_success(key)`
- `is_on_cooldown(key) → bool`
- `get_cooldown_remaining(key) → float`
- `get_all_stats() → dict`
- `reset(key=None)` — сбросить ключ или всё

## Тесты
- round_robin обходит 3 ключа по кругу
- ключ на cooldown пропускается
- все на cooldown → get_next_key() = None
- 403 → ключ disabled навсегда
- exponential backoff: 1→2→4→8→16
- thread-safe: 10 потоков одновременно пишут ошибки
