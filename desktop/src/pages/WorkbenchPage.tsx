import { useEffect, useState } from 'react';
import { ArrowRight, Search, Trash2 } from 'lucide-react';
import { deleteProject, getProjects } from '../api/client';
import type { Project } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill, statusVariant } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

type Props = {
  onNavigate: (path: string) => void;
};

export function WorkbenchPage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function loadProjects() {
    setLoading(true);
    setError(null);
    getProjects()
      .then((items) => {
        setProjects(items);
        setSelectedId((current) => current ?? items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadProjects, []);

  const filtered = projects.filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));
  const selected = filtered.find((project) => project.id === selectedId) ?? filtered[0] ?? null;

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
      <TopBar title="作品库" subtitle={`${projects.length} 个项目 · 本地 SQLite 工作区`} onRefresh={loadProjects} onNewProject={() => onNavigate('/new-project')} />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {projects.length === 0 && !loading ? (
        <EmptyState
          title="还没有作品"
          description="导入 TXT / EPUB / DOCX 创建第一个改写工程。"
          action={<PrimaryButton onClick={() => onNavigate('/new-project')}>新建工程</PrimaryButton>}
        />
      ) : (
        <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
          <GlassCard title="项目列表" strong>
            <label className="mb-4 flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-[var(--text-muted)]">
              <Search size={16} />
              <input
                className="w-full bg-transparent text-white outline-none placeholder:text-[var(--text-soft)]"
                placeholder="搜索项目名称..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="space-y-3">
              {filtered.map((project) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selected?.id === project.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={project.id}
                  onClick={() => setSelectedId(project.id)}
                  onDoubleClick={() => onNavigate(`/workspace/${project.id}`)}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/8 text-xs font-black text-[var(--accent-gold)]">
                      {(project.source_format ?? 'TXT').toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-white">{project.name}</p>
                      <p className="mt-1 text-xs text-[var(--text-muted)]">{project.total_chapters} 章 · {project.total_words.toLocaleString()} 字</p>
                    </div>
                    <StatusPill variant={statusVariant(project.status)}>{project.status}</StatusPill>
                  </div>
                </button>
              ))}
            </div>
          </GlassCard>

          <GlassCard title="项目详情" eyebrow="Selected Project" strong>
            {selected ? (
              <div className="grid grid-cols-[220px_1fr] gap-6 max-xl:grid-cols-1">
                <div className="flex min-h-72 items-center justify-center rounded-3xl border border-white/10 bg-white/[0.04] text-3xl font-black text-[var(--accent-gold)]">
                  {(selected.source_format ?? 'BOOK').toUpperCase()}
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill variant={statusVariant(selected.status)}>{selected.status}</StatusPill>
                    <StatusPill variant="info">{selected.current_stage}</StatusPill>
                  </div>
                  <h2 className="mt-5 text-3xl font-bold text-white">{selected.name}</h2>
                  <p className="mt-2 text-sm text-[var(--text-muted)]">{selected.book_title || '暂无书籍标题'} · {selected.author || '未知作者'}</p>
                  <div className="mt-6 grid grid-cols-4 gap-3 max-xl:grid-cols-2">
                    <DetailMetric label="章节" value={selected.total_chapters} />
                    <DetailMetric label="字数" value={selected.total_words.toLocaleString()} />
                    <DetailMetric label="阶段" value={selected.current_stage} />
                    <DetailMetric label="完成度" value={`${Math.round(selected.progress * 100)}%`} />
                  </div>
                  <div className="mt-7 flex flex-wrap gap-3">
                    <PrimaryButton onClick={() => onNavigate(`/workspace/${selected.id}`)}>
                      进入创作台
                      <ArrowRight size={16} />
                    </PrimaryButton>
                    <SecondaryButton onClick={() => onNavigate('/new-project')}>新建工程</SecondaryButton>
                    <DangerButton onClick={() => handleDelete(selected)}>
                      <Trash2 size={16} />
                      删除项目
                    </DangerButton>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState title="没有匹配项目" description="调整搜索条件或创建新的改写工程。" />
            )}
          </GlassCard>
        </div>
      )}
    </div>
  );
}

function DetailMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <p className="text-xs text-[var(--text-soft)]">{label}</p>
      <p className="mt-2 font-semibold text-white">{value}</p>
    </div>
  );
}
