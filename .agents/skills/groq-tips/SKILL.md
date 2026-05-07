---
name: groq-tips
description: Всё про работу с Groq API в plan-app — модели, лимиты, retry, ротация ключей, структурный вывод. Используй при работе с любым кодом в app/ai/groq*.
---

# Groq API — карманный справочник

Groq — это **inference-провайдер** для open-weight моделей (Llama, Qwen, Gemma, Whisper). Он **не обучает** свои модели, только хостит чужие на быстрых LPU-чипах.

---

## 1. Какие модели мы используем

| Роль | Модель | Контекст | tps* |
|---|---|---|---|
| Splitter (разбить поток мысли) | `llama-3.1-8b-instant` | 131K | ~750 |
| Classifier (теги, горизонты) | `llama-3.3-70b-versatile` | 131K | ~270 |
| Classifier (A/B альтернатива) | `meta-llama/llama-4-scout-17b-16e-instruct` | 131K | ~600 |
| Critic (валидация) | `qwen-qwq-32b` | 131K | ~400 |
| Courier (LLM-стиль) | `llama-3.1-8b-instant` | — | — |
| Whisper (voice → text) | `whisper-large-v3` | 25 МБ файл | — |

*tps = tokens per second, ориентировочно по бенчам Groq

### Резервы
- `meta-llama/llama-4-maverick-17b-128e-instruct` — крупнее scout, попробовать в А/B
- `gemma2-9b-it` — лёгкая Google-модель, для fallback
- `whisper-large-v3-turbo` — быстрее, чуть менее точно

---

## 2. Rate limits (free tier на 1 ключ, на 2026)

Точные лимиты меняются — смотри https://console.groq.com/docs/rate-limits.

Грубо для free:
- ~30 RPM (requests per minute)
- ~1800 RPH (requests per hour)
- ~14400 RPD (requests per day)
- лимит токенов в сутки тоже есть

### Почему нам нужно 3 ключа
Один юзер ≈ 50 запросов/день — хватит **одного** ключа с большим запасом. Три нужны:
1. **Изоляция ролей** — если упёрся splitter, не падает classifier
2. **Резерв** — один ключ забанили / отозвали → переключаемся
3. **Будущее** — масштаб на 100 юзеров

См. `app/ai/groq_router.py` (когда напишем) — простой round-robin/by-role-роутер ~50 строк.

---

## 3. Retry-стратегия

```python
import asyncio
from groq import AsyncGroq, RateLimitError, APIError

async def call_with_retry(client, **kwargs):
    delays = [1, 2, 4, 8]  # exponential
    for d in delays:
        try:
            return await client.chat.completions.create(**kwargs)
        except RateLimitError:
            await asyncio.sleep(d)
        except APIError as e:
            if e.status_code >= 500:
                await asyncio.sleep(d)
            else:
                raise
    raise RuntimeError("Groq retries exhausted")
```

При 429 (rate limit) — переключаемся на следующий ключ из пула, **не ждём**.

---

## 4. Structured output через `instructor`

Никогда не парсить JSON регэкспом — instructor + Pydantic делает это надёжнее.

```python
from instructor import from_groq, Mode
from groq import Groq
from pydantic import BaseModel

class Intent(BaseModel):
    text: str
    type: Literal["task", "note"]
    horizon: str

client = from_groq(Groq(api_key=key), mode=Mode.JSON)
result: Intent = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    response_model=Intent,
    messages=[...],
    max_retries=2,
    temperature=0.1,
)
```

### Грабли
- В Mode.JSON — модель **должна** видеть слово "JSON" в системном промпте, иначе instructor может зависнуть
- `max_retries=2` — instructor сам дотачивает промпт при ошибке валидации, не путать с network retry

---

## 5. Whisper

```python
from groq import AsyncGroq

client = AsyncGroq(api_key=settings.groq_whisper_key)

async def transcribe(audio_bytes: bytes, lang: str = "ru") -> str:
    transcription = await client.audio.transcriptions.create(
        file=("voice.ogg", audio_bytes, "audio/ogg"),
        model="whisper-large-v3",
        language=lang,
        response_format="text",  # просто строка, без timestamps
        temperature=0.0,
    )
    return transcription
```

### Грабли
- Файл ≤ 25 МБ. Telegram voice ≤ 20 МБ — попадаем
- `language="ru"` — обязательно, иначе модель может перевести в EN
- Voice от Telegram — `.ogg` (Opus), Whisper понимает

---

## 6. Логирование вызовов

Каждый Groq-вызов логировать:
```python
logger.info(
    "groq_call",
    extra={
        "model": model,
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
        "latency_ms": int((t1 - t0) * 1000),
        "key_id": key_id,  # какой из ключей пула
    },
)
```

Это нужно для:
- мониторинга latency
- балансировки ключей
- bills (когда выйдем на платный tier)

---

## 7. Безопасность ключей

- В коде — **только** через `Settings` (Pydantic)
- В Render Free — через ENV (`Settings` reads `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`)
- Локально — `.env` в `.gitignore`
- Никогда не логировать значение ключа (даже первые/последние символы)
- При компрометации — отзыв через https://console.groq.com/keys + новый ключ

---

## 8. Тестирование без живого Groq

Локально:
```python
import respx
import httpx

@respx.mock
async def test_classifier():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "..."}}]})
    )
    ...
```

В CI **никогда** не дёргаем живой Groq — все тесты на моках.

---

## 9. Eval-кейсы

Для каждого промпта — фикс. Когда меняем промпт / модель — прогоняем eval перед мерджем. Метрика: % случаев, где `output == expected` (или `f1` для multi-label).

См. `app/ai/prompts/<name>.eval.yaml` (когда появится).

---

## 10. Полезные ссылки

- Groq docs: https://console.groq.com/docs
- Models: https://console.groq.com/docs/models
- Rate limits: https://console.groq.com/docs/rate-limits
- instructor: https://github.com/instructor-ai/instructor
- groq-python: https://github.com/groq/groq-python
