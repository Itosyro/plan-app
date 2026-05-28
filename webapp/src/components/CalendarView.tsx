// Calendar for the Mini-App (Phase 7e/B). Three modes — Month, Week,
// Agenda — switchable via a SegmentedControl and persisted to
// CloudStorage. Tasks with a due date are fetched client-side and
// bucketed by local day in the user's tz. Event pills are tinted by a
// deterministic per-category color.
//
// DnD: month day-cells and week day-columns are droppable
// (CALDAY_PREFIX) so a dragged task reschedules onto the target day
// (App.tsx::handleDragEnd preserves local time-of-day).

import { useEffect, useMemo, useState } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import {
  CalendarDays,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Clock,
  ListTree,
} from "lucide-react";
import { apiClient } from "../api/client";
import { getCache, setCache } from "../lib/cache";
import { categoryColor, localDateKey, localTime } from "../lib/format";
import { haptic } from "../lib/telegram";
import { StorageKeys, storageGet, storageSet } from "../lib/storage";
import type { Task } from "../types";
import { SegmentedControl, type SegmentOption } from "./SegmentedControl";

export const CALDAY_PREFIX = "calday:";

type CalMode = "month" | "week" | "agenda";

const MODE_OPTIONS: SegmentOption<CalMode>[] = [
  { value: "month", label: "Месяц", icon: CalendarDays },
  { value: "week", label: "Неделя", icon: CalendarRange },
  { value: "agenda", label: "Агенда", icon: ListTree },
];

interface Props {
  tz: string;
  refreshSignal: number;
  /** Optimistic drop payload: shift one task's due_at in place. */
  optimisticReschedule?: { id: number; dueAt: string; nonce: number } | null;
  onOpen: (id: number) => void;
}

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

function todayKey(tz: string): string {
  return localDateKey(new Date().toISOString(), tz) ?? "";
}
function mondayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}
function dateKeyOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}
function startOfWeek(d: Date): Date {
  const off = mondayIndex(d);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - off);
}
function timeKey(t: Task): string {
  return t.due_at ?? "";
}

