// Full-screen task detail. Reached by tapping a TaskCard title.
// Replaces the inline "Перенести / Удалить" buttons that used to
// live on each card, matching the MENO/Bento detail-page model.
//
// Layout (top-to-bottom):
//   • Sticky header with «‹ Назад», page title, large action chip
//   • Editable title (autosizes, blur-to-save)
//   • Description textarea (blur-to-save)
//   • Tappable rows for: горизонт, дата, категория, приоритет
//   • Destructive «Удалить задачу» button at the bottom, glued to
//     ``--safe-bottom`` so it never overlaps the home indicator.
//
// Saving model: each field commits on blur (text inputs) or on
// pick (sheet selectors). Errors are shown inline at the top so
// the user knows what failed without a modal. Optimistic UI is
// not used here — these edits are infrequent.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Flag,
  Inbox,
  Tag,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { formatDue } from "../lib/format";
import { haptic } from "../lib/telegram";
import type {
  Category,
  Horizon,
  HorizonSlug,
  Task,
  TaskPriority,
  TaskUpdate,
} from "../types";
import { BottomSheetDate } from "./BottomSheetDate";
import { BottomSheetSelect } from "./BottomSheetSelect";
import { IconTile, type TileTone } from "./IconTile";

interface Props {
  taskId: number;
  tz: string;
  horizons: Horizon[];
  categories: Category[];
  onClose: () => void;
  /**
   * Called after a successful mutation (patch or delete). The parent
   * uses this to refresh the task list and counts without us
   * needing to hold the list state ourselves.
   */
  onMutated: () => void;
  /** Called after a successful delete so the parent can navigate away. */
  onDeleted: () => void;
}

const HORIZON_TONE: Record<HorizonSlug, TileTone> = {
  today: "orange",
  tomorrow: "amber",
  week: "violet",
  month: "indigo",
  year: "blue",
  someday: "slate",
};

const PRIORITY_OPTIONS: { value: TaskPriority; label: string; hint?: string }[] = [
  { value: "high", label: "Высокий", hint: "Срочно, важно" },
  { value: "medium", label: "Средний", hint: "По умолчанию" },
  { value: "low", label: "Низкий", hint: "Когда будет время" },
];

const PRIORITY_LABEL: Record<TaskPriority, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

const PRIORITY_TONE: Record<TaskPriority, TileTone> = {
  high: "rose",
  medium: "amber",
  low: "emerald",
};

