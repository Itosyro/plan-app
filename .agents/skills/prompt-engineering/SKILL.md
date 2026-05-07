---
name: prompt-engineering
description: Distilled best practices for designing prompts in plan-app. Use this when writing or revising any LLM prompt (Splitter, Classifier, Critic, Courier).
---

# Prompt-engineering — карманный справочник

Это **выжимка** из:
- [Anthropic Prompt Engineering Tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial)
- [Anthropic Cookbook](https://github.com/anthropics/anthropic-cookbook)
- [Brex Prompt Engineering Guide](https://github.com/brexhq/prompt-engineering) — полный текст в `.agents/skills/brex-prompt-engineering/REFERENCE.md`
- [dair-ai Prompt Engineering Guide](https://www.promptingguide.ai/)

Применяется ко всем промптам в `app/ai/`.

---

## 1. Базовая структура промпта

Любой системный промпт в plan-app состоит из 5 секций (в этом порядке):

```
ROLE       — кто ты в этом запросе ("Ты — классификатор задач плановщика…")
CONTEXT    — что происходит, какие у юзера настройки, текущее время / TZ
TASK       — что конкретно нужно сделать
CONSTRAINTS— чего нельзя (никаких комментариев, только JSON, не выдумывать поля…)
EXAMPLES   — 2–4 few-shot примера ввода→вывода
```

Если хоть одна секция пропущена — модель уйдёт в галлюцинации.

---

## 2. Few-shot examples — обязательно

Вместо «Расклассифицируй вход на категории» дай **2 примера**:

```
Вход: "пробежка завтра утром"
Выход: {"task": "пробежка", "horizon": "завтра", "category": "спорт", "confidence": 0.9}

Вход: "обсудить с Машей бюджет на отпуск"
Выход: {"task": "обсудить с Машей бюджет на отпуск", "horizon": "когда-нибудь", "category": "семья", "confidence": 0.7}
```

Few-shot **в 5–10 раз** уменьшает количество ошибок формата.

---

## 3. Structured output — через `instructor`

Никогда не парсить JSON регэкспом. Использовать [instructor](https://github.com/instructor-ai/instructor) с Pydantic-схемой:

```python
from instructor import from_groq
from pydantic import BaseModel
from groq import Groq

class TaskClassification(BaseModel):
    task: str
    horizon: Literal["сегодня", "завтра", "неделя", "месяц", "год", "когда-нибудь"]
    category: str
    confidence: float

client = from_groq(Groq(api_key=...))
result = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    response_model=TaskClassification,
    messages=[...],
    max_retries=2,
)
```

Если модель вернула что-то невалидное — instructor **сам** делает retry с подсказкой.

---

## 4. Низкая температура для классификации, высокая для генерации

| Задача | temperature |
|---|---|
| Splitter (разбить на интенты) | 0.0 |
| Classifier (теги, горизонты) | 0.0 — 0.2 |
| Critic (валидация) | 0.0 |
| Courier (ответ юзеру в свободной форме) | 0.7 — 0.9 |

`temperature=0.0` ≠ детерминизм (на Groq всё равно может варьироваться), но даёт максимум стабильности.

---

## 5. Цепочка размышлений (CoT) — только для Critic

Critic — `qwen-qwq-32b`, reasoning-модель. У неё нативный CoT. **Не нужно** добавлять «думай по шагам» — это просадит качество.

Для Splitter/Classifier (быстрые модели) — **тоже не добавлять CoT** в массовых вызовах. CoT удваивает токены и латентность ради 5–10% точности, что нам не критично.

---

## 6. Имена полей — короткие, английские

Pydantic-схемы — на английском (`task`, `horizon`, `category`), значения — на русском («сегодня», «спорт»). Английские имена сильно стабильнее в JSON-output.

---

## 7. Длина системного промпта

- Splitter: ≤ 300 токенов системника + few-shot
- Classifier: ≤ 800 токенов системника + few-shot + список категорий юзера
- Critic: ≤ 600 токенов системника + черновик + правила

Длиннее — растёт latency, падает focus модели. Если нужно больше контекста — переноси в few-shot.

---

## 8. Dynamic context (категории/горизонты юзера)

Categories и horizons вытягиваются из БД и подставляются в системный промпт каждый вызов. Если юзер за неделю набрал ≥ 30 категорий — это сигнал, что модель плохо переиспользует существующие → **поднять threshold confidence на создание новой**.

---

## 9. Локализация: всегда RU в инпуте/аутпуте, EN в инструкциях

System prompt — на английском (стабильнее, лучше следует), few-shot — на русском (повторяет вход юзера), output — на русском (что юзер видит).

```
SYSTEM (EN): You are a task classifier for a Russian-language planner bot…
EXAMPLE (RU): Вход: "купить хлеб" → Выход: {"task": "купить хлеб", ...}
```

---

## 10. Anti-hallucination guardrails

В каждом промпте Classifier:

```
- DO NOT invent categories that are not in the user list, unless none fits.
- If creating a new category, output `category_is_new: true` and propose `category_keywords: [...]`.
- DO NOT extract dates that the user did not say. If unclear, set horizon to "когда-нибудь".
```

Critic потом проверит, что модель не выдумала.

---

## 11. Частые ошибки промпт-инжиниринга в нашем проекте

1. **Слишком общий ROLE** — «ты помощник» → классификатор не знает контекст. **Лучше:** «Ты классификатор задач для русскоязычного Telegram-плановщика. Юзер скидывает поток мысли, ты раскладываешь на структурированные интенты».
2. **Few-shot из идеальных кейсов** — модель не учится на edge cases. **Лучше:** включить пограничные («хм надо бы пробежать но завтра дождь обещают»).
3. **Не указано как обрабатывать пустой вход** — модель что-то выдумает. **Лучше:** «If input is ambiguous or empty, return `[]`.»
4. **Имена категорий по-разному в системе и в БД** — duplicate. **Лучше:** `lower().strip()` перед сравнением, кеш в памяти Worker'а.

---

## 12. Когда обращаться к мощной модели (70B vs 8B)

| Задача | Модель |
|---|---|
| Splitter | `llama-3.1-8b-instant` (быстро, дёшево) |
| Classifier (стабильный кейс) | `llama-3.3-70b-versatile` |
| Classifier (новый/непонятный кейс) | A/B на `llama-4-scout-17b-16e-instruct` |
| Critic | `qwen-qwq-32b` (reasoning) |
| Courier (LLM-стиль) | `llama-3.1-8b-instant` (быстрый ответ юзеру) |

Деталь по каждой модели — в `.agents/skills/groq-tips/SKILL.md`.

---

## 13. Eval — обязательно

Каждый промпт держим в `app/ai/prompts/<name>.md`, к нему рядом `app/ai/prompts/<name>.eval.yaml` — 30+ кейсов (вход → ожидаемый выход). При изменении промпта прогоняем eval, не ниже baseline-метрики (см. `.agents/skills/plan-app-internal/SKILL.md`).

---

## 14. Что прочитать дальше

- Полный Brex guide: `.agents/skills/brex-prompt-engineering/REFERENCE.md`
- Anthropic interactive tutorial (online): https://github.com/anthropics/prompt-eng-interactive-tutorial
- dair-ai guide: https://www.promptingguide.ai/
- Anthropic cookbook (рецепты): https://github.com/anthropics/anthropic-cookbook
