# Блок 4 — ContextAdapter

**Статус:** ⏳ В работе
**Дата старта:** 2026-05-05
**Исполнитель:** agent-2 (claude-code, параллельно с блоками 2-3)

## Задача
Адаптировать контекст разговора под лимиты модели при failover.

## Файлы на выходе
- `smartkeyrouter/context_adapter.py`
- `smartkeyrouter/tests/test_context_adapter.py`

## Проблема
```
Модель A (limit=65536) → упала
Модель B (limit=8192)
Текущий контекст = 50000 токенов
→ Нужно обрезать умно
```

## Методы

### prepare_context(messages, target_context_limit, strategy, reserve_for_response=2048)
Главный метод. Возвращает messages готовые для новой модели.

### count_tokens_approximate(messages) → int
Приблизительный подсчёт токенов:
- Формула: `len(весь текст) / 3.5`
- Запас +10% сверху для безопасности
- НЕ использовать tiktoken или другие tokenizer-библиотеки

### _truncate_middle(messages, target_limit) → list[dict]
Удалять сообщения из середины истории.
Сохранять ВСЕГДА:
- system prompt (первое message с role=system)
- последние 4 сообщения (последний обмен)
Остальное: удалять от середины к краям.

### _truncate_oldest(messages, target_limit) → list[dict]
Удалять самые старые сообщения.
Сохранять:
- system prompt
Удалять: earliest user/assistant messages.

### convert_tool_calls(messages, target_provider) → list[dict]
Конвертировать tool_calls в формат целевого провайдера.
Если провайдер не поддерживает tool_calls в истории → конвертировать в текст:
`[tool: имя_инструмента, результат: ...]`

## Стратегии (из конфига)
- `truncate_middle` — удалять из середины
- `truncate_oldest` — удалять старые
- `error` — вернуть ошибку если контекст больше лимита

## Тесты
- контекст меньше лимита → без изменений
- truncate_middle сохраняет system + последние 4
- truncate_oldest сохраняет system prompt
- подсчёт токенов: 350 символов ≈ 100 токенов
