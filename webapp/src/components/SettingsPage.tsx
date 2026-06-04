// Phase 7c → 7e/E2: Mini-App Settings page.
//
// Mirrors the bot's ``/settings`` keyboard surface: same fields, same
// allow-listed values, same defaults. Server-side validation lives in
// app/bot/services/settings.py::ALLOWED_SETTING_VALUES — the option
// vocabularies below MUST stay in sync (PATCH /api/me 422s otherwise).
//
// All mutations go through PATCH /api/me, which updates ``User.tz``,
// ``User.display_name`` and ``UserSettings`` in one transaction and
// returns the fresh ``Me`` payload — no extra GET round-trip.
//
// Visual language (7e/E2, Mira-inspired Telegram-native): rows are
// grouped into a single rounded card per section (iOS grouped list),
// with an accent-colored section header above. Boolean prefs use an
// iOS toggle Switch; multi-choice prefs open a bottom-sheet picker.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Globe,
  Inbox,
  Languages,
  ListChecks,
  MessageSquare,
  Moon,
  Pencil,
  Settings2,
  ShieldCheck,
  Sun,
  Sunset,
  Trash2,
  User,
  type LucideIcon,
} from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { getWebApp, haptic } from "../lib/telegram";
import { navigate } from "../lib/router";
import type { Me, TrashCounts, Timezone } from "../types";
import { BottomSheetSelect } from "./BottomSheetSelect";
import { IconTile, type TileTone } from "./IconTile";
import { Switch } from "./Switch";

// ── Settings navigation stack ──────────────────────────────────────────
type SettingsScreen = "main" | "profile" | "notifications" | "responses" | "behavior";

// Option vocabularies. These match the labels used in
// app/bot/routers/settings.py::SETTING_OPTIONS so the bot and the
// Mini-App show identical wording. Values must match
// ALLOWED_SETTING_VALUES on the server.
const CRITIC_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: "always", label: "Всегда" },
  { value: "confidence", label: "По уверенности" },
  { value: "never", label: "Никогда" },
];

const MORNING_DIGEST_OPTIONS: { value: string; label: string }[] = [
  { value: "07:00", label: "07:00" },
  { value: "08:00", label: "08:00" },
  { value: "09:00", label: "09:00" },
  { value: "10:00", label: "10:00" },
];

const EVENING_DIGEST_OPTIONS: { value: string; label: string }[] = [
  { value: "20:00", label: "20:00" },
  { value: "21:00", label: "21:00" },
  { value: "22:00", label: "22:00" },
  { value: "23:00", label: "23:00" },
];

const RESPONSE_STYLE_OPTIONS: { value: string; label: string }[] = [
  { value: "template_only", label: "Только шаблоны" },
  { value: "llm_only", label: "Только LLM" },
  { value: "mix", label: "Микс" },
];

const COURIER_TEMPLATE_OPTIONS: { value: string; label: string }[] = [
  { value: "neutral", label: "Нейтральный" },
  { value: "formal_master", label: "Слуга" },
  { value: "friendly", label: "Дружеский" },
  { value: "playful", label: "Игривый" },
  { value: "terse", label: "Лаконичный" },
  { value: "respectful", label: "Почтительный" },
];

const WEEK_DUE_SEMANTIC_OPTIONS: { value: string; label: string }[] = [
  { value: "deadline_sunday", label: "Дедлайн воскресенье" },
  { value: "deadline_saturday", label: "Дедлайн суббота" },
  { value: "spread_evenly", label: "Равномерно" },
];

interface Props {
  me: Me;
  onUpdated: (me: Me) => void;
}

