import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function PrimaryButton({ children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-button)] bg-[linear-gradient(135deg,var(--accent-gold),var(--accent-blue))] px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-black/20 transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
