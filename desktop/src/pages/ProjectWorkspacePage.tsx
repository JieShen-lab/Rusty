import { useEffect, useMemo, useState } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronRight, Download, FileText, Play, Save, Sparkles } from 'lucide-react';
import {
  detectScene,
  expandChapterPlot,
  exportEpub,
  exportPromptPackage,
  exportTxt,
  extractProjectPromptPackage,
  getChapters,
  getProject,
  getProjectChapter,
  getProjectExportPlan,
  getPrompts,
  rewriteChapter,
  runProjectSummary,
  saveChapterRewrite,
  saveProjectExportPlan,
  summarizeChapter,
  updateProjectSettings,
} from '../api/client';
import type {
  Chapter,
  ChapterDetail,
  ExportPlanItem,
  PipelineRunResult,
  ProjectDetail,
  ProjectPurpose,
  PromptTemplate,
} from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { PrimaryButton } from '../components/PrimaryButton';
import { StageStepper } from '../components/StageStepper';
import { StatusPill, statusVariant } from '../components/StatusPill';

type Props = {
  projectId?: number;
  onNavigate: (path: string) => void;
};

const rewriteStages = ['原文', '章节总结', '识别处理', '剧情扩展', 'AI 改写', '导出'];
const analysisStages = ['原文', '章节总结', '提示词包提取', '审核与导出'];

