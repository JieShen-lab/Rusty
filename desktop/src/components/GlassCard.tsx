import type { ReactNode } from 'react';

type GlassCardProps = {
  title?: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
  strong?: boolean;
  interactive?: boolean;
};

export function GlassCard({ title, eyebrow, children, className = '', strong = false, interactive = false }: GlassCardProps) {
  return (
    <section
      className={[
        'glass-card rounded-[var(--radius-card)] border p-5 shadow-glass',
        strong ? 'glass-card-strong' : '',
        interactive ? 'transition hover:-translate-y-px hover:border-white/25 hover:bg-white/[0.08]' : '',
        className,
      ].join(' ')}
    >
      {(eyebrow || title) && (
        <header className="mb-4">
          {eyebrow && <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent-gold)]">{eyebrow}</p>}
          {title && <h2 className="text-lg font-semibold text-[var(--text-main)]">{title}</h2>}
        </header>
      )}
      {children}
    </section>
  );
}
