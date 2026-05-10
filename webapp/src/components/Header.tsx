import type { Me } from "../types";

interface Props {
  me: Me | null;
  greeting?: string; // optional override (e.g. "Доброе утро, …")
}

// Bento-page header. Display-typed title + soft subtitle. The
// large display weight uses the Inter Variable opsz axis (see
// ``index.css :: .font-display``) so the title reads tighter
// than the body text without loading a second font.
export function Header({ me, greeting = "План" }: Props) {
  const subtitle = me?.display_name
    ? `Привет, ${me.display_name}`
    : "Лента твоих задач";
  return (
    <header className="mb-4 flex items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-tg-text">
          {greeting}
        </h1>
        <p className="mt-0.5 truncate text-[13px] text-tg-hint">{subtitle}</p>
      </div>
    </header>
  );
}
