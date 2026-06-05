// Full-screen task search. Opens from the Header search button; the
// user types, results refresh after a small debounce, tapping a row
// opens its TaskDetail. Closed by tapping the back arrow or pressing
// Escape on hardware keyboards.
//
// Why an overlay and not an inline SearchBar like NotesList: the user
// usually wants to find *one* task across all horizons/categories
// without re-pointing the filters they had set on the list. The
// overlay fully replaces the screen for the duration of the search,
// then disappears — list state behind it is preserved.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Search, X } from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { categoryColor, formatDue } from "../lib/format";
import { haptic } from "../lib/telegram";
import type { Task } from "../types";
import { SkeletonList } from "./Skeleton";

interface Props {
  tz: string;
  onClose: () => void;
  onOpen: (id: number) => void;
}

const DEBOUNCE_MS = 200;
const MIN_QUERY_LEN = 2;

export function SearchOverlay({ tz, onClose, onOpen }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Autofocus the input on mount so the user can type immediately.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Hardware Escape closes the overlay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Debounced search. Ignores stale responses so a slow request
  // arriving after a faster one doesn't clobber newer results.
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LEN) {
      setResults(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    const seq = Date.now();
    const handle = window.setTimeout(async () => {
      try {
        const data = await apiClient.tasks({
          q: trimmed,
          include_done: true,
          limit: 50,
        });
        // Drop the response if the user has since typed something else
        // (the cleanup below clears the seq via a closure check).
        if (currentSeq.current !== seq) return;
        setResults(data);
      } catch (err) {
        if (currentSeq.current !== seq) return;
        if (err instanceof ApiError && err.status === 422) {
          setError("Слишком длинный запрос");
        } else {
          setError("Не удалось загрузить результаты");
        }
        setResults([]);
      } finally {
        if (currentSeq.current === seq) setLoading(false);
      }
    }, DEBOUNCE_MS);
    currentSeq.current = seq;
    return () => {
      window.clearTimeout(handle);
    };
  }, [query]);

  const currentSeq = useRef(0);

  const handleOpen = useCallback(
    (id: number) => {
      haptic("select");
      onClose();
      onOpen(id);
    },
    [onClose, onOpen],
  );

  const showEmpty = useMemo(
    () => query.trim().length >= MIN_QUERY_LEN && !loading && results !== null && results.length === 0,
    [query, loading, results],
  );

  return (
    <div
      className="fixed inset-0 z-30 flex flex-col bg-bento animate-fade-in"
      role="dialog"
      aria-label="Поиск задач"
    >
      <header
        className="flex items-center gap-2 border-b border-black/[0.04] bg-bento-card px-3 shadow-bento"
        style={{ paddingTop: "calc(var(--safe-top) + 0.5rem)", paddingBottom: "0.5rem" }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="ease-apple inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-tg-text transition-all duration-200 active:scale-[0.95] hover:bg-bento"
        >
          <ArrowLeft size={22} strokeWidth={2.25} aria-hidden />
        </button>
        <label className="flex flex-1 items-center gap-2 rounded-2xl bg-bento px-3 py-2 ring-1 ring-black/5 focus-within:ring-tg-button/30">
          <Search size={16} strokeWidth={2.25} className="text-tg-hint" aria-hidden />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Найти в задачах…"
            maxLength={200}
            enterKeyHint="search"
            className="min-w-0 flex-1 bg-transparent text-[15px] text-tg-text placeholder:text-tg-hint focus:outline-none"
          />
          {query.length > 0 && (
            <button
              type="button"
              aria-label="Очистить запрос"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              className="ease-apple inline-flex h-6 w-6 items-center justify-center rounded-full text-tg-hint transition-all duration-150 hover:bg-bento-card active:scale-95"
            >
              <X size={14} strokeWidth={2.5} aria-hidden />
            </button>
          )}
        </label>
      </header>

      <div
        className="flex-1 overflow-y-auto px-4 pt-3"
        style={{ paddingBottom: "calc(var(--safe-bottom) + 1rem)" }}
      >
        {query.trim().length === 0 && (
          <p className="px-2 py-12 text-center text-[14px] text-tg-hint animate-fade-in">
            Начни вводить — найду по названию, описанию и оригиналу.
          </p>
        )}
        {query.trim().length > 0 && query.trim().length < MIN_QUERY_LEN && (
          <p className="px-2 py-8 text-center text-[13px] text-tg-hint animate-fade-in">
            Ещё хотя бы одну букву…
          </p>
        )}
        {loading && <SkeletonList rows={4} kind="task" />}
        {!loading && error !== null && (
          <p className="px-2 py-8 text-center text-[14px] text-tg-hint animate-fade-in">
            {error}
          </p>
        )}
        {showEmpty && (
          <p className="px-2 py-8 text-center text-[14px] text-tg-hint animate-fade-in">
            Ничего не нашлось.
          </p>
        )}
        {!loading && results !== null && results.length > 0 && (
          <ul className="flex flex-col gap-2 animate-fade-in">
            {results.map((task) => (
              <li key={task.id}>
                <SearchResultCard task={task} tz={tz} query={query} onOpen={handleOpen} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface ResultProps {
  task: Task;
  tz: string;
  query: string;
  onOpen: (id: number) => void;
}

function SearchResultCard({ task, tz, query, onOpen }: ResultProps) {
  const isDone = task.status === "done";
  const c = categoryColor(task.category_id);
  const due = task.due_at ? formatDue(task.due_at, tz) : null;
  return (
    <button
      type="button"
      onClick={() => onOpen(task.id)}
      className="ease-apple flex w-full items-start gap-3 rounded-2xl bg-bento-card p-3 text-left shadow-bento ring-1 ring-black/5 transition-all duration-150 active:scale-[0.99]"
    >
      <span aria-hidden className={"mt-1 h-8 w-1 shrink-0 rounded-full " + c.dot} />
      <div className="min-w-0 flex-1">
        <span
          className={
            "block break-words text-[14px] leading-snug " +
            (isDone ? "text-tg-hint line-through" : "text-tg-text")
          }
        >
          {highlight(task.title, query)}
        </span>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-tg-hint">
          {task.category_name && (
            <span className={"rounded-full px-1.5 py-0.5 " + c.pill + " " + c.text}>
              {task.category_name}
            </span>
          )}
          {due && <span className="tabular">{due}</span>}
          {task.horizon_slug && task.horizon_slug !== "today" && <span>· {task.horizon_slug}</span>}
        </div>
      </div>
    </button>
  );
}

// Bold the first matched substring (case-insensitive). Keeps the rest
// of the title as-is so screen readers still pick up the full text.
function highlight(text: string, query: string): React.ReactNode {
  const needle = query.trim();
  if (needle.length === 0) return text;
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-tg-button/15 px-0.5 text-tg-text rounded">
        {text.slice(idx, idx + needle.length)}
      </mark>
      {text.slice(idx + needle.length)}
    </>
  );
}
