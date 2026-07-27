import type { ReactNode } from 'react';
import { Plus, RefreshCcw } from 'lucide-react';
import { SecondaryButton } from './SecondaryButton';
import { PrimaryButton } from './PrimaryButton';

type TopBarProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  onRefresh?: () => void;
  onNewProject?: () => void;
};

export function TopBar({ title, subtitle, actions, onRefresh, onNewProject }: TopBarProps) {
  return (
    <header className="page-topbar">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="page-topbar-actions">
        {actions}
        {onRefresh && (
          <SecondaryButton onClick={onRefresh}>
            <RefreshCcw size={16} />
            刷新
          </SecondaryButton>
        )}
        {onNewProject && (
          <PrimaryButton onClick={onNewProject}>
            <Plus size={16} />
            新建工程
          </PrimaryButton>
        )}
      </div>
    </header>
  );
}
