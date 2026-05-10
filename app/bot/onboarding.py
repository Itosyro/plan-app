"""Onboarding helpers — popular timezone keyboard + label lookup.

The user picks a timezone via inline keyboard buttons (CIS-popular
zones up front) instead of typing an IANA string. This is the
reliable, low-friction path; falls back to free-text only when the
user explicitly taps "Указать другой ✏️".

callback_data format: ``onb:tz:<iana>`` (e.g. ``onb:tz:Europe/Moscow``)
or ``onb:tz:custom`` for the manual-entry path.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Popular timezones for the CIS / Eastern-Europe audience. Order is
# semi-geographical (West → East) within each row pair, so the most
# likely picks (Moscow, Kyiv, Almaty, Tashkent) end up in the first
# screenful for most clients. Display labels are short Russian city
# names; the actual IANA value is what we persist.
#
# To add a new option: append ``(label, iana)`` here and verify
# ``zoneinfo.ZoneInfo(iana)`` on the runner platform (Render uses tzdata
# from ``alpine`` which has the full IANA set since 2014).
POPULAR_TIMEZONES: list[tuple[str, str]] = [
    ("Москва", "Europe/Moscow"),
    ("Минск", "Europe/Minsk"),
    ("Киев", "Europe/Kyiv"),
    ("Калининград", "Europe/Kaliningrad"),
    ("Ереван", "Asia/Yerevan"),
    ("Тбилиси", "Asia/Tbilisi"),
    ("Алма-Ата", "Asia/Almaty"),
    ("Ташкент", "Asia/Tashkent"),
    ("Бишкек", "Asia/Bishkek"),
    ("Екатеринбург", "Asia/Yekaterinburg"),
    ("Новосибирск", "Asia/Novosibirsk"),
    ("Владивосток", "Asia/Vladivostok"),
]

CUSTOM_TZ_LABEL: str = "Указать другой ✏️"
CUSTOM_TZ_CALLBACK: str = "onb:tz:custom"


def _tz_button(label: str, iana: str) -> InlineKeyboardButton:
    """Build a single timezone button. ``callback_data`` is well below
    the 64-byte Telegram limit even for the longest IANA string."""
    return InlineKeyboardButton(text=label, callback_data=f"onb:tz:{iana}")


def tz_keyboard() -> InlineKeyboardMarkup:
    """Build the inline keyboard shown alongside the greeting.

    Layout: 3 columns × 4 rows of popular zones, then a final wide row
    with "Указать другой ✏️" for free-text entry. Buttons-per-row=3 fits
    comfortably on a phone without text wrapping for our short labels.
    """
    rows: list[list[InlineKeyboardButton]] = []
    cols_per_row = 3
    for chunk_start in range(0, len(POPULAR_TIMEZONES), cols_per_row):
        chunk = POPULAR_TIMEZONES[chunk_start : chunk_start + cols_per_row]
        rows.append([_tz_button(label, iana) for label, iana in chunk])

    rows.append(
        [
            InlineKeyboardButton(
                text=CUSTOM_TZ_LABEL,
                callback_data=CUSTOM_TZ_CALLBACK,
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def label_for_iana(iana: str) -> str:
    """Return the friendly Russian label for a known IANA tz, or the
    IANA string itself if unknown (custom tz path).

    Used in the "Готово, ты в Москве" acknowledgement so the user sees
    a city, not an ``Asia/Almaty`` IANA path.
    """
    for label, tz in POPULAR_TIMEZONES:
        if tz == iana:
            return label
    return iana


def parse_tz_callback(data: str) -> str | None:
    """Extract the IANA timezone from an ``onb:tz:<iana>`` callback string.

    Returns:
        - The IANA string for known popular zones (e.g. ``Europe/Moscow``).
        - ``"custom"`` for the manual-entry path.
        - ``None`` for malformed payloads.

    The handler is responsible for validating that the IANA string
    parses (via ``zoneinfo``); we only verify the wire format here.
    """
    if not data.startswith("onb:tz:"):
        return None
    payload = data[len("onb:tz:") :]
    if not payload:
        return None
    return payload
