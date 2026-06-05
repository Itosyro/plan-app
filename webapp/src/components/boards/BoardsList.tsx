// Full-screen boards list screen.
//
// Entry point for the Доски feature. Shows named Excalidraw boards,
// «+ Новая» button, relative timestamps, delete with confirmation.
//
// Data via useCachedResource("boards", ...) — instant cache + skeleton.
// Creating a board: POST → navigate to its canvas.
// Delete: long-press row (or trailing ×) → confirm → DELETE.

import { useCallback, useMemo, useRef, useState } from "react";
import { ChevronLeft, PenLine, Plus, Trash2 } from "lucide-react";
import { apiClient } from "../../api/client";
import { useCachedResource } from "../../lib/useCachedResource";
import { invalidate } from "../../lib/cache";
import { haptic } from "../../lib/telegram";
import { navigate } from "../../lib/router";
import type { Board } from "../../types";
import { SkeletonList } from "../Skeleton";

export const BOARDS_CACHE_KEY = "boards";

// Relative time formatter (Russian).
function relativeTime(iso: string): string {
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const diff = Date.now() - Date.parse(utc);
  if (Number.isNaN(diff)) return "";
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "только что";
  if (mins < 60) return `${mins} мин назад`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "вчера";
  if (days < 7) return `${days} дн назад`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} нед назад`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} мес назад`;
  return `${Math.floor(months / 12)} г назад`;
}

