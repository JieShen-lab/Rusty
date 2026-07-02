import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, Compass, PenLine } from 'lucide-react';
import { getProjects } from '../api/client';
import type { Project } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { MetricCard } from '../components/MetricCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill, statusVariant } from '../components/StatusPill';

type Props = {
  onNavigate: (path: string) => void;
};

export function HomePage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setLoading(true);
    getProjects()
      .then(setProjects)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const totalChapters = projects.reduce((sum, project) => sum + project.total_chapters, 0);
  const completedChapters = projects.reduce((sum, project) => sum + project.completed_chapters, 0);
  const pendingChapters = Math.max(totalChapters - completedChapters, 0);
  const recent = projects.slice(0, 4);

  return (
    <div className="space-y-6">
      <section className="mx-auto max-w-4xl py-8 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          {now.toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
        </p>
        <h1 className="mt-3 text-6xl font-black tracking-[-0.06em] text-white max-md:text-4xl">
          {now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </h1>
        <p className="mt-4 text-lg text-[var(--text-muted)]">Build in public, write in private.</p>
        <div className="mt-5 flex justify-center gap-2">
          {['策划', '脚本', '改写', '发布'].map((tag) => (
            <StatusPill key={tag} variant="warning">
              {tag}
            </StatusPill>
          ))}
        </div>
      </section>

      {error && <GlassCard className="border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}

      <div className="grid grid-cols-4 gap-4 max-xl:grid-cols-2 max-sm:grid-cols-1">
        <MetricCard label="本月改写章节" value={completedChapters} hint={loading ? '读取中' : '来自本地项目进度'} />
        <MetricCard label="作品库项目数" value={projects.length} hint="SQLite 本地项目" />
        <MetricCard label="草稿数" value={projects.filter((project) => project.status === 'draft').length} hint="待启动工程" />
        <MetricCard label="待处理章节数" value={pendingChapters} hint="总章节减已完成" />
      </div>

      <div className="grid grid-cols-[1fr_1.3fr_1fr] gap-5 max-xl:grid-cols-1">
        <GlassCard title="本地创作工作台" eyebrow="Studio">
          <div className="flex items-start gap-4">
            <div className="rounded-3xl border border-white/10 bg-white/10 p-4 text-[var(--accent-gold)]">
              <PenLine size={34} />
            </div>
            <div>
              <p className="text-sm leading-6 text-[var(--text-muted)]">
                Rusty 保留 Python 业务层，UI-R2 将项目浏览、章节阅读和改写状态迁移到 Electron + React。
              </p>
              <SecondaryButton className="mt-5" onClick={() => onNavigate('/library')}>
                打开作品库
              </SecondaryButton>
            </div>
          </div>
        </GlassCard>

        <GlassCard title="快速入口" eyebrow="Command Center">
          <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
            <button className="command-tile" onClick={() => onNavigate('/library')}>
              <BookOpen size={22} />
              <span>管理作品</span>
              <ArrowRight size={16} />
            </button>
            <button className="command-tile" onClick={() => onNavigate('/new-project')}>
              <Compass size={22} />
              <span>新建工程</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </GlassCard>

        <GlassCard title="整体进度" eyebrow="Progress">
          <div className="space-y-4">
            <div className="h-3 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-[linear-gradient(90deg,var(--accent-gold),var(--accent-blue))]" style={{ width: `${totalChapters ? (completedChapters / totalChapters) * 100 : 0}%` }} />
            </div>
            <p className="text-sm text-[var(--text-muted)]">
              {completedChapters} / {totalChapters} 章节完成
            </p>
          </div>
        </GlassCard>
      </div>

      <div className="grid grid-cols-[1.3fr_1fr] gap-5 max-xl:grid-cols-1">
        {recent.length === 0 ? (
          <EmptyState
            title="还没有作品"
            description="导入 TXT / EPUB / DOCX 创建第一个改写工程。"
            action={<PrimaryButton onClick={() => onNavigate('/new-project')}>新建工程</PrimaryButton>}
          />
        ) : (
          <GlassCard title="近期项目" eyebrow="Recent">
            <div className="space-y-3">
              {recent.map((project) => (
                <button className="project-row" key={project.id} onClick={() => onNavigate(`/workspace/${project.id}`)}>
                  <span>
                    <strong>{project.name}</strong>
                    <small>{project.total_chapters} 章 · {project.total_words.toLocaleString()} 字</small>
                  </span>
                  <StatusPill variant={statusVariant(project.status)}>{project.status}</StatusPill>
                </button>
              ))}
            </div>
          </GlassCard>
        )}

        <GlassCard title="趋势" eyebrow="Signal">
          <p className="text-sm leading-6 text-[var(--text-muted)]">
            UI-R2 暂以项目总量和完成度展示本地趋势。更细的每日改写统计将在后续 API 接入导出/流水线历史后补齐。
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
