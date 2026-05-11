// «Заметки» tab. Plain list of notes for the current user, freshest
// first. Tap a card → open detail. Plus a substring search on title
// or body so the tab is usable when the list grows.

import { useEffect, useMemo, useState } from "react";
import { Search, StickyNote, X } from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import type { Note } from "../types";
import { EmptyState } from "./EmptyState";
import { NoteCard } from "./NoteCard";

interface Props {
  /**
   * Bumped by the parent whenever a mutation occurs (delete in detail
   * page, create from the FAB). Each change triggers a refetch so the
   * list reflects the truth without us having to plumb optimistic
   * state through the detail page.
   */
  refreshSignal: number;
  onOpen: (id: number) => void;
}

export function NotesList({ refreshSignal, onOpen }: Props) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await apiClient.notes();
        if (!cancelled) {
          setNotes(resp);
          setError(null);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          setError("Не удалось проверить вход.");
        } else {
          setError("Не удалось загрузить заметки.");
        }
        setNotes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  const filtered = useMemo(() => {
    if (notes === null) return null;
    const q = query.trim().toLowerCase();
    if (q.length === 0) return notes;
    return notes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        (n.body !== null && n.body.toLowerCase().includes(q)),
    );
  }, [notes, query]);

  if (notes === null) {
    return (
      <div className="py-10 text-center text-sm text-tg-hint">Загружаем…</div>
    );
  }

  if (error !== null && notes.length === 0) {
    return (
      <EmptyState
        icon={StickyNote}
        tone="amber"
        title="Не получилось"
        hint={error}
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
        <div className="rounded-3xl bg-bento-card p-4 text-center text-sm text-tg-hint shadow-bento ring-1 ring-black/5">
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
    <label className="ease-apple flex items-center gap-2 rounded-2xl bg-bento-card px-3 py-2 shadow-bento ring-1 ring-black/5 transition-colors focus-within:ring-tg-button/30">
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