export function BoardsList() {
  const { data: boards, showSkeleton, refetch } = useCachedResource<Board[]>(
    BOARDS_CACHE_KEY,
    () => apiClient.boards(),
    [],
  );

  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  // Long-press detection: 500ms hold → show confirm-delete state.
  const longPressTimerRef = useRef<number | undefined>(undefined);

  const handleBack = useCallback(() => {
    haptic("select");
    navigate("/");
  }, []);

  const handleCreate = useCallback(async () => {
    if (creating) return;
    haptic("select");
    setCreating(true);
    try {
      const board = await apiClient.createBoard();
      invalidate(BOARDS_CACHE_KEY);
      navigate(`/board/${board.id}`);
    } catch {
      haptic("error");
    } finally {
      setCreating(false);
    }
  }, [creating]);

  const handleOpen = useCallback((id: number) => {
    haptic("select");
    navigate(`/board/${id}`);
  }, []);

  const handleDeleteConfirm = useCallback(
    async (id: number) => {
      if (deletingId !== null) return;
      haptic("warn");
      setDeletingId(id);
      try {
        await apiClient.deleteBoard(id);
        invalidate(BOARDS_CACHE_KEY);
        refetch();
      } catch {
        haptic("error");
      } finally {
        setDeletingId(null);
        setConfirmDeleteId(null);
      }
    },
    [deletingId, refetch],
  );

  const handleLongPressStart = useCallback((id: number) => {
    longPressTimerRef.current = window.setTimeout(() => {
      haptic("warn");
      setConfirmDeleteId(id);
    }, 500);
  }, []);

  const handleLongPressEnd = useCallback(() => {
    if (longPressTimerRef.current !== undefined) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = undefined;
    }
  }, []);

  const sortedBoards = useMemo(
    () =>
      boards
        ? [...boards].sort(
            (a, b) =>
              Date.parse(b.updated_at.endsWith("Z") ? b.updated_at : b.updated_at + "Z") -
              Date.parse(a.updated_at.endsWith("Z") ? a.updated_at : a.updated_at + "Z"),
          )
        : [],
    [boards],
  );

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-tg-bg">
      {/* Header */}
      <header
        className="flex shrink-0 items-center gap-2 border-b border-black/[0.06] bg-tg-bg px-2 py-2 dark:border-white/[0.06]"
        style={{ paddingTop: "calc(var(--safe-top, 0px) + 0.5rem)" }}
      >
        <button
          type="button"
          onClick={handleBack}
          aria-label="Назад"
          className="ease-apple inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
        >
          <ChevronLeft size={20} strokeWidth={2.5} aria-hidden />
        </button>
        <h1 className="font-display min-w-0 flex-1 text-[20px] font-semibold tracking-tight text-tg-text">
          Доски
        </h1>
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={creating}
          aria-label="Новая доска"
          className="ease-apple inline-flex h-9 items-center gap-1.5 rounded-xl bg-tg-button px-3 text-[13px] font-medium text-tg-button-text shadow-sm transition-all duration-150 active:scale-95 disabled:opacity-60"
        >
          <Plus size={16} strokeWidth={2.5} aria-hidden />
          Новая
        </button>
      </header>

      {/* Body */}
      <div
        className="flex-1 overflow-y-auto px-4 py-3"
        style={{ paddingBottom: "calc(var(--safe-bottom, 0px) + 1rem)" }}
      >
        {boards === undefined && showSkeleton ? (
          <SkeletonList rows={4} kind="note" />
        ) : sortedBoards.length === 0 ? (
          <div className="mt-16 flex flex-col items-center gap-3 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-bento-card shadow-bento ring-1 ring-tg-divider/40">
              <PenLine size={28} strokeWidth={1.75} className="text-tg-hint" aria-hidden />
            </div>
            <p className="text-[15px] font-medium text-tg-text">
              Пока нет досок
            </p>
            <p className="max-w-[220px] text-[13px] text-tg-hint">
              Создай первую — нажми «Новая» выше
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {sortedBoards.map((board) => (
              <BoardRow
                key={board.id}
                board={board}
                confirmDelete={confirmDeleteId === board.id}
                deleting={deletingId === board.id}
                onOpen={handleOpen}
                onDeleteRequest={() => setConfirmDeleteId(board.id)}
                onDeleteConfirm={() => void handleDeleteConfirm(board.id)}
                onDeleteCancel={() => setConfirmDeleteId(null)}
                onLongPressStart={() => handleLongPressStart(board.id)}
                onLongPressEnd={handleLongPressEnd}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface BoardRowProps {
  board: Board;
  confirmDelete: boolean;
  deleting: boolean;
  onOpen: (id: number) => void;
  onDeleteRequest: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  onLongPressStart: () => void;
  onLongPressEnd: () => void;
}

function BoardRow({
  board,
  confirmDelete,
  deleting,
  onOpen,
  onDeleteRequest,
  onDeleteConfirm,
  onDeleteCancel,
  onLongPressStart,
  onLongPressEnd,
}: BoardRowProps) {
  return (
    <li>
      {confirmDelete ? (
        // Confirm-delete inline state: replace the row with an action bar.
        <div className="ease-apple flex items-center gap-2 rounded-2xl bg-bento-card px-4 py-3 ring-1 ring-tg-divider/40 shadow-bento animate-fade-in">
          <span className="min-w-0 flex-1 truncate text-[14px] text-tg-text">
            Удалить «{board.name}»?
          </span>
          <button
            type="button"
            onClick={onDeleteCancel}
            className="ease-apple rounded-xl bg-bento px-3 py-1.5 text-[13px] text-tg-text/70 transition-all active:scale-95"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={onDeleteConfirm}
            disabled={deleting}
            className="ease-apple rounded-xl bg-rose-500/10 px-3 py-1.5 text-[13px] font-medium text-rose-600 transition-all active:scale-95 disabled:opacity-60 dark:text-rose-400"
          >
            {deleting ? "…" : "Удалить"}
          </button>
        </div>
      ) : (
        <div
          role="button"
          tabIndex={0}
          aria-label={`Открыть доску ${board.name}`}
          className="ease-apple flex cursor-pointer items-center gap-3 rounded-2xl bg-bento-card px-4 py-3 shadow-bento ring-1 ring-tg-divider/40 transition-all duration-150 active:scale-[0.98]"
          onClick={() => onOpen(board.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onOpen(board.id);
          }}
          onPointerDown={onLongPressStart}
          onPointerUp={onLongPressEnd}
          onPointerLeave={onLongPressEnd}
          onPointerCancel={onLongPressEnd}
        >
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="font-display truncate text-[15px] font-medium tracking-tight text-tg-text">
              {board.name}
            </span>
            <span className="text-[12px] text-tg-hint">
              изменено {relativeTime(board.updated_at)}
            </span>
          </div>
          <button
            type="button"
            aria-label={`Удалить доску ${board.name}`}
            onClick={(e) => {
              e.stopPropagation();
              onDeleteRequest();
              haptic("warn");
            }}
            className="ease-apple inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-tg-hint/60 transition-all duration-150 hover:bg-rose-500/10 hover:text-rose-500 active:scale-90"
          >
            <Trash2 size={15} strokeWidth={2} aria-hidden />
          </button>
        </div>
      )}
    </li>
  );
}
