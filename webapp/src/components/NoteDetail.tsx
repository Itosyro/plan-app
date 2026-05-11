// Full-screen note detail. Reached by tapping a NoteCard, or by the
// «+» FAB in the Notes header (in which case ``mode === "create"``
// and the page starts with empty drafts; on first save we POST and
// switch to view-mode for the new row, syncing the URL to /note/:id).
//
// Layout mirrors TaskDetail (sticky header, editable title, body
// textarea, tone-coded rows, destructive «Удалить» at the bottom)
// but with fewer rows — notes have no date/horizon/priority, only
// optional category.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Tag, Trash2, type LucideIcon } from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import { navigate } from "../lib/router";
import type { Category, Note, NoteUpdate } from "../types";
import { BottomSheetSelect } from "./BottomSheetSelect";
import { IconTile, type TileTone } from "./IconTile";

type Mode = { kind: "view"; noteId: number } | { kind: "create" };

interface Props {
  mode: Mode;
  categories: Category[];
  onClose: () => void;
  /** Called after a successful mutation (patch, create, or delete). */
  onMutated: () => void;
  /** Called after a successful delete so the parent can navigate away. */
  onDeleted: () => void;
}

export function NoteDetail({
  mode,
  categories,
  onClose,
  onMutated,
  onDeleted,
}: Props) {
  const [note, setNote] = useState<Note | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [bodyDraft, setBodyDraft] = useState("");
  const [draftCategoryId, setDraftCategoryId] = useState<number | null>(null);
  const [showCategorySheet, setShowCategorySheet] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isCreate = mode.kind === "create";

  const load = useCallback(async () => {
    if (mode.kind !== "view") return;
    setLoadError(null);
    try {
      const fresh = await apiClient.note(mode.noteId);
      setNote(fresh);
      setTitleDraft(fresh.title);
      setBodyDraft(fresh.body ?? "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadError("Заметка не найдена. Возможно, её уже удалили.");
      } else {
        setLoadError("Не удалось загрузить заметку. Проверь связь.");
      }
    }
  }, [mode]);

  useEffect(() => {
    if (mode.kind === "view") {
      void load();
    } else {
      // Reset for create mode.
      setNote(null);
      setTitleDraft("");
      setBodyDraft("");
      setDraftCategoryId(null);
    }
  }, [mode, load]);

  const createNote = useCallback(
    async (title: string): Promise<Note | null> => {
      setPending("title");
      setSaveError(null);
      try {
        const fresh = await apiClient.createNote({
          title,
          body: bodyDraft.trim().length === 0 ? null : bodyDraft.trim(),
          category_id: draftCategoryId,
        });
        setNote(fresh);
        haptic("success");
        onMutated();
        navigate(`/note/${fresh.id}`);
        return fresh;
      } catch (err) {
        haptic("error");
        setSaveError(
          err instanceof ApiError && err.status === 422
            ? "Не получилось — проверь значение"
            : "Не удалось сохранить",
        );
        return null;
      } finally {
        setPending(null);
      }
    },
    [bodyDraft, draftCategoryId, onMutated],
  );

  const patch = useCallback(
    async (field: string, body: NoteUpdate): Promise<void> => {
      if (note === null) return;
      setPending(field);
      setSaveError(null);
      try {
        const fresh = await apiClient.patchNote(note.id, body);
        setNote(fresh);
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
    [note, onMutated],
  );

  const remove = useCallback(async () => {
    if (note === null) return;
    setPending("delete");
    setSaveError(null);
    try {
      await apiClient.deleteNote(note.id);
      haptic("success");
      onMutated();
      onDeleted();
    } catch (err) {
      haptic("error");
      if (err instanceof ApiError && err.status === 404) {
        onMutated();
        onDeleted();
        return;
      }
      setSaveError("Не удалось удалить");
    } finally {
      setPending(null);
    }
  }, [note, onMutated, onDeleted]);

  const categoryId = note?.category_id ?? draftCategoryId;
  const categoryLabel = useMemo(() => {
    if (categoryId === null || categoryId === undefined) return "Без категории";
    const hit = categories.find((c) => c.id === categoryId);
    return hit ? hit.name : note?.category_name ?? "—";
  }, [categoryId, categories, note]);

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
          {isCreate && note === null ? "Новая заметка" : "Заметка"}
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

      {(note !== null || isCreate) && (
        <>
          <section className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
              Название
            </label>
            <textarea
              value={titleDraft}
              maxLength={256}
              rows={2}
              autoFocus={isCreate && note === null}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => {
                const trimmed = titleDraft.trim();
                if (note === null) {
                  if (trimmed.length > 0) {
                    void createNote(trimmed);
                  }
                } else if (trimmed && trimmed !== note.title) {
                  void patch("title", { title: trimmed });
                } else if (!trimmed) {
                  setTitleDraft(note.title);
                }
              }}
              className="font-display mt-1 w-full resize-none rounded-xl border-none bg-transparent text-[19px] font-semibold leading-snug tracking-tight text-tg-text focus:outline-none"
              placeholder="Короткое название"
              disabled={pending === "title"}
            />
          </section>

          <section className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
              Текст
            </label>
            <textarea
              value={bodyDraft}
              maxLength={8192}
              rows={8}
              onChange={(e) => setBodyDraft(e.target.value)}
              onBlur={() => {
                if (note === null) return; // body saved with create on title-blur
                const trimmed = bodyDraft.trim();
                const current = note.body ?? "";
                if (trimmed !== current) {
                  void patch("body", {
                    body: trimmed.length === 0 ? null : trimmed,
                  });
                }
              }}
              className="mt-1 w-full resize-none rounded-xl border-none bg-transparent text-[15px] leading-relaxed text-tg-text focus:outline-none"
              placeholder="Текст заметки, контекст, ссылки…"
              disabled={pending === "body"}
            />
          </section>

          <section className="flex flex-col gap-1.5">
            <DetailRow
              icon={Tag}
              tone="teal"
              label="Категория"
              value={categoryLabel}
              onClick={() => setShowCategorySheet(true)}
              disabled={pending === "category_id" || categories.length === 0}
            />
          </section>

          {note !== null && (
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
              Удалить заметку
            </button>
          )}
        </>
      )}

      {/* ── sheets ─────────────────────────────────────────────── */}
      <BottomSheetSelect
        open={showCategorySheet}
        onClose={() => setShowCategorySheet(false)}
        title="Категория"
        options={[
          { value: "", label: "Без категории" },
          ...categories.map((c) => ({ value: String(c.id), label: c.name })),
        ]}
        value={categoryId === null || categoryId === undefined ? "" : String(categoryId)}
        onSelect={(value) => {
          if (value === "") {
            if (note !== null && note.category_id !== null) {
              // No backend support for clearing yet via API contract
              // (PATCH skips ``None``). Treat as no-op visually.
              setDraftCategoryId(null);
              return;
            }
            setDraftCategoryId(null);
            return;
          }
          const id = Number.parseInt(value, 10);
          if (!Number.isFinite(id) || id <= 0) return;
          if (note === null) {
            setDraftCategoryId(id);
          } else {
            void patch("category_id", { category_id: id });
          }
        }}
      />
      {note !== null && (
        <ConfirmDeleteSheet
          open={confirmDelete}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={async () => {
            setConfirmDelete(false);
            await remove();
          }}
          pending={pending === "delete"}
          title={note.title}
        />
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
        aria-label="Удалить заметку"
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
          Удалить заметку?
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
