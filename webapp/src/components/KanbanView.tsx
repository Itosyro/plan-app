// Kanban board for the Mini-App (Phase 7e/A). Columns are the user's
// **categories** (+ a synthetic "Без категории" column), Todoist-style
// "разделы". Dragging a card between columns re-assigns its
// ``category_id`` (drop into "Без категории" clears it). A trailing
// "+ Раздел" affordance creates a new category = new column.
//
// DnD reliability (the 7d board was broken):
//   - Cards set ``touch-action: none`` so the horizontal scroll
//     container doesn't steal the touch gesture before dnd-kit sees it.
//   - The dragged card is rendered in a portal ``<DragOverlay>`` (in
//     App.tsx) instead of being CSS-transformed in place, so the
//     source column no longer always wins ``over`` resolution.
//   - App.tsx uses ``closestCorners`` collision detection.
//
// The board fetches its own task set (all open tasks) and reloads on
// ``refreshSignal`` so a drag / complete keeps every column in sync.

import { useCallback, useMemo, useState } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { Check, Plus, X } from "lucide-react";
import { apiClient } from "../api/client";
import { mutateCache } from "../lib/cache";
import { useCachedResource } from "../lib/useCachedResource";
import { haptic } from "../lib/telegram";
import type { Category, Task } from "../types";

// Drop-target id scheme for kanban columns. Distinct prefix so it never
// collides with horizon-slug pills (list view) or calendar-day targets.
export const KCAT_PREFIX = "kcat:";
export const KCAT_NONE = `${KCAT_PREFIX}none`;
export const kcatId = (categoryId: number | null) =>
  categoryId === null ? KCAT_NONE : `${KCAT_PREFIX}${categoryId}`;

export const KANBAN_CACHE_KEY = "kanban-tasks";

interface Props {
  categories: Category[];
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
  onCreateCategory: (name: string) => Promise<void> | void;
}

export function KanbanView({
  categories,
  onOpen,
  onDone,
  onCreateCategory,
}: Props) {
  // Single shared cache for the board's task set. App.tsx owns the
  // optimistic drop (writes via ``mutateCache``) and the failure-path
  // invalidate; this component just reads what's there.
  const { data } = useCachedResource<Task[]>(
    KANBAN_CACHE_KEY,
    () => apiClient.tasks({ limit: 500 }),
    [],
  );
  const tasks = data ?? [];

  // Checkbox done: App's handler only patches the LIST cache — mark
  // the card done in the board cache too so it strikes through
  // instantly. Server truth arrives via the KANBAN_CACHE_KEY
  // invalidate App fires on both success and failure.
  const handleDone = useCallback(
    async (id: number) => {
      mutateCache<Task[]>(KANBAN_CACHE_KEY, (prev) =>
        (prev ?? []).map((t) =>
          t.id === id
            ? { ...t, status: "done", completed_at: new Date().toISOString() }
            : t,
        ),
      );
      await onDone(id);
    },
    [onDone],
  );

  // Group open tasks by category. Columns follow the categories prop
  // order; uncategorized tasks land in the trailing "Без категории".
  const byCategory = useMemo(() => {
    const m = new Map<number | null, Task[]>();
    m.set(null, []);
    for (const c of categories) m.set(c.id, []);
    for (const t of tasks) {
      const key = t.category_id;
      const arr = m.get(key);
      if (arr) arr.push(t);
      else m.set(key, [t]);
    }
    return m;
  }, [tasks, categories]);

  return (
    <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2">
      {categories.map((c) => (
        <KanbanColumn
          key={c.id}
          categoryId={c.id}
          label={c.name}
          tasks={byCategory.get(c.id) ?? []}
          onOpen={onOpen}
          onDone={handleDone}
        />
      ))}
      <KanbanColumn
        key="none"
        categoryId={null}
        label="Без категории"
        tasks={byCategory.get(null) ?? []}
        onOpen={onOpen}
        onDone={handleDone}
      />
      <AddColumn onCreate={onCreateCategory} />
    </div>
  );
}

interface ColumnProps {
  categoryId: number | null;
  label: string;
  tasks: Task[];
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
}

function KanbanColumn({ categoryId, label, tasks, onOpen, onDone }: ColumnProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: kcatId(categoryId),
    data: { kind: "kanban-col", categoryId },
  });
  // The column is a white panel on the tinted page (cards inside are
  // tinted tiles) — a clear three-level depth so neighbouring columns
  // never blend (the old all-grey columns merged with the page).
  return (
    <div
      ref={setNodeRef}
      className={
        "flex w-[80vw] max-w-[290px] shrink-0 snap-start flex-col rounded-3xl bg-bento-card p-2.5 shadow-bento ring-1 transition-colors duration-150 " +
        (isOver ? "ring-2 ring-tg-button/50" : "ring-black/[0.06]")
      }
    >
      <div className="mb-1 flex items-center justify-between border-b border-tg-divider/50 px-1.5 pb-2 pt-0.5">
        <span className="font-display truncate text-[14px] font-semibold tracking-tight text-tg-text">
          {label}
        </span>
        <span className="ml-2 shrink-0 rounded-full bg-bento px-2 py-0.5 text-[11px] font-semibold text-tg-hint tabular">
          {tasks.length}
        </span>
      </div>
      <div className="flex flex-col gap-2 pt-1">
        {tasks.length === 0 ? (
          <p className="px-2 py-6 text-center text-[12px] text-tg-hint/60">Пусто</p>
        ) : (
          tasks.map((t) => (
            <DraggableCard
              key={t.id}
              task={t}
              categoryId={categoryId}
              onOpen={onOpen}
              onDone={onDone}
            />
          ))
        )}
      </div>
    </div>
  );
}

