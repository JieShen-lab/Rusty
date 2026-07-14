import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, Compass, MessageSquareText } from 'lucide-react';
import { getProjects } from '../api/client';
import type { Project } from '../api/types';
import { GlassCard } from '../components/GlassCard';
import { MetricCard } from '../components/MetricCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';

type Props = {
  onNavigate: (path: string) => void;
};

const shortcuts = [
  { label: '提示词包', description: '统一管理规则、故事发展与人物锚点', path: '/prompts', icon: MessageSquareText },
  { label: '作品库', description: '进入已有的分析或改写项目', path: '/library', icon: BookOpen },
] as const;

export function HomePage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    getProjects()
      .then(setProjects)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const totalChapters = projects.reduce((sum, project) => sum + project.total_chapters, 0);
  const completedChapters = projects.reduce((sum, project) => sum + project.completed_chapters, 0);
  const pendingChapters = Math.max(totalChapters - completedChapters, 0);
  const completion = totalChapters ? Math.round((completedChapters / totalChapters) * 100) : 0;

  return (
    <div className="space-y-5">
      {error && <GlassCard className="border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}

      <section className="grid grid-cols-[minmax(0,1.15fr)_minmax(420px,0.85fr)] gap-5 max-xl:grid-cols-1">
        <GlassCard className="flex min-h-[300px] flex-col justify-between p-8" strong>
          <div>
            <p className="text-sm text-[var(--text-muted)]">
              {now.toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </p>
            <p className="mt-3 text-5xl font-black tracking-[-0.05em] text-white">
              {now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
            </p>
            <h1 className="mt-8 text-3xl font-bold text-white">开始今天的创作</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--text-muted)]">从作品库继续已有项目，或创建新的分析与改写流程。</p>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <PrimaryButton onClick={() => onNavigate('/new-project')}>
              <Compass size={16} />
              新建项目
            </PrimaryButton>
            <SecondaryButton onClick={() => onNavigate('/library')}>
              <BookOpen size={16} />
              打开作品库
            </SecondaryButton>
          </div>
        </GlassCard>

        <GlassCard title="常用配置" strong>
          <div className="divide-y divide-white/10 overflow-hidden rounded-2xl border border-white/10">
            {shortcuts.map(({ label, description, path, icon: Icon }) => (
              <button className="group flex w-full cursor-pointer items-center gap-4 bg-white/[0.025] px-4 py-4 text-left transition hover:bg-white/[0.07]" key={path} onClick={() => onNavigate(path)} type="button">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-[var(--accent-blue)]"><Icon size={18} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-white">{label}</span>
                  <span className="mt-1 block text-xs text-[var(--text-muted)]">{description}</span>
                </span>
                <ArrowRight className="text-[var(--text-soft)] transition group-hover:translate-x-1 group-hover:text-white" size={17} />
              </button>
            ))}
          </div>
        </GlassCard>
      </section>

      <section className="grid grid-cols-4 gap-4 max-xl:grid-cols-2 max-sm:grid-cols-1" aria-label="项目概览">
        <MetricCard label="项目总数" value={projects.length} hint={loading ? '读取中' : '本地项目'} />
        <MetricCard label="总章节数" value={totalChapters} hint="全部项目" />
        <MetricCard label="已完成章节" value={completedChapters} hint="分析或改写完成" />
        <MetricCard label="待处理章节" value={pendingChapters} hint="尚未完成" />
      </section>

      <GlassCard className="grid grid-cols-[220px_1fr] items-center gap-6 max-md:grid-cols-1" title="整体进度">
        <div>
          <p className="text-4xl font-bold text-white">{completion}%</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">{completedChapters} / {totalChapters} 章节完成</p>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-[linear-gradient(90deg,var(--accent-gold),var(--accent-blue))] transition-[width]" style={{ width: `${completion}%` }} />
        </div>
      </GlassCard>
    </div>
  );
}
