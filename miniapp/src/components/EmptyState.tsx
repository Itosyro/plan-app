'use client';

interface EmptyStateProps {
  icon: string;
  title: string;
  description: string;
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center animate-fade-in">
      <span className="text-4xl mb-4">{icon}</span>
      <h3 className="text-[16px] font-semibold text-[var(--text-primary)] mb-1.5">{title}</h3>
      <p className="text-[13px] text-[var(--text-muted)] leading-relaxed max-w-[260px]">{description}</p>
    </div>
  );
}
