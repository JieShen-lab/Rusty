import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function DangerButton({ children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`button danger ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
