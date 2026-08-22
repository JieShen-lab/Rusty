import type { ReactNode } from 'react';
import { CircleDashed } from 'lucide-react';

type EmptyStateProps = {
  title: string;
  action?: ReactNode;
};

export function EmptyState({ title, action }: EmptyStateProps) {
  return (
    <div className="surface-card flex min-h-[260px] flex-col items-center justify-center rounded-[var(--radius-card)] border p-8 text-center">
      <div className="mb-4 rounded-2xl border border-[var(--line)] bg-[var(--paper-muted)] p-4 text-[var(--accent)]">
        <CircleDashed size={32} />
      </div>
      <h2 className="text-xl font-semibold text-[var(--text-main)]">{title}</h2>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
