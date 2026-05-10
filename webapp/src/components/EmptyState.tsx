import { Sparkles, type LucideIcon } from "lucide-react";
import { IconTile, type TileTone } from "./IconTile";

interface Props {
  // Backwards-compatible: callers can still pass an emoji string, but
  // new usage should pass ``icon`` so the empty state matches the
  // bento illustration style.
  emoji?: string;
  icon?: LucideIcon;
  tone?: TileTone;
  title: string;
  hint: string;
}

// Bento empty-state card. Large IconTile illustration + display
// heading + soft hint. Sits inside a rounded card on the bento
// background so it reads as "intentional empty" rather than a gap.
export function EmptyState({
  emoji,
  icon,
  tone = "slate",
  title,
  hint,
}: Props) {
  const Icon: LucideIcon = icon ?? Sparkles;
  return (
    <div className="mt-8 flex flex-col items-center rounded-3xl bg-bento-card px-6 py-10 text-center shadow-bento ring-1 ring-black/5">
      {emoji && !icon ? (
        <div aria-hidden className="mb-3 text-5xl">
          {emoji}
        </div>
      ) : (
        <IconTile icon={Icon} tone={tone} size="lg" label={title} />
      )}
      <h2 className="font-display mt-4 text-[20px] font-semibold tracking-tight text-tg-text">
        {title}
      </h2>
      <p className="mt-1.5 max-w-xs text-[14px] leading-relaxed text-tg-hint">
        {hint}
      </p>
    </div>
  );
}
