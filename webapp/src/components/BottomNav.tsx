import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  Inbox,
  ListTodo,
  Settings,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { haptic } from "../lib/telegram";

// Material 3 NavigationBar with sliding active-indicator pill.
//
// Visual spec:
//   - Full-width bar flush to screen edges with a hairline top border.
//     Matches Android Telegram style (not the iOS floating island).
//   - Active tab gets an M3 "active indicator" pill: tg-button/12 tinted
//     capsule behind the icon only (not the label).
//   - Single absolutely-positioned pill element that translates to the
//     active tab center. Stays mounted and slides — no remount, pure CSS.
//   - Labels always visible under icons (M3 spec).
//   - Icon strokeWidth: active 2.25, inactive 1.75, same 22px size.
//   - Easing: cubic-bezier(0.16, 1, 0.3, 1) — expo ease-out (spring feel).
//
// Badge: numeric bubble on inbox tab, capped at 9+.
export type NavTab = "tasks" | "notes" | "calendar" | "inbox" | "settings";

interface Props {
  active: NavTab;
  onChange: (tab: NavTab) => void;
  badges?: Partial<Record<NavTab, number>>;
}

interface Item {
  id: NavTab;
  label: string;
  icon: LucideIcon;
}

const ITEMS: Item[] = [
  { id: "tasks",    label: "Задачи",    icon: ListTodo    },
  { id: "notes",    label: "Заметки",   icon: StickyNote  },
  { id: "calendar", label: "Календарь", icon: CalendarDays },
  { id: "inbox",    label: "Входящие",  icon: Inbox       },
  { id: "settings", label: "Настройки", icon: Settings    },
];

// M3 active indicator dimensions (px).
const PILL_W = 56;
const PILL_H = 32;

export function BottomNav({ active, onChange, badges }: Props) {
  const activeIndex = Math.max(
    0,
    ITEMS.findIndex((it) => it.id === active),
  );

  // Track rendered cell widths to center the pill precisely.
  const cellRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pillX, setPillX] = useState(0);

  useEffect(() => {
    const el = cellRefs.current[activeIndex];
    if (!el) return;
    const { offsetLeft, offsetWidth } = el;
    setPillX(offsetLeft + offsetWidth / 2 - PILL_W / 2);
  }, [activeIndex]);

  return (
    <nav
      aria-label="Главные разделы"
      className="fixed inset-x-0 bottom-0 z-30"
      style={{ paddingBottom: "var(--safe-bottom, 0px)" }}
    >
      {/* Hairline top border + frosted glass bar */}
      <div className="border-t border-black/[0.04] bg-tg-bg/95 backdrop-blur-xl dark:border-white/[0.06]">
        <div className="relative flex items-stretch">
          {/* M3 active-indicator pill: single element, translates to active tab */}
          <span
            aria-hidden
            className="pointer-events-none absolute top-2 rounded-full bg-tg-button/[0.12]"
            style={{
              width: `${PILL_W}px`,
              height: `${PILL_H}px`,
              transform: `translateX(${pillX}px)`,
              transition: "transform 220ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />

          {ITEMS.map((item, i) => {
            const Icon = item.icon;
            const isActive = item.id === active;
            const badge = badges?.[item.id] ?? 0;
            return (
              <button
                key={item.id}
                ref={(el) => { cellRefs.current[i] = el; }}
                type="button"
                aria-label={badge > 0 ? `${item.label} (${badge})` : item.label}
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  if (isActive) return;
                  haptic("select");
                  onChange(item.id);
                }}
                className="relative z-10 flex flex-1 flex-col items-center gap-0.5 pb-1.5 pt-2"
              >
                {/* Icon zone — pill sits behind this */}
                <span className="relative flex h-8 w-14 items-center justify-center">
                  <Icon
                    size={22}
                    strokeWidth={isActive ? 2.25 : 1.75}
                    aria-hidden
                    className={
                      "transition-colors duration-150 " +
                      (isActive ? "text-tg-button" : "text-tg-hint")
                    }
                  />
                  {badge > 0 && (
                    <span
                      aria-hidden
                      className="absolute right-0.5 top-0 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-tg-button-text ring-2 ring-tg-bg"
                    >
                      {badge > 9 ? "9+" : badge}
                    </span>
                  )}
                </span>
                {/* Label */}
                <span
                  className={
                    "text-[10.5px] leading-tight tracking-tight transition-colors duration-150 " +
                    (isActive
                      ? "font-medium text-tg-button"
                      : "font-normal text-tg-hint")
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
