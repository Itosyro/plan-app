// Friendly date+time picker inside a BottomSheet. Replaces native
// ``<input type="datetime-local">`` (which renders as a different
// widget on every platform).
//
// Layout:
//   ┌────────────────────────────┐
//   │ [Сегодня] [Завтра] [+1 нед]│  ← quick presets (tone-coded)
//   │                            │
//   │  Дата:  [2026-05-12]       │
//   │  Время: [09:00]            │
//   │                            │
//   │  Убрать дату               │  ← rose, opt-out
//   └────────────────────────────┘
//   [Отмена]              [Готово]
//
// Implementation note: we keep the date and time as separate native
// inputs (so iOS / Android still show their native pickers when
// tapped — those are good for date entry). Everything else is
// custom-styled.

import { useEffect, useState } from "react";
import { CalendarDays, X } from "lucide-react";
import { BottomSheet } from "./BottomSheet";
import { haptic } from "../lib/telegram";

interface Props {
  open: boolean;
  onClose: () => void;
  /** ISO datetime (naive-UTC, as returned by the API) or null. */
  value: string | null;
  /** Receives ISO datetime, or ``null`` to clear. */
  onSelect: (iso: string | null) => void;
  /** IANA tz used to render presets in the user's local time. */
  tz: string;
}

interface Preset {
  key: string;
  label: string;
  build: (tz: string) => Date;
}

// Presets pick a sensible default time (09:00 user-local) so the
// task lands on the morning of the picked day. Users can fine-tune
// with the date/time inputs underneath.
const PRESETS: Preset[] = [
  {
    key: "today",
    label: "Сегодня",
    build: (tz) => atLocal(0, 9, 0, tz),
  },
  {
    key: "tomorrow",
    label: "Завтра",
    build: (tz) => atLocal(1, 9, 0, tz),
  },
  {
    key: "next_week",
    label: "+1 неделя",
    build: (tz) => atLocal(7, 9, 0, tz),
  },
];

// Build a Date at ``today + offsetDays`` at the given local hour:minute
// in ``tz``. We compute the offset in UTC, then format-and-reparse so
// the returned Date represents the right wall-clock moment.
function atLocal(offsetDays: number, hour: number, minute: number, tz: string): Date {
  const now = new Date();
  const dt = new Date(now.getTime() + offsetDays * 86400000);
  // Format the calendar day in the target tz, then construct an
  // ISO with the requested HH:mm and let JS interpret it as local
  // wall-clock. The result is then re-zoned into ``tz``.
  try {
    const ymd = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(dt);
    // ``ymd`` is ``YYYY-MM-DD``.
    const hh = String(hour).padStart(2, "0");
    const mm = String(minute).padStart(2, "0");
    return new Date(`${ymd}T${hh}:${mm}:00`);
  } catch {
    const fallback = new Date(dt);
    fallback.setHours(hour, minute, 0, 0);
    return fallback;
  }
}

function toLocalIsoParts(iso: string, tz: string): { date: string; time: string } {
  // Backend returns naive-UTC; append ``Z`` so JS interprets it as UTC.
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const dt = new Date(utc);
  if (Number.isNaN(dt.getTime())) {
    return { date: "", time: "" };
  }
  try {
    const date = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(dt);
    const time = new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(dt);
    return { date, time };
  } catch {
    return { date: "", time: "" };
  }
}

function toIsoUtc(localDate: string, localTime: string): string | null {
  if (!localDate || !localTime) return null;
  const wallClock = new Date(`${localDate}T${localTime}:00`);
  if (Number.isNaN(wallClock.getTime())) return null;
  return wallClock.toISOString();
}

export function BottomSheetDate({ open, onClose, value, onSelect, tz }: Props) {
  const initial = value ? toLocalIsoParts(value, tz) : { date: "", time: "" };
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  // Sync state when the sheet re-opens with a different value.
  useEffect(() => {
    if (!open) return;
    const parts = value ? toLocalIsoParts(value, tz) : { date: "", time: "" };
    setDate(parts.date);
    setTime(parts.time);
    setActivePreset(null);
  }, [open, value, tz]);

  function commit(): void {
    const iso = toIsoUtc(date, time);
    if (iso === null) {
      // No date entered — close without changes.
      onClose();
      return;
    }
    haptic("success");
    onSelect(iso);
    onClose();
  }

  function applyPreset(p: Preset): void {
    haptic("select");
    const dt = p.build(tz);
    const ymd = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(dt);
    const hhmm = new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(dt);
    setDate(ymd);
    setTime(hhmm);
    setActivePreset(p.key);
  }

  function clear(): void {
    haptic("warn");
    onSelect(null);
    onClose();
  }

  const footer = (
    <div className="flex items-center justify-between gap-2">
      <button
        type="button"
        onClick={onClose}
        className="ease-apple rounded-xl px-4 py-2 text-[14px] font-medium text-tg-hint transition-all duration-200 active:scale-[0.96]"
      >
        Отмена
      </button>
      <button
        type="button"
        onClick={commit}
        disabled={!date || !time}
        className="ease-apple rounded-xl bg-tg-button px-5 py-2 text-[14px] font-semibold text-tg-button-text transition-all duration-200 active:scale-[0.96] disabled:opacity-50"
      >
        Готово
      </button>
    </div>
  );

  return (
    <BottomSheet open={open} onClose={onClose} title="Когда" footer={footer}>
      <div className="flex flex-col gap-4">
        <div className="flex gap-2">
          {PRESETS.map((p) => {
            const isActive = activePreset === p.key;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => applyPreset(p)}
                className={
                  "ease-apple flex-1 rounded-2xl px-3 py-2.5 text-[13px] font-medium transition-all duration-200 active:scale-[0.96] " +
                  (isActive
                    ? "bg-tg-button/10 text-tg-button ring-1 ring-tg-button/30"
                    : "bg-bento text-tg-text/80 hover:text-tg-text")
                }
              >
                {p.label}
              </button>
            );
          })}
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] font-medium text-tg-hint">Дата</span>
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setActivePreset(null);
            }}
            className="ease-apple rounded-2xl bg-bento px-4 py-3 text-[15px] text-tg-text focus:outline-none focus:ring-2 focus:ring-tg-button"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] font-medium text-tg-hint">Время</span>
          <input
            type="time"
            value={time}
            onChange={(e) => {
              setTime(e.target.value);
              setActivePreset(null);
            }}
            className="ease-apple rounded-2xl bg-bento px-4 py-3 text-[15px] text-tg-text focus:outline-none focus:ring-2 focus:ring-tg-button"
          />
        </label>

        {value && (
          <button
            type="button"
            onClick={clear}
            className="ease-apple mt-1 inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-500/10 px-4 py-3 text-[14px] font-medium text-rose-700 transition-all duration-200 active:scale-[0.97] dark:text-rose-300"
          >
            <X size={16} strokeWidth={2.25} aria-hidden />
            Убрать дату
          </button>
        )}

        <div className="flex items-center gap-2 rounded-2xl bg-bento px-3 py-2 text-[12px] text-tg-hint">
          <CalendarDays size={14} strokeWidth={2.25} aria-hidden />
          <span className="min-w-0 truncate">
            Время указано в твоём поясе: {tz}
          </span>
        </div>
      </div>
    </BottomSheet>
  );
}
