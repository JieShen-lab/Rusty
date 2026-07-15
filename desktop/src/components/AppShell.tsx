import type { ReactNode } from 'react';
import { Sidebar, type RouteKey } from './Sidebar';

type AppShellProps = { active: RouteKey; children: ReactNode; onNavigate: (path: string) => void };

export function AppShell({ active, children, onNavigate }: AppShellProps) {
  const edgeToEdge = active === 'workspace' || active === 'prompts' || active === 'new-project';
  return (
    <div className="app-shell">
      <div className="window-drag-region" />
      <div className="shell-body">
        <Sidebar active={active} onNavigate={onNavigate} />
        <main className={`route-content ${edgeToEdge ? 'edge-to-edge' : ''}`}>{children}</main>
      </div>
    </div>
  );
}
