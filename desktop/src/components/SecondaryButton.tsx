import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function SecondaryButton({ children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`button secondary ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
