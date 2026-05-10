import type { Me } from "../types";

interface Props {
  me: Me | null;
}

export function Header({ me }: Props) {
  return (
    <header className="mb-3 flex items-baseline justify-between">
      <h1 className="text-[22px] font-semibold tracking-tight text-tg-text">
        План
      </h1>
      {me?.display_name && (
        <span className="text-xs text-tg-hint">{me.display_name}</span>
      )}
    </header>
  );
}
