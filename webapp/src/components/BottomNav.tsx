import { CalendarDays, ListTodo, Settings, type LucideIcon } from "lucide-react";
import { haptic } from "../lib/telegram";

// Three top-level Mini-App tabs. Only "tasks" is wired to real
// content right now — "calendar" and "settings" stub out as
// onClick → placeholder routes so the nav is testable end-to-end
// without blocking PR B on PR C/D.
export type NavTab = "tasks" | "calendar" | "settings";

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
  { id: "calendar", label: "Календарь", icon: CalendarDays },
  { id: "settings", label: "Настройки", icon: Settings },
];

export function BottomNav({ active, onChange }: Props) {
  return (
    <nav
      aria-label="Главные разделы"
      className="fixed inset-x-0 z-30 flex justify-center"
      style={{ bottom: "calc(var(--safe-bottom) + 0.75rem)" }}
    >
      <div className="flex items-center gap-1 rounded-full border border-tg-divider bg-tg-bg/95 px-1.5 py-1.5 shadow-lg backdrop-blur">
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
                "flex items-center gap-1.5 rounded-full px-3 py-2 text-sm transition-all " +
                (isActive
                  ? "bg-tg-text text-tg-bg shadow-sm"
                  : "text-tg-hint hover:text-tg-text")
              }
            >
              <Icon size={18} strokeWidth={2} aria-hidden />
              {/* Label only shows on the active tab — keeps the bar
                  compact at narrow viewports. Inactive tabs are
                  icon-only with aria-label for screen readers. */}
              {isActive && <span className="font-medium">{item.label}</span>}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
