import { BookOpen, Bot, Home, Library, MapPinned, Palette } from 'lucide-react';

export type RouteKey = 'home' | 'library' | 'workspace' | 'models' | 'prompts' | 'styles' | 'anchors' | 'new-project';

type SidebarProps = {
  active: RouteKey;
  onNavigate: (path: string) => void;
};

const items = [
  { key: 'home', label: '首页', path: '/home', icon: Home },
  { key: 'library', label: '作品库', path: '/library', icon: Library },
  { key: 'prompts', label: 'Prompts', cn: '提示词', path: '/prompts', icon: BookOpen },
  { key: 'styles', label: 'Styles', cn: '风格', path: '/styles', icon: Palette },
  { key: 'anchors', label: 'Anchors', cn: '锚点', path: '/anchors', icon: MapPinned },
] as const;

const modelItem = { key: 'models', label: '模型', path: '/models', icon: Bot } as const;

export function Sidebar({ active, onNavigate }: SidebarProps) {
  return (
    <aside className="glass-sidebar flex w-[88px] shrink-0 flex-col items-center gap-5 border-r border-white/10 px-3 py-5">
      <button className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/10 text-lg font-black text-[var(--accent-gold)]">
        R
      </button>
      <nav className="flex w-full flex-1 flex-col items-center gap-3">
        {items.map(({ key, label, path, icon: Icon, ...item }) => {
          const cn = 'cn' in item ? item.cn : label;
          const selected = active === key || (active === 'new-project' && key === 'library');
          return (
            <button
              aria-label={label}
              className={[
                'group flex h-14 w-14 cursor-pointer flex-col items-center justify-center rounded-2xl border text-[11px] transition',
                selected
                  ? 'border-sky-300/25 bg-sky-300/15 text-white shadow-lg shadow-sky-950/30'
                  : 'border-transparent bg-transparent text-[var(--text-soft)] hover:border-white/10 hover:bg-white/8 hover:text-white',
              ].join(' ')}
              key={key}
              onClick={() => onNavigate(path)}
              title={cn}
            >
              <Icon size={19} />
              <span className="mt-1">{cn}</span>
            </button>
          );
        })}
        <NavItem
          active={active === modelItem.key}
          icon={modelItem.icon}
          label={modelItem.label}
          onClick={() => onNavigate(modelItem.path)}
          className="mt-auto"
        />
      </nav>
    </aside>
  );
}

function NavItem({ active, className = '', icon: Icon, label, onClick }: { active: boolean; className?: string; icon: typeof Bot; label: string; onClick: () => void }) {
  return (
    <button
      aria-label={label}
      className={`group flex h-14 w-14 cursor-pointer flex-col items-center justify-center rounded-2xl border text-[11px] transition ${active ? 'border-sky-300/25 bg-sky-300/15 text-white shadow-lg shadow-sky-950/30' : 'border-transparent bg-transparent text-[var(--text-soft)] hover:border-white/10 hover:bg-white/8 hover:text-white'} ${className}`}
      onClick={onClick}
      title={label}
      type="button"
    >
      <Icon size={19} />
      <span className="mt-1">{label}</span>
    </button>
  );
}
