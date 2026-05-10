import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  title: string;
  description: string;
}

// Minimal placeholder shown when a bottom-nav tab has no real
// content yet. Settings (PR C) and Calendar (Phase 5.5) ship with
// real screens later; this avoids dead-end taps in the meantime.
export function ComingSoon({ icon: Icon, title, description }: Props) {
  return (
    <div className="mt-12 flex flex-col items-center px-6 text-center">
      <div className="rounded-2xl bg-tg-secondary p-4">
        <Icon size={28} strokeWidth={1.5} className="text-tg-hint" />
      </div>
      <h2 className="mt-4 text-base font-medium text-tg-text">{title}</h2>
      <p className="mt-1 max-w-xs text-sm text-tg-hint">{description}</p>
    </div>
  );
}