export function ProjectWorkspacePage({ projectId, onNavigate }: Props) {
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [boundPromptId, setBoundPromptId] = useState<number | null>(null);
  const [exportPlan, setExportPlan] = useState<ExportPlanItem[]>([]);
  const [activeStage, setActiveStage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [rewriteDraft, setRewriteDraft] = useState('');
  const [plotExpansionEnabled, setPlotExpansionEnabled] = useState(true);

  const purpose = projectPurpose(projectDetail);
  const stages = purpose === 'summary' ? analysisStages : rewriteStages;
  const project = projectDetail?.project;
  const selectedPackage = prompts.find((item) => item.id === boundPromptId) ?? null;

  useEffect(() => {
    if (!projectId) return;
    void reloadWorkspace(null).catch((err: unknown) => setError(errorMessage(err)));
    // reloadWorkspace owns parallel initial loading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedChapterId) return;
    getProjectChapter(projectId, selectedChapterId)
      .then((detail) => applyChapterDetail(detail))
      .catch((err: unknown) => setError(errorMessage(err)));
  }, [projectId, selectedChapterId]);

  const completedStages = useMemo(() => {
    const completed = [0];
    const statuses = new Map(chapterDetail?.stage_statuses.map((item) => [item.stage, item.status]) ?? []);
    if (statuses.get('summary') === 'completed') completed.push(1);
    if (purpose === 'summary') {
      if (selectedPackage?.source_project_id === projectId) completed.push(2, 3);
      return completed;
    }
    if (statuses.get('scene_detection') === 'completed') completed.push(2);
    if (statuses.get('plot_expansion') === 'completed') completed.push(3);
    if (statuses.get('rewrite') === 'completed' || chapterDetail?.chapter.status === 'kept_original') completed.push(4);
    if (projectDetail?.exports.length) completed.push(5);
    return completed;
  }, [chapterDetail, projectDetail?.exports.length, projectId, purpose, selectedPackage?.source_project_id]);

  if (!projectId) {
    return <EmptyState title="尚未选择项目" description="请先到作品库选择项目。" action={<PrimaryButton onClick={() => onNavigate('/library')}>前往作品库</PrimaryButton>} />;
  }

  async function reloadWorkspace(chapterId: number | null = selectedChapterId) {
    if (!projectId) return;
    setError(null);
    const [detail, chapterItems, promptItems, plan] = await Promise.all([
      getProject(projectId),
      getChapters(projectId),
      getPrompts(),
      getProjectExportPlan(projectId),
    ]);
    setProjectDetail(detail);
    setChapters(chapterItems);
    setPrompts(promptItems);
    setBoundPromptId(numberSetting(detail.settings?.prompt_template_id));
    setExportPlan(plan);
    const nextChapterId = chapterId ?? chapterItems[0]?.id ?? null;
    setSelectedChapterId(nextChapterId);
    if (nextChapterId) applyChapterDetail(await getProjectChapter(projectId, nextChapterId));
  }

  function applyChapterDetail(detail: ChapterDetail) {
    setChapterDetail(detail);
    setRewriteDraft(detail.chapter.rewritten_text || '');
    setPlotExpansionEnabled(detail.ai_outputs.plot_expansion_enabled ?? true);
  }

  async function runAction(label: string, action: () => Promise<unknown>, nextStage?: number) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (isPipelineRunResult(result)) {
        const summary = `${label}：成功 ${result.processed} 章，失败 ${result.failed} 章。`;
        if (result.failed) setError(`${summary} 请查看章节错误信息。`);
        else setMessage(summary);
      } else {
        setMessage(`${label}完成。`);
      }
      await reloadWorkspace();
      if (nextStage !== undefined) setActiveStage(nextStage);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function bindPrompt(value: string) {
    if (!projectId || !projectDetail) return;
    const promptId = value ? Number(value) : null;
    const settings = projectDetail.settings ?? {};
    setBusy(true);
    setError(null);
    try {
      const updated = await updateProjectSettings(projectId, {
        model_id: numberSetting(settings.model_id),
        prompt_template_id: promptId,
        processing_mode: purpose,
        concurrency: numberSetting(settings.concurrency) ?? 1,
        target_word_count: numberSetting(settings.target_word_count),
        min_expansion_ratio: numberSetting(settings.min_expansion_ratio),
      });
      setProjectDetail(updated);
      setBoundPromptId(promptId);
      setMessage(promptId ? '已绑定提示词包。' : '已取消提示词包绑定。');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveRewrite() {
    if (!chapterDetail) return;
    await runAction('保存改写', () => saveChapterRewrite(chapterDetail.chapter.id, rewriteDraft));
  }

  async function handleSaveExportPlan() {
    const saved = await saveProjectExportPlan(projectId!, {
      items: exportPlan.map((item, index) => ({
        chapter_id: item.chapter_id,
        export_order: index + 1,
        export_title: item.export_title,
        include_in_export: item.include_in_export,
      })),
    });
    setExportPlan(saved);
  }

  async function handleExport(kind: 'txt' | 'epub') {
    await runAction(`导出 ${kind.toUpperCase()}`, () => kind === 'txt' ? exportTxt(projectId!) : exportEpub(projectId!));
  }

  async function handlePackageExport() {
    if (!selectedPackage) return;
    setBusy(true);
    setError(null);
    try {
      const result = await exportPromptPackage(selectedPackage.id);
      downloadJson(result.content, `${safeFileName(selectedPackage.name)}.json`);
      setMessage('提示词包 JSON 已导出。');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function moveExportPlanItem(index: number, delta: -1 | 1) {
    setExportPlan((current) => {
      const nextIndex = index + delta;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next.map((item, itemIndex) => ({ ...item, export_order: itemIndex + 1 }));
    });
  }

  const chapter = chapterDetail?.chapter;
  const chapterError = chapterDetail?.errors[0];

  return (
    <div className="workspace-page flex h-full min-h-0 flex-col">
      <header className="mb-3 flex shrink-0 items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-bold text-white">{project?.name ?? '读取项目中'}</h1>
            <StatusPill variant="info">{purpose === 'summary' ? '分析项目' : '改写项目'}</StatusPill>
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">{project ? `${project.total_chapters} 章 · ${project.total_words.toLocaleString()} 字` : '正在读取项目'}</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="hidden items-center gap-2 text-xs text-[var(--text-muted)] xl:flex">
            提示词包
            <select className="form-input w-52 py-2 text-xs" disabled={busy} value={boundPromptId ?? ''} onChange={(event) => void bindPrompt(event.target.value)}>
              <option value="">请选择</option>
              {prompts.map((prompt) => <option key={prompt.id} value={prompt.id}>{prompt.name}</option>)}
            </select>
          </label>
          <div className="w-44 max-md:hidden">
            <div className="mb-1 flex justify-between text-xs text-[var(--text-muted)]"><span>项目进度</span><span>{project ? Math.round(project.progress * 100) : 0}%</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-[var(--accent-blue)]" style={{ width: `${project ? project.progress * 100 : 0}%` }} /></div>
          </div>
        </div>
      </header>

      <div className="mb-3 shrink-0"><StageStepper stages={stages} activeStage={activeStage} completedStages={completedStages} onStageChange={setActiveStage} /></div>

      {(error || message || chapterError) && (
        <div className={`mb-3 shrink-0 rounded-xl border px-3 py-2 text-xs ${error || chapterError ? 'border-rose-300/25 bg-rose-400/10 text-rose-100' : 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100'}`}>
          {error || chapterError?.message || message}
        </div>
      )}

      <div className="relative grid min-h-0 flex-1 grid-cols-[250px_1fr] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/28 max-lg:grid-cols-1">
        <aside className="min-h-0 overflow-y-auto border-r border-white/10 p-3 max-lg:hidden">
          <div className="mb-3"><p className="text-sm font-semibold text-white">章节</p><p className="mt-0.5 text-xs text-[var(--text-muted)]">{chapters.length} 章</p></div>
          <div className="space-y-2">
            {chapters.map((item) => (
              <button className={`w-full rounded-xl border p-3 text-left ${item.id === selectedChapterId ? 'border-sky-300/35 bg-sky-300/10' : 'border-white/10 bg-white/[0.025] hover:bg-white/[0.06]'}`} key={item.id} onClick={() => setSelectedChapterId(item.id)} type="button">
                <div className="flex items-center justify-between gap-2"><span className="truncate text-sm text-white">{item.title}</span><StatusPill variant={statusVariant(item.status)}>{statusLabel(item.status)}</StatusPill></div>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{item.word_count.toLocaleString()} 字</p>
              </button>
            ))}
          </div>
        </aside>

        <main className="min-h-0 overflow-hidden pb-14">
          <StageContent
            activeStage={activeStage}
            detail={chapterDetail}
            exportPlan={exportPlan}
            onExportPlanChange={setExportPlan}
            onMoveExportItem={moveExportPlanItem}
            packageTemplate={selectedPackage}
            plotEnabled={plotExpansionEnabled}
            purpose={purpose}
            rewriteDraft={rewriteDraft}
            setPlotEnabled={setPlotExpansionEnabled}
            setRewriteDraft={setRewriteDraft}
          />
        </main>

        <ActionDock>
          {activeStage < stages.length - 1 && <StageButton disabled={busy} onClick={() => setActiveStage((current) => current + 1)}>下一步<ChevronRight size={14} /></StageButton>}
          {chapter && activeStage === 1 && <StageButton disabled={busy} onClick={() => void runAction('总结本章', () => summarizeChapter(chapter.id))}><Sparkles size={14} />总结本章</StageButton>}
          {activeStage === 1 && <StageButton disabled={busy} onClick={() => void runAction('总结全部', () => runProjectSummary(projectId))}><Play size={14} />总结全部</StageButton>}
          {purpose === 'summary' && activeStage === 2 && <StageButton disabled={busy} onClick={() => void runAction('提取提示词包', () => extractProjectPromptPackage(projectId), 3)}><Sparkles size={14} />提取提示词包</StageButton>}
          {purpose === 'summary' && activeStage === 3 && <StageButton disabled={busy || !selectedPackage} onClick={() => void handlePackageExport()}><Download size={14} />导出 JSON</StageButton>}
          {purpose === 'summary' && activeStage === 3 && <StageButton onClick={() => onNavigate('/prompts')}><FileText size={14} />到提示词板审核</StageButton>}
          {purpose === 'rewrite' && chapter && activeStage === 2 && <StageButton disabled={busy || !boundPromptId} onClick={() => void runAction('识别本章', () => detectScene(chapter.id), 3)}><Sparkles size={14} />识别本章</StageButton>}
          {purpose === 'rewrite' && chapter && activeStage === 3 && <StageButton disabled={busy || !boundPromptId} onClick={() => void runAction(plotExpansionEnabled ? '扩展剧情' : '跳过剧情扩展', () => expandChapterPlot(chapter.id, plotExpansionEnabled), 4)}><Sparkles size={14} />{plotExpansionEnabled ? '生成剧情线' : '确认跳过'}</StageButton>}
          {purpose === 'rewrite' && chapter && activeStage === 4 && <StageButton disabled={busy || !boundPromptId} onClick={() => void runAction('AI 改写', () => rewriteChapter(chapter.id))}><Sparkles size={14} />AI 改写</StageButton>}
          {purpose === 'rewrite' && activeStage === 4 && <StageButton disabled={busy || !chapter} onClick={() => void handleSaveRewrite()}><Save size={14} />保存文本</StageButton>}
          {purpose === 'rewrite' && activeStage === 5 && <StageButton disabled={busy} onClick={() => void runAction('保存导出设置', handleSaveExportPlan)}><Save size={14} />保存设置</StageButton>}
          {purpose === 'rewrite' && activeStage === 5 && <StageButton disabled={busy} onClick={() => void handleExport('txt')}><Download size={14} />TXT</StageButton>}
          {purpose === 'rewrite' && activeStage === 5 && <StageButton disabled={busy} onClick={() => void handleExport('epub')}><Download size={14} />EPUB</StageButton>}
        </ActionDock>
      </div>
    </div>
  );
}

function StageContent({ activeStage, detail, exportPlan, onExportPlanChange, onMoveExportItem, packageTemplate, plotEnabled, purpose, rewriteDraft, setPlotEnabled, setRewriteDraft }: {
  activeStage: number;
  detail: ChapterDetail | null;
  exportPlan: ExportPlanItem[];
  onExportPlanChange: (items: ExportPlanItem[]) => void;
  onMoveExportItem: (index: number, delta: -1 | 1) => void;
  packageTemplate: PromptTemplate | null;
  plotEnabled: boolean;
  purpose: ProjectPurpose;
  rewriteDraft: string;
  setPlotEnabled: (value: boolean) => void;
  setRewriteDraft: (value: string) => void;
}) {
  if (!detail) return <EmptyState title="暂无章节" description="项目中没有可显示的章节。" />;
  const { chapter, ai_outputs: outputs } = detail;

  if (activeStage === 0) return <TextPane title={`${chapter.title} · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />;
  if (activeStage === 1) return <TextPane title="章节总结" text={outputs.plot_summary || '尚未生成本章总结。'} />;
  if (purpose === 'summary' && activeStage >= 2) return <PromptPackagePane packageTemplate={packageTemplate} extracted={activeStage === 3} />;
  if (purpose === 'rewrite' && activeStage === 2) {
    const text = outputs.needs_rewrite === null
      ? '尚未识别本章。'
      : `是否需要改写：${outputs.needs_rewrite ? '是' : '否'}\n场景分类：${outputs.scene_labels?.join('、') || '无'}\n识别说明：${outputs.scene_reasoning || '无'}`;
    return <TextPane title="识别结果" text={text} />;
  }
  if (purpose === 'rewrite' && activeStage === 3) {
    return (
      <div className="flex h-full min-h-0 flex-col p-4">
        <label className="mb-3 flex shrink-0 items-center justify-between rounded-xl border border-white/10 bg-white/[0.035] px-4 py-3">
          <span><strong className="text-sm text-white">让 AI 增加剧情线</strong><small className="mt-1 block text-xs text-[var(--text-muted)]">在故事与人物锚点范围内强化关键节点、因果链或支线。</small></span>
          <input checked={plotEnabled} onChange={(event) => setPlotEnabled(event.target.checked)} type="checkbox" />
        </label>
        <pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-7 text-slate-100">{outputs.expanded_plot || (plotEnabled ? '尚未生成本章剧情扩展方案。' : '本章将跳过剧情扩展。')}</pre>
      </div>
    );
  }
  if (purpose === 'rewrite' && activeStage === 4) {
    return (
      <div className="grid h-full min-h-0 grid-cols-2 divide-x divide-white/10 max-lg:grid-cols-1 max-lg:divide-x-0">
        <TextPane title={`原文 · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />
        <div className="flex min-h-0 flex-col p-4"><h2 className="mb-3 text-sm font-semibold text-white">改写稿</h2><textarea className="min-h-0 flex-1 resize-none overflow-y-auto rounded-xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-7 text-slate-100 outline-none focus:border-sky-300/35" placeholder="尚未生成改写文本。" value={rewriteDraft} onChange={(event) => setRewriteDraft(event.target.value)} /></div>
      </div>
    );
  }
  return <ExportPlanPane items={exportPlan} onChange={onExportPlanChange} onMove={onMoveExportItem} />;
}

function PromptPackagePane({ extracted, packageTemplate }: { extracted: boolean; packageTemplate: PromptTemplate | null }) {
  if (!packageTemplate) return <EmptyState title={extracted ? '尚未提取提示词包' : '准备提取提示词包'} description="先完成章节总结，再使用右下角按钮让 AI 提取改写规则、故事锚点与人物锚点。" />;
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-3"><div><h2 className="text-lg font-semibold text-white">{packageTemplate.name}</h2><p className="mt-1 text-xs text-[var(--text-muted)]">{packageTemplate.description || '项目提示词包'}</p></div><StatusPill variant="success">已生成</StatusPill></div>
      <div className="grid grid-cols-2 gap-3 max-xl:grid-cols-1">
        <PackageSection title="通用改写规则" value={packageTemplate.rewrite_rules} />
        <PackageSection title={`场景分类 · ${packageTemplate.scene_rules.length}`} value={packageTemplate.scene_rules.map((rule) => `${rule.display_name} (${rule.scene_key})\n${rule.description}`).join('\n\n')} />
        <PackageSection title="故事发展锚点" value={JSON.stringify(packageTemplate.story_anchor, null, 2)} />
        <PackageSection title={`人物锚点 · ${packageTemplate.characters.length}`} value={JSON.stringify(packageTemplate.characters, null, 2)} />
      </div>
    </div>
  );
}

function PackageSection({ title, value }: { title: string; value: string }) {
  return <section className="rounded-xl border border-white/10 bg-white/[0.025] p-4"><h3 className="text-sm font-semibold text-white">{title}</h3><pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-slate-300">{value || '暂无内容'}</pre></section>;
}

function ExportPlanPane({ items, onChange, onMove }: { items: ExportPlanItem[]; onChange: (items: ExportPlanItem[]) => void; onMove: (index: number, delta: -1 | 1) => void }) {
  return (
    <div className="h-full overflow-y-auto p-4"><h2 className="text-sm font-semibold text-white">导出章节</h2><p className="mt-1 text-xs text-[var(--text-muted)]">调整顺序、标题和是否包含。</p><div className="mt-4 space-y-2">{items.map((item, index) => (
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] p-2" key={item.chapter_id}>
        <input checked={item.include_in_export} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, include_in_export: event.target.checked } : current))} type="checkbox" />
        <span className="w-10 text-xs text-[var(--text-soft)]">#{index + 1}</span>
        <input className="form-input py-2 text-sm" value={item.export_title} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, export_title: event.target.value } : current))} />
        <span className="w-16 text-xs text-[var(--text-muted)]">{exportSourceLabel(item.source_status)}</span>
        <button className="stage-icon-button" disabled={index === 0} onClick={() => onMove(index, -1)} title="上移" type="button"><ArrowUp size={14} /></button>
        <button className="stage-icon-button" disabled={index === items.length - 1} onClick={() => onMove(index, 1)} title="下移" type="button"><ArrowDown size={14} /></button>
      </div>
    ))}</div></div>
  );
}