export function SettingsPage({ me, onUpdated }: Props) {
  const [timezones, setTimezones] = useState<Timezone[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Pending field name while a PATCH is in flight — we use this to
  // disable the relevant control without locking the whole page.
  const [pending, setPending] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [editingTz, setEditingTz] = useState(false);
  const [trashCounts, setTrashCounts] = useState<TrashCounts | null>(null);

  // Local navigation stack — never touches the global hash router.
  const [stack, setStack] = useState<SettingsScreen[]>(["main"]);
  const [navDirection, setNavDirection] = useState<"forward" | "back">("forward");
  // Ref so the BackButton handler closure always sees fresh stack.
  const stackRef = useRef(stack);
  stackRef.current = stack;

  useEffect(() => {
    let cancelled = false;
    apiClient
      .timezones()
      .then((rows) => {
        if (!cancelled) setTimezones(rows);
      })
      .catch(() => {
        if (!cancelled) setTimezones([]);
      });
    apiClient
      .trashCounts()
      .then((counts) => {
        if (!cancelled) setTrashCounts(counts);
      })
      .catch(() => {
        // Non-fatal: badge won't show.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Telegram BackButton wiring — show when depth > 1, hide at root.
  useEffect(() => {
    const bb = getWebApp()?.BackButton;
    if (!bb) return;

    const handler = () => {
      const current = stackRef.current;
      if (current.length > 1) {
        haptic("select");
        setNavDirection("back");
        setStack((s) => s.slice(0, -1));
      }
    };

    if (stack.length > 1) {
      bb.show();
      bb.onClick(handler);
    } else {
      bb.hide();
    }

    return () => {
      // offClick is part of Bot API 6.1+; guard defensively for very old clients.
      try { bb.offClick(handler); } catch { /* ignore */ }
    };
  }, [stack.length]);

  const tzLabel = useMemo(() => {
    if (timezones === null) return me.tz;
    const hit = timezones.find((t) => t.iana === me.tz);
    return hit ? hit.label : me.tz;
  }, [timezones, me.tz]);

  async function patch<K extends string>(
    field: K,
    body: Parameters<typeof apiClient.patchMe>[0],
  ): Promise<void> {
    setPending(field);
    setError(null);
    try {
      const fresh = await apiClient.patchMe(body);
      onUpdated(fresh);
      haptic("success");
    } catch (err) {
      haptic("error");
      if (err instanceof ApiError) {
        setError(err.status === 422 ? "Значение не подходит" : "Не удалось сохранить");
      } else {
        setError("Нет связи с сервером");
      }
    } finally {
      setPending(null);
    }
  }

  function push(screen: SettingsScreen) {
    haptic("select");
    setNavDirection("forward");
    setStack((s) => [...s, screen]);
  }

  function back() {
    haptic("select");
    setNavDirection("back");
    setStack((s) => s.slice(0, -1));
  }

  const settings = me.settings;
  const currentScreen = stack[stack.length - 1];
  const animClass = navDirection === "forward" ? "animate-screen-in-right" : "animate-screen-in-left";

  // Sub-screen back header
  function SubHeader() {
    return (
      <header className="flex items-center gap-1 px-1 pb-2">
        <button
          onClick={back}
          className="ease-apple flex items-center gap-0.5 text-tg-link active:scale-90 transition-transform"
        >
          <ChevronLeft size={20} />
          <span>Настройки</span>
        </button>
      </header>
    );
  }

  // Summary value helpers for main list
  const responseSummary =
    COURIER_TEMPLATE_OPTIONS.find((o) => o.value === (settings?.courier_template_style ?? "neutral"))?.label ?? "";
  const profileSummary = me.display_name || tzLabel;
  const morningLabel =
    MORNING_DIGEST_OPTIONS.find((o) => o.value === (settings?.morning_digest_at ?? "08:00"))?.label ?? "";
  const eveningLabel =
    EVENING_DIGEST_OPTIONS.find((o) => o.value === (settings?.evening_digest_at ?? "21:00"))?.label ?? "";
  const notifSummary = `${morningLabel} / ${eveningLabel}`;
  const behaviorSummary =
    CRITIC_MODE_OPTIONS.find((o) => o.value === (settings?.critic_mode ?? "confidence"))?.label ?? "";

  return (
    <div className="flex flex-col gap-6 pb-4">
      {error && (
        <div className="rounded-3xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100 animate-fade-in">
          {error}
        </div>
      )}

      {/* ── Main list ── */}
      {currentScreen === "main" && (
        <div key="main" className={animClass}>
          <div className="flex flex-col gap-6">
            <div className="overflow-hidden rounded-3xl bg-bento-card shadow-bento ring-1 ring-black/5">
              <div className="divide-y divide-tg-divider/40">
                <MainCategoryRow
                  icon={User}
                  tone="indigo"
                  label="Профиль"
                  summary={profileSummary}
                  onClick={() => push("profile")}
                />
                <MainCategoryRow
                  icon={Bell}
                  tone="rose"
                  label="Уведомления и дайджесты"
                  summary={notifSummary}
                  onClick={() => push("notifications")}
                />
                <MainCategoryRow
                  icon={MessageSquare}
                  tone="emerald"
                  label="Ответы бота"
                  summary={`Тон: ${responseSummary}`}
                  onClick={() => push("responses")}
                />
                <MainCategoryRow
                  icon={Settings2}
                  tone="violet"
                  label="Поведение разбора"
                  summary={`Критик: ${behaviorSummary}`}
                  onClick={() => push("behavior")}
                />
              </div>
            </div>

            <SettingsSection title="Данные" index={0}>
              <CompletedRow />
              <TrashRow trashCounts={trashCounts} />
            </SettingsSection>
          </div>
        </div>
      )}

      {/* ── Profile sub-screen ── */}
      {currentScreen === "profile" && (
        <div key="profile" className={animClass}>
          <SubHeader />
          <SettingsSection title="Профиль" index={0}>
            <SettingsTextRow
              icon={User}
              tone="indigo"
              label="Имя"
              value={me.display_name ?? ""}
              placeholder="Без имени"
              editing={editingName}
              pending={pending === "display_name"}
              onEdit={() => setEditingName(true)}
              onCancel={() => setEditingName(false)}
              onSubmit={async (value) => {
                const trimmed = value.trim();
                if (!trimmed || trimmed === me.display_name) {
                  setEditingName(false);
                  return;
                }
                await patch("display_name", { display_name: trimmed });
                setEditingName(false);
              }}
            />
            <SettingsTimezoneRow
              icon={Globe}
              tone="blue"
              label="Часовой пояс"
              currentIana={me.tz}
              currentLabel={tzLabel}
              timezones={timezones ?? []}
              editing={editingTz}
              pending={pending === "tz"}
              onEdit={() => setEditingTz(true)}
              onCancel={() => setEditingTz(false)}
              onSubmit={async (iana) => {
                const trimmed = iana.trim();
                if (!trimmed || trimmed === me.tz) {
                  setEditingTz(false);
                  return;
                }
                await patch("tz", { tz: trimmed });
                setEditingTz(false);
              }}
            />
          </SettingsSection>
        </div>
      )}

      {/* ── Notifications sub-screen ── */}
      {currentScreen === "notifications" && (
        <div key="notifications" className={animClass}>
          <SubHeader />
          <div className="flex flex-col gap-6">
            <SettingsSection title="Дайджест" index={0}>
              <SettingsSelectRow
                icon={Sun}
                tone="orange"
                label="Утром"
                value={settings?.morning_digest_at ?? "08:00"}
                options={MORNING_DIGEST_OPTIONS}
                disabled={pending === "morning_digest_at"}
                onChange={(value) =>
                  patch("morning_digest_at", { settings: { morning_digest_at: value } })
                }
              />
              <SettingsSelectRow
                icon={Sunset}
                tone="amber"
                label="Вечером"
                value={settings?.evening_digest_at ?? "21:00"}
                options={EVENING_DIGEST_OPTIONS}
                disabled={pending === "evening_digest_at"}
                onChange={(value) =>
                  patch("evening_digest_at", { settings: { evening_digest_at: value } })
                }
              />
            </SettingsSection>
            <SettingsSection title="Напоминания" index={1}>
              <Row>
                <RowLabel
                  icon={Bell}
                  tone="rose"
                  label="В тот же день"
                  hint="За сколько до срока"
                />
              </Row>
              <OffsetChipRow
                offsets={settings?.default_reminder_offsets?.same_day ?? []}
                presets={SAME_DAY_PRESETS}
                disabled={pending === "default_reminder_offsets"}
                onChange={(next) =>
                  patch("default_reminder_offsets", {
                    settings: {
                      default_reminder_offsets: {
                        same_day: next,
                        multi_day:
                          settings?.default_reminder_offsets?.multi_day ?? [],
                      },
                    },
                  })
                }
              />
              <Row>
                <RowLabel
                  icon={Bell}
                  tone="rose"
                  label="За несколько дней"
                  hint="Когда срок завтра и позже"
                />
              </Row>
              <OffsetChipRow
                offsets={settings?.default_reminder_offsets?.multi_day ?? []}
                presets={MULTI_DAY_PRESETS}
                disabled={pending === "default_reminder_offsets"}
                onChange={(next) =>
                  patch("default_reminder_offsets", {
                    settings: {
                      default_reminder_offsets: {
                        same_day:
                          settings?.default_reminder_offsets?.same_day ?? [],
                        multi_day: next,
                      },
                    },
                  })
                }
              />
              <Row>
                <RowLabel
                  icon={Bell}
                  tone="slate"
                  label="Голосом"
                  hint="«напомни в 15:00 про звонок» — поставит/перенесёт"
                />
              </Row>
            </SettingsSection>
          </div>
        </div>
      )}

      {/* ── Responses sub-screen ── */}
      {currentScreen === "responses" && (
        <div key="responses" className={animClass}>
          <SubHeader />
          <SettingsSection title="Ответы бота" index={0}>
            <SettingsSelectRow
              icon={Languages}
              tone="teal"
              label="Источник"
              value={settings?.response_style_source ?? "mix"}
              options={RESPONSE_STYLE_OPTIONS}
              disabled={pending === "response_style_source"}
              onChange={(value) =>
                patch("response_style_source", { settings: { response_style_source: value } })
              }
            />
            <SettingsSelectRow
              icon={MessageSquare}
              tone="emerald"
              label="Тон"
              value={settings?.courier_template_style ?? "neutral"}
              options={COURIER_TEMPLATE_OPTIONS}
              disabled={pending === "courier_template_style"}
              onChange={(value) =>
                patch("courier_template_style", { settings: { courier_template_style: value } })
              }
            />
          </SettingsSection>
        </div>
      )}

      {/* ── Behavior sub-screen ── */}
      {currentScreen === "behavior" && (
        <div key="behavior" className={animClass}>
          <SubHeader />
          <SettingsSection title="Поведение разбора" index={0}>
            <SettingsToggleRow
              icon={ListChecks}
              tone="sky"
              label="Первый шаг"
              hint="Абстрактную задачу превращаю в конкретный первый шаг 🎯"
              checked={settings?.concretize_tasks ?? false}
              disabled={pending === "concretize_tasks"}
              onChange={(next) =>
                patch("concretize_tasks", { settings: { concretize_tasks: next } })
              }
            />
            <SettingsToggleRow
              icon={Inbox}
              tone="amber"
              label="Входящие"
              hint="Сомнительные и большие разборы отправляю на проверку во вкладку «Входящие»"
              checked={settings?.review_enabled ?? true}
              disabled={pending === "review_enabled"}
              onChange={(next) =>
                patch("review_enabled", { settings: { review_enabled: next } })
              }
            />
            <SettingsSelectRow
              icon={ShieldCheck}
              tone="violet"
              label="Критик"
              value={settings?.critic_mode ?? "confidence"}
              options={CRITIC_MODE_OPTIONS}
              disabled={pending === "critic_mode"}
              onChange={(value) => patch("critic_mode", { settings: { critic_mode: value } })}
            />
            <SettingsSelectRow
              icon={Moon}
              tone="slate"
              label="«На неделе»"
              value={settings?.week_due_semantic ?? "deadline_sunday"}
              options={WEEK_DUE_SEMANTIC_OPTIONS}
              disabled={pending === "week_due_semantic"}
              onChange={(value) =>
                patch("week_due_semantic", { settings: { week_due_semantic: value } })
              }
            />
          </SettingsSection>
        </div>
      )}
    </div>
  );
}

// ── Main-list category row ──────────────────────────────────────────────

function MainCategoryRow({
  icon,
  tone,
  label,
  summary,
  onClick,
}: {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  summary?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="ease-apple flex min-h-[56px] w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-bento/60 active:bg-bento"
    >
      <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
        <IconTile icon={icon} tone={tone} size="md" />
        <span className="truncate font-medium">{label}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
        {summary && (
          <span className="max-w-[130px] truncate">{summary}</span>
        )}
        <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
      </span>
    </button>
  );
}

// ── Section wrapper ─────────────────────────────────────────────────
//
// Mira-style grouped list: one rounded card per section holding all its
// rows with hairline dividers between them, an accent-colored header
// above. The card cascades in with a small staggered slide-up.

interface SectionProps {
  title: string;
  index: number;
  children: React.ReactNode;
}

function SettingsSection({ title, index, children }: SectionProps) {
  return (
    <section
      style={{
        animation: "sheet-row-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both",
        animationDelay: `${index * 55}ms`,
      }}
    >
      <header className="mb-2 px-4 text-[13px] font-semibold tracking-tight text-tg-link">
        {title}
      </header>
      <div className="overflow-hidden rounded-3xl bg-bento-card shadow-bento ring-1 ring-black/5">
        <div className="divide-y divide-tg-divider/40">{children}</div>
      </div>
    </section>
  );
}

// ── Grouped-list row primitive ──────────────────────────────────────

interface RowProps {
  children: React.ReactNode;
  as?: "div" | "button";
  disabled?: boolean;
  onClick?: () => void;
  ariaPressed?: boolean;
  className?: string;
}

function Row({ children, as = "div", disabled, onClick, ariaPressed, className: extraClassName }: RowProps) {
  const className =
    "ease-apple flex min-h-[56px] w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-150 " +
    (disabled ? "opacity-60 " : "") +
    (onClick && !disabled ? "hover:bg-bento/60 active:bg-bento" : "") +
    (extraClassName ? " " + extraClassName : "");
  if (as === "button") {
    return (
      <button
        type="button"
        className={className}
        onClick={onClick}
        disabled={disabled}
        aria-pressed={ariaPressed}
      >
        {children}
      </button>
    );
  }
  return <div className={className}>{children}</div>;
}

// Label cell: icon tile + (label / optional hint).
function RowLabel({
  icon,
  tone,
  label,
  hint,
}: {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  hint?: string;
}) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-3 text-[15px] text-tg-text">
      <IconTile icon={icon} tone={tone} size="md" />
      <span className="min-w-0">
        <span className="block truncate font-medium">{label}</span>
        {hint && (
          <span className="mt-0.5 block truncate text-[12px] leading-snug text-tg-hint">
            {hint}
          </span>
        )}
      </span>
    </span>
  );
}

// ── Toggle row (boolean prefs) ──────────────────────────────────────

interface ToggleRowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  hint?: string;
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
}

function SettingsToggleRow({
  icon,
  tone,
  label,
  hint,
  checked,
  disabled,
  onChange,
}: ToggleRowProps) {
  // The whole row toggles; the Switch renders presentational so we don't
  // nest a button inside a button.
  return (
    <Row
      as="button"
      disabled={disabled}
      ariaPressed={checked}
      onClick={() => onChange(!checked)}
    >
      <RowLabel icon={icon} tone={tone} label={label} hint={hint} />
      <Switch checked={checked} presentational />
    </Row>
  );
}

// ── Bell info row (static for now) ──────────────────────────────────

// ── Reminder offsets editor (WS4) ───────────────────────────────────
//
// Two presets — ``same_day`` (task due today) and ``multi_day`` (task
// due tomorrow or later) — each rendered as a row of toggleable chips.
// A chip stores its offset in minutes; toggling adds/removes the value
// from the array, and we PATCH the whole structure server-side. The
// server sorts desc + dedups + bounds 0..10080 min, so the UI just
// needs to send a clean list — no further client-side validation.

const SAME_DAY_PRESETS: { minutes: number; label: string }[] = [
  { minutes: 15, label: "15 мин" },
  { minutes: 30, label: "30 мин" },
  { minutes: 60, label: "1 час" },
  { minutes: 240, label: "4 часа" },
  { minutes: 720, label: "12 часов" },
];

const MULTI_DAY_PRESETS: { minutes: number; label: string }[] = [
  { minutes: 60, label: "1 час" },
  { minutes: 240, label: "4 часа" },
  { minutes: 1440, label: "1 день" },
  { minutes: 2880, label: "2 дня" },
  { minutes: 10080, label: "1 неделя" },
];

interface OffsetEditorProps {
  offsets: number[];
  presets: { minutes: number; label: string }[];
  disabled: boolean;
  onChange: (next: number[]) => void;
}

function OffsetChipRow({ offsets, presets, disabled, onChange }: OffsetEditorProps) {
  const selected = new Set(offsets);
  return (
    <div className="flex flex-wrap gap-1.5 px-3 py-2.5">
      {presets.map((p) => {
        const isOn = selected.has(p.minutes);
        return (
          <button
            key={p.minutes}
            type="button"
            disabled={disabled}
            onClick={() => {
              haptic("select");
              const next = new Set(selected);
              if (isOn) next.delete(p.minutes);
              else next.add(p.minutes);
              onChange([...next].sort((a, b) => b - a));
            }}
            className={
              "ease-apple rounded-full px-3 py-1 text-[12px] font-medium transition-all duration-150 active:scale-95 " +
              (isOn
                ? "bg-tg-button text-tg-button-text shadow-bento"
                : "bg-bento text-tg-hint ring-1 ring-black/[0.04] hover:text-tg-text") +
              (disabled ? " opacity-50" : "")
            }
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Completed row (history of done tasks, ≠ Trash) ──────────────────

function CompletedRow() {
  return (
    <Row as="button" onClick={() => navigate("/completed")}>
      <RowLabel
        icon={CheckCircle2}
        tone="emerald"
        label="Выполненные"
        hint="История завершённых задач"
      />
      <ChevronRight size={16} strokeWidth={2.25} className="shrink-0 text-tg-hint" aria-hidden />
    </Row>
  );
}

// ── Trash row ───────────────────────────────────────────────────────

function TrashRow({ trashCounts }: { trashCounts: TrashCounts | null }) {
  const total = trashCounts ? trashCounts.tasks + trashCounts.notes : 0;
  return (
    <Row as="button" onClick={() => navigate("/trash")}>
      <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
        <IconTile icon={Trash2} tone="slate" size="md" />
        <span className="truncate font-medium">Корзина</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
        {total > 0 && (
          <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-600">
            {total}
          </span>
        )}
        <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
      </span>
    </Row>
  );
}

// ── Generic select row ──────────────────────────────────────────────
//
// Tapping the row opens a BottomSheet picker (BottomSheetSelect).

interface SelectRowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  value: string;
  options: { value: string; label: string; hint?: string }[];
  disabled: boolean;
  onChange: (value: string) => void;
}

function SettingsSelectRow({
  icon,
  tone,
  label,
  value,
  options,
  disabled,
  onChange,
}: SelectRowProps) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  const currentLabel = current?.label ?? value;
  return (
    <>
      <Row as="button" disabled={disabled} onClick={() => setOpen(true)}>
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="font-display max-w-[160px] truncate font-medium tracking-tight text-tg-text/80">
            {currentLabel}
          </span>
          <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
        </span>
      </Row>
      <BottomSheetSelect
        open={open}
        onClose={() => setOpen(false)}
        title={label}
        options={options}
        value={value}
        onSelect={onChange}
      />
    </>
  );
}

// ── Inline-edit text row (display name) ─────────────────────────────

interface TextRowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  value: string;
  placeholder: string;
  editing: boolean;
  pending: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSubmit: (value: string) => Promise<void> | void;
}

function SettingsTextRow({
  icon,
  tone,
  label,
  value,
  placeholder,
  editing,
  pending,
  onEdit,
  onCancel,
  onSubmit,
}: TextRowProps) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    if (editing) setDraft(value);
  }, [editing, value]);

  if (!editing) {
    return (
      <Row as="button" disabled={pending} onClick={onEdit} className="animate-fade-in">
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="max-w-[160px] truncate">{value || placeholder}</span>
          <Pencil size={13} strokeWidth={2.25} aria-hidden />
          <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
        </span>
      </Row>
    );
  }

  return (
    <form
      className="flex items-center gap-2 px-4 py-3 animate-fade-in"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit(draft);
      }}
    >
      <IconTile icon={icon} tone={tone} size="md" />
      <input
        autoFocus
        type="text"
        className="min-w-0 flex-1 rounded-xl bg-bento px-3 py-1.5 text-[14px] text-tg-text focus:outline-none focus:ring-2 focus:ring-tg-button"
        value={draft}
        maxLength={128}
        placeholder={placeholder}
        disabled={pending}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
      />
      <button
        type="button"
        onClick={onCancel}
        className="ease-apple shrink-0 rounded-xl px-2.5 py-1.5 text-[13px] text-tg-hint transition-all duration-200 active:scale-[0.96]"
        disabled={pending}
      >
        Отмена
      </button>
      <button
        type="submit"
        className="ease-apple shrink-0 rounded-xl bg-tg-button px-2.5 py-1.5 text-[13px] font-medium text-tg-button-text transition-all duration-200 active:scale-[0.96] disabled:opacity-50"
        disabled={pending}
      >
        Сохранить
      </button>
    </form>
  );
}

// ── Timezone row (popular dropdown + "Другой" inline input) ─────────

interface TimezoneRowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  currentIana: string;
  currentLabel: string;
  timezones: Timezone[];
  editing: boolean;
  pending: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSubmit: (iana: string) => Promise<void> | void;
}

function SettingsTimezoneRow({
  icon,
  tone,
  label,
  currentIana,
  currentLabel,
  timezones,
  editing,
  pending,
  onEdit,
  onCancel,
  onSubmit,
}: TimezoneRowProps) {
  // Two surfaces: a tap on the row opens the popular-zones picker
  // (BottomSheetSelect). A small "Указать другой" link switches to a
  // free-text input for arbitrary IANA zones.
  const popularContains = timezones.some((t) => t.iana === currentIana);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [customMode, setCustomMode] = useState(false);
  const [draft, setDraft] = useState(currentIana);

  useEffect(() => {
    if (editing) {
      setSheetOpen(false);
      setCustomMode(!popularContains);
      setDraft(currentIana);
    } else {
      setSheetOpen(false);
      setCustomMode(false);
    }
  }, [editing, currentIana, popularContains]);

  if (!editing) {
    return (
      <Row as="button" disabled={pending} onClick={onEdit} className="animate-fade-in">
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="max-w-[160px] truncate">{currentLabel}</span>
          <Pencil size={13} strokeWidth={2.25} aria-hidden />
          <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
        </span>
      </Row>
    );
  }

  // Editing surface: a cell with an IconTile, the current picker (either
  // a tappable row → sheet OR a free-text input), and Cancel/Save.
  return (
    <>
      <form
        className="flex flex-col gap-2 px-4 py-3 animate-fade-in"
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(draft);
        }}
      >
        <div className="flex items-center gap-2">
          <IconTile icon={icon} tone={tone} size="md" />
          {customMode ? (
            <input
              autoFocus
              type="text"
              className="min-w-0 flex-1 rounded-xl bg-bento px-3 py-1.5 text-[14px] text-tg-text focus:outline-none focus:ring-2 focus:ring-tg-button animate-fade-in"
              value={draft}
              maxLength={64}
              placeholder="Europe/Moscow"
              spellCheck={false}
              disabled={pending}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  onCancel();
                }
              }}
            />
          ) : (
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              disabled={pending || timezones.length === 0}
              className="ease-apple flex min-w-0 flex-1 items-center justify-between rounded-xl bg-bento px-3 py-2 text-[14px] text-tg-text transition-all duration-200 active:scale-[0.99] hover:bg-bento/70 animate-fade-in"
            >
              <span className="truncate">
                {timezones.find((t) => t.iana === draft)?.label ?? draft}
              </span>
              <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
            </button>
          )}
        </div>
        <div className="flex items-center justify-between gap-2 text-[13px]">
          <button
            type="button"
            className="ease-apple rounded-xl px-2 py-1 text-tg-link transition-all duration-200 active:scale-[0.96]"
            onClick={() => setCustomMode((m) => !m)}
            disabled={pending}
          >
            {customMode ? "Из списка" : "Указать другой"}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="ease-apple rounded-xl px-2.5 py-1.5 text-tg-hint transition-all duration-200 active:scale-[0.96]"
              disabled={pending}
            >
              Отмена
            </button>
            <button
              type="submit"
              className="ease-apple rounded-xl bg-tg-button px-2.5 py-1.5 font-medium text-tg-button-text transition-all duration-200 active:scale-[0.96] disabled:opacity-50"
              disabled={pending}
            >
              Сохранить
            </button>
          </div>
        </div>
      </form>
      <BottomSheetSelect
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title="Часовой пояс"
        options={timezones.map((tz) => ({ value: tz.iana, label: tz.label }))}
        value={draft}
        onSelect={(value) => setDraft(value)}
      />
    </>
  );
}
