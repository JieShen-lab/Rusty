import type { ReactNode } from 'react';

type MetricCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  trend?: ReactNode;
};

export function MetricCard({ label, value, hint, trend }: MetricCardProps) {
  return (
    <div className="glass-card rounded-2xl border p-5 shadow-glass">
      <p className="text-xs font-medium text-[var(--text-muted)]">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <strong className="text-3xl font-bold tracking-tight text-[var(--text-main)]">{value}</strong>
        {trend && <span className="text-xs text-[var(--accent-green)]">{trend}</span>}
      </div>
      {hint && <p className="mt-2 text-xs text-[var(--text-soft)]">{hint}</p>}
    </div>
  );
}
