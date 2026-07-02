import { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { exportEpub, exportTxt, getChapters, getProject, getProjectChapter } from '../api/client';
import type { Chapter, ChapterDetail, ProjectDetail } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StageStepper } from '../components/StageStepper';
import { StatusPill, statusVariant } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

type Props = {
  projectId?: number;
  onNavigate: (path: string) => void;
};

const stages = ['书籍拆分', '内容总结', '识别待处理', 'AI 改写', '合并输出'];

export function ProjectWorkspacePage({ projectId, onNavigate }: Props) {
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [activeStage, setActiveStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setError(null);
    Promise.all([getProject(projectId), getChapters(projectId)])
      .then(([project, items]) => {
        setProjectDetail(project);
        setChapters(items);
        setSelectedChapterId((current) => current ?? items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedChapterId) return;
    getProjectChapter(projectId, selectedChapterId)
      .then(setChapterDetail)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId, selectedChapterId]);

  if (!projectId) {
    return <EmptyState title="尚未选择项目" description="请先到作品库选择一个项目。" action={<PrimaryButton onClick={() => onNavigate('/library')}>前往作品库</PrimaryButton>} />;
  }

  const project = projectDetail?.project;
  const selected = chapterDetail?.chapter;
  const completed = project ? Math.round(project.progress * stages.length) : 0;

  async function handleExport(kind: 'txt' | 'epub') {
    if (!projectId) return;
    setExportMessage(null);
    try {
      const result = kind === 'txt' ? await exportTxt(projectId) : await exportEpub(projectId);
      setExportMessage(`已导出：${result.output_path}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <TopBar
        title={project?.name ?? '创作台'}
        subtitle={project ? `${project.total_chapters} 章 · ${project.total_words.toLocaleString()} 字` : '读取项目中'}
        onRefresh={() => window.location.reload()}
      />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      <div className="mb-5">
        <StageStepper stages={stages} activeStage={activeStage} completedStages={Array.from({ length: completed }, (_, index) => index).filter((index) => index < activeStage)} />
      </div>
      <div className="grid grid-cols-[300px_1fr_280px] gap-5 max-2xl:grid-cols-[260px_1fr] max-lg:grid-cols-1">
        <GlassCard title="章节导航" strong className="max-h-[calc(100vh-190px)] overflow-auto">
          <p className="mb-4 text-sm text-[var(--text-muted)]">{chapters.length} 章 · {project?.completed_chapters ?? 0} 已完成</p>
          <div className="space-y-2">
            {chapters.map((chapter) => (
              <button
                className={`w-full cursor-pointer rounded-2xl border p-3 text-left transition ${selectedChapterId === chapter.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                key={chapter.id}
                onClick={() => setSelectedChapterId(chapter.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-white">{chapter.title}</span>
                  <StatusPill variant={statusVariant(chapter.status)}>{chapter.status}</StatusPill>
                </div>
                <p className="mt-1 text-xs text-[var(--text-soft)]">{chapter.word_count.toLocaleString()} 字</p>
              </button>
            ))}
          </div>
        </GlassCard>

        <GlassCard strong className="min-h-[640px]">
          <div className="mb-5 flex flex-wrap gap-2">
            {stages.map((stage, index) => (
              <button className={`rounded-full border px-3 py-1 text-xs ${activeStage === index ? 'border-sky-300/30 bg-sky-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`} key={stage} onClick={() => setActiveStage(index)}>
                {stage}
              </button>
            ))}
          </div>
          {selected ? <StageContent activeStage={activeStage} detail={chapterDetail} /> : <EmptyState title="请选择章节" description="选择章节后可查看原文、总结、识别和改写结果。" />}
        </GlassCard>

        <aside className="space-y-5 max-2xl:col-span-2 max-lg:col-span-1">
          <GlassCard title="项目统计">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Stat label="总字数" value={project?.total_words.toLocaleString() ?? '-'} />
              <Stat label="章节数" value={project?.total_chapters ?? '-'} />
              <Stat label="已完成" value={project?.completed_chapters ?? '-'} />
              <Stat label="总进度" value={project ? `${Math.round(project.progress * 100)}%` : '-'} />
            </div>
          </GlassCard>
          <GlassCard title="导出">
            <div className="flex flex-col gap-3">
              <PrimaryButton onClick={() => handleExport('txt')}>
                <Download size={16} />
                导出 TXT
              </PrimaryButton>
              <SecondaryButton onClick={() => handleExport('epub')}>
                <FileText size={16} />
                导出 EPUB
              </SecondaryButton>
            </div>
            {exportMessage && <p className="mt-4 break-all text-xs text-emerald-200">{exportMessage}</p>}
          </GlassCard>
          <GlassCard title="错误信息">
            {chapterDetail?.errors.length ? (
              <div className="space-y-2">
                {chapterDetail.errors.map((item) => (
                  <p className="rounded-xl border border-rose-300/20 bg-rose-400/10 p-3 text-xs text-rose-100" key={item.id}>
                    {item.stage}: {item.message}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">暂无错误。</p>
            )}
          </GlassCard>
        </aside>
      </div>
    </div>
  );
}

function StageContent({ activeStage, detail }: { activeStage: number; detail: ChapterDetail | null }) {
  if (!detail) return null;
  const chapter = detail.chapter;
  const outputs = detail.ai_outputs;
  if (activeStage === 1) {
    return <TextPanel title="剧情概要" text={outputs.plot_summary || '暂无章节总结，请点击后续流水线入口生成总结。'} />;
  }
  if (activeStage === 2) {
    return (
      <TextPanel
        title="场景识别"
        text={outputs.needs_rewrite === null ? '暂无场景识别结果。' : `是否需要改写：${outputs.needs_rewrite ? '是' : '否'}\n标签：${outputs.scene_labels?.join(', ') || '无'}\n理由：${outputs.scene_reasoning || '无'}`}
      />
    );
  }
  if (activeStage === 3) {
    return (
      <div className="grid grid-cols-2 gap-4 max-xl:grid-cols-1">
        <TextPanel title="原文" text={chapter.original_text} />
        <TextPanel title="改写文" text={chapter.rewritten_text || '暂无改写文本。'} />
      </div>
    );
  }
  if (activeStage === 4) {
    return <TextPanel title="合并输出" text="请使用右侧导出按钮生成 TXT / EPUB。UI-R2 暂不在前端合并全文。" />;
  }
  return <TextPanel title={`${chapter.title} · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />;
}

function TextPanel({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h2 className="mb-4 text-2xl font-bold text-white">{title}</h2>
      <pre className="chapter-text whitespace-pre-wrap rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-8 text-slate-100">{text}</pre>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      <p className="text-xs text-[var(--text-soft)]">{label}</p>
      <p className="mt-1 font-semibold text-white">{value}</p>
    </div>
  );
}
