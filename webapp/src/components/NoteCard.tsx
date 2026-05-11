import { Tag } from "lucide-react";
import type { Note } from "../types";
import { haptic } from "../lib/telegram";

interface Props {
  note: Note;
  onOpen: (id: number) => void;
}

// Minimalist note card — title + first line of body as preview, plus a
// category chip. Tap anywhere on the card opens the detail page.
// No checkbox, no actions inline (mirrors TaskCard simplification).
export function NoteCard({ note, onOpen }: Props) {
  const preview =
    note.body && note.body.length > 0 ? firstParagraph(note.body) : null;

  return (
    <button
      type="button"
      aria-label={`Открыть «${note.title}»`}
      onClick={() => {
        haptic("select");
        onOpen(note.id);
      }}
      className="ease-apple w-full rounded-3xl bg-bento-card p-4 text-left shadow-bento ring-1 ring-black/5 transition-all duration-200 active:scale-[0.99]"
    >
      <div className="font-display break-words text-[16px] font-medium leading-snug tracking-tight text-tg-text">
        {note.title}
      </div>
      {preview && (
        <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-tg-hint">
          {preview}
        </p>
      )}
      {note.category_name && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-bento px-2 py-0.5 text-[11px] text-tg-text/70">
            <Tag size={11} strokeWidth={2} aria-hidden />
            {note.category_name}
          </span>
        </div>
      )}
    </button>
  );
}

// Trim to first non-empty paragraph; collapse runs of whitespace. We
// only show ~2 lines via ``line-clamp``, so cheap preview is fine.
function firstParagraph(body: string): string {
  const trimmed = body.trim();
  const lineEnd = trimmed.search(/\n\s*\n/);
  const slice = lineEnd === -1 ? trimmed : trimmed.slice(0, lineEnd);
  return slice.replace(/\s+/g, " ").slice(0, 240);
}
