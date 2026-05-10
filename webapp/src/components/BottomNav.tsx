import { CalendarDays, ListTodo, Settings, type LucideIcon } from "lucide-react";
import { haptic } from "../lib/telegram";

// Three top-level Mini-App tabs. Floating "island" nav matched to the
// Mira / Apple Bento reference: white pill, soft shadow, active tab
// gets a tinted oval pill behind icon + label so it reads as
// "selected state" without being noisy.
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
      style={{ bottom: "calc(var(--safe-bottom) + 0.875rem)" }}
    >
      <div className="flex items-center gap-1 rounded-full bg-bento-card/85 p-1.5 shadow-island ring-1 ring-black/5 backdrop-blur-xl">
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
                "ease-apple flex items-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-medium transition-all duration-300 active:scale-[0.96] " +
                (isActive
                  ? "bg-tg-button/10 text-tg-button"
                  : "text-tg-hint hover:text-tg-text")
              }
            >
              <Icon
                size={18}
                strokeWidth={2.2}
                aria-hidden
                className={isActive ? "text-tg-button" : ""}
              />
              {/* Label only renders on the active tab — keeps the
                  bar compact at narrow viewports. Inactive tabs
                  stay icon-only with aria-label for screen readers. */}
              {isActive && <span className="font-display tracking-tight">{item.label}</span>}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
