import { useEffect, useState } from 'react';
import { ArrowRight, FileText, Search, Trash2 } from 'lucide-react';
import { deleteProject, getProjects } from '../api/client';
import type { Project } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { StatusPill, statusVariant } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

type Props = {
  onNavigate: (path: string) => void;
};

export function WorkbenchPage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function loadProjects() {
    setLoading(true);
    setError(null);
    getProjects()
      .then(setProjects)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadProjects, []);

  const filtered = projects.filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));

  async function handleDelete(project: Project) {
    if (!window.confirm(`确认删除工程「${project.name}」？`)) return;
    try {
      await deleteProject(project.id);
      loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <TopBar title="作品库" subtitle={`${projects.length} 个项目 · 点击项目直接进入对应流程`} onRefresh={loadProjects} onNewProject={() => onNavigate('/new-project')} />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {projects.length === 0 && !loading ? (
        <EmptyState
          title="还没有作品"
          description="导入 TXT / EPUB / DOCX，创建改写或分析项目。"
          action={<PrimaryButton onClick={() => onNavigate('/new-project')}>新建项目</PrimaryButton>}
        />
      ) : (
        <GlassCard strong>
          <label className="mb-4 flex max-w-md items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-[var(--text-muted)]">
            <Search size={16} />
            <input
              className="w-full bg-transparent text-white outline-none placeholder:text-[var(--text-soft)]"
              placeholder="搜索项目名称..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="divide-y divide-white/10 overflow-hidden rounded-2xl border border-white/10">
            {filtered.map((project) => (
              <div className="group flex items-center gap-4 bg-white/[0.025] px-4 py-3 transition hover:bg-white/[0.065]" key={project.id}>
                <button className="flex min-w-0 flex-1 cursor-pointer items-center gap-4 text-left" onClick={() => onNavigate(`/workspace/${project.id}`)} type="button">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-[var(--accent-gold)]">
                    <FileText size={19} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-white">{project.name}</span>
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">{project.book_title || '未命名书籍'} · {project.total_chapters} 章 · {project.total_words.toLocaleString()} 字</span>
                  </span>
                  <span className="hidden items-center gap-6 text-xs text-[var(--text-muted)] md:flex">
                    <span>{project.current_stage}</span>
                    <span>{Math.round(project.progress * 100)}%</span>
                  </span>
                  <StatusPill variant={statusVariant(project.status)}>{project.status}</StatusPill>
                  <ArrowRight className="text-[var(--text-soft)] transition group-hover:translate-x-1 group-hover:text-white" size={18} />
                </button>
                <button
                  aria-label={`删除 ${project.name}`}
                  className="rounded-lg p-2 text-[var(--text-soft)] transition hover:bg-rose-400/10 hover:text-rose-200"
                  onClick={() => handleDelete(project)}
                  title="删除项目"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
          {filtered.length === 0 && <EmptyState title="没有匹配项目" description="调整搜索条件或新建项目。" />}
        </GlassCard>
      )}
    </div>
  );
}
