import type { ReactNode } from 'react';

type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info';

const classes: Record<Variant, string> = {
  default: 'border-slate-400/20 bg-slate-300/10 text-slate-300',
  success: 'border-emerald-300/25 bg-emerald-400/10 text-emerald-200',
  warning: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
  danger: 'border-rose-300/25 bg-rose-400/10 text-rose-200',
  info: 'border-sky-300/25 bg-sky-400/10 text-sky-200',
};

export function statusVariant(status?: string | null): Variant {
  const normalized = (status ?? '').toLowerCase();
  if (['processed', 'completed', 'rewritten', 'kept_original', 'ready'].includes(normalized)) return 'success';
  if (['processing', 'running', 'split', 'imported'].includes(normalized)) return 'info';
  if (['pending', 'draft', 'needs_rewrite', 'partial'].includes(normalized)) return 'warning';
  if (['failed', 'error', 'deleted'].includes(normalized)) return 'danger';
  return 'default';
}

export function StatusPill({ children, variant = 'default' }: { children: ReactNode; variant?: Variant }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${classes[variant]}`}>
      {children}
    </span>
  );
}
