import type { ReactNode } from 'react';
import { Sidebar, type RouteKey } from './Sidebar';

type AppShellProps = {
  active: RouteKey;
  children: ReactNode;
  onNavigate: (path: string) => void;
};

export function AppShell({ active, children, onNavigate }: AppShellProps) {
  const constrained = active === 'workspace' || active === 'prompts';
  return (
    <div className={`app-shell text-[var(--text-main)] ${constrained ? 'h-screen overflow-hidden' : 'min-h-screen'}`}>
      <div className="window-drag-region" />
      <div className="ambient-layer" />
      <div className={`relative z-10 flex pt-9 ${constrained ? 'h-screen min-h-0' : 'min-h-screen'}`}>
        <Sidebar active={active} onNavigate={onNavigate} />
        <main className={`min-w-0 flex-1 px-7 py-6 max-lg:px-4 ${constrained ? 'h-full min-h-0 overflow-hidden' : ''}`}>{children}</main>
      </div>
    </div>
  );
}
