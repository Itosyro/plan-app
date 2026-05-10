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
    <div className="flex flex-col gap-4 pb-4">
      {error && (
        <div className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <SettingsSection icon={User} title="Основные">
        <SettingsTextRow
          icon={User}
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

      <SettingsSection icon={Bell} title="Дайджест">
        <SettingsSelectRow
          icon={Sun}
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
          label="Вечером"
          value={settings?.evening_digest_at ?? "21:00"}
          options={EVENING_DIGEST_OPTIONS}
          disabled={pending === "evening_digest_at"}
          onChange={(value) =>
            patch("evening_digest_at", { settings: { evening_digest_at: value } })
          }
        />
      </SettingsSection>

      <SettingsSection icon={MessageSquare} title="Ответы бота">
        <SettingsSelectRow
          icon={Languages}
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
          label="Тон"
          value={settings?.courier_template_style ?? "neutral"}
          options={COURIER_TEMPLATE_OPTIONS}
          disabled={pending === "courier_template_style"}
          onChange={(value) =>
            patch("courier_template_style", { settings: { courier_template_style: value } })
          }
        />
      </SettingsSection>

      <SettingsSection icon={ShieldCheck} title="Поведение">
        <SettingsSelectRow
          icon={ShieldCheck}
          label="Критик"
          value={settings?.critic_mode ?? "confidence"}
          options={CRITIC_MODE_OPTIONS}
          disabled={pending === "critic_mode"}
          onChange={(value) => patch("critic_mode", { settings: { critic_mode: value } })}
        />
        <SettingsSelectRow
          icon={Moon}
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
  );
}

// ── Section wrapper ─────────────────────────────────────────────────

interface SectionProps {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
}

function SettingsSection({ icon: Icon, title, children }: SectionProps) {
  return (
    <section className="overflow-hidden rounded-2xl bg-tg-secondary/60">
      <header className="flex items-center gap-2 px-4 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-tg-hint">
        <Icon size={14} strokeWidth={2} aria-hidden />
        <span>{title}</span>
      </header>
      <div className="flex flex-col divide-y divide-tg-divider/60">
        {children}
      </div>
    </section>
  );
}

// ── Generic select row ──────────────────────────────────────────────

interface SelectRowProps {
  icon: LucideIcon;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  disabled: boolean;
  onChange: (value: string) => void;
}

function SettingsSelectRow({
  icon: Icon,
  label,
  value,
  options,
  disabled,
  onChange,
}: SelectRowProps) {
  return (
    <label
      className={
        "flex items-center justify-between gap-3 px-4 py-3 " +
        (disabled ? "opacity-60" : "")
      }
    >
      <span className="flex min-w-0 items-center gap-3 text-sm text-tg-text">
        <Icon size={16} strokeWidth={2} className="text-tg-hint" aria-hidden />
        <span className="truncate">{label}</span>
      </span>
      <select
        className="shrink-0 rounded-lg bg-tg-bg px-2 py-1.5 text-sm font-medium text-tg-text shadow-sm focus:outline-none focus:ring-2 focus:ring-tg-button"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ── Inline-edit text row (display name) ─────────────────────────────

interface TextRowProps {
  icon: LucideIcon;
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
  icon: Icon,
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
      <button
        type="button"
        className="flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-tg-secondary"
        onClick={onEdit}
        disabled={pending}
      >
        <span className="flex min-w-0 items-center gap-3 text-sm text-tg-text">
          <Icon size={16} strokeWidth={2} className="text-tg-hint" aria-hidden />
          <span className="truncate">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-sm text-tg-hint">
          <span className="max-w-[180px] truncate">
            {value || placeholder}
          </span>
          <Pencil size={14} strokeWidth={2} aria-hidden />
        </span>
      </button>
    );
  }

  return (
    <form
      className="flex items-center gap-2 px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit(draft);
      }}
    >
      <Icon size={16} strokeWidth={2} className="shrink-0 text-tg-hint" aria-hidden />
      <input
        autoFocus
        type="text"
        className="min-w-0 flex-1 rounded-lg bg-tg-bg px-2 py-1.5 text-sm text-tg-text shadow-sm focus:outline-none focus:ring-2 focus:ring-tg-button"
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
        className="shrink-0 rounded-lg px-2 py-1.5 text-sm text-tg-hint"
        disabled={pending}
      >
        Отмена
      </button>
      <button
        type="submit"
        className="shrink-0 rounded-lg bg-tg-text px-2 py-1.5 text-sm font-medium text-tg-bg disabled:opacity-50"
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
  icon: Icon,
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
  const popularContains = timezones.some((t) => t.iana === currentIana);
  const [mode, setMode] = useState<"popular" | "custom">(
    popularContains ? "popular" : "custom",
  );
  const [draft, setDraft] = useState(currentIana);

  useEffect(() => {
    if (editing) {
      setMode(popularContains ? "popular" : "custom");
      setDraft(currentIana);
    }
  }, [editing, currentIana, popularContains]);

  if (!editing) {
    return (
      <button
        type="button"
        className="flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-tg-secondary"
        onClick={onEdit}
        disabled={pending}
      >
        <span className="flex min-w-0 items-center gap-3 text-sm text-tg-text">
          <Icon size={16} strokeWidth={2} className="text-tg-hint" aria-hidden />
          <span className="truncate">{label}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-sm text-tg-hint">
          <span className="max-w-[180px] truncate">{currentLabel}</span>
          <Pencil size={14} strokeWidth={2} aria-hidden />
        </span>
      </button>
    );
  }

  return (
    <form
      className="flex flex-col gap-2 px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit(draft);
      }}
    >
      <div className="flex items-center gap-2">
        <Icon size={16} strokeWidth={2} className="shrink-0 text-tg-hint" aria-hidden />
        {mode === "popular" ? (
          <select
            autoFocus
            className="min-w-0 flex-1 rounded-lg bg-tg-bg px-2 py-1.5 text-sm text-tg-text shadow-sm focus:outline-none focus:ring-2 focus:ring-tg-button"
            value={draft}
            disabled={pending || timezones.length === 0}
            onChange={(e) => setDraft(e.target.value)}
          >
            {timezones.map((tz) => (
              <option key={tz.iana} value={tz.iana}>
                {tz.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            autoFocus
            type="text"
            className="min-w-0 flex-1 rounded-lg bg-tg-bg px-2 py-1.5 text-sm text-tg-text shadow-sm focus:outline-none focus:ring-2 focus:ring-tg-button"
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
        )}
      </div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <button
          type="button"
          className="text-tg-link"
          onClick={() => setMode((m) => (m === "popular" ? "custom" : "popular"))}
          disabled={pending}
        >
          {mode === "popular" ? "Указать другой" : "Из списка"}
        </button>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-2 py-1.5 text-tg-hint"
            disabled={pending}
          >
            Отмена
          </button>
          <button
            type="submit"
            className="rounded-lg bg-tg-text px-2 py-1.5 font-medium text-tg-bg disabled:opacity-50"
            disabled={pending}
          >
            Сохранить
          </button>
        </div>
      </div>
    </form>
  );
}
