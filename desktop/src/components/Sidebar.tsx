import { Bot, BookOpen, LibraryBig, FolderOpen, Moon, Sun, UserRound } from 'lucide-react';
import type { UiTheme } from '../theme';

export type RouteKey = 'library' | 'workspace' | 'models' | 'prompts' | 'authors' | 'documents' | 'new-project';
type SidebarProps = {
  active: RouteKey;
  onNavigate: (path: string) => void;
  onToggleTheme: () => void;
  theme: UiTheme;
};

const items = [
  { key: 'library', label: '工程', path: '/library', icon: FolderOpen },
  { key: 'prompts', label: '提示词', path: '/prompts', icon: BookOpen },
  { key: 'authors', label: '作者', path: '/authors', icon: UserRound },
  { key: 'documents', label: '文档库', path: '/documents', icon: LibraryBig },
  { key: 'models', label: '模型', path: '/models', icon: Bot },
] as const;

export function Sidebar({ active, onNavigate, onToggleTheme, theme }: SidebarProps) {
  const dark = theme === 'dark';
  const themeLabel = dark ? '浅色' : '深色';

  return (
    <aside className="app-rail">
      <nav>
        {items.map(({ icon: Icon, key, label, path }) => {
          const selected = active === key || ((active === 'new-project' || active === 'workspace') && key === 'library');
          return (
            <button
              aria-current={selected ? 'page' : undefined}
              aria-label={label}
              className={`rail-item ${selected ? 'selected' : ''}`}
              key={key}
              onClick={() => onNavigate(path)}
              title={label}
              type="button"
            >
              <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
      <button
        aria-label={`切换到${themeLabel}模式`}
        aria-pressed={dark}
        className="rail-item theme-toggle"
        onClick={onToggleTheme}
        title={`切换到${themeLabel}模式`}
        type="button"
      >
        {dark ? <Sun aria-hidden="true" size={20} strokeWidth={1.8} /> : <Moon aria-hidden="true" size={20} strokeWidth={1.8} />}
        <span>{themeLabel}</span>
      </button>
    </aside>
  );
}
