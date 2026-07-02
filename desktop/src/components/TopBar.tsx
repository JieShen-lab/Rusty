import { Plus, RefreshCcw } from 'lucide-react';
import { SecondaryButton } from './SecondaryButton';
import { PrimaryButton } from './PrimaryButton';

type TopBarProps = {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  onNewProject?: () => void;
};

export function TopBar({ title, subtitle, onRefresh, onNewProject }: TopBarProps) {
  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent-gold)]">Rusty Studio</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[var(--text-muted)]">{subtitle}</p>}
      </div>
      <div className="flex gap-3">
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
