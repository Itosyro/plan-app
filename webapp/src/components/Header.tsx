import type { Me } from "../types";

interface Props {
  me: Me | null;
}

export function Header({ me }: Props) {
  return (
    <header className="mb-3 flex items-center justify-between">
      <div>
        <h1 className="text-xl font-semibold text-tg-text">План</h1>
        {me?.display_name && (
          <p className="text-xs text-tg-hint">Привет, {me.display_name} 👋</p>
        )}
      </div>
      <div className="text-right text-xs text-tg-hint">
        {me?.tz && <span>{me.tz}</span>}
      </div>
    </header>
  );
}
