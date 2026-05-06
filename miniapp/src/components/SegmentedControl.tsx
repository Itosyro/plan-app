'use client';

interface SegmentedControlProps {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}

export function SegmentedControl({ value, options, onChange }: SegmentedControlProps) {
  return (
    <div className="flex bg-[var(--bg-section)] rounded-[var(--radius-sm)] p-1 gap-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`flex-1 py-2 px-3 text-[13px] font-medium rounded-[8px] transition-all ${
            value === option.value
              ? 'bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-muted)]'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