export function CalendarView({ tz, refreshSignal, optimisticReschedule, onOpen }: Props) {
  const now = useMemo(() => new Date(), []);
  const [mode, setMode] = useState<CalMode>("month");
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(now));
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>(() => todayKey(tz));

  // Hydrate persisted mode once.
  useEffect(() => {
    let cancelled = false;
    void storageGet(StorageKeys.lastCalendarView).then((v) => {
      if (!cancelled && (v === "month" || v === "week" || v === "agenda")) setMode(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Visible date window for the current view, as UTC ISO bounds for the
  // server-side `[due_at_from, due_at_to)` filter. Buffered generously so
  // every rendered cell (incl. tz offsets and adjacent-month spill) is
  // covered. `due_at_from` is inclusive, `due_at_to` exclusive.
  const { dueAtFrom, dueAtTo } = useMemo(() => {
    let start: Date;
    let end: Date;
    if (mode === "month") {
      // First of month − 7d … first of next month + 7d (covers grid spill).
      start = new Date(viewYear, viewMonth, 1 - 7);
      end = new Date(viewYear, viewMonth + 1, 1 + 7);
    } else if (mode === "week") {
      // Visible week ± 1 day buffer (week is weekStart … weekStart+6).
      start = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() - 1);
      end = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + 7 + 1);
    } else {
      // Agenda lists everything from today forward (open-ended) — use a
      // wide forward window.
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
      end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 180);
    }
    return { dueAtFrom: start.toISOString(), dueAtTo: end.toISOString() };
  }, [mode, viewYear, viewMonth, weekStart, now]);

  useEffect(() => {
    let cancelled = false;
    // Show the last-known tasks for this exact window instantly (so
    // navigating back to a visited month/week doesn't flash empty),
    // then revalidate in the background.
    const cacheKey = `cal:${dueAtFrom}:${dueAtTo}`;
    const cached = getCache<Task[]>(cacheKey);
    if (cached) setTasks(cached);
    void (async () => {
      try {
        const resp = await apiClient.tasks({
          include_done: true,
          due_at_from: dueAtFrom,
          due_at_to: dueAtTo,
        });
        const dated = resp.filter((t) => t.due_at !== null);
        setCache(cacheKey, dated);
        if (!cancelled) setTasks(dated);
      } catch (err) {
        if (!cancelled) console.error("calendar load failed", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSignal, dueAtFrom, dueAtTo]);

  // Apply an optimistic reschedule the instant App.tsx resolves a day
  // drop — the event re-buckets onto the target day with no refetch.
  // Keyed on ``nonce`` so an identical re-drop still re-fires. Cache for
  // the current window is updated so a quick re-nav doesn't flash stale.
  useEffect(() => {
    if (!optimisticReschedule) return;
    const { id, dueAt } = optimisticReschedule;
    setTasks((prev) => {
      const next = prev.map((t) => (t.id === id ? { ...t, due_at: dueAt } : t));
      setCache(`cal:${dueAtFrom}:${dueAtTo}`, next);
      return next;
    });
  }, [optimisticReschedule?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const byDay = useMemo(() => {
    const map = new Map<string, Task[]>();
    for (const t of tasks) {
      const key = localDateKey(t.due_at, tz);
      if (!key) continue;
      const arr = map.get(key);
      if (arr) arr.push(t);
      else map.set(key, [t]);
    }
    for (const arr of map.values()) arr.sort((a, b) => timeKey(a).localeCompare(timeKey(b)));
    return map;
  }, [tasks, tz]);

  const changeMode = (m: CalMode) => {
    setMode(m);
    void storageSet(StorageKeys.lastCalendarView, m);
  };

  return (
    <div className="flex flex-col gap-4">
      <SegmentedControl
        ariaLabel="Режим календаря"
        options={MODE_OPTIONS}
        value={mode}
        onChange={changeMode}
      />

      <div key={mode} className="animate-tab-in">
      {mode === "month" && (
        <MonthView
          tz={tz}
          byDay={byDay}
          viewYear={viewYear}
          viewMonth={viewMonth}
          selectedKey={selectedKey}
          onPrev={() => {
            haptic("select");
            if (viewMonth === 0) {
              setViewMonth(11);
              setViewYear((y) => y - 1);
            } else setViewMonth((m) => m - 1);
          }}
          onNext={() => {
            haptic("select");
            if (viewMonth === 11) {
              setViewMonth(0);
              setViewYear((y) => y + 1);
            } else setViewMonth((m) => m + 1);
          }}
          onSelect={(k) => {
            haptic("select");
            setSelectedKey(k);
          }}
          onOpen={onOpen}
        />
      )}

      {mode === "week" && (
        <WeekView
          tz={tz}
          byDay={byDay}
          weekStart={weekStart}
          onPrev={() => {
            haptic("select");
            setWeekStart((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() - 7));
          }}
          onNext={() => {
            haptic("select");
            setWeekStart((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7));
          }}
          onToday={() => {
            haptic("select");
            setWeekStart(startOfWeek(new Date()));
          }}
          onOpen={onOpen}
        />
      )}

      {mode === "agenda" && <AgendaView tz={tz} tasks={tasks} onOpen={onOpen} />}
      </div>
    </div>
  );
}

// ── Month ───────────────────────────────────────────────────────────

interface MonthProps {
  tz: string;
  byDay: Map<string, Task[]>;
  viewYear: number;
  viewMonth: number;
  selectedKey: string;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (key: string) => void;
  onOpen: (id: number) => void;
}

function MonthView({
  tz, byDay, viewYear, viewMonth, selectedKey, onPrev, onNext, onSelect, onOpen,
}: MonthProps) {
  const cells = useMemo(() => {
    const first = new Date(viewYear, viewMonth, 1);
    const gridStart = new Date(viewYear, viewMonth, 1 - mondayIndex(first));
    const out: { key: string; day: number; inMonth: boolean }[] = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
      out.push({ key: dateKeyOf(d), day: d.getDate(), inMonth: d.getMonth() === viewMonth });
    }
    return out;
  }, [viewYear, viewMonth]);

  const tKey = todayKey(tz);
  const selectedTasks = byDay.get(selectedKey) ?? [];

  return (
    <>
      <div className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
        <div className="mb-3 flex items-center justify-between">
          <NavButton dir="prev" onClick={onPrev} label="Предыдущий месяц" />
          <span className="font-display text-[16px] font-semibold tracking-tight text-tg-text">
            {MONTHS[viewMonth]} {viewYear}
          </span>
          <NavButton dir="next" onClick={onNext} label="Следующий месяц" />
        </div>
        <div className="mb-1 grid grid-cols-7 gap-1">
          {WEEKDAYS.map((w) => (
            <div key={w} className="text-center text-[10px] font-medium uppercase tracking-wide text-tg-hint">
              {w}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {cells.map((cell) => (
            <MonthCell
              key={cell.key}
              dateKey={cell.key}
              day={cell.day}
              inMonth={cell.inMonth}
              isToday={cell.key === tKey}
              isSelected={cell.key === selectedKey}
              tasks={byDay.get(cell.key) ?? []}
              onSelect={() => onSelect(cell.key)}
            />
          ))}
        </div>
      </div>

      <DayDetail tz={tz} dateKey={selectedKey} tasks={selectedTasks} onOpen={onOpen} />
    </>
  );
}

interface MonthCellProps {
  dateKey: string;
  day: number;
  inMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  tasks: Task[];
  onSelect: () => void;
}

function MonthCell({ dateKey, day, inMonth, isToday, isSelected, tasks, onSelect }: MonthCellProps) {
  const { isOver, setNodeRef } = useDroppable({ id: CALDAY_PREFIX + dateKey });
  const shown = tasks.slice(0, 2);
  const extra = tasks.length - shown.length;
  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={onSelect}
      className={
        "ease-apple flex min-h-[58px] flex-col items-stretch gap-0.5 rounded-xl p-1 text-left transition-all duration-150 active:scale-[0.96] " +
        (isOver
          ? "bg-tg-button/20 ring-2 ring-tg-button"
          : isSelected
            ? "bg-tg-button/10 ring-1 ring-tg-button/30"
            : inMonth
              ? "hover:bg-bento"
              : "opacity-40")
      }
    >
      <span
        className={
          "mx-auto flex h-5 w-5 items-center justify-center rounded-full text-[12px] " +
          (isToday
            ? "bg-tg-button font-semibold text-tg-button-text"
            : isSelected
              ? "font-semibold text-tg-button"
              : "text-tg-text")
        }
      >
        {day}
      </span>
      {shown.map((t) => {
        const c = categoryColor(t.category_id);
        return (
          <span
            key={t.id}
            className={
              "truncate rounded px-1 text-[9px] leading-[1.3] " +
              c.pill +
              " " +
              (t.status === "done" ? "text-tg-hint line-through" : c.text)
            }
          >
            {t.title}
          </span>
        );
      })}
      {extra > 0 && <span className="px-1 text-[9px] text-tg-hint">ещё {extra}</span>}
    </button>
  );
}

// ── Week ────────────────────────────────────────────────────────────

interface WeekProps {
  tz: string;
  byDay: Map<string, Task[]>;
  weekStart: Date;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onOpen: (id: number) => void;
}

function WeekView({ tz, byDay, weekStart, onPrev, onNext, onToday, onOpen }: WeekProps) {
  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + i);
      return { date: d, key: dateKeyOf(d) };
    });
  }, [weekStart]);
  const tKey = todayKey(tz);
  const last = days[6].date;
  const rangeLabel =
    weekStart.getMonth() === last.getMonth()
      ? `${weekStart.getDate()}–${last.getDate()} ${MONTHS[weekStart.getMonth()].toLowerCase()}`
      : `${weekStart.getDate()} ${MONTHS[weekStart.getMonth()].slice(0, 3).toLowerCase()} – ${last.getDate()} ${MONTHS[last.getMonth()].slice(0, 3).toLowerCase()}`;

  return (
    <div className="rounded-3xl bg-bento-card p-3 shadow-bento ring-1 ring-black/5">
      <div className="mb-2 flex items-center justify-between">
        <NavButton dir="prev" onClick={onPrev} label="Предыдущая неделя" />
        <button
          type="button"
          onClick={onToday}
          className="font-display rounded-full px-3 py-1 text-[15px] font-semibold tracking-tight text-tg-text transition-colors hover:bg-bento"
        >
          {rangeLabel}
        </button>
        <NavButton dir="next" onClick={onNext} label="Следующая неделя" />
      </div>
      <div className="flex flex-col gap-1.5">
        {days.map(({ date, key }) => (
          <WeekDayRow
            key={key}
            dateKey={key}
            weekday={WEEKDAYS[mondayIndex(date)]}
            day={date.getDate()}
            isToday={key === tKey}
            tz={tz}
            tasks={byDay.get(key) ?? []}
            onOpen={onOpen}
          />
        ))}
      </div>
    </div>
  );
}

interface WeekDayRowProps {
  dateKey: string;
  weekday: string;
  day: number;
  isToday: boolean;
  tz: string;
  tasks: Task[];
  onOpen: (id: number) => void;
}

function WeekDayRow({ dateKey, weekday, day, isToday, tz, tasks, onOpen }: WeekDayRowProps) {
  const { isOver, setNodeRef } = useDroppable({ id: CALDAY_PREFIX + dateKey });
  return (
    <div
      ref={setNodeRef}
      className={
        "flex gap-2 rounded-2xl p-1.5 transition-colors duration-150 " +
        (isOver ? "bg-tg-button/15 ring-1 ring-tg-button/40" : "")
      }
    >
      <div className="flex w-10 shrink-0 flex-col items-center pt-0.5">
        <span className="text-[10px] uppercase text-tg-hint">{weekday}</span>
        <span
          className={
            "flex h-7 w-7 items-center justify-center rounded-full text-[14px] font-semibold " +
            (isToday ? "bg-tg-button text-tg-button-text" : "text-tg-text")
          }
        >
          {day}
        </span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1 py-0.5">
        {tasks.length === 0 ? (
          <span className="py-1.5 text-[12px] text-tg-hint/50">—</span>
        ) : (
          tasks.map((t) => (
            <WeekEvent key={t.id} task={t} time={localTime(t.due_at, tz)} onOpen={onOpen} />
          ))
        )}
      </div>
    </div>
  );
}

function WeekEvent({ task, time, onOpen }: { task: Task; time: string | null; onOpen: (id: number) => void }) {
  const isDone = task.status === "done";
  const c = categoryColor(task.category_id);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    data: { kind: "caltask", dueAt: task.due_at },
    disabled: isDone,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50, touchAction: "none" as const }
    : { touchAction: "none" as const };
  return (
    <button
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      type="button"
      onClick={() => onOpen(task.id)}
      className={
        "ease-apple flex items-center gap-2 rounded-lg px-2 py-1.5 text-left ring-1 ring-black/[0.04] transition-shadow " +
        c.pill +
        " " +
        (isDragging ? "shadow-bento-lg" : "")
      }
    >
      <span aria-hidden className={"h-3 w-1 shrink-0 rounded-full " + c.dot} />
      {time && <span className="shrink-0 text-[11px] font-medium text-tg-hint tabular">{time}</span>}
      <span
        className={
          "min-w-0 flex-1 truncate text-[13px] " +
          (isDone ? "text-tg-hint line-through" : "text-tg-text")
        }
      >
        {task.title}
      </span>
    </button>
  );
}

// ── Agenda ──────────────────────────────────────────────────────────

function AgendaView({ tz, tasks, onOpen }: { tz: string; tasks: Task[]; onOpen: (id: number) => void }) {
  const tKey = todayKey(tz);
  // Upcoming (today onward), grouped by day, chronological.
  const groups = useMemo(() => {
    const upcoming = tasks
      .filter((t) => (localDateKey(t.due_at, tz) ?? "") >= tKey)
      .sort((a, b) => timeKey(a).localeCompare(timeKey(b)));
    const map = new Map<string, Task[]>();
    for (const t of upcoming) {
      const key = localDateKey(t.due_at, tz) ?? "—";
      const arr = map.get(key);
      if (arr) arr.push(t);
      else map.set(key, [t]);
    }
    return [...map.entries()];
  }, [tasks, tz, tKey]);

  if (groups.length === 0) {
    return (
      <p className="px-1 py-10 text-center text-[14px] text-tg-hint">
        Нет запланированных задач впереди.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {groups.map(([key, items]) => (
        <section key={key}>
          <header className="mb-2 px-1 text-[13px] font-semibold tracking-tight text-tg-link">
            {agendaHeading(key, tz, tKey)}
          </header>
          <div className="overflow-hidden rounded-3xl bg-bento-card shadow-bento ring-1 ring-black/5">
            <div className="divide-y divide-tg-divider/40">
              {items.map((t) => {
                const c = categoryColor(t.category_id);
                const isDone = t.status === "done";
                const time = localTime(t.due_at, tz);
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => onOpen(t.id)}
                    className="ease-apple flex min-h-[52px] w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-bento/60 active:bg-bento"
                  >
                    <span aria-hidden className={"h-8 w-1 shrink-0 rounded-full " + c.dot} />
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
              })}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}

function agendaHeading(key: string, tz: string, todayK: string): string {
  if (key === todayK) return "Сегодня";
  const yKey = localDateKey(new Date(Date.now() + 86_400_000).toISOString(), tz);
  if (key === yKey) return "Завтра";
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

// ── Shared ──────────────────────────────────────────────────────────

function NavButton({ dir, onClick, label }: { dir: "prev" | "next"; onClick: () => void; label: string }) {
  const Icon = dir === "prev" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="ease-apple flex h-9 w-9 items-center justify-center rounded-full text-tg-hint transition-all duration-150 hover:bg-bento active:scale-90"
    >
      <Icon size={20} strokeWidth={2.25} aria-hidden />
    </button>
  );
}

interface DayDetailProps {
  tz: string;
  dateKey: string;
  tasks: Task[];
  onOpen: (id: number) => void;
}

function DayDetail({ tz, tasks, onOpen }: DayDetailProps) {
  if (tasks.length === 0) {
    return <p className="px-1 py-6 text-center text-[14px] text-tg-hint">На этот день задач нет.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {tasks.map((t) => (
        <DraggableTaskRow key={t.id} task={t} time={localTime(t.due_at, tz)} onOpen={onOpen} />
      ))}
    </div>
  );
}

interface DraggableTaskRowProps {
  task: Task;
  time: string | null;
  onOpen: (id: number) => void;
}

function DraggableTaskRow({ task, time, onOpen }: DraggableTaskRowProps) {
  const isDone = task.status === "done";
  const c = categoryColor(task.category_id);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    data: { kind: "caltask", dueAt: task.due_at },
    disabled: isDone,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50, touchAction: "none" as const }
    : { touchAction: "none" as const };
  return (
    <button
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      type="button"
      onClick={() => onOpen(task.id)}
      className={
        "ease-apple flex items-center gap-3 rounded-2xl bg-bento-card p-3 text-left ring-1 ring-black/5 transition-all duration-150 active:scale-[0.99] " +
        (isDragging ? "shadow-bento-lg" : "shadow-bento")
      }
    >
      <span aria-hidden className={"h-8 w-1 shrink-0 rounded-full " + c.dot} />
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
