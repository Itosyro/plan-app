// Month-grid calendar for the Mini-App (Phase 7d). Shows tasks that
// have a due date, bucketed into day cells in the user's timezone.
// Tapping a day reveals that day's tasks below the grid; tapping a
// task opens the detail screen (same route as the list).
//
// Tasks are fetched client-side (the personal task volume is small)
// and re-bucketed whenever the visible month changes or the parent
// bumps ``refreshSignal`` after a mutation.

import { useEffect, useMemo, useState } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { apiClient } from "../api/client";
import { localDateKey, localTime } from "../lib/format";
import { haptic } from "../lib/telegram";
import type { Task } from "../types";

// Droppable id prefix for a calendar day cell. App.tsx::handleDragEnd
// recognises this to reschedule a dragged task onto the target day.
export const CALDAY_PREFIX = "calday:";

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
            return (
              <DayCell
                key={cell.key}
                dateKey={cell.key}
                dayNumber={cell.date.getDate()}
                inMonth={cell.inMonth}
                isToday={cell.key === tKey}
                isSelected={cell.key === selectedKey}
                hasTasks={dayTasks.length > 0}
                allDone={dayTasks.length > 0 && dayTasks.every((t) => t.status === "done")}
                onSelect={() => {
                  haptic("select");
                  setSelectedKey(cell.key);
                }}
              />
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
            .map((t) => (
              <DraggableTaskRow
                key={t.id}
                task={t}
                time={localTime(t.due_at, tz)}
                onOpen={onOpen}
              />
            ))
        )}
      </div>
    </div>
  );
}

interface DayCellProps {
  dateKey: string;
  dayNumber: number;
  inMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  hasTasks: boolean;
  allDone: boolean;
  onSelect: () => void;
}

function DayCell({
  dateKey,
  dayNumber,
  inMonth,
  isToday,
  isSelected,
  hasTasks,
  allDone,
  onSelect,
}: DayCellProps) {
  const { isOver, setNodeRef } = useDroppable({ id: CALDAY_PREFIX + dateKey });
  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={onSelect}
      className={
        "ease-apple relative flex aspect-square flex-col items-center justify-center rounded-2xl text-[14px] transition-all duration-150 active:scale-90 " +
        (isOver
          ? "bg-tg-button/25 ring-2 ring-tg-button"
          : isSelected
            ? "bg-tg-button/15 font-semibold text-tg-button"
            : inMonth
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
        {dayNumber}
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
}

interface DraggableTaskRowProps {
  task: Task;
  time: string | null;
  onOpen: (id: number) => void;
}

function DraggableTaskRow({ task, time, onOpen }: DraggableTaskRowProps) {
  const isDone = task.status === "done";
  // Attach the current ``due_at`` so App.tsx::handleDragEnd can shift it
  // to the drop-target day while preserving the local time-of-day.
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    data: { kind: "caltask", dueAt: task.due_at },
    disabled: isDone,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;
  return (
    <button
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      type="button"
      onClick={() => onOpen(task.id)}
      className={
        "ease-apple flex touch-manipulation items-center gap-3 rounded-2xl bg-bento-card p-3 text-left ring-1 ring-black/5 transition-all duration-150 active:scale-[0.99] " +
        (isDragging ? "shadow-bento-lg" : "shadow-bento")
      }
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
        {task.title}
      </span>
    </button>
  );
}
