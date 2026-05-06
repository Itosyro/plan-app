'use client';

export function TaskSkeleton() {
  return (
    <div className="mb-2.5">
      <div className="skeleton h-4 w-24 mb-3" />
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="bg-[var(--bg-card)] rounded-[var(--radius)] p-4 mb-2.5 border border-[var(--border)]"
        >
          <div className="flex items-start gap-3">
            <div className="skeleton w-[22px] h-[22px] rounded-full flex-shrink-0" />
            <div className="flex-1">
              <div className="skeleton h-4 w-3/4 mb-2" />
              <div className="skeleton h-3 w-1/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function SettingsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="bg-[var(--bg-card)] rounded-[var(--radius)] p-4 border border-[var(--border)]"
        >
          <div className="flex items-center justify-between">
            <div className="skeleton h-4 w-40" />
            <div className="skeleton h-6 w-11 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
