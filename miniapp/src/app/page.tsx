'use client';

import { useEffect, useMemo } from 'react';
import { useStore } from '@/lib/store';
import { TaskSection } from '@/components/TaskSection';
import { EmptyState } from '@/components/EmptyState';
import { TaskSkeleton } from '@/components/Skeleton';
import { SegmentedControl } from '@/components/SegmentedControl';
import type { Task } from '@/types';

function isOverdue(task: Task): boolean {
  if (!task.scheduledFor && !task.deadlineAt) return false;
  const date = task.deadlineAt || task.scheduledFor;
  if (!date) return false;
  const d = new Date(date);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return d < today && task.status !== 'done' && task.status !== 'canceled';
}

function isToday(task: Task): boolean {
  return task.status === 'today' || task.status === 'inbox';
}

function isTomorrow(task: Task): boolean {
  return task.status === 'tomorrow';
}

function hasNoDate(task: Task): boolean {
  return task.status === 'upcoming' || task.status === 'someday';
}

export default function HomePage() {
  const { tasks, loading, fetchTasks, completeTask, rescheduleTask, view, setView } = useStore();

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status !== 'done' && t.status !== 'canceled'),
    [tasks]
  );

  const overdue = useMemo(() => activeTasks.filter(isOverdue), [activeTasks]);
  const today = useMemo(() => activeTasks.filter((t) => isToday(t) && !isOverdue(t)), [activeTasks]);
  const tomorrow = useMemo(() => activeTasks.filter(isTomorrow), [activeTasks]);
  const noDate = useMemo(() => activeTasks.filter(hasNoDate), [activeTasks]);

  const handleComplete = (id: string) => completeTask(id);
  const handleReschedule = (id: string) => rescheduleTask(id, 'tomorrow');

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-[22px] font-bold">Задачи</h1>
        <span className="text-[13px] text-[var(--text-muted)]">
          {activeTasks.length} активных
        </span>
      </div>

      <div className="mb-4">
        <SegmentedControl
          value={view}
          options={[
            { value: 'list', label: 'Список' },
            { value: 'circles', label: 'Круги' },
          ]}
          onChange={(v) => {
            setView(v as 'list' | 'circles');
            if (v === 'circles') {
              window.location.href = '/circles';
            }
          }}
        />
      </div>

      {loading ? (
        <>
          <TaskSkeleton />
          <TaskSkeleton />
        </>
      ) : activeTasks.length === 0 ? (
        <EmptyState
          icon="📭"
          title="Пока пусто"
          description="Отправьте голосовое или текст боту — задачи появятся здесь"
        />
      ) : (
        <>
          <TaskSection
            title="Просрочено"
            icon="🔴"
            tasks={overdue}
            onComplete={handleComplete}
            onReschedule={handleReschedule}
          />
          <TaskSection
            title="Сегодня"
            icon="📌"
            tasks={today}
            onComplete={handleComplete}
            onReschedule={handleReschedule}
          />
          <TaskSection
            title="Завтра"
            icon="📅"
            tasks={tomorrow}
            onComplete={handleComplete}
            onReschedule={handleReschedule}
          />
          <TaskSection
            title="Без даты"
            icon="📦"
            tasks={noDate}
            onComplete={handleComplete}
            onReschedule={handleReschedule}
          />
        </>
      )}
    </div>
  );
}
