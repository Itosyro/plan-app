// Skeleton placeholders for cold loads — outlines of the future content
// appear instantly, then real data fades in over them. Removes the
// "blank screen → 'Загружаем…' → pop" jolt on first open of each tab.
//
// The shapes mirror the real cards (same radius, ring, shadow, padding)
// so when the data lands the layout doesn't shift. Pulse via Tailwind's
// `animate-pulse`; `prefers-reduced-motion` is respected globally.

interface SkeletonLineProps {
  /** Tailwind width (e.g. "w-1/2", "w-3/4", "w-24"). */
  width?: string;
  /** Tailwind height (e.g. "h-3", "h-4"). */
  height?: string;
}

export function SkeletonLine({ width = "w-full", height = "h-3" }: SkeletonLineProps) {
  return <span className={`block rounded-md bg-bento ${width} ${height}`} />;
}

export function SkeletonTaskCard() {
  return (
    <div className="rounded-2xl bg-bento-card p-3 shadow-bento ring-1 ring-black/5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 h-5 w-5 shrink-0 rounded-full bg-bento" />
        <div className="flex min-w-0 flex-1 flex-col gap-2 py-0.5">
          <SkeletonLine width="w-3/4" height="h-3.5" />
          <SkeletonLine width="w-2/5" height="h-2.5" />
        </div>
      </div>
    </div>
  );
}

export function SkeletonNoteCard() {
  return (
    <div className="rounded-2xl bg-bento-card p-3 shadow-bento ring-1 ring-black/5">
      <div className="flex flex-col gap-2">
        <SkeletonLine width="w-2/3" height="h-3.5" />
        <SkeletonLine width="w-full" height="h-2.5" />
        <SkeletonLine width="w-5/6" height="h-2.5" />
      </div>
    </div>
  );
}

interface SkeletonListProps {
  /** Number of rows to render. */
  rows?: number;
  /** Kind of card shape. */
  kind?: "task" | "note";
}

export function SkeletonList({ rows = 4, kind = "task" }: SkeletonListProps) {
  const Card = kind === "task" ? SkeletonTaskCard : SkeletonNoteCard;
  return (
    <ul className="flex animate-pulse flex-col gap-2" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i}>
          <Card />
        </li>
      ))}
    </ul>
  );
}

/** Skeleton for the InboxReview list — each review is a tall card with
 *  several rows + an action bar. */
export function SkeletonInboxList({ rows = 3 }: { rows?: number }) {
  return (
    <ul className="flex animate-pulse flex-col gap-3" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <li
          key={i}
          className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5"
        >
          <div className="flex flex-col gap-3">
            <SkeletonLine width="w-1/3" height="h-3" />
            <div className="flex flex-col gap-2">
              <SkeletonLine width="w-5/6" height="h-3.5" />
              <SkeletonLine width="w-2/3" height="h-3.5" />
            </div>
            <div className="mt-1 flex gap-2">
              <span className="h-9 w-24 rounded-xl bg-bento" />
              <span className="h-9 w-20 rounded-xl bg-bento" />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Full-app boot skeleton — what the user sees before the API shell
 *  resolves on first open. Mirrors the real shell so layout stays stable
 *  when content lands. */
export function SkeletonAppShell() {
  return (
    <div
      className="mx-auto flex max-w-md flex-col gap-4 px-4 pb-24 pt-4"
      style={{ paddingTop: "calc(var(--safe-top) + 1rem)" }}
      aria-hidden="true"
    >
      <div className="flex animate-pulse flex-col gap-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-2">
            <SkeletonLine width="w-32" height="h-5" />
            <SkeletonLine width="w-24" height="h-3" />
          </div>
          <span className="h-10 w-10 rounded-full bg-bento" />
        </div>
        {/* Horizon tabs row */}
        <div className="flex gap-2 overflow-hidden">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="h-8 w-20 shrink-0 rounded-full bg-bento" />
          ))}
        </div>
        {/* Task cards */}
        <ul className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <li key={i}>
              <SkeletonTaskCard />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
