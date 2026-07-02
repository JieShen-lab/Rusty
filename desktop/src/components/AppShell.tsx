import type { ReactNode } from 'react';
import { Sidebar, type RouteKey } from './Sidebar';

type AppShellProps = {
  active: RouteKey;
  children: ReactNode;
  onNavigate: (path: string) => void;
};

export function AppShell({ active, children, onNavigate }: AppShellProps) {
  return (
    <div className="app-shell min-h-screen text-[var(--text-main)]">
      <div className="window-drag-region" />
      <div className="ambient-layer" />
      <div className="relative z-10 flex min-h-screen pt-9">
        <Sidebar active={active} onNavigate={onNavigate} />
        <main className="min-w-0 flex-1 px-7 py-6 max-lg:px-4">{children}</main>
      </div>
    </div>
  );
}