function TextPane({ title, text }: { title: string; text: string }) {
  return <div className="flex h-full min-h-0 flex-col p-4"><h2 className="mb-3 shrink-0 text-sm font-semibold text-white">{title}</h2><pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-7 text-slate-100">{text}</pre></div>;
}

function ActionDock({ children }: { children: ReactNode }) {
  return <div className="absolute bottom-3 right-3 z-20 flex max-w-[calc(100%-24px)] flex-wrap justify-end gap-2 rounded-xl border border-sky-300/20 bg-slate-950/90 p-2 shadow-xl shadow-black/30 backdrop-blur-xl">{children}</div>;
}

function StageButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.08] px-3 text-xs font-semibold text-white transition hover:border-sky-300/35 hover:bg-sky-300/10 disabled:cursor-not-allowed disabled:opacity-45" type="button" {...props}>{children}</button>;
}

function projectPurpose(detail: ProjectDetail | null): ProjectPurpose {
  return detail?.settings?.processing_mode === 'summary' ? 'summary' : 'rewrite';
}

function numberSetting(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function isPipelineRunResult(value: unknown): value is PipelineRunResult {
  return Boolean(value && typeof value === 'object' && 'processed' in value && 'failed' in value);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function downloadJson(content: string, fileName: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function safeFileName(name: string) {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'prompt-package';
}

function statusLabel(status: string) {
  if (status === 'rewritten') return '已改写';
  if (status === 'kept_original') return '保留原文';
  if (status === 'failed') return '失败';
  return '已导入';
}

function exportSourceLabel(status: ExportPlanItem['source_status']) {
  if (status === 'manual_rewrite') return '手动改写';
  if (status === 'ai_rewrite') return 'AI 改写';
  if (status === 'kept_original') return '保留原文';
  return '原文';
}
