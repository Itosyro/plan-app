interface Props {
  emoji: string;
  title: string;
  hint: string;
}

export function EmptyState({ emoji, title, hint }: Props) {
  return (
    <div className="mt-12 flex flex-col items-center px-6 text-center">
      <div className="text-5xl">{emoji}</div>
      <h2 className="mt-3 text-lg font-medium text-tg-text">{title}</h2>
      <p className="mt-1 text-sm text-tg-hint">{hint}</p>
    </div>
  );
}
