# SmartKeyRouter

> **Fallback-роутер для LLM API** — автоматическое переключение между провайдерами и ключами при rate limits (429).

## Контекст
- Hermes Agent использует LLM через API-провайдеры (OpenRouter, Qwen, Allama Cloud)
- Бесплатные API дают 429 ошибки — нужен автоматический failover
- Роутер должен расширяться через YAML без правки кода

## Статусы блоков

| Блок | Название | Статус | Исполнитель |
|------|----------|--------|-------------|
| 0 | Архитектура | ✅ Готово | - |
| 1 | ConfigLoader + YAML | ✅ Готово (05.05) | Hermes |
| 2 | KeyPool + FailureTracker | ✅ Готово (05.05) | Hermes |
| 3 | ProviderAdapter | ✅ Готово (05.05) | Hermes |
| 4 | ContextAdapter | ✅ Готово (05.05) | Hermes |
| 5 | ProviderRegistry + RouterCore | ✅ Готово (06.05) | Hermes |
| 6 | CLI + Логирование | ✅ Готово (06.05) | Hermes |
| 7 | Hermes Integration + README | ✅ Готово (06.05) | Hermes |

## Прогресс

- [x] 81 тест проходят
- [x] README.md создан
- [x] hermes_integration.py готов

## Файловая структура

```
keyrouter/
├── keyrouter.yaml
├── .env.example
├── README.md
├── config_loader.py      ← Блок 1
├── key_pool.py           ← Блок 2
├── failure_tracker.py     ← Блок 2
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py
│   ├── generic_openai_adapter.py
│   ├── openrouter_adapter.py
│   └── qwen_adapter.py
├── context_adapter.py    ← Блок 4
├── provider_registry.py  ← Блок 5
├── router_core.py        ← Блок 5
├── router_logger.py      ← Блок 6
├── cli.py                ← Блок 6
├── hermes_integration.py ← Блок 7
└── tests/
    ├── test_config_loader.py
    ├── test_key_pool.py
    ├── test_failure_tracker.py
    ├── test_adapters.py
    ├── test_context_adapter.py
    ├── test_router_core.py
    └── test_router_logger.py
```

## Правила реализации
1. Ключи ТОЛЬКО через env vars
2. Адаптеры возвращают AdapterResponse, не бросают исключений
3. Ключи маскируются: первые 8 символов + "***"
4. FailureTracker thread-safe (threading.Lock)
5. Один блок за раз, с тестами

## Критические правила
- НИКОГДА ключи в коде/YAML — только env
- НИКОГДА exceptions из адаптеров наружу
- ВСЕГДА маскировать ключи в логах
- ВСЕГДА threading.Lock() в FailureTracker
- ОДИН блок → тесты → подтверждение → следующий

## Использование

```python
from hermes_integration import HermesRouter

router = HermesRouter()
response = router.chat([{"role": "user", "content": "Привет!"}])
print(response.content)
```

## Ресурсы
- [[SmartKeyRouter-Block1]] — детали Блока 1
- [[SmartKeyRouter-Block2]] — детали Блока 2
- [[SmartKeyRouter-Block3]] — детали Блока 3
- [[SmartKeyRouter-Block4]] — детали Блока 4
- [[SmartKeyRouter-Block5]] — детали Блока 5
- [[SmartKeyRouter-Block6]] — детали Блока 6
- [[SmartKeyRouter-Block7]] — детали Блока 7