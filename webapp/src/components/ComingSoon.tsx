import type { LucideIcon } from "lucide-react";
import { IconTile, type TileTone } from "./IconTile";

interface Props {
  icon: LucideIcon;
  title: string;
  description: string;
  tone?: TileTone;
}

// Minimal placeholder shown when a bottom-nav tab has no real
// content yet. Same bento-card silhouette as ``EmptyState`` so the
// two read as a family.
export function ComingSoon({ icon, title, description, tone = "indigo" }: Props) {
  return (
    <div className="mt-8 flex flex-col items-center rounded-3xl bg-bento-card px-6 py-10 text-center shadow-bento ring-1 ring-black/5">
      <IconTile icon={icon} tone={tone} size="lg" label={title} />
      <h2 className="font-display mt-4 text-[20px] font-semibold tracking-tight text-tg-text">
        {title}
      </h2>
      <p className="mt-1.5 max-w-xs text-[14px] leading-relaxed text-tg-hint">
        {description}
      </p>
    </div>
  );
}
