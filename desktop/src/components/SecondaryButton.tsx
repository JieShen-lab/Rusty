import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function SecondaryButton({ children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-button)] border border-white/12 bg-white/[0.06] px-4 py-2.5 text-sm font-semibold text-[var(--text-main)] transition hover:border-white/25 hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
