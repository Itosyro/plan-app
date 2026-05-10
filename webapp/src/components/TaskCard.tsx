import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { Check, Clock, Flag, Move, Tag, Trash2 } from "lucide-react";
import type { HorizonSlug, Task } from "../types";
import { formatDue } from "../lib/format";
import { haptic } from "../lib/telegram";
import { IconTile, type TileTone } from "./IconTile";

const HORIZON_OPTIONS: { slug: HorizonSlug; label: string }[] = [
  { slug: "today", label: "Сегодня" },
  { slug: "tomorrow", label: "Завтра" },
  { slug: "week", label: "На неделе" },
  { slug: "month", label: "В месяце" },
  { slug: "year", label: "В году" },
  { slug: "someday", label: "Когда-нибудь" },
];

// Only ``high`` and ``low`` show a priority chip; ``medium`` is the
// default tone and would just be visual noise on every card. Tones
// chosen to match the Mira reference: warm red for urgent, calm
// green for low-priority.
const PRIORITY_TONE: Record<"high" | "low", TileTone> = {
  high: "rose",
  low: "emerald",
};

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
  const priorityTone =
    task.priority === "high" || task.priority === "low"
      ? PRIORITY_TONE[task.priority]
      : null;

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
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0) scale(1.02)`,
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
        "ease-apple touch-manipulation rounded-3xl bg-bento-card p-4 ring-1 ring-black/5 transition-all duration-200 " +
        (isDone ? "opacity-50 " : "opacity-100 ") +
        (isDragging ? "shadow-bento-lg" : "shadow-bento")
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
            "ease-spring mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-[1.5px] transition-all duration-300 " +
            (isDone
              ? "scale-100 border-emerald-500 bg-emerald-500 text-white"
              : "scale-100 border-tg-hint/40 bg-bento-card hover:border-emerald-400 active:scale-90")
          }
        >
          {isDone && <Check size={14} strokeWidth={3} />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            {priorityTone && (
              <IconTile
                icon={Flag}
                tone={priorityTone}
                size="sm"
                label={
                  task.priority === "high"
                    ? "Высокий приоритет"
                    : "Низкий приоритет"
                }
              />
            )}
            <div
              className={
                "font-display min-w-0 break-words pt-0.5 text-[16px] font-medium leading-snug tracking-tight " +
                (isDone ? "text-tg-hint line-through" : "text-tg-text")
              }
            >
              {task.title}
            </div>
          </div>
          {(due || task.category_name) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-tg-hint">
              {due && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bento px-2 py-0.5">
                  <Clock size={12} strokeWidth={2} aria-hidden />
                  {due}
                </span>
              )}
              {task.category_name && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bento px-2 py-0.5 text-[11px] text-tg-text/70">
                  <Tag size={11} strokeWidth={2} aria-hidden />
                  {task.category_name}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      {!isDone && (
        <div className="ease-apple mt-3 flex items-center gap-1.5 transition-all duration-200">
          <button
            type="button"
            disabled={busy}
            aria-label="Перенести в другой горизонт"
            aria-expanded={moveOpen}
            onClick={() => {
              haptic("select");
              setMoveOpen((v) => !v);
            }}
            className={
              "ease-apple inline-flex items-center gap-1.5 rounded-2xl bg-bento px-2.5 py-1.5 text-[12px] font-medium text-tg-text/80 transition-all duration-200 active:scale-[0.96] " +
              (moveOpen ? "ring-1 ring-tg-button/40 text-tg-button" : "")
            }
          >
            <Move size={13} strokeWidth={2.25} aria-hidden />
            Перенести
          </button>
          <button
            type="button"
            disabled={busy}
            aria-label="Удалить задачу"
            onClick={() =>
              wrap(async () => {
                haptic("warn");
                await onDelete(task.id);
              })
            }
            className="ease-apple ml-auto inline-flex items-center gap-1.5 rounded-2xl bg-bento px-2.5 py-1.5 text-[12px] font-medium text-rose-600 transition-all duration-200 hover:bg-rose-50 active:scale-[0.96]"
          >
            <Trash2 size={13} strokeWidth={2.25} aria-hidden />
            Удалить
          </button>
        </div>
      )}
      {moveOpen && !isDone && (
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {HORIZON_OPTIONS.map((h) => {
            const isCurrent = h.slug === task.horizon_slug;
            return (
              <button
                key={h.slug}
                type="button"
                disabled={busy || isCurrent}
                onClick={() =>
                  wrap(async () => {
                    haptic("select");
                    await onMove(task.id, h.slug);
                    setMoveOpen(false);
                  })
                }
                className={
                  "ease-apple rounded-xl px-2 py-1.5 text-[12px] font-medium transition-all duration-200 active:scale-[0.96] " +
                  (isCurrent
                    ? "bg-tg-button/10 text-tg-button"
                    : "bg-bento text-tg-text hover:bg-bento/60")
                }
              >
                {h.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

