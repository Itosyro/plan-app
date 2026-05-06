# Блок 3 — ProviderAdapter

**Статус:** ⏳ В работе
**Дата старта:** 2026-05-05
**Исполнитель:** agent-2 (claude-code, параллельно с блоком 2)

## Задача
Универсальный интерфейс для всех LLM провайдеров.

## Файлы на выходе
- `smartkeyrouter/adapters/__init__.py`
- `smartkeyrouter/adapters/base_adapter.py` — AdapterResponse dataclass
- `smartkeyrouter/adapters/generic_openai_adapter.py` — базовый OpenAI-совместимый
- `smartkeyrouter/adapters/openrouter_adapter.py`
- `smartkeyrouter/adapters/qwen_adapter.py`
- `smartkeyrouter/tests/test_adapters.py`

## AdapterResponse dataclass
```python
@dataclass
class AdapterResponse:
    success: bool
    content: str | None = None
    error_code: int | None = None
    retry_after: int | None = None  # из заголовка Retry-After
    tokens_used: int | None = None
    model_used: str | None = None
```

## Базовый класс
```python
class BaseProviderAdapter:
    def send_request(
        self,
        messages: list[dict],
        model_id: str,
        api_key: str,
        base_url: str | None = None,
        **kwargs
    ) -> AdapterResponse:
        raise NotImplementedError
```

## Адаптеры

### GenericOpenAIAdapter (универсальный)
- base_url из конфига
- Используется для Allama Cloud и новых провайдеров
- timeout = 60 секунд

### OpenRouterAdapter
- Base URL: `https://openrouter.ai/api/v1/chat/completions`
- Headers: `Authorization: Bearer {key}`
- Формат: стандартный OpenAI chat completions
- Логировать `usage.total_tokens`

### QwenAdapter
- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- OpenAI-совместимый формат
- Headers: `Authorization: Bearer {key}`

## Обработка ошибок в адаптерах
- `Timeout` → AdapterResponse(success=False, error_code=408)
- `ConnectionError` → AdapterResponse(success=False, error_code=503)
- HTTP 429 → прочитать Retry-After header, передать в retry_after
- ЛЮБАЯ ошибка → вернуть AdapterResponse, НЕ бросать exception

## Тесты (mock HTTP, не реальные запросы)
- Успешный ответ парсится правильно
- 429 с Retry-After → retry_after заполнен
- Timeout → error_code=408
- Connection error → error_code=503
