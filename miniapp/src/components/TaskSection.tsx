'use client';

import type { Task } from '@/types';
import { TaskCard } from './TaskCard';

interface TaskSectionProps {
  title: string;
  tasks: Task[];
  icon?: string;
  onComplete: (id: string) => void;
  onReschedule: (id: string) => void;
}

export function TaskSection({ title, tasks, icon, onComplete, onReschedule }: TaskSectionProps) {
  if (tasks.length === 0) return null;

  return (
    <section className="mb-5">
      <h2 className="text-[13px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2.5 px-1">
        {icon && <span className="mr-1">{icon}</span>}
        {title}
        <span className="ml-1.5 text-[var(--text-muted)] font-normal normal-case">
          {tasks.length}
        </span>
      </h2>

      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onComplete={onComplete}
          onReschedule={onReschedule}
        />
      ))}
    </section>
  );
}
