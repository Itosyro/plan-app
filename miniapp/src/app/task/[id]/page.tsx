'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useStore } from '@/lib/store';
import { SegmentedControl } from '@/components/SegmentedControl';
import type { Task } from '@/types';

const statusLabels: Record<string, string> = {
  inbox: 'Входящие',
  today: 'Сегодня',
  tomorrow: 'Завтра',
  upcoming: 'Скоро',
  someday: 'Когда-нибудь',
  done: 'Выполнено',
  canceled: 'Отменено',
};

const priorityLabels: Record<string, string> = {
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};

const energyLabels: Record<string, string> = {
  high: 'Высокая',
  medium: 'Средняя',
  low: 'Низкая',
};

const priorityColors: Record<string, string> = {
  high: 'var(--priority-high)',
  medium: 'var(--priority-medium)',
  low: 'var(--priority-low)',
};

export default function TaskDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { completeTask, reopenTask, deleteTask } = useStore();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('task');

  useEffect(() => {
    const id = params?.id;
    if (!id || typeof id !== 'string') return;

    api
      .getTask(id)
      .then(setTask)
      .catch(() => setTask(null))
      .finally(() => setLoading(false));
  }, [params?.id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <span className="text-4xl mb-4">🤷</span>
        <h3 className="text-[16px] font-semibold mb-1">Задача не найдена</h3>
        <button
          onClick={() => router.push('/')}
          className="mt-4 px-4 py-2 bg-[var(--accent)] text-white rounded-[var(--radius-sm)] text-[14px]"
        >
          К задачам
        </button>
      </div>
    );
  }

  const handleComplete = async () => {
    await completeTask(task.id);
    setTask({ ...task, status: 'done', completedAt: new Date().toISOString() });
  };

  const handleReopen = async () => {
    await reopenTask(task.id);
    setTask({ ...task, status: 'inbox', completedAt: null });
  };

  const handleDelete = async () => {
    await deleteTask(task.id);
    router.push('/');
  };

  const handleReschedule = async (status: string) => {
    await api.rescheduleTask(task.id, status);
    setTask({ ...task, status: status as Task['status'] });
  };

  return (
    <div className="animate-fade-in">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-[var(--accent)] text-[14px] font-medium mb-4"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Назад
      </button>

      <div className="bg-[var(--bg-card)] rounded-[var(--radius)] p-5 border border-[var(--border)] shadow-[var(--shadow)] mb-4">
        <div className="flex items-start gap-3 mb-4">
          <div
            className="w-3 h-3 rounded-full mt-1.5 flex-shrink-0"
            style={{ backgroundColor: priorityColors[task.priority] }}
          />
          <h1 className={`text-[18px] font-semibold leading-tight ${task.status === 'done' ? 'line-through text-[var(--text-muted)]' : ''}`}>
            {task.title}
          </h1>
        </div>

        {task.description && (
          <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed mb-4 pl-6">
            {task.description}
          </p>
        )}

        <div className="mb-4">
          <SegmentedControl
            value={tab}
            options={[
              { value: 'task', label: 'Задача' },
              { value: 'info', label: 'Информация' },
            ]}
            onChange={setTab}
          />
        </div>

        {tab === 'task' ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2">
              <span className="text-[13px] text-[var(--text-secondary)]">Статус</span>
              <select
                value={task.status}
                onChange={(e) => handleReschedule(e.target.value)}
                className="text-[13px] bg-[var(--bg-section)] px-3 py-1.5 rounded-[8px] border-none outline-none text-[var(--text-primary)]"
              >
                {Object.entries(statusLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {task.project && (
              <div className="flex items-center justify-between py-2">
                <span className="text-[13px] text-[var(--text-secondary)]">Проект</span>
                <span
                  className="text-[13px] px-3 py-1 rounded-full font-medium"
                  style={{
                    backgroundColor: task.project.color ? `${task.project.color}18` : 'var(--accent-light)',
                    color: task.project.color || 'var(--accent)',
                  }}
                >
                  {task.project.title}
                </span>
              </div>
            )}

            {task.notes && task.notes.length > 0 && (
              <div className="pt-2">
                <span className="text-[13px] text-[var(--text-secondary)] block mb-2">Заметки</span>
                {task.notes.map((note) => (
                  <div key={note.id} className="bg-[var(--bg-section)] rounded-[var(--radius-sm)] p-3 mb-2">
                    {note.title && <p className="text-[13px] font-medium mb-1">{note.title}</p>}
                    <p className="text-[13px] text-[var(--text-secondary)]">{note.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <InfoRow label="Приоритет" value={priorityLabels[task.priority] || task.priority} />
            <InfoRow label="Энергия" value={energyLabels[task.energyLevel] || task.energyLevel} />
            {task.estimatedMinutes && (
              <InfoRow label="Оценка" value={`${task.estimatedMinutes} мин`} />
            )}
            {task.deadlineAt && (
              <InfoRow
                label="Дедлайн"
                value={new Date(task.deadlineAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
              />
            )}
            {task.scheduledFor && (
              <InfoRow
                label="Запланировано"
                value={new Date(task.scheduledFor).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}
              />
            )}
            <InfoRow
              label="Создана"
              value={new Date(task.createdAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}
            />
            {task.completedAt && (
              <InfoRow
                label="Завершена"
                value={new Date(task.completedAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}
              />
            )}
          </div>
        )}
      </div>

      <div className="flex gap-2.5">
        {task.status === 'done' ? (
          <button
            onClick={handleReopen}
            className="flex-1 py-3 bg-[var(--accent)] text-white rounded-[var(--radius-sm)] text-[14px] font-medium active:scale-[0.98] transition-transform"
          >
            Вернуть в работу
          </button>
        ) : (
          <button
            onClick={handleComplete}
            className="flex-1 py-3 bg-[var(--accent)] text-white rounded-[var(--radius-sm)] text-[14px] font-medium active:scale-[0.98] transition-transform"
          >
            Выполнено
          </button>
        )}

        <button
          onClick={handleDelete}
          className="py-3 px-5 bg-[var(--priority-high)]10 text-[var(--priority-high)] rounded-[var(--radius-sm)] text-[14px] font-medium active:scale-[0.98] transition-transform border border-[var(--priority-high)]30"
        >
          Удалить
        </button>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--border)] last:border-b-0">
      <span className="text-[13px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[13px] text-[var(--text-primary)] font-medium">{value}</span>
    </div>
  );
}
