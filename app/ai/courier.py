"""Courier — формирование ответа пользователю после обработки сообщения.

Ответ состоит из двух частей:
1. Подтверждение (рандомно): ~50% из шаблонов, ~50% через LLM (llama-3.1-8b-instant)
2. Резюме сделанного — детерминированно из персистнутых записей (без LLM)

Две независимые настройки на ``UserSettings``:
- ``response_style_source`` — *источник* подтверждения. Принимает
  строго ``template_only`` / ``llm_only`` / ``mix`` (дефолт ``mix``).
  Любое другое значение → ``use_llm=False`` (см. fallback в
  :func:`generate_courier_reply`).
- ``courier_template_style`` — *тон* (ключ из :data:`TEMPLATES`):
  ``neutral`` (дефолт) / ``formal_master`` / ``friendly`` /
  ``playful`` / ``terse`` / ``respectful``.

Pre-2026-05-09 настройка источника шла под именами
``formal``/``casual``/``mix`` и две из трёх кнопок ничего не делали,
см. ``docs/REVIEW-2026-05-09.md::C-1``.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult
from app.shared.logging import get_logger

logger = get_logger(__name__)

COURIER_MODEL = "llama-3.1-8b-instant"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "courier.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    """Read the courier system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


# ── Шаблоны подтверждений по стилям (>=5 на каждый) ──────────────────

TEMPLATES: dict[str, list[str]] = {
    "neutral": [
        "Записал.",
        "Принял, всё сохранил.",
        "Готово, обработал.",
        "Сохранил, всё на месте.",
        "Принято и разложено.",
        "Обработал твоё сообщение.",
    ],
    "formal_master": [
        "Слушаюсь, мой господин.",
        "Всё исполнено, мой господин.",
        "Как прикажете, мой господин. Записано.",
        "Будет сделано, мой господин.",
        "Принято к исполнению, мой господин.",
        "Ваше поручение записано, мой господин.",
    ],
    "friendly": [
        "Ловлю на лету! Всё записал.",
        "Без проблем, братан! Сохранил.",
        "Сделано, дружище!",
        "Всё чётко, записал!",
        "Держи пять! Разложил всё по полочкам.",
        "Легко! Всё на месте.",
    ],
    "playful": [
        "Опа! Разобрал твой поток мыслей \U0001f9e0",
        "Бип-буп, всё записано! \U0001f916",
        "Мозги поскрипели — всё разложил!",
        "Поймал всё на лету, как ниндзя! \U0001f977",
        "Та-дам! Всё разложено по полочкам.",
        "Раз-два — и готово! Магия \u2728",
    ],
    "terse": [
        "Записал.",
        "Ок.",
        "Готово.",
        "Принял.",
        "\u2705",
        "Сделано.",
    ],
    "respectful": [
        "Благодарю, всё записал для вас.",
        "Принято, ваши задачи сохранены.",
        "С удовольствием — всё обработал для вас.",
        "Готово. Ваши задачи разложены.",
        "Всё сохранено, будьте спокойны.",
        "Обработал ваше сообщение. Всё в порядке.",
    ],
}


def _pick_template(style: str) -> str:
    """Return a random template for the given style."""
    variants = TEMPLATES.get(style, TEMPLATES["neutral"])
    return random.choice(variants)


async def generate_courier_reply(
    router: GroqKeyRouter,
    style: str,
    *,
    mode: str = "mix",
) -> str:
    """Generate a confirmation phrase (template or LLM).

    ``mode``:
    - ``template_only`` — always pick from templates
    - ``llm_only`` — always generate via LLM
    - ``mix`` — 50/50 random choice
    """
    use_llm = False
    if mode == "llm_only":
        use_llm = True
    elif mode == "mix":
        use_llm = random.random() < 0.5

    if not use_llm:
        return _pick_template(style)

    system_prompt = _load_prompt()
    user_message = f"Style: {style}\nGenerate a confirmation."

    client = instructor.from_groq(
        AsyncGroq(api_key=router.current_key),
        mode=instructor.Mode.JSON,
    )

    t0 = time.monotonic()

    from pydantic import BaseModel, Field

    class CourierReply(BaseModel):
        """Single confirmation phrase from the courier LLM."""

        text: str = Field(description="Short confirmation phrase in Russian")

    reply = await client.chat.completions.create(
        model=COURIER_MODEL,
        response_model=CourierReply,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.9,
        max_retries=2,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "courier.llm_done",
        style=style,
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return reply.text


def build_summary(classifier_results: list[ClassifierResult]) -> str:
    """Build a deterministic summary of processed items (no LLM)."""
    if not classifier_results:
        return ""

    lines: list[str] = []
    for cr in classifier_results:
        kind = "\U0001f4cc задача" if cr.is_task else "\U0001f4dd заметка"
        lines.append(f"{kind}: {cr.title} [{cr.category_name}]")

    n = len(lines)
    header = f"Разобрал на {_pluralize(n)}:\n"
    return header + "\n".join(lines)


def _pluralize(n: int) -> str:
    """Russian plural for 'элемент'."""
    if 11 <= n % 100 <= 19:
        return f"{n} элементов"
    mod = n % 10
    if mod == 1:
        return f"{n} элемент"
    if 2 <= mod <= 4:
        return f"{n} элемента"
    return f"{n} элементов"


async def courier_respond(
    router: GroqKeyRouter,
    classifier_results: list[ClassifierResult],
    *,
    mode: str = "mix",
    style: str = "neutral",
) -> str:
    """Build the full reply: confirmation + summary."""
    confirmation = await generate_courier_reply(router, style, mode=mode)
    summary = build_summary(classifier_results)

    if summary:
        return f"{confirmation}\n\n{summary}"
    return confirmation
