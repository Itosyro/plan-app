import {
  CalendarDays,
  ListTodo,
  Settings,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { haptic } from "../lib/telegram";

// Four top-level Mini-App tabs. Telegram-style floating pill: deep
// 28px radius, strong blur, soft outer shadow. The active state is a
// sliding capsule behind the icon — it animates left/right when the
// user switches tabs instead of just swapping colors. Icons gain a
// slight scale + the label switches to semibold so the active cell
// reads as "raised" even on grayscale screens.
//
// The capsule is one absolutely-positioned element translated via
// transform — keeps the layout 100% stable (no width recomputation,
// no flex jitter when switching tabs).
export type NavTab = "tasks" | "notes" | "calendar" | "settings";

interface Props {
  active: NavTab;
  onChange: (tab: NavTab) => void;
}

interface Item {
  id: NavTab;
  label: string;
  icon: LucideIcon;
}

const ITEMS: Item[] = [
  { id: "tasks", label: "Задачи", icon: ListTodo },
  { id: "notes", label: "Заметки", icon: StickyNote },
  { id: "calendar", label: "Календарь", icon: CalendarDays },
  { id: "settings", label: "Настройки", icon: Settings },
];

// Fixed cell width so the capsule can slide with a simple
// ``translateX(activeIndex * CELL_PX)``. Matches what Telegram uses
// for its 4-tab nav on phones.
const CELL_PX = 76;

export function BottomNav({ active, onChange }: Props) {
  const activeIndex = Math.max(
    0,
    ITEMS.findIndex((it) => it.id === active),
  );

  return (
    <nav
      aria-label="Главные разделы"
      className="fixed inset-x-0 z-30 flex justify-center px-4"
      style={{ bottom: "calc(var(--safe-bottom) + 0.875rem)" }}
    >
      <div
        className="rounded-[28px] bg-bento-card/80 p-1.5 shadow-island ring-1 ring-black/5 backdrop-blur-2xl"
      >
        <div
          className="relative flex items-center"
          style={{ width: `${CELL_PX * ITEMS.length}px` }}
        >
          {/* Sliding active-tab capsule. ``cubic-bezier`` matches the
              iOS / Telegram spring (soft overshoot for tactility). */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 rounded-[22px] bg-tg-button/12"
            style={{
              width: `${CELL_PX}px`,
              transform: `translateX(${activeIndex * CELL_PX}px)`,
              transition: "transform 320ms cubic-bezier(0.32, 0.72, 0.20, 1.05)",
            }}
          />
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.id === active;
            return (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  if (isActive) return;
                  haptic("select");
                  onChange(item.id);
                }}
                className={
                  "relative z-10 flex flex-col items-center justify-center gap-0.5 rounded-[22px] py-1.5 transition-colors duration-200 active:scale-[0.94] " +
                  (isActive ? "text-tg-button" : "text-tg-hint hover:text-tg-text")
                }
                style={{ width: `${CELL_PX}px` }}
              >
                <Icon
                  size={22}
                  strokeWidth={isActive ? 2.4 : 2.0}
                  aria-hidden
                  className={
                    "transition-transform duration-300 " +
                    (isActive ? "scale-110" : "scale-100")
                  }
                />
                <span
                  className={
                    "font-display text-[11px] leading-tight tracking-tight transition-all duration-200 " +
                    (isActive ? "font-semibold" : "font-medium")
                  }
                >
                  {item.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
