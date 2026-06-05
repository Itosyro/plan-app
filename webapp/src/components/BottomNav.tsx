import {
  CalendarDays,
  Inbox,
  ListTodo,
  Settings,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { haptic } from "../lib/telegram";

// Five top-level Mini-App tabs. Telegram-style floating pill: deep
// 28px radius, strong blur, soft outer shadow. The active state is a
// sliding capsule behind the icon — it animates left/right when the
// user switches tabs instead of just swapping colors. Icons gain a
// slight scale + the label switches to semibold so the active cell
// reads as "raised" even on grayscale screens.
//
// The capsule is one absolutely-positioned element translated via
// transform — keeps the layout 100% stable (no width recomputation,
// no flex jitter when switching tabs).
export type NavTab = "tasks" | "notes" | "calendar" | "inbox" | "settings";

interface Props {
  active: NavTab;
  onChange: (tab: NavTab) => void;
  // Optional per-tab counts shown as a small bubble (e.g. «Входящие»
  // pending-review count). Zero / missing → no bubble.
  badges?: Partial<Record<NavTab, number>>;
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
  { id: "inbox", label: "Входящие", icon: Inbox },
  { id: "settings", label: "Настройки", icon: Settings },
];

// Fixed cell width so the capsule can slide with a simple
// ``translateX(activeIndex * CELL_PX)``. Narrowed from 86 to fit five
// cells on a phone-width island (5 × 68 + padding ≈ 356px) while still
// keeping ≥56px touch targets and readable labels.
const CELL_PX = 68;

export function BottomNav({ active, onChange, badges }: Props) {
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
      <div className="rounded-[30px] bg-bento-card/85 p-2 shadow-island ring-1 ring-black/[0.06] backdrop-blur-2xl">
        <div
          className="relative flex items-center"
          style={{ width: `${CELL_PX * ITEMS.length}px` }}
        >
          {/* Sliding active-tab capsule — a clear filled pill (Mira
              style) so the current tab reads unmistakably. cubic-bezier
              matches the iOS / Telegram spring (soft overshoot). */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 rounded-[24px] bg-tg-button/[0.14] ring-1 ring-tg-button/[0.10]"
            style={{
              width: `${CELL_PX}px`,
              transform: `translateX(${activeIndex * CELL_PX}px)`,
              transition: "transform 340ms cubic-bezier(0.32, 0.72, 0.20, 1.05)",
            }}
          />
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.id === active;
            const badge = badges?.[item.id] ?? 0;
            return (
              <button
                key={item.id}
                type="button"
                aria-label={
                  badge > 0 ? `${item.label} (${badge})` : item.label
                }
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  if (isActive) return;
                  haptic("select");
                  onChange(item.id);
                }}
                className={
                  "relative z-10 flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-[24px] py-2 transition-colors duration-200 active:scale-[0.94] " +
                  // Inactive: solid black icon + label (Mira style, not
                  // washed-out grey). Active: turns blue inside the pill.
                  (isActive ? "text-tg-button" : "text-tg-text/90 hover:text-tg-text")
                }
                style={{ width: `${CELL_PX}px` }}
              >
                <span className="relative">
                  <Icon
                    size={24}
                    strokeWidth={isActive ? 2.5 : 2.0}
                    aria-hidden
                    className={
                      "transition-transform duration-300 " +
                      (isActive ? "scale-110" : "scale-100")
                    }
                  />
                  {badge > 0 && (
                    <span
                      aria-hidden
                      className="absolute -right-2.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-bento-card"
                    >
                      {badge > 9 ? "9+" : badge}
                    </span>
                  )}
                </span>
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
