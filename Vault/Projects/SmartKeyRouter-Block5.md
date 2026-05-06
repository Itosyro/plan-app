# Блок 5 — RouterCore + ProviderRegistry

**Статус:** Ожидает (зависит от блоков 1-4)
**Исполнитель:** agent-3 (claude-code)

## Задача
Главная логика роутера — склеить все компоненты.

## Файлы на выходе
- `smartkeyrouter/provider_registry.py`
- `smartkeyrouter/router_core.py`
- `smartkeyrouter/tests/test_router_core.py`

## RouterResponse dataclass
```python
@dataclass
class RouterResponse:
    success: bool
    content: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    key_masked: str | None = None
    switches_made: int = 0
    total_latency_ms: int = 0
    error_message: str | None = None
```

## RouterCore

```python
class RouterCore:
    def __init__(self, config_path: str = "keyrouter.yaml"):
        self.config = ConfigLoader(config_path)
        self.providers = ProviderRegistry(self.config)
        self.failure_tracker = FailureTracker(self.config.global_settings)
        self.context_adapter = ContextAdapter(self.config.global_settings)
        self.logger = self._setup_logger()
```

### Метод chat(messages, **kwargs) → RouterResponse

Алгоритм:
1. Провайдеры отсортированные по priority
2. Для каждого провайдера:
   a. key_pool.get_next_key()
   b. Если ключей нет → WARNING, next провайдер
   c. Для каждой модели по priority:
      - ContextAdapter.prepare_context()
      - ProviderAdapter.send_request()
      - 429/503 → record_failure, next
      - 401/403 → disabled навсегда
      - Успех → RouterResponse
3. Все исчерпаны → RouterResponse(success=False)

### get_status() → dict
### reset_cooldowns(provider_name: str | None)

## ProviderRegistry
- Загружает провайдеры из ConfigLoader
- Создаёт KeyPool и Adapter для каждого
- get_providers_sorted_by_priority()
- get_key_pool(provider_name)
- get_adapter(provider_name)

## Тесты (mock адаптеры)
- 429 → auto-switch ко второму провайдеру
- второй успех → результат
- все исчерпаны → ошибка
- контекст передаётся корректно
- switches_made считается
