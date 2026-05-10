// Apple/Mira-style icon-tile: a small rounded square with a tinted
// background and a centred lucide icon. Used everywhere we'd
// otherwise have a bare icon — settings rows, horizon labels,
// task-card priority indicators, the empty-state illustration.
//
// The colour is chosen from a fixed palette so the same domain
// concept always reads the same. Tailwind sees the literal class
// names below and keeps them in the build (no string-concat traps).

import type { LucideIcon } from "lucide-react";

export type TileTone =
  | "violet"
  | "indigo"
  | "blue"
  | "sky"
  | "teal"
  | "emerald"
  | "amber"
  | "orange"
  | "rose"
  | "pink"
  | "slate";

const TONE_BG: Record<TileTone, string> = {
  violet: "bg-violet-500",
  indigo: "bg-indigo-500",
  blue: "bg-blue-500",
  sky: "bg-sky-500",
  teal: "bg-teal-500",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  orange: "bg-orange-500",
  rose: "bg-rose-500",
  pink: "bg-pink-500",
  slate: "bg-slate-500",
};

export type TileSize = "sm" | "md" | "lg";

const SIZE_CLASSES: Record<TileSize, { box: string; icon: number }> = {
  sm: { box: "h-7 w-7 rounded-lg", icon: 15 },
  md: { box: "h-9 w-9 rounded-xl", icon: 18 },
  lg: { box: "h-11 w-11 rounded-2xl", icon: 22 },
};

interface Props {
  icon: LucideIcon;
  tone: TileTone;
  size?: TileSize;
  label?: string; // optional accessible label
}

export function IconTile({ icon: Icon, tone, size = "md", label }: Props) {
  const { box, icon } = SIZE_CLASSES[size];
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={
        "inline-flex shrink-0 items-center justify-center text-white shadow-bento " +
        TONE_BG[tone] +
        " " +
        box
      }
    >
      <Icon size={icon} strokeWidth={2.25} />
    </span>
  );
}