interface DraggableCardProps {
  task: Task;
  categoryId: number | null;
  onOpen: (id: number) => void;
  onDone: (id: number) => Promise<void> | void;
}

function DraggableCard({ task, categoryId, onOpen, onDone }: DraggableCardProps) {
  const isDone = task.status === "done";
  // Carry the full task + current category so App.tsx can render the
  // DragOverlay snapshot and detect no-op drops.
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.id,
    data: { kind: "kanban", categoryId, task },
    disabled: isDone,
  });
  return (
    <div
      ref={setNodeRef}
      // touch-action:none keeps the horizontal scroll container from
      // hijacking the touch gesture so dnd-kit gets the pointermove.
      style={{ touchAction: "none" }}
      {...attributes}
      {...listeners}
      // The real card stays put (no transform) — the DragOverlay carries
      // the moving visual. While dragging we just dim the placeholder.
      className={isDragging ? "opacity-40" : ""}
    >
      <KanbanCardView task={task} onOpen={onOpen} onDone={onDone} />
    </div>
  );
}

interface CardViewProps {
  task: Task;
  onOpen?: (id: number) => void;
  onDone?: (id: number) => Promise<void> | void;
  /** Rendered inside the DragOverlay — lift + slight tilt, no handlers. */
  overlay?: boolean;
}

// Pure card visual, shared between the in-column draggable and the
// DragOverlay snapshot.
export function KanbanCardView({ task, onOpen, onDone, overlay = false }: CardViewProps) {
  const isDone = task.status === "done";
  // Busy-guard (same as TaskCard): a second tap while the PATCH is in
  // flight would fire a duplicate mutation.
  const [busy, setBusy] = useState(false);
  // Tinted tile inside the white column. The drag overlay snapshot pops
  // to a solid white lifted card for clear "picked up" feedback.
  return (
    <div
      className={
        "ease-apple rounded-2xl p-3 ring-1 transition-shadow duration-150 " +
        (overlay
          ? "bg-bento-card shadow-bento-lg ring-black/5 rotate-[1.5deg] scale-[1.03]"
          : "bg-bento ring-black/[0.05]")
      }
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          aria-label={isDone ? "Готово" : "Отметить выполненной"}
          disabled={isDone || overlay || busy}
          onClick={(e) => {
            e.stopPropagation();
            if (busy || onDone === undefined) return;
            haptic("success");
            setBusy(true);
            void Promise.resolve(onDone(task.id)).finally(() => setBusy(false));
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
          onClick={() => onOpen?.(task.id)}
          disabled={overlay}
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

function AddColumn({ onCreate }: { onCreate: (name: string) => Promise<void> | void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const trimmed = name.trim();
    if (trimmed === "" || busy) return;
    setBusy(true);
    try {
      await onCreate(trimmed);
      setName("");
      setEditing(false);
      haptic("success");
    } catch (err) {
      console.error("create category failed", err);
    } finally {
      setBusy(false);
    }
  };

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="ease-apple flex h-[52px] w-[62vw] max-w-[210px] shrink-0 snap-start items-center gap-2 rounded-3xl border-2 border-dashed border-tg-hint/25 bg-bento-card/40 px-4 text-[14px] font-medium text-tg-hint transition-all duration-200 hover:border-tg-button/40 hover:text-tg-text active:scale-[0.98]"
      >
        <Plus size={18} strokeWidth={2.4} aria-hidden />
        Добавить раздел
      </button>
    );
  }

  return (
    <div className="flex w-[80vw] max-w-[290px] shrink-0 snap-start flex-col gap-2 rounded-3xl bg-bento-card p-2.5 shadow-bento ring-1 ring-black/[0.06]">
      <div className="flex items-center gap-1.5">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submit();
            if (e.key === "Escape") {
              setEditing(false);
              setName("");
            }
          }}
          placeholder="Название раздела"
          maxLength={64}
          className="font-display min-w-0 flex-1 rounded-xl bg-bento-card px-3 py-2 text-[14px] text-tg-text shadow-bento ring-1 ring-black/5 outline-none placeholder:text-tg-hint/60"
        />
        <button
          type="button"
          aria-label="Отмена"
          onClick={() => {
            setEditing(false);
            setName("");
          }}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-tg-hint transition-colors hover:bg-bento-card"
        >
          <X size={18} strokeWidth={2.25} aria-hidden />
        </button>
      </div>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={name.trim() === "" || busy}
        className="ease-apple rounded-xl bg-tg-button py-2 text-[13px] font-semibold text-tg-button-text transition-all duration-200 active:scale-[0.98] disabled:opacity-40"
      >
        Добавить
      </button>
    </div>
  );
}
