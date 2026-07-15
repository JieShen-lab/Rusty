import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode };

export function PrimaryButton({ children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`button primary ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
