import type { ReactNode } from 'react';
import type { UiTheme } from '../theme';
import { Sidebar, type RouteKey } from './Sidebar';

type AppShellProps = {
  active: RouteKey;
  children: ReactNode;
  onNavigate: (path: string) => void;
  onToggleTheme: () => void;
  theme: UiTheme;
};

export function AppShell({ active, children, onNavigate, onToggleTheme, theme }: AppShellProps) {
  const edgeToEdge = active === 'workspace' || active === 'prompts' || active === 'new-project';
  return (
    <div className="app-shell">
      <div className="window-drag-region" />
      <div className="shell-body">
        <Sidebar active={active} onNavigate={onNavigate} onToggleTheme={onToggleTheme} theme={theme} />
        <main className={`route-content ${edgeToEdge ? 'edge-to-edge' : ''}`}>{children}</main>
      </div>
    </div>
  );
}
