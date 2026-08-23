import { useEffect, useState } from 'react';
import { ArrowRight, Plus, Search, Trash2 } from 'lucide-react';
import { deleteProject, getProjects } from '../api/client';
import type { Project } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { PrimaryButton } from '../components/PrimaryButton';

type Props = {
  onNavigate: (path: string) => void;
};

type ProjectFilter = 'all' | 'active' | 'complete';
type ProjectSort = 'updated' | 'name';

export function WorkbenchPage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ProjectFilter>('all');
  const [sort, setSort] = useState<ProjectSort>('updated');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function loadProjects() {
    setLoading(true);
    setError(null);
    getProjects()
      .then((items) => {
        setProjects(items);
        setSelectedId((current) => current && items.some((project) => project.id === current) ? current : items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadProjects, []);

  const normalizedQuery = query.trim().toLowerCase();
  const filtered = projects
    .filter((project) => {
      const matchesQuery = !normalizedQuery || `${project.name} ${project.book_title ?? ''}`.toLowerCase().includes(normalizedQuery);
      const complete = project.progress >= 1 || project.status === 'completed';
      const matchesFilter = filter === 'all' || (filter === 'complete' ? complete : !complete);
      return matchesQuery && matchesFilter;
    })
    .sort((left, right) => sort === 'name'
      ? left.name.localeCompare(right.name, 'zh-CN')
      : new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  const selected = projects.find((project) => project.id === selectedId) ?? null;

  async function handleDelete(project: Project) {
    if (!window.confirm(`确认删除工程「${project.name}」？`)) return;
    try {
      await deleteProject(project.id);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section className="project-library-page">
      <header className="project-library-header">
        <div>
          <h1>工程</h1>
          <p>{loading ? '读取中…' : `${projects.length} 个工程`}</p>
        </div>
        <PrimaryButton onClick={() => onNavigate('/new-project')}>
          <Plus size={16} />
          新建工程
        </PrimaryButton>
      </header>
      {error ? <div className="inline-alert error">后端错误：{error}</div> : null}
      {projects.length === 0 && !loading ? (
        <EmptyState
          title="还没有工程"
          action={<PrimaryButton onClick={() => onNavigate('/new-project')}>新建工程</PrimaryButton>}
        />
      ) : (
        <div className="project-library-layout">
          <aside className="project-browser">
            <div className="project-filters">
              <label className="project-search">
                <Search aria-hidden="true" size={17} />
                <input aria-label="搜索工程" placeholder="搜索工程名称…" value={query} onChange={(event) => setQuery(event.target.value)} />
              </label>
              <div>
                <select aria-label="筛选工程" value={filter} onChange={(event) => setFilter(event.target.value as ProjectFilter)}>
                  <option value="all">全部</option>
                  <option value="active">进行中</option>
                  <option value="complete">已完成</option>
                </select>
                <select aria-label="工程排序" value={sort} onChange={(event) => setSort(event.target.value as ProjectSort)}>
                  <option value="updated">最近更新</option>
                  <option value="name">名称</option>
                </select>
              </div>
            </div>
            <div className="project-list" aria-label="工程列表">
            {filtered.map((project) => (
              <button
                aria-pressed={project.id === selectedId}
                className={`project-list-item ${project.id === selectedId ? 'selected' : ''}`}
                key={project.id}
                onClick={() => setSelectedId(project.id)}
                onDoubleClick={() => onNavigate(`/workspace/${project.id}`)}
                type="button"
              >

                  <span className="project-list-copy">
                    <strong>{project.name}</strong>
                    <small>{formatStage(project.current_stage)} · {Math.round(project.progress * 100)}%</small>
                  </span>
                  <time>{formatDate(project.updated_at)}</time>
              </button>
            ))}
            {filtered.length === 0 ? <div className="compact-empty">没有匹配工程</div> : null}
          </div>
          </aside>

          {selected ? (
            <section className="project-detail-card" aria-label={`${selected.name} 工程详情`}>
              <div className="project-cover">{selected.name.trim() || '未命名工程'}</div>
              <div className="project-detail-content">
                <div className="project-detail-meta">
                  <span><i />{formatStatus(selected.status)}</span>
                  <span>更新于 {formatDate(selected.updated_at)}</span>
                </div>
                <h2>{selected.name}</h2>
                <p>{[selected.book_title, selected.author].filter(Boolean).join(' · ') || '未填写书名与作者'}</p>
                <dl className="project-stats">
                  <div><dt>章节</dt><dd>{selected.total_chapters}</dd></div>
                  <div><dt>字数</dt><dd>{selected.total_words.toLocaleString()}</dd></div>
                  <div><dt>阶段</dt><dd>{formatStage(selected.current_stage)}</dd></div>
                  <div><dt>完成度</dt><dd className="accent">{Math.round(selected.progress * 100)}%</dd></div>
                </dl>
                <div className="project-detail-actions">
                  <PrimaryButton onClick={() => onNavigate(`/workspace/${selected.id}`)}>
                    <ArrowRight size={16} />
                    进入工程
                  </PrimaryButton>
                  <DangerButton onClick={() => void handleDelete(selected)}>
                    <Trash2 size={16} />
                    删除
                  </DangerButton>
                </div>
              </div>
            </section>
          ) : <div className="project-detail-empty">选择一个工程查看详情</div>}
        </div>
      )}
    </section>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '未知日期' : date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function formatStatus(status: string) {
  const labels: Record<string, string> = { imported: '待启动', pending: '待启动', active: '进行中', processing: '处理中', completed: '已完成', failed: '失败' };
  return labels[status] ?? status;
}

function formatStage(stage: string) {
  const labels: Record<string, string> = {
    imported: '已导入',
    split: '内容拆分',
    analyze: '章节分析',
    rewrite: '章节改写',
    export: '导出',
    completed: '已完成',
  };
  return labels[stage] ?? stage;
}
