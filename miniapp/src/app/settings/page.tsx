'use client';

import { useEffect } from 'react';
import { useStore } from '@/lib/store';
import { Toggle } from '@/components/Toggle';
import { SettingsSkeleton } from '@/components/Skeleton';

interface SettingRowProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}

function SettingRow({ label, description, checked, onChange }: SettingRowProps) {
  return (
    <div className="flex items-center justify-between py-3.5 px-4 bg-[var(--bg-card)] rounded-[var(--radius)] border border-[var(--border)] shadow-[var(--shadow)] mb-2.5">
      <div className="flex-1 mr-3">
        <span className="text-[14px] font-medium text-[var(--text-primary)]">{label}</span>
        {description && (
          <p className="text-[12px] text-[var(--text-muted)] mt-0.5">{description}</p>
        )}
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export default function SettingsPage() {
  const { settings, fetchSettings, updateSettings, loading } = useStore();

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  if (!settings) {
    return (
      <div>
        <h1 className="text-[22px] font-bold mb-4">Настройки</h1>
        <SettingsSkeleton />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-[22px] font-bold mb-5">Настройки</h1>

      <div className="mb-5">
        <h2 className="text-[13px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2.5 px-1">
          Уведомления
        </h2>

        <SettingRow
          label="Напоминания"
          description="Уведомления о задачах"
          checked={settings.remindersEnabled}
          onChange={(v) => updateSettings({ remindersEnabled: v })}
        />

        <SettingRow
          label="Summary после обработки"
          description="Краткий итог после разбора сообщения"
          checked={settings.postProcessingSummaryEnabled}
          onChange={(v) => updateSettings({ postProcessingSummaryEnabled: v })}
        />

        <SettingRow
          label="Ежедневный дайджест"
          description="Список задач на день каждое утро"
          checked={settings.dailyDigestEnabled}
          onChange={(v) => updateSettings({ dailyDigestEnabled: v })}
        />

        {settings.dailyDigestEnabled && (
          <div className="flex items-center justify-between py-3.5 px-4 bg-[var(--bg-card)] rounded-[var(--radius)] border border-[var(--border)] shadow-[var(--shadow)] mb-2.5">
            <span className="text-[14px] font-medium">Время дайджеста</span>
            <input
              type="time"
              value={settings.dailyDigestTime || '09:00'}
              onChange={(e) => updateSettings({ dailyDigestTime: e.target.value })}
              className="bg-[var(--bg-section)] px-3 py-1.5 rounded-[8px] text-[13px] border-none outline-none"
            />
          </div>
        )}

        <SettingRow
          label="Пинг зависших задач"
          description="Напоминать о задачах без движения"
          checked={settings.stuckTasksPingEnabled}
          onChange={(v) => updateSettings({ stuckTasksPingEnabled: v })}
        />
      </div>

      <div className="mb-5">
        <h2 className="text-[13px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2.5 px-1">
          Задачи
        </h2>

        <SettingRow
          label="Удалять при выполнении"
          description="Скрывать задачу после отметки «Выполнено»"
          checked={settings.deleteTaskOnDone}
          onChange={(v) => updateSettings({ deleteTaskOnDone: v })}
        />

        <SettingRow
          label="Удалять заметки с задачей"
          description="При удалении задачи удалять связанные заметки"
          checked={settings.deleteNotesWithTask}
          onChange={(v) => updateSettings({ deleteNotesWithTask: v })}
        />
      </div>

      <div>
        <h2 className="text-[13px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2.5 px-1">
          Интерфейс
        </h2>

        <SettingRow
          label="Режим «Круги»"
          description="Альтернативный визуальный вид задач"
          checked={settings.circlesViewEnabled}
          onChange={(v) => updateSettings({ circlesViewEnabled: v })}
        />
      </div>
    </div>
  );
}
