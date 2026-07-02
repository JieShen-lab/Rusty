import type { ReactNode } from 'react';
import { CircleDashed } from 'lucide-react';

type EmptyStateProps = {
  title: string;
  description: string;
  action?: ReactNode;
};

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="glass-card flex min-h-[260px] flex-col items-center justify-center rounded-[var(--radius-card)] border p-8 text-center shadow-glass">
      <div className="mb-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-[var(--accent-gold)]">
        <CircleDashed size={32} />
      </div>
      <h2 className="text-xl font-semibold text-[var(--text-main)]">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-muted)]">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
