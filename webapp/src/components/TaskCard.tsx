import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { Check, Clock, Flag, Move, Trash2 } from "lucide-react";
import type { HorizonSlug, Task } from "../types";
import { formatDue } from "../lib/format";
import { priorityFlagColor } from "../lib/icons";
import { haptic } from "../lib/telegram";

const HORIZON_OPTIONS: { slug: HorizonSlug; label: string }[] = [
  { slug: "today", label: "Сегодня" },
  { slug: "tomorrow", label: "Завтра" },
  { slug: "week", label: "На неделе" },
  { slug: "month", label: "В месяце" },
  { slug: "year", label: "В году" },
  { slug: "someday", label: "Когда-нибудь" },
];

interface Props {
  task: Task;
  tz: string;
  onDone: (id: number) => Promise<void> | void;
  onMove: (id: number, slug: HorizonSlug) => Promise<void> | void;
  onDelete: (id: number) => Promise<void> | void;
}

export function TaskCard({ task, tz, onDone, onMove, onDelete }: Props) {
  const [busy, setBusy] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const due = formatDue(task.due_at, tz);
  const isDone = task.status === "done";
  const showFlag = task.priority === "high" || task.priority === "low";

  // Phase 5.4b: drag-n-drop. The whole card is draggable; activation
  // is delayed (PointerSensor in App.tsx) so a quick tap on the
  // checkbox / move / delete buttons inside still fires onClick.
  // Long-press → card lifts → user drags up to a horizon pill which
  // is registered as a drop target in HorizonTabs.
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    disabled: isDone,
  });

  const dragStyle = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  const wrap = async (fn: () => Promise<void> | void) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={dragStyle}
      {...attributes}
      {...listeners}
      className={
        "rounded-2xl bg-tg-secondary/60 p-3.5 transition-all touch-manipulation " +
        (isDone ? "opacity-50 " : "opacity-100 ") +
        (isDragging
          ? "shadow-xl ring-2 ring-tg-button/40 bg-tg-bg "
          : "active:bg-tg-secondary ")
      }
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          aria-label={isDone ? "Готово" : "Отметить выполненной"}
          disabled={busy || isDone}
          onClick={() =>
            wrap(async () => {
              haptic("success");
              await onDone(task.id);
            })
          }
          className={
            "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-[1.5px] transition-colors " +
            (isDone
              ? "border-tg-button bg-tg-button text-tg-button-text"
              : "border-tg-hint/60 hover:border-tg-button hover:bg-tg-button/5")
          }
        >
          {isDone && <Check size={14} strokeWidth={3} />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            {showFlag && (
              <Flag
                size={15}
                strokeWidth={2}
                aria-hidden
                className={"mt-1 shrink-0 " + priorityFlagColor(task.priority)}
              />
            )}
            <div
              className={
                "min-w-0 break-words text-[15px] leading-snug " +
                (isDone ? "text-tg-hint line-through" : "text-tg-text")
              }
            >
              {task.title}
            </div>
          </div>
          {(due || task.category_name) && (
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-tg-hint">
              {due && (
                <span className="inline-flex items-center gap-1">
                  <Clock size={13} strokeWidth={2} aria-hidden />
                  {due}
                </span>
              )}
              {task.category_name && (
                <span className="rounded-full bg-tg-bg px-2 py-0.5 text-[11px] text-tg-text/70">
                  {task.category_name}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      {!isDone && (
        <div className="mt-3 flex items-center gap-1 border-t border-tg-divider/50 pt-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => setMoveOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-tg-link hover:bg-tg-bg"
          >
            <Move size={13} strokeWidth={2} aria-hidden />
            Перенести
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                haptic("warn");
                await onDelete(task.id);
              })
            }
            className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-tg-destructive hover:bg-tg-bg"
          >
            <Trash2 size={13} strokeWidth={2} aria-hidden />
            Удалить
          </button>
        </div>
      )}
      {moveOpen && !isDone && (
        <div className="mt-2 grid grid-cols-3 gap-1">
          {HORIZON_OPTIONS.map((h) => (
            <button
              key={h.slug}
              type="button"
              disabled={busy || h.slug === task.horizon_slug}
              onClick={() =>
                wrap(async () => {
                  haptic("select");
                  await onMove(task.id, h.slug);
                  setMoveOpen(false);
                })
              }
              className={
                "rounded-md px-2 py-1.5 text-xs " +
                (h.slug === task.horizon_slug
                  ? "bg-tg-button/20 text-tg-button"
                  : "bg-tg-bg text-tg-text hover:bg-tg-bg/70")
              }
            >
              {h.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
