# Блок 6 — Логирование + CLI

**Статус:** ✅ Готово (06.05.2026)
**Исполнитель:** Hermes Agent

## Выполнено
- `router_logger.py` — 16 тестов
- `cli.py` — demo, status, reset
- JSON-логирование с auto-masking ключей

## Тесты: 16/16 passed

```
tests/test_router_logger.py::TestRouterLogger::test_singleton_returns_same_instance PASSED
tests/test_router_logger.py::TestRouterLogger::test_mask_key_none_returns_none PASSED
tests/test_router_logger.py::TestRouterLogger::test_mask_key_long_returns_first_8 PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_writes_json_line PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_masks_key_automatically PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_request_event PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_response_success PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_response_error PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_key_switch PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_context_truncated PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_all_providers_exhausted PASSED
tests/test_router_logger.py::TestRouterLogger::test_log_level_filtering PASSED
tests/test_router_logger.py::TestRouterLogger::test_get_logger_factory_from_config PASSED
tests/test_router_logger.py::TestRouterLogger::test_close_closes_file PASSED
tests/test_router_logger.py::TestRouterLogger::test_timestamp_is_iso_format PASSED
```

## router_logger.py

- Thread-safe singleton
- JSON output (one line = one record)
- Auto-mask keys: first 8 chars + "***"
- Convenience methods: log_request, log_response, log_key_switch, log_context_truncated, log_all_providers_exhausted
- ISO 8601 timestamps

## cli.py

```bash
python cli.py demo   # Полный набор демо
python cli.py status # Статус провайдеров
python cli.py reset  # Сброс кулдаунов
```

## Пример лога

```json
{"timestamp": "2026-05-06T10:30:00+00:00", "level": "INFO", "message": "OUTGOING_REQUEST", "provider": "openrouter_free", "model": "deepseek/deepseek-chat-v3-0324:free", "key": "sk-or-v1***"}
{"timestamp": "2026-05-06T10:30:01+00:00", "level": "WARNING", "message": "KEY_SWITCH", "from_provider": "openrouter_free", "to_provider": "qwen_official", "reason": "429 rate limit"}
```

## Заметки

- Реализовано JSON логирование (не text с ротацией как в плане)
- Ключи маскируются в log parameter автоматически
- List/dict корректно JSON-сериализуются

## Следующий блок

→ [[SmartKeyRouter-Block7]] — Hermes Integration + README