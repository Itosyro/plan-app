// Phase 7c: Mini-App Settings page.
//
// Mirrors the bot's ``/settings`` keyboard surface: same fields, same
// allow-listed values, same defaults. Server-side validation lives in
// app/bot/services/settings.py::ALLOWED_SETTING_VALUES — the option
// vocabularies below MUST stay in sync (PATCH /api/me 422s otherwise).
//
// All mutations go through PATCH /api/me, which updates ``User.tz``,
// ``User.display_name`` and ``UserSettings`` in one transaction and
// returns the fresh ``Me`` payload — no extra GET round-trip.

import { useEffect, useMemo, useState } from "react";
import {
  Bell,
  ChevronRight,
  Globe,
  Languages,
  MessageSquare,
  Moon,
  Pencil,
  ShieldCheck,
  Sun,
  Sunset,
  User,
  type LucideIcon,
} from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import type { Me, Timezone } from "../types";
import { BottomSheetSelect } from "./BottomSheetSelect";
import { IconTile, type TileTone } from "./IconTile";

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

  useEffect(() => {
    let cancelled = false;
    apiClient
      .timezones()
      .then((rows) => {
        if (!cancelled) setTimezones(rows);
      })
      .catch(() => {
        // Non-fatal: the picker falls back to free-text entry.
        if (!cancelled) setTimezones([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const settings = me.settings;

  return (
    <div className="flex flex-col gap-5 pb-4">
      {error && (
        <div className="rounded-3xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100">
          {error}
        </div>
      )}

      <SettingsSection title="Основные">
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

      <SettingsSection title="Дайджест">
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

      <SettingsSection title="Ответы бота">
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

      <SettingsSection title="Поведение">
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

      <SettingsSection title="Уведомления">
        <BellRow />
      </SettingsSection>
    </div>
  );
}

// ── Section wrapper ─────────────────────────────────────────────────
//
// Each section now renders its rows as **independent bento cards**
// separated by a small gap, rather than one card with internal
// dividers. The section title sits above the cards, in the same
// hint-color uppercase style that iOS Settings uses.

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

function SettingsSection({ title, children }: SectionProps) {
  return (
    <section>
      <header className="mb-2 px-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
        {title}
      </header>
      <div className="flex flex-col gap-1.5">{children}</div>
    </section>
  );
}

// ── Card row primitive ──────────────────────────────────────────────

interface CardRowProps {
  children: React.ReactNode;
  as?: "div" | "label" | "button" | "form";
  disabled?: boolean;
  onClick?: () => void;
}

function CardRow({ children, as = "div", disabled, onClick }: CardRowProps) {
  const className =
    "ease-apple flex items-center justify-between gap-3 rounded-2xl bg-bento-card px-4 py-3 shadow-bento ring-1 ring-black/5 transition-all duration-200 " +
    (disabled ? "opacity-60 " : "") +
    (onClick && !disabled ? "active:scale-[0.99] hover:bg-bento-card/90" : "");
  if (as === "button") {
    return (
      <button
        type="button"
        className={"text-left " + className}
        onClick={onClick}
        disabled={disabled}
      >
        {children}
      </button>
    );
  }
  if (as === "label") {
    return <label className={className}>{children}</label>;
  }
  return <div className={className}>{children}</div>;
}

// ── Bell info row (static for now) ──────────────────────────────────

function BellRow() {
  return (
    <CardRow>
      <span className="flex min-w-0 flex-1 items-center gap-3 text-[15px] text-tg-text">
        <IconTile icon={Bell} tone="rose" size="md" />
        <span className="min-w-0">
          <span className="block truncate font-medium">Напоминания</span>
          <span className="block truncate text-[12px] text-tg-hint">
            Управляются ботом / голосом
          </span>
        </span>
      </span>
      <span className="shrink-0 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-600">
        Включены
      </span>
    </CardRow>
  );
}

// ── Generic select row ──────────────────────────────────────────────
//
// Tapping the row opens a BottomSheet picker (BottomSheetSelect).
// The native ``<select>`` is gone — it rendered as a Material
// dropdown on Android, didn't honor our font/theme, and was a
// notable complaint in v13 UX feedback.

interface SelectRowProps {
  icon: LucideIcon;
  tone: TileTone;
  label: string;
  value: string;
  options: { value: string; label: string }[];
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
      <CardRow as="button" disabled={disabled} onClick={() => setOpen(true)}>
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="font-display max-w-[160px] truncate font-medium tracking-tight text-tg-text/80">
            {currentLabel}
          </span>
          <ChevronRight size={14} strokeWidth={2.25} aria-hidden />
        </span>
      </CardRow>
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
      <CardRow as="button" disabled={pending} onClick={onEdit}>
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="max-w-[160px] truncate">
            {value || placeholder}
          </span>
          <Pencil size={13} strokeWidth={2.25} aria-hidden />
          <ChevronRight size={14} strokeWidth={2.25} aria-hidden />
        </span>
      </CardRow>
    );
  }

  return (
    <form
      className="ease-apple flex items-center gap-2 rounded-2xl bg-bento-card px-4 py-3 shadow-bento ring-1 ring-tg-button/30 transition-all duration-200"
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
  // (BottomSheetSelect). A small "Указать другой" link inside the
  // sheet's footer area is not natively supported, so we expose a
  // separate "free-text" sub-row when ``editing`` is true and the
  // user explicitly entered custom mode.
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
      <CardRow as="button" disabled={pending} onClick={onEdit}>
        <span className="flex min-w-0 items-center gap-3 text-[15px] text-tg-text">
          <IconTile icon={icon} tone={tone} size="md" />
          <span className="truncate font-medium">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-tg-hint">
          <span className="max-w-[160px] truncate">{currentLabel}</span>
          <Pencil size={13} strokeWidth={2.25} aria-hidden />
          <ChevronRight size={14} strokeWidth={2.25} aria-hidden />
        </span>
      </CardRow>
    );
  }

  // Editing surface: bento card with an IconTile, the current
  // picker (either tappable row → sheet OR free-text input), and
  // Cancel/Save row.
  return (
    <>
      <form
        className="ease-apple flex flex-col gap-2 rounded-2xl bg-bento-card px-4 py-3 shadow-bento ring-1 ring-tg-button/30 transition-all duration-200"
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
              className="min-w-0 flex-1 rounded-xl bg-bento px-3 py-1.5 text-[14px] text-tg-text focus:outline-none focus:ring-2 focus:ring-tg-button"
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
              className="ease-apple flex min-w-0 flex-1 items-center justify-between rounded-xl bg-bento px-3 py-2 text-[14px] text-tg-text transition-all duration-200 active:scale-[0.99] hover:bg-bento/70"
            >
              <span className="truncate">
                {timezones.find((t) => t.iana === draft)?.label ?? draft}
              </span>
              <ChevronRight size={14} strokeWidth={2.25} aria-hidden />
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
