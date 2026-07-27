import type { ReactNode } from 'react';

type SurfaceCardProps = {
  title?: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
};

export function SurfaceCard({ title, eyebrow, children, className = '' }: SurfaceCardProps) {
  return (
    <section className={`surface-card rounded-[var(--radius-card)] border p-5 ${className}`}>
      {(eyebrow || title) && (
        <header className="mb-4">
          {eyebrow && <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">{eyebrow}</p>}
          {title && <h2 className="text-lg font-semibold text-[var(--text-main)]">{title}</h2>}
        </header>
      )}
      {children}
    </section>
  );
}
