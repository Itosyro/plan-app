// «Заметки» tab. Plain list of notes for the current user, freshest
// first. Tap a card → open detail. Plus a substring search on title
// or body so the tab is usable when the list grows.
//
// Data lifecycle is owned by ``useCachedResource``: instant repaint
// from the module-scoped cache, fresh fetch in the background,
// skeleton only when the cold fetch is slow. Cross-screen
// optimism (delete confirmed inside NoteDetail) lands here via
// ``mutateCache("notes", ...)`` from App.tsx — no prop chain.

import { useMemo, useState } from "react";
import { Search, StickyNote, X } from "lucide-react";
import { ApiError } from "../api/client";
import { apiClient } from "../api/client";
import { useCachedResource } from "../lib/useCachedResource";
import { haptic } from "../lib/telegram";
import type { Note } from "../types";
import { EmptyState } from "./EmptyState";
import { NoteCard } from "./NoteCard";
import { SkeletonList } from "./Skeleton";

interface Props {
  onOpen: (id: number) => void;
}

export const NOTES_CACHE_KEY = "notes";

export function NotesList({ onOpen }: Props) {
  const { data: notes, showSkeleton, error } = useCachedResource<Note[]>(
    NOTES_CACHE_KEY,
    () => apiClient.notes(),
    [],
  );
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (notes === undefined) return null;
    const q = query.trim().toLowerCase();
    if (q.length === 0) return notes;
    return notes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        (n.body !== null && n.body.toLowerCase().includes(q)),
    );
  }, [notes, query]);

  if (notes === undefined) {
    // Cold first paint and the fetch is slow — show a skeleton.
    // Warm re-entry uses cached data and skips this branch entirely.
    return showSkeleton ? <SkeletonList rows={5} kind="note" /> : null;
  }

  if (error !== null && notes.length === 0) {
    const message =
      error instanceof ApiError && error.status === 401
        ? "Не удалось проверить вход."
        : "Не удалось загрузить заметки.";
    return (
      <EmptyState
        icon={StickyNote}
        tone="amber"
        title="Не получилось"
        hint={message}
      />
    );
  }

  if (notes.length === 0) {
    return (
      <EmptyState
        icon={StickyNote}
        tone="amber"
        title="Заметок пока нет"
        hint="Надиктуй или напиши боту что-нибудь, что не задача и не напоминание — оно прилетит сюда. Или нажми «+» сверху."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <SearchBar value={query} onChange={setQuery} />
      {filtered !== null && filtered.length === 0 ? (
        <div className="rounded-3xl bg-bento-card p-4 text-center text-sm text-tg-hint shadow-bento ring-1 ring-tg-divider/40">
          По запросу ничего не нашлось.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {(filtered ?? []).map((note) => (
            <li key={note.id}>
              <NoteCard note={note} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface SearchBarProps {
  value: string;
  onChange: (next: string) => void;
}

function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <label className="ease-apple flex items-center gap-2 rounded-2xl bg-bento-card px-3 py-2 shadow-bento ring-1 ring-tg-divider/40 transition-colors focus-within:ring-tg-button/30">
      <Search size={16} strokeWidth={2.25} className="text-tg-hint" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Найти в заметках…"
        className="min-w-0 flex-1 bg-transparent text-[14px] text-tg-text placeholder:text-tg-hint focus:outline-none"
      />
      {value.length > 0 && (
        <button
          type="button"
          aria-label="Очистить поиск"
          onClick={() => {
            haptic("select");
            onChange("");
          }}
          className="ease-apple inline-flex h-6 w-6 items-center justify-center rounded-full text-tg-hint transition-all duration-150 hover:bg-bento active:scale-95"
        >
          <X size={14} strokeWidth={2.5} aria-hidden />
        </button>
      )}
    </label>
  );
}
