import { Bot, BookOpen, FolderOpen, Home, Users } from 'lucide-react';

export type RouteKey = 'home' | 'library' | 'workspace' | 'models' | 'prompts' | 'anchors' | 'new-project';
type SidebarProps = { active: RouteKey; onNavigate: (path: string) => void };

const items = [
  { key: 'home', label: '工作台', path: '/home', icon: Home },
  { key: 'library', label: '工程', path: '/library', icon: FolderOpen },
  { key: 'prompts', label: '提示词', path: '/prompts', icon: BookOpen },
  { key: 'anchors', label: '人物卡', path: '/anchors', icon: Users },
  { key: 'models', label: '模型', path: '/models', icon: Bot },
] as const;

export function Sidebar({ active, onNavigate }: SidebarProps) {
  return <aside className="app-rail"><button aria-label="返回工作台" className="brand-button" onClick={() => onNavigate('/home')} type="button">R</button><nav>{items.map(({ icon: Icon, key, label, path }) => { const selected = active === key || ((active === 'new-project' || active === 'workspace') && key === 'library'); return <button aria-current={selected ? 'page' : undefined} aria-label={label} className={`rail-item ${selected ? 'selected' : ''}`} key={key} onClick={() => onNavigate(path)} title={label} type="button"><Icon size={19} /><span>{label}</span></button>; })}</nav></aside>;
}
