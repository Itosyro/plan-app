# Блок 1 — ConfigLoader + keyrouter.yaml

**Статус:** ⏳ В работе
**Дата старта:** 2026-05-05
**Исполнитель:** agent-1 (claude-code)

## Задача
Создать загрузчик конфигурации и пример YAML.

## Файлы на выходе
- `smartkeyrouter/keyrouter.yaml` — конфиг с 3 провайдерами
- `smartkeyrouter/.env.example` — шаблон env vars
- `smartkeyrouter/config_loader.py` — класс ConfigLoader
- `smartkeyrouter/tests/test_config_loader.py` — unit-тесты

## Требования к ConfigLoader
1. Читать `keyrouter.yaml` через PyYAML
2. Для `{env: "VAR_NAME"}` — брать из `os.environ`
3. Если env нет — WARNING, ключ пропускается
4. Если у провайдера нет ключей — WARNING, провайдер disabled
5. Валидация: priority уникальны, context_limit > 0, name уникальны
6. Метод `reload()` — перечитать конфиг без перезапуска
7. Возвращает dataclass/TypedDict

## Тесты
- 2 реальных + 1 отсутствующая env-переменная
- Пропущенный ключ → WARNING
- Провайдер без ключей → disabled
- Дубликат priority → ValidationError

## Принцип работы ConfigLoader
```
load() → читает YAML
       → для каждого ключа: os.environ[env_var]
       → если None: WARNING, skip
       → если все skip у провайдера: WARNING, disabled
       → валидировать
       → вернуть SmartKeyRouterConfig
```

## Ключевые решения реализации
- Использовать dataclasses для типизации
- ConfigLoader — singleton? Нет, создаётся в RouterCore
- YAML путь по умолчанию: "keyrouter.yaml" рядом с config_loader.py
