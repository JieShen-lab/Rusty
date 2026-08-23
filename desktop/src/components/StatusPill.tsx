import type { ReactNode } from 'react';

type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info';

const classes: Record<Variant, string> = {
  default: 'status-pill-default',
  success: 'status-pill-success',
  warning: 'status-pill-warning',
  danger: 'status-pill-danger',
  info: 'status-pill-info',
};

export function statusVariant(status?: string | null): Variant {
  const normalized = (status ?? '').toLowerCase();
  if (['processed', 'completed', 'rewritten', 'kept_original', 'ready'].includes(normalized)) return 'success';
  if (['processing', 'running', 'split', 'imported'].includes(normalized)) return 'info';
  if (['pending', 'draft', 'partial'].includes(normalized)) return 'warning';
  if (['failed', 'error', 'deleted'].includes(normalized)) return 'danger';
  return 'default';
}

export function StatusPill({ children, variant = 'default' }: { children: ReactNode; variant?: Variant }) {
  return (
    <span className={`status-pill inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${classes[variant]}`}>
      {children}
    </span>
  );
}