export function TaskDetail({
  taskId,
  tz,
  horizons,
  categories,
  onClose,
  onMutated,
  onDeleted,
}: Props) {
  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [descDraft, setDescDraft] = useState("");
  const [showHorizonSheet, setShowHorizonSheet] = useState(false);
  const [showCategorySheet, setShowCategorySheet] = useState(false);
  const [showDateSheet, setShowDateSheet] = useState(false);
  const [showPrioritySheet, setShowPrioritySheet] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const fresh = await apiClient.task(taskId);
      setTask(fresh);
      setTitleDraft(fresh.title);
      setDescDraft(fresh.description ?? "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadError("Задача не найдена. Возможно, её уже удалили.");
      } else {
        setLoadError("Не удалось загрузить задачу. Проверь связь.");
      }
    }
  }, [taskId]);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = useCallback(
    async (field: string, body: TaskUpdate): Promise<void> => {
      if (task === null) return;
      setPending(field);
      setSaveError(null);
      try {
        const fresh = await apiClient.patchTask(task.id, body);
        setTask(fresh);
        haptic("success");
        onMutated();
      } catch (err) {
        haptic("error");
        if (err instanceof ApiError) {
          setSaveError(
            err.status === 422 ? "Не получилось — проверь значение" : "Не удалось сохранить",
          );
        } else {
          setSaveError("Нет связи с сервером");
        }
      } finally {
        setPending(null);
      }
    },
    [task, onMutated],
  );

  const remove = useCallback(async () => {
    if (task === null) return;
    setPending("delete");
    setSaveError(null);
    try {
      await apiClient.deleteTask(task.id);
      haptic("success");
      onMutated();
      onDeleted();
    } catch (err) {
      haptic("error");
      if (err instanceof ApiError && err.status === 404) {
        // Already gone — treat as success.
        onMutated();
        onDeleted();
        return;
      }
      setSaveError("Не удалось удалить");
    } finally {
      setPending(null);
    }
  }, [task, onMutated, onDeleted]);

  const categoryLabel = useMemo(() => {
    if (task === null || task.category_id === null) return "Не выбрана";
    const hit = categories.find((c) => c.id === task.category_id);
    return hit ? hit.name : task.category_name ?? "—";
  }, [task, categories]);

  const horizonLabel = useMemo(() => {
    if (task === null || task.horizon_slug === null) return "Не выбран";
    const hit = horizons.find((h) => h.slug === task.horizon_slug);
    return hit ? hit.label : task.horizon_slug;
  }, [task, horizons]);

  const dueLabel = task?.due_at ? formatDue(task.due_at, tz) ?? "—" : "Без даты";
  const horizonTone =
    task?.horizon_slug !== null && task?.horizon_slug !== undefined
      ? HORIZON_TONE[task.horizon_slug as HorizonSlug] ?? "slate"
      : "slate";
  const priorityTone = task ? PRIORITY_TONE[task.priority] : "amber";

  return (
    <div
      className="mx-auto flex max-w-md flex-col gap-4 px-4"
      style={{
        paddingTop: "calc(var(--safe-top) + 0.5rem)",
        paddingBottom: "calc(var(--safe-bottom) + 5.5rem)",
      }}
    >
      <header className="sticky top-0 z-10 -mx-4 flex items-center gap-2 bg-bento/90 px-4 py-2 backdrop-blur-xl">
        <button
          type="button"
          onClick={onClose}
          aria-label="Назад"
          className="ease-apple inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-tg-text transition-all duration-200 active:scale-[0.95] hover:bg-bento-card"
        >
          <ChevronLeft size={22} strokeWidth={2.25} aria-hidden />
        </button>
        <span className="font-display flex-1 truncate text-[15px] font-medium tracking-tight text-tg-hint">
          Задача
        </span>
      </header>

      {loadError && (
        <div className="rounded-3xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100 dark:bg-rose-950/40 dark:text-rose-200">
          {loadError}
        </div>
      )}

      {saveError && (
        <div className="rounded-3xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100 dark:bg-rose-950/40 dark:text-rose-200">
          {saveError}
        </div>
      )}

      {task !== null && (
        <>
          <section className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
              Название
            </label>
            <textarea
              value={titleDraft}
              maxLength={256}
              rows={2}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => {
                const trimmed = titleDraft.trim();
                if (trimmed && trimmed !== task.title) {
                  void patch("title", { title: trimmed });
                } else if (!trimmed) {
                  // Don't allow empty title — revert.
                  setTitleDraft(task.title);
                }
              }}
              className="font-display mt-1 w-full resize-none rounded-xl border-none bg-transparent text-[19px] font-semibold leading-snug tracking-tight text-tg-text focus:outline-none"
              placeholder="Что нужно сделать?"
              disabled={pending === "title"}
            />
          </section>

          <section className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
              Описание
            </label>
            <textarea
              value={descDraft}
              maxLength={4096}
              rows={4}
              onChange={(e) => setDescDraft(e.target.value)}
              onBlur={() => {
                const trimmed = descDraft.trim();
                const current = task.description ?? "";
                if (trimmed !== current) {
                  void patch("description", {
                    description: trimmed.length === 0 ? null : trimmed,
                  });
                }
              }}
              className="mt-1 w-full resize-none rounded-xl border-none bg-transparent text-[15px] leading-relaxed text-tg-text focus:outline-none"
              placeholder="Заметки, контекст, ссылки…"
              disabled={pending === "description"}
            />
          </section>

          <section className="flex flex-col gap-1.5">
            <DetailRow
              icon={CalendarDays}
              tone="violet"
              label="Дата"
              value={dueLabel}
              onClick={() => setShowDateSheet(true)}
              disabled={pending === "due_at"}
            />
            <DetailRow
              icon={Inbox}
              tone={horizonTone}
              label="Горизонт"
              value={horizonLabel}
              onClick={() => setShowHorizonSheet(true)}
              disabled={pending === "horizon_slug"}
            />
            <DetailRow
              icon={Tag}
              tone="teal"
              label="Категория"
              value={categoryLabel}
              onClick={() => setShowCategorySheet(true)}
              disabled={pending === "category_id" || categories.length === 0}
            />
            <DetailRow
              icon={Flag}
              tone={priorityTone}
              label="Приоритет"
              value={PRIORITY_LABEL[task.priority]}
              onClick={() => setShowPrioritySheet(true)}
              disabled={pending === "priority"}
            />
          </section>

          <button
            type="button"
            onClick={() => {
              haptic("warn");
              setConfirmDelete(true);
            }}
            disabled={pending === "delete"}
            className="ease-apple mt-2 inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-500/10 px-4 py-3 text-[15px] font-medium text-rose-700 transition-all duration-200 active:scale-[0.97] disabled:opacity-60 dark:text-rose-300"
          >
            <Trash2 size={16} strokeWidth={2.25} aria-hidden />
            Удалить задачу
          </button>
        </>
      )}

      {/* ── sheets ─────────────────────────────────────────────── */}
      {task !== null && (
        <>
          <BottomSheetSelect
            open={showHorizonSheet}
            onClose={() => setShowHorizonSheet(false)}
            title="Горизонт"
            options={horizons.map((h) => ({ value: h.slug, label: h.label }))}
            value={task.horizon_slug ?? ""}
            onSelect={(value) => {
              void patch("horizon_slug", { horizon_slug: value as HorizonSlug });
            }}
          />
          <BottomSheetSelect
            open={showCategorySheet}
            onClose={() => setShowCategorySheet(false)}
            title="Категория"
            options={categories.map((c) => ({ value: String(c.id), label: c.name }))}
            value={task.category_id === null ? "" : String(task.category_id)}
            onSelect={(value) => {
              const id = Number.parseInt(value, 10);
              if (Number.isFinite(id) && id > 0) {
                void patch("category_id", { category_id: id });
              }
            }}
          />
          <BottomSheetSelect
            open={showPrioritySheet}
            onClose={() => setShowPrioritySheet(false)}
            title="Приоритет"
            options={PRIORITY_OPTIONS}
            value={task.priority}
            onSelect={(value) => {
              void patch("priority", { priority: value as TaskPriority });
            }}
          />
          <BottomSheetDate
            open={showDateSheet}
            onClose={() => setShowDateSheet(false)}
            value={task.due_at}
            tz={tz}
            onSelect={(iso) => {
              void patch("due_at", { due_at: iso });
            }}
          />
          <ConfirmDeleteSheet
            open={confirmDelete}
            onCancel={() => setConfirmDelete(false)}
            onConfirm={async () => {
              setConfirmDelete(false);
              await remove();
            }}
            pending={pending === "delete"}
            title={task.title}
          />
        </>
      )}
    </div>
  );
}

