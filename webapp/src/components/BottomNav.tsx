import {
  CalendarDays,
  ListTodo,
  Settings,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { haptic } from "../lib/telegram";

// Four top-level Mini-App tabs. Floating "island" nav matched to the
// Mira / Apple Bento reference: white pill, soft shadow, fixed-width
// cells so the bar doesn't reshape when switching tabs.
//
// Layout per tab: 22 px icon over an 11 px label, stacked vertically.
// Active state changes color only — width stays constant so adjacent
// tabs don't jump.
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

export function BottomNav({ active, onChange }: Props) {
  return (
    <nav
      aria-label="Главные разделы"
      className="fixed inset-x-0 z-30 flex justify-center px-4"
      style={{ bottom: "calc(var(--safe-bottom) + 0.875rem)" }}
    >
      <div className="flex items-center gap-1 rounded-3xl bg-bento-card/85 p-1.5 shadow-island ring-1 ring-black/5 backdrop-blur-xl">
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
                "ease-apple flex w-[72px] flex-col items-center justify-center gap-0.5 rounded-2xl px-2 py-1.5 transition-all duration-200 active:scale-[0.96] " +
                (isActive
                  ? "bg-tg-button/10 text-tg-button"
                  : "text-tg-hint hover:text-tg-text")
              }
            >
              <Icon
                size={22}
                strokeWidth={2.1}
                aria-hidden
                className={isActive ? "text-tg-button" : ""}
              />
              <span
                className={
                  "font-display text-[11px] leading-tight tracking-tight " +
                  (isActive ? "font-semibold" : "font-medium")
                }
              >
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
