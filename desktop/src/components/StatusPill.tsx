import type { ReactNode } from 'react';

type Variant = 'success' | 'warning' | 'info';

const classes: Record<Variant, string> = {
  success: 'status-pill-success',
  warning: 'status-pill-warning',
  info: 'status-pill-info',
};

export function StatusPill({ children, variant }: { children: ReactNode; variant: Variant }) {
  return (
    <span className={`status-pill inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${classes[variant]}`}>
      {children}
    </span>
  );
}
