"""Courier — формирование ответа пользователю после обработки сообщения.

Ответ состоит из двух частей:
1. Подтверждение (рандомно): ~50% из шаблонов, ~50% через LLM (llama-3.1-8b-instant)
2. Резюме сделанного — детерминированно из персистнутых записей (без LLM)

PR-E (бот-карточка): резюме теперь не вшито в текст, а живёт в
:class:`SummaryItem` списком, который пайплайн отдаёт роутерам. Текст
остаётся однострочным confirmation phrase, а строки `\u2610 Title` /
`\u2705 Title` уезжают в inline-keyboard (см.
:func:`build_summary_keyboard`). Старый :func:`build_summary` оставлен
для внутренних вызовов и интроспекции (юнит-тесты, легаси-логирование).

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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import instructor
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter, call_with_rotation
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
#
# PR-E: переписаны дружелюбнее. Стало два требования:
# 1. Никаких сухих «Принял.» / «Записал.» — фразы должны звучать как
#    живой ассистент, а не "backend acknowledged".
# 2. Не более одной emoji-вставки на фразу (раньше playful был
#    парадом из 🤖 / 🥷 / 🧠 — юзер прямо просил так не делать).
#
# Сам список задач уехал в inline-keyboard (см. ``build_summary_keyboard``),
# поэтому шаблон может быть совсем короткий — на 1 строку, без
# перечисления.

TEMPLATES: dict[str, list[str]] = {
    "neutral": [
        "Окей, разобрал.",
        "Готово — посмотри ниже.",
        "Разложил по полкам.",
        "Всё на месте, можно сверить.",
        "Разобрал твоё сообщение.",
        "Готово, проверь список.",
    ],
    "formal_master": [
        "Готово, мой господин.",
        "Всё разобрано, мой господин.",
        "Поручение исполнено, мой господин.",
        "Разложил по полкам, мой господин.",
        "Список готов, мой господин.",
        "К услугам, мой господин — посмотри ниже.",
    ],
    "friendly": [
        "Лови — разобрал твоё сообщение.",
        "Готово, дружище, всё на месте.",
        "Окей, разложил по полкам.",
        "Поймал, проверь список снизу.",
        "Готово — глянь, ничего не упустил?",
        "Всё разобрал, отметь, что готово.",
    ],
    "playful": [
        "Опа, разобрал твой поток мыслей.",
        "Та-дам — список готов.",
        "Готово, проверь, всё ли поймал.",
        "Раз-два — и разложил по полкам.",
        "Лови карточку — что отметим сделанным?",
        "Поймал на лету, посмотри ниже.",
    ],
    "terse": [
        "Готово.",
        "Окей.",
        "Разобрал.",
        "Разложил.",
        "Принято.",
        "На месте.",
    ],
    "respectful": [
        "Готово, всё разобрано.",
        "Принято — посмотрите список ниже.",
        "Разложил по полкам, можно сверить.",
        "Готово, проверьте, пожалуйста, список.",
        "Список готов — поправите, если что не так.",
        "Всё на месте, спасибо за сообщение.",
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

    from pydantic import BaseModel, Field

    class CourierReply(BaseModel):
        """Single confirmation phrase from the courier LLM."""

        text: str = Field(description="Short confirmation phrase in Russian")

    async def _do_call(r: GroqKeyRouter) -> CourierReply:
        client = instructor.from_groq(
            AsyncGroq(api_key=r.current_key),
            mode=instructor.Mode.JSON,
        )
        return await client.chat.completions.create(
            model=COURIER_MODEL,
            response_model=CourierReply,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.9,
            max_retries=2,
        )

    t0 = time.monotonic()
    reply = await call_with_rotation(router, _do_call)
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "courier.llm_done",
        style=style,
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return reply.text


@dataclass
class SummaryItem:
    """One row in the recognised-card inline keyboard.

    ``kind`` decides the row's interactive semantics:

    * ``"task"`` — the row toggles between ``\u2610`` and ``\u2705``;
      tapping it flips the underlying ``Task.status`` between ``new``
      and ``done`` via ``cb_summary_toggle`` (see
      ``app/bot/routers/callbacks.py``).
    * ``"note"`` — the row is a non-interactive label prefixed with
      ``\U0001f4c4`` ("document"); the callback just answers with a
      short toast ("Заметка.") and never mutates DB state. Notes don't
      have a ``done`` concept, so we surface them visually but skip the
      toggle. The semantics may change once the user picks one of the
      alternatives in HANDOFF v15 §Open questions.
    """

    kind: Literal["task", "note"]
    title: str
    category_name: str
    persisted_id: int
    status: Literal["pending", "done"] = "pending"


TASK_PENDING_PREFIX = "\u2610 "  # ☐
TASK_DONE_PREFIX = "\u2705 "  # ✅
NOTE_PREFIX = "\U0001f4c4 "  # 📄

# Telegram caps inline button labels at ~64 chars in practice; titles
# above this look cut on narrow Android screens. We trim *before*
# appending the category suffix to keep the keyboard tidy.
_BUTTON_TITLE_MAX = 40


def _trim_for_button(text: str, *, limit: int = _BUTTON_TITLE_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def _row_label(item: SummaryItem) -> str:
    """Render one inline-keyboard row label for ``item``.

    Tasks: ``\u2610 Title \u00b7 Category`` / ``\u2705 Title \u00b7 Category``
    Notes: ``\U0001f4c4 Title \u00b7 Category``
    """
    if item.kind == "task":
        prefix = TASK_DONE_PREFIX if item.status == "done" else TASK_PENDING_PREFIX
    else:
        prefix = NOTE_PREFIX
    trimmed = _trim_for_button(item.title)
    if item.category_name:
        return f"{prefix}{trimmed} \u00b7 {item.category_name}"
    return f"{prefix}{trimmed}"


def build_summary_keyboard(items: list[SummaryItem]) -> InlineKeyboardMarkup:
    """Build the recognised-card inline keyboard (one row per item).

    Empty input → empty keyboard (callers should send no markup at all
    in that case, but constructing an empty :class:`InlineKeyboardMarkup`
    is still valid aiogram and useful for tests).
    """
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        callback_data = f"summary:toggle:{item.kind}:{item.persisted_id}"
        rows.append([InlineKeyboardButton(text=_row_label(item), callback_data=callback_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def flip_item(items: list[SummaryItem], target_id: int, *, kind: str) -> list[SummaryItem]:
    """Return a new list with the matching item's status flipped.

    Used by the callback handler when it doesn't have the full
    :class:`SummaryItem` list to mutate — we reconstruct from the
    current keyboard, flip, rebuild. Items that don't match are
    returned unchanged.
    """
    out: list[SummaryItem] = []
    for item in items:
        if item.kind == kind == "task" and item.persisted_id == target_id:
            new_status: Literal["pending", "done"] = (
                "done" if item.status == "pending" else "pending"
            )
            out.append(
                SummaryItem(
                    kind=item.kind,
                    title=item.title,
                    category_name=item.category_name,
                    persisted_id=item.persisted_id,
                    status=new_status,
                )
            )
        else:
            out.append(item)
    return out


def build_summary(classifier_results: list[ClassifierResult]) -> str:
    """Build a deterministic text summary of processed items (no LLM).

    Legacy / introspection helper: PR-E moved the summary into an
    inline keyboard (see :func:`build_summary_keyboard`), so the bot
    pipeline does **not** call this function anymore. Kept so unit
    tests and ad-hoc diagnostics can still describe a classification
    batch in one string.
    """
    if not classifier_results:
        return ""

    lines: list[str] = []
    for cr in classifier_results:
        prefix = "Задача" if cr.is_task else "Заметка"
        lines.append(f"{prefix}: {cr.title} \u00b7 {cr.category_name}")

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
    items: list[SummaryItem],
    *,
    mode: str = "mix",
    style: str = "neutral",
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build a confirmation phrase + (optional) recognised-card keyboard.

    PR-E: returns ``(text, keyboard)``. ``text`` is the confirmation
    phrase only — the list of recognised items lives in ``keyboard``
    as togglable rows. When ``items`` is empty (e.g. the splitter
    returned zero units), ``keyboard`` is ``None`` and only the
    confirmation goes back to the user.
    """
    confirmation = await generate_courier_reply(router, style, mode=mode)
    if not items:
        return confirmation, None
    return confirmation, build_summary_keyboard(items)
