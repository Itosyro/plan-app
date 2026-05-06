'use client';

import type { Task } from '@/types';
import Link from 'next/link';

const priorityColors: Record<string, string> = {
  high: 'var(--priority-high)',
  medium: 'var(--priority-medium)',
  low: 'var(--priority-low)',
};

const priorityLabels: Record<string, string> = {
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};

interface TaskCardProps {
  task: Task;
  onComplete: (id: string) => void;
  onReschedule: (id: string) => void;
}

export function TaskCard({ task, onComplete, onReschedule }: TaskCardProps) {
  return (
    <div className="animate-fade-in bg-[var(--bg-card)] rounded-[var(--radius)] p-4 shadow-[var(--shadow)] border border-[var(--border)] mb-2.5 transition-all active:scale-[0.98]">
      <div className="flex items-start gap-3">
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onComplete(task.id);
          }}
          className="mt-0.5 w-[22px] h-[22px] rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors hover:bg-[var(--accent-light)]"
          style={{ borderColor: priorityColors[task.priority] || priorityColors.medium }}
          aria-label="Отметить выполненной"
        >
          {task.status === 'done' && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={priorityColors[task.priority]} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
        </button>

        <Link href={`/task/${task.id}`} className="flex-1 min-w-0">
          <h3
            className={`text-[15px] font-medium leading-tight ${
              task.status === 'done' ? 'line-through text-[var(--text-muted)]' : ''
            }`}
          >
            {task.title}
          </h3>

          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {task.project && (
              <span
                className="text-[11px] px-2 py-0.5 rounded-full font-medium"
                style={{
                  backgroundColor: task.project.color ? `${task.project.color}18` : 'var(--accent-light)',
                  color: task.project.color || 'var(--accent)',
                }}
              >
                {task.project.title}
              </span>
            )}

            {task.estimatedMinutes && (
              <span className="text-[11px] text-[var(--text-muted)]">
                ~{task.estimatedMinutes} мин
              </span>
            )}

            {task.deadlineAt && (
              <span className="text-[11px] text-[var(--priority-high)]">
                ⏰ {new Date(task.deadlineAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
              </span>
            )}
          </div>
        </Link>

        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onReschedule(task.id);
          }}
          className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          aria-label="Перенести"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