// ── helpers ────────────────────────────────────────────────────────

interface RowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  value: string;
  onClick: () => void;
  disabled?: boolean;
}

function DetailRow({ icon, tone, label, value, onClick, disabled }: RowProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        "ease-apple flex items-center justify-between gap-3 rounded-2xl bg-bento-card px-4 py-3 text-left shadow-bento ring-1 ring-black/5 transition-all duration-200 " +
        (disabled ? "opacity-60 " : "active:scale-[0.99] hover:bg-bento-card/90")
      }
    >
      <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
        <IconTile icon={icon} tone={tone} size="md" />
        <span className="min-w-0">
          <span className="block text-[12px] text-tg-hint">{label}</span>
          <span className="font-display block truncate font-medium tracking-tight">
            {value}
          </span>
        </span>
      </span>
      <ChevronRight
        size={18}
        strokeWidth={2.25}
        className="shrink-0 text-tg-hint"
        aria-hidden
      />
    </button>
  );
}

interface ConfirmProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => Promise<void> | void;
  pending: boolean;
  title: string;
}

function ConfirmDeleteSheet({ open, onCancel, onConfirm, pending, title }: ConfirmProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div
        aria-hidden
        onClick={onCancel}
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        style={{ animation: "fade-in 150ms ease-out" }}
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label="Удалить задачу"
        className="relative z-10 w-full max-w-md rounded-t-3xl bg-bento-card p-5 shadow-bento-lg ring-1 ring-black/5"
        style={{
          animation: "slide-up 250ms cubic-bezier(0.16, 1, 0.3, 1)",
          paddingBottom: "calc(var(--safe-bottom) + 1rem)",
        }}
      >
        <div className="mb-4 flex justify-center pt-1">
          <span className="block h-1.5 w-10 rounded-full bg-tg-hint/30" aria-hidden />
        </div>
        <h3 className="font-display text-center text-[17px] font-semibold tracking-tight text-tg-text">
          Удалить задачу?
        </h3>
        <p className="mt-1 line-clamp-2 text-center text-[13px] text-tg-hint">
          «{title}»
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="ease-apple inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-500 px-4 py-3 text-[15px] font-semibold text-white transition-all duration-200 active:scale-[0.97] disabled:opacity-60"
          >
            <Trash2 size={16} strokeWidth={2.25} aria-hidden />
            {pending ? "Удаляем…" : "Удалить"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="ease-apple inline-flex items-center justify-center rounded-2xl bg-bento px-4 py-3 text-[15px] font-medium text-tg-text transition-all duration-200 active:scale-[0.97]"
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
