// Month-grid calendar for the Mini-App (Phase 7d). Shows tasks that
// have a due date, bucketed into day cells in the user's timezone.
// Tapping a day reveals that day's tasks below the grid; tapping a
// task opens the detail screen (same route as the list).
//
// Tasks are fetched client-side (the personal task volume is small)
// and re-bucketed whenever the visible month changes or the parent
// bumps ``refreshSignal`` after a mutation.

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { apiClient } from "../api/client";
import { localDateKey, localTime } from "../lib/format";
import { haptic } from "../lib/telegram";
import type { Task } from "../types";

interface Props {
  tz: string;
  refreshSignal: number;
  onOpen: (id: number) => void;
}

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
];

// Today's calendar-day key in the user's tz, for the "today" ring.
function todayKey(tz: string): string {
  return localDateKey(new Date().toISOString(), tz) ?? "";
}

// Monday-first weekday index (0=Mon..6=Sun) for a JS Date.
function mondayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

export function CalendarView({ tz, refreshSignal, onOpen }: Props) {
  const now = useMemo(() => new Date(), []);
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth()); // 0-11
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>(() => todayKey(tz));

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await apiClient.tasks({ include_done: true });
        if (!cancelled) setTasks(resp.filter((t) => t.due_at !== null));
      } catch (err) {
        if (!cancelled) console.error("calendar load failed", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  // Bucket tasks by local day key once per task-set change.
  const byDay = useMemo(() => {
    const map = new Map<string, Task[]>();
    for (const t of tasks) {
      const key = localDateKey(t.due_at, tz);
      if (!key) continue;
      const arr = map.get(key);
      if (arr) arr.push(t);
      else map.set(key, [t]);
    }
    return map;
  }, [tasks, tz]);

  // Build the 6×7 grid of day cells for the visible month. Leading /
  // trailing cells from adjacent months are rendered dimmed.
  const cells = useMemo(() => {
    const first = new Date(viewYear, viewMonth, 1);
    const startOffset = mondayIndex(first);
    const gridStart = new Date(viewYear, viewMonth, 1 - startOffset);
    const out: { date: Date; key: string; inMonth: boolean }[] = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate(),
      ).padStart(2, "0")}`;
      out.push({ date: d, key, inMonth: d.getMonth() === viewMonth });
    }
    return out;
  }, [viewYear, viewMonth]);

  const tKey = todayKey(tz);
  const selectedTasks = byDay.get(selectedKey) ?? [];

  const goPrev = () => {
    haptic("select");
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };
  const goNext = () => {
    haptic("select");
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
        <div className="mb-3 flex items-center justify-between">
          <button
            type="button"
            aria-label="Предыдущий месяц"
            onClick={goPrev}
            className="ease-apple flex h-9 w-9 items-center justify-center rounded-full text-tg-hint transition-all duration-150 hover:bg-bento active:scale-90"
          >
            <ChevronLeft size={20} strokeWidth={2.25} aria-hidden />
          </button>
          <span className="font-display text-[16px] font-semibold tracking-tight text-tg-text">
            {MONTHS[viewMonth]} {viewYear}
          </span>
          <button
            type="button"
            aria-label="Следующий месяц"
            onClick={goNext}
            className="ease-apple flex h-9 w-9 items-center justify-center rounded-full text-tg-hint transition-all duration-150 hover:bg-bento active:scale-90"
          >
            <ChevronRight size={20} strokeWidth={2.25} aria-hidden />
          </button>
        </div>

        <div className="mb-1 grid grid-cols-7 gap-1">
          {WEEKDAYS.map((w) => (
            <div
              key={w}
              className="text-center text-[11px] font-medium uppercase tracking-wide text-tg-hint"
            >
              {w}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {cells.map((cell) => {
            const dayTasks = byDay.get(cell.key) ?? [];
            const hasTasks = dayTasks.length > 0;
            const isToday = cell.key === tKey;
            const isSelected = cell.key === selectedKey;
            const allDone = hasTasks && dayTasks.every((t) => t.status === "done");
            return (
              <button
                key={cell.key}
                type="button"
                onClick={() => {
                  haptic("select");
                  setSelectedKey(cell.key);
                }}
                className={
                  "ease-apple relative flex aspect-square flex-col items-center justify-center rounded-2xl text-[14px] transition-all duration-150 active:scale-90 " +
                  (isSelected
                    ? "bg-tg-button/15 font-semibold text-tg-button"
                    : cell.inMonth
                      ? "text-tg-text hover:bg-bento"
                      : "text-tg-hint/40")
                }
              >
                <span
                  className={
                    isToday && !isSelected
                      ? "flex h-6 w-6 items-center justify-center rounded-full bg-tg-button/15 text-tg-button"
                      : ""
                  }
                >
                  {cell.date.getDate()}
                </span>
                {hasTasks && (
                  <span
                    aria-hidden
                    className={
                      "absolute bottom-1 h-1.5 w-1.5 rounded-full " +
                      (allDone ? "bg-emerald-500/60" : "bg-tg-button")
                    }
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {selectedTasks.length === 0 ? (
          <p className="px-1 py-6 text-center text-[14px] text-tg-hint">
            На этот день задач нет.
          </p>
        ) : (
          selectedTasks
            .slice()
            .sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? ""))
            .map((t) => {
              const time = localTime(t.due_at, tz);
              const isDone = t.status === "done";
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onOpen(t.id)}
                  className="ease-apple flex items-center gap-3 rounded-2xl bg-bento-card p-3 text-left shadow-bento ring-1 ring-black/5 transition-all duration-150 active:scale-[0.99]"
                >
                  <span className="flex w-12 shrink-0 items-center gap-1 text-[12px] font-medium text-tg-hint">
                    <Clock size={12} strokeWidth={2} aria-hidden />
                    {time ?? "—"}
                  </span>
                  <span
                    className={
                      "min-w-0 flex-1 truncate text-[15px] " +
                      (isDone ? "text-tg-hint line-through" : "text-tg-text")
                    }
                  >
                    {t.title}
                  </span>
                </button>
              );
            })
        )}
      </div>
    </div>
  );
}
