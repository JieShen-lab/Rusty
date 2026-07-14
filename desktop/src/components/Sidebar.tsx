import { BookOpen, Bot, Home, Library } from 'lucide-react';

export type RouteKey = 'home' | 'library' | 'workspace' | 'models' | 'prompts' | 'new-project';

type SidebarProps = {
  active: RouteKey;
  onNavigate: (path: string) => void;
};

const items = [
  { key: 'home', label: '首页', path: '/home', icon: Home },
  { key: 'library', label: '作品库', path: '/library', icon: Library },
  { key: 'prompts', label: '提示词包', path: '/prompts', icon: BookOpen },
] as const;

const modelItem = { key: 'models', label: '模型', path: '/models', icon: Bot } as const;

export function Sidebar({ active, onNavigate }: SidebarProps) {
  return (
    <aside className="glass-sidebar flex w-[88px] shrink-0 flex-col items-center gap-5 border-r border-white/10 px-3 py-5">
      <button className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/10 text-lg font-black text-[var(--accent-gold)]" type="button">R</button>
      <nav className="flex w-full flex-1 flex-col items-center gap-3">
        {items.map(({ key, label, path, icon: Icon }) => {
          const selected = active === key || (active === 'new-project' && key === 'library');
          return (
            <button
              aria-label={label}
              className={`group flex h-14 w-14 cursor-pointer flex-col items-center justify-center rounded-2xl border text-[11px] transition ${selected ? 'border-sky-300/25 bg-sky-300/15 text-white shadow-lg shadow-sky-950/30' : 'border-transparent bg-transparent text-[var(--text-soft)] hover:border-white/10 hover:bg-white/8 hover:text-white'}`}
              key={key}
              onClick={() => onNavigate(path)}
              title={label}
              type="button"
            >
              <Icon size={19} />
              <span className="mt-1">{label}</span>
            </button>
          );
        })}
        <NavItem active={active === modelItem.key} icon={modelItem.icon} label={modelItem.label} onClick={() => onNavigate(modelItem.path)} />
      </nav>
    </aside>
  );
}

function NavItem({ active, icon: Icon, label, onClick }: { active: boolean; icon: typeof Bot; label: string; onClick: () => void }) {
  return (
    <button
      aria-label={label}
      className={`group mt-auto flex h-14 w-14 cursor-pointer flex-col items-center justify-center rounded-2xl border text-[11px] transition ${active ? 'border-sky-300/25 bg-sky-300/15 text-white shadow-lg shadow-sky-950/30' : 'border-transparent bg-transparent text-[var(--text-soft)] hover:border-white/10 hover:bg-white/8 hover:text-white'}`}
      onClick={onClick}
      title={label}
      type="button"
    >
      <Icon size={19} />
      <span className="mt-1">{label}</span>
    </button>
  );
}
