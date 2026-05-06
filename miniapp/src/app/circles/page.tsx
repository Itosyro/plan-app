'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useStore } from '@/lib/store';
import { SegmentedControl } from '@/components/SegmentedControl';
import { EmptyState } from '@/components/EmptyState';
import Link from 'next/link';
import type { Task } from '@/types';

const prioritySizes: Record<string, number> = {
  high: 80,
  medium: 60,
  low: 45,
};

const priorityColors: Record<string, string> = {
  high: '#e85d5d',
  medium: '#e8a94d',
  low: '#8bb896',
};

function getCircleSize(task: Task): number {
  let base = prioritySizes[task.priority] || 60;
  if (task.estimatedMinutes) {
    base = Math.max(40, Math.min(100, base + task.estimatedMinutes / 5));
  }
  return base;
}

interface CircleData {
  task: Task;
  x: number;
  y: number;
  r: number;
}

function layoutCircles(tasks: Task[], width: number, height: number): CircleData[] {
  const circles: CircleData[] = [];
  const sorted = [...tasks].sort((a, b) => {
    const pOrder = { high: 0, medium: 1, low: 2 };
    return (pOrder[a.priority as keyof typeof pOrder] ?? 1) - (pOrder[b.priority as keyof typeof pOrder] ?? 1);
  });

  const centerX = width / 2;
  const centerY = height / 2;

  sorted.forEach((task, i) => {
    const r = getCircleSize(task) / 2;
    let placed = false;
    let attempt = 0;

    const angle = (i / sorted.length) * Math.PI * 2 - Math.PI / 2;
    const dist = 30 + i * 18;

    let x = centerX + Math.cos(angle) * dist;
    let y = centerY + Math.sin(angle) * dist;

    while (!placed && attempt < 100) {
      let overlaps = false;
      for (const c of circles) {
        const dx = x - c.x;
        const dy = y - c.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < r + c.r + 6) {
          overlaps = true;
          break;
        }
      }

      if (!overlaps && x - r > 5 && x + r < width - 5 && y - r > 5 && y + r < height - 5) {
        placed = true;
      } else {
        const a2 = angle + (attempt * 0.3);
        const d2 = dist + attempt * 8;
        x = centerX + Math.cos(a2) * d2;
        y = centerY + Math.sin(a2) * d2;
        attempt++;
      }
    }

    circles.push({ task, x, y, r });
  });

  return circles;
}

export default function CirclesPage() {
  const { tasks, loading, fetchTasks, setView } = useStore();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchTasks();
    setView('circles');
  }, [fetchTasks, setView]);

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status !== 'done' && t.status !== 'canceled'),
    [tasks]
  );

  const circles = useMemo(() => {
    const w = typeof window !== 'undefined' ? Math.min(window.innerWidth - 32, 400) : 360;
    const h = 400;
    return layoutCircles(activeTasks, w, h);
  }, [activeTasks]);

  const containerWidth = typeof window !== 'undefined' ? Math.min(window.innerWidth - 32, 400) : 360;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-[22px] font-bold">Задачи</h1>
      </div>

      <div className="mb-4">
        <SegmentedControl
          value="circles"
          options={[
            { value: 'list', label: 'Список' },
            { value: 'circles', label: 'Круги' },
          ]}
          onChange={(v) => {
            if (v === 'list') {
              setView('list');
              window.location.href = '/';
            }
          }}
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-[400px]">
          <div className="w-8 h-8 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
        </div>
      ) : activeTasks.length === 0 ? (
        <EmptyState
          icon="🫧"
          title="Нет активных задач"
          description="Отправьте голосовое или текст боту — задачи появятся как пузыри"
        />
      ) : (
        <div
          ref={containerRef}
          className="relative mx-auto"
          style={{ width: containerWidth, height: 400 }}
        >
          {circles.map((c) => (
            <Link
              key={c.task.id}
              href={`/task/${c.task.id}`}
              className="absolute flex items-center justify-center rounded-full transition-transform active:scale-95 shadow-[var(--shadow-md)]"
              style={{
                left: c.x - c.r,
                top: c.y - c.r,
                width: c.r * 2,
                height: c.r * 2,
                backgroundColor: `${priorityColors[c.task.priority] || priorityColors.medium}20`,
                border: `2px solid ${priorityColors[c.task.priority] || priorityColors.medium}60`,
              }}
            >
              <span
                className="text-center px-1 leading-tight font-medium"
                style={{
                  fontSize: Math.max(9, Math.min(13, c.r / 3.5)),
                  color: priorityColors[c.task.priority] || priorityColors.medium,
                  maxWidth: c.r * 1.6,
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {c.task.title}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
