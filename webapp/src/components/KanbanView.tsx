// Kanban board for the Mini-App (Phase 7d). Shows open tasks as
// columns, one per horizon, with cards draggable between columns to
// re-assign the horizon. Reuses the App-level DndContext: a column is
// a droppable whose id is the horizon slug, so dropping a card fires
// the same ``handleMove`` the horizon pills use.
//
// The board fetches its own task set (all open tasks, grouped client
// side) and reloads on ``refreshSignal`` so a drag / complete keeps
// every column in sync.

import { useEffect, useMemo, useState } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { Check } from "lucide-react";
import { apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import type { Horizon, HorizonSlug, Task } from "../types";

interface Props {
  horizons: Horizon[];
  refreshSignal: number;
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
}

// Column order matches the horizon vocabulary (nearest first).
const COLUMN_ORDER: HorizonSlug[] = [
  "today",
  "tomorrow",
  "week",
  "month",
  "year",
  "someday",
];

export function KanbanView({ horizons, refreshSignal, onOpen, onDone }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await apiClient.tasks({ limit: 500 });
        if (!cancelled) setTasks(resp);
      } catch (err) {
        if (!cancelled) console.error("kanban load failed", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  const labelBySlug = useMemo(() => {
    const m = new Map<string, string>();
    for (const h of horizons) m.set(h.slug, h.label);
    return m;
  }, [horizons]);

  const byHorizon = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const slug of COLUMN_ORDER) m.set(slug, []);
    for (const t of tasks) {
      const slug = t.horizon_slug ?? "someday";
      const arr = m.get(slug);
      if (arr) arr.push(t);
      else m.set(slug, [t]);
    }
    return m;
  }, [tasks]);

  return (
    <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2">
      {COLUMN_ORDER.map((slug) => (
        <KanbanColumn
          key={slug}
          slug={slug}
          label={labelBySlug.get(slug) ?? slug}
          tasks={byHorizon.get(slug) ?? []}
          onOpen={onOpen}
          onDone={onDone}
        />
      ))}
    </div>
  );
}

interface ColumnProps {
  slug: HorizonSlug;
  label: string;
  tasks: Task[];
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
}

function KanbanColumn({ slug, label, tasks, onOpen, onDone }: ColumnProps) {
  const { isOver, setNodeRef } = useDroppable({ id: slug });
  return (
    <div
      ref={setNodeRef}
      className={
        "flex w-[78vw] max-w-[280px] shrink-0 flex-col rounded-3xl p-2 transition-colors duration-150 " +
        (isOver ? "bg-tg-button/10 ring-2 ring-tg-button/40" : "bg-bento")
      }
    >
      <div className="flex items-center justify-between px-2 py-1.5">
        <span className="font-display text-[14px] font-semibold tracking-tight text-tg-text">
          {label}
        </span>
        <span className="rounded-full bg-bento-card px-2 py-0.5 text-[11px] font-medium text-tg-hint">
          {tasks.length}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        {tasks.length === 0 ? (
          <p className="px-2 py-4 text-center text-[12px] text-tg-hint/70">Пусто</p>
        ) : (
          tasks.map((t) => (
            <KanbanCard key={t.id} task={t} slug={slug} onOpen={onOpen} onDone={onDone} />
          ))
        )}
      </div>
    </div>
  );
}

interface CardProps {
  task: Task;
  slug: HorizonSlug;
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
}

function KanbanCard({ task, slug, onOpen, onDone }: CardProps) {
  const isDone = task.status === "done";
  // Carry the current horizon so App.tsx::handleDragEnd can skip a
  // no-op drop without needing the task in its own list state.
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    data: { kind: "kanban", horizonSlug: slug },
    disabled: isDone,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0) scale(1.03)`, zIndex: 50 }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={
        "ease-apple touch-manipulation rounded-2xl bg-bento-card p-3 ring-1 ring-black/5 transition-all duration-150 " +
        (isDragging ? "shadow-bento-lg" : "shadow-bento")
      }
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          aria-label={isDone ? "Готово" : "Отметить выполненной"}
          disabled={isDone}
          onClick={(e) => {
            e.stopPropagation();
            haptic("success");
            void onDone(task.id);
          }}
          className={
            "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-[1.5px] transition-all duration-200 " +
            (isDone
              ? "border-emerald-500 bg-emerald-500 text-white"
              : "border-tg-hint/40 bg-bento-card active:scale-90")
          }
        >
          {isDone && <Check size={12} strokeWidth={3} />}
        </button>
        <button
          type="button"
          onClick={() => onOpen(task.id)}
          className="min-w-0 flex-1 text-left"
        >
          <span
            className={
              "block break-words text-[14px] leading-snug " +
              (isDone ? "text-tg-hint line-through" : "text-tg-text")
            }
          >
            {task.title}
          </span>
          {task.subtasks_total > 0 && (
            <span className="mt-1 inline-block text-[11px] text-tg-hint">
              {task.subtasks_done}/{task.subtasks_total}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
