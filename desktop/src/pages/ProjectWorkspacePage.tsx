import { useEffect, useMemo, useState } from 'react';
import type { ButtonHTMLAttributes, Dispatch, ReactNode, SetStateAction } from 'react';
import { ArrowDown, ArrowUp, ChevronRight, Download, FileText, Play, RefreshCcw, Save, Sparkles } from 'lucide-react';
import {
  bindProjectCharacter,
  bindProjectOutline,
  bindProjectStyle,
  detectScene,
  exportEpub,
  exportTxt,
  getChapters,
  getCharacterCards,
  getOutlineTemplates,
  getProject,
  getProjectCharacters,
  getProjectChapter,
  getProjectExportPlan,
  getProjectOutline,
  getProjectStyle,
  getStyleTemplates,
  retryChapterStage,
  rewriteChapter,
  runProjectPipeline,
  runProjectSummary,
  saveChapterRewrite,
  saveProjectExportPlan,
  summarizeChapter,
  unbindProjectCharacter,
} from '../api/client';
import type {
  Chapter,
  ChapterDetail,
  CharacterCard,
  ExportPlanItem,
  OutlineTemplate,
  PipelineRunResult,
  ProjectDetail,
  ProjectPurpose,
  StyleTemplate,
} from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { PrimaryButton } from '../components/PrimaryButton';
import { StageStepper } from '../components/StageStepper';
import { StatusPill, statusVariant } from '../components/StatusPill';

type Props = {
  projectId?: number;
  onNavigate: (path: string) => void;
};

const rewriteStages = ['原文', '章节总结', '识别处理', 'AI 改写', '导出'];
const summaryStages = ['原文', '章节总结', '全书汇总'];

export function ProjectWorkspacePage({ projectId, onNavigate }: Props) {
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [activeStage, setActiveStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [styleTemplates, setStyleTemplates] = useState<StyleTemplate[]>([]);
  const [boundStyleId, setBoundStyleId] = useState<number | null>(null);
  const [outlineTemplates, setOutlineTemplates] = useState<OutlineTemplate[]>([]);
  const [boundOutlineId, setBoundOutlineId] = useState<number | null>(null);
  const [characterCards, setCharacterCards] = useState<CharacterCard[]>([]);
  const [boundCharacterIds, setBoundCharacterIds] = useState<number[]>([]);
  const [exportPlan, setExportPlan] = useState<ExportPlanItem[]>([]);
  const [summaryOverview, setSummaryOverview] = useState('');
  const [busy, setBusy] = useState(false);
  const [rewriteDraft, setRewriteDraft] = useState('');

  const purpose = projectPurpose(projectDetail);
  const stages = purpose === 'summary' ? summaryStages : rewriteStages;
  const project = projectDetail?.project;
  const selected = chapterDetail?.chapter;

  useEffect(() => {
    if (!projectId) return;
    void reloadWorkspace(null).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    // reloadWorkspace intentionally owns the parallel initial load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedChapterId) return;
    getProjectChapter(projectId, selectedChapterId)
      .then((detail) => {
        setChapterDetail(detail);
        setRewriteDraft(detail.chapter.rewritten_text || '');
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId, selectedChapterId]);

  useEffect(() => {
    if (!projectId || purpose !== 'summary' || activeStage !== 2 || chapters.length === 0) return;
    Promise.all(chapters.map((chapter) => getProjectChapter(projectId, chapter.id)))
      .then((details) => {
        const text = details
          .map((detail) => detail.ai_outputs.plot_summary ? `${detail.chapter.title}\n${detail.ai_outputs.plot_summary}` : '')
          .filter(Boolean)
          .join('\n\n');
        setSummaryOverview(text);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [activeStage, chapters, projectId, purpose]);

  const completedStages = useMemo(() => {
    const completed = [0];
    const statuses = new Map(chapterDetail?.stage_statuses.map((item) => [item.stage, item.status]) ?? []);
    if (statuses.get('summary') === 'completed') completed.push(1);
    if (purpose === 'summary') {
      if (summaryOverview) completed.push(2);
      return completed;
    }
    if (statuses.get('scene_detection') === 'completed') completed.push(2);
    if (statuses.get('rewrite') === 'completed' || selected?.status === 'kept_original') completed.push(3);
    if (projectDetail?.exports.length) completed.push(4);
    return completed;
  }, [chapterDetail, projectDetail?.exports.length, purpose, selected?.status, summaryOverview]);

  if (!projectId) {
    return <EmptyState title="尚未选择项目" description="请先到作品库选择一个项目。" action={<PrimaryButton onClick={() => onNavigate('/library')}>前往作品库</PrimaryButton>} />;
  }

  async function reloadWorkspace(chapterId: number | null = selectedChapterId) {
    if (!projectId) return;
    setError(null);
    const [detail, items, styles, styleBinding, outlines, outlineBinding, cards, characterBinding, plan] = await Promise.all([
      getProject(projectId),
      getChapters(projectId),
      getStyleTemplates(),
      getProjectStyle(projectId),
      getOutlineTemplates(),
      getProjectOutline(projectId),
      getCharacterCards(),
      getProjectCharacters(projectId),
      getProjectExportPlan(projectId),
    ]);
    setProjectDetail(detail);
    setChapters(items);
    setStyleTemplates(styles);
    setBoundStyleId(styleBinding.style_template?.id ?? null);
    setOutlineTemplates(outlines);
    setBoundOutlineId(outlineBinding.outline_template?.id ?? null);
    setCharacterCards(cards);
    setBoundCharacterIds(characterBinding.character_cards.map((card) => card.id));
    setExportPlan(plan);
    const nextChapterId = chapterId ?? items[0]?.id ?? null;
    setSelectedChapterId(nextChapterId);
    if (nextChapterId) {
      const nextDetail = await getProjectChapter(projectId, nextChapterId);
      setChapterDetail(nextDetail);
      setRewriteDraft(nextDetail.chapter.rewritten_text || '');
    }
  }

  async function runAction(label: string, action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (isPipelineRunResult(result)) {
        const summary = `${label}：成功 ${result.processed} 章，失败 ${result.failed} 章${result.skipped ? `，保留原文 ${result.skipped} 章` : ''}${result.paused ? '，已暂停' : ''}。`;
        if (result.failed > 0) setError(`${summary} 请查看当前章节错误。`);
        else setMessage(summary);
      } else {
        setMessage(`${label}完成。`);
      }
      await reloadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleStyleBinding(value: string) {
    if (!projectId) return;
    setBusy(true);
    try {
      const binding = await bindProjectStyle(projectId, value ? Number(value) : null);
      setBoundStyleId(binding.style_template?.id ?? null);
      setMessage(binding.style_template ? `已绑定风格：${binding.style_template.name}` : '已取消风格绑定。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleOutlineBinding(value: string) {
    if (!projectId) return;
    setBusy(true);
    try {
      const binding = await bindProjectOutline(projectId, value ? Number(value) : null);
      setBoundOutlineId(binding.outline_template?.id ?? null);
      setMessage(binding.outline_template ? `已绑定大纲：${binding.outline_template.name}` : '已取消大纲绑定。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleCharacterBinding(cardId: number, checked: boolean) {
    if (!projectId) return;
    setBusy(true);
    try {
      const binding = checked
        ? await bindProjectCharacter(projectId, cardId, boundCharacterIds.length + 1)
        : await unbindProjectCharacter(projectId, cardId);
      setBoundCharacterIds(binding.character_cards.map((card) => card.id));
      setMessage('角色绑定已更新。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveExportPlan() {
    if (!projectId) return;
    setBusy(true);
    try {
      const saved = await saveProjectExportPlan(projectId, {
        items: exportPlan.map((item, index) => ({
          chapter_id: item.chapter_id,
          export_order: index + 1,
          export_title: item.export_title,
          include_in_export: item.include_in_export,
        })),
      });
      setExportPlan(saved);
      setMessage('导出章节设置已保存。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleExport(kind: 'txt' | 'epub') {
    if (!projectId) return;
    setBusy(true);
    try {
      const result = kind === 'txt' ? await exportTxt(projectId) : await exportEpub(projectId);
      setMessage(`已导出：${result.output_path}`);
      await reloadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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

  const chapterId = selected?.id;
  const chapterError = chapterDetail?.errors[0];

  return (
    <div className="workspace-page flex h-full min-h-0 flex-col">
      <header className="mb-3 flex shrink-0 items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-bold text-white">{project?.name ?? '读取项目中'}</h1>
            <StatusPill variant="info">{purpose === 'summary' ? '总结项目' : '改写项目'}</StatusPill>
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">{project ? `${project.total_chapters} 章 · ${project.total_words.toLocaleString()} 字` : '正在读取项目信息'}</p>
        </div>
        <div className="w-48 shrink-0 max-md:hidden">
          <div className="mb-1 flex justify-between text-xs text-[var(--text-muted)]">
            <span>项目进度</span><span>{project ? Math.round(project.progress * 100) : 0}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-[var(--accent-blue)]" style={{ width: `${project ? project.progress * 100 : 0}%` }} /></div>
        </div>
      </header>

      <div className="mb-3 shrink-0">
        <StageStepper stages={stages} activeStage={activeStage} completedStages={completedStages} onStageChange={setActiveStage} />
      </div>

      {(error || message || chapterError) && (
        <div className={`mb-3 shrink-0 rounded-xl border px-3 py-2 text-xs ${error || chapterError ? 'border-rose-300/25 bg-rose-400/10 text-rose-100' : 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100'}`}>
          {error || (chapterError ? `${chapterError.stage}：${chapterError.message}` : message)}
        </div>
      )}

      <div className="workspace-frame grid min-h-0 flex-1 grid-cols-[230px_minmax(0,1fr)] overflow-hidden rounded-2xl border border-white/10 bg-[var(--bg-panel-strong)]">
        <aside className="flex min-h-0 flex-col border-r border-white/10 bg-black/10">
          <div className="shrink-0 border-b border-white/10 px-3 py-3">
            <p className="text-sm font-semibold text-white">章节</p>
            <p className="mt-0.5 text-xs text-[var(--text-soft)]">{chapters.length} 章</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {chapters.map((chapter) => (
              <button
                className={`mb-1.5 w-full cursor-pointer rounded-xl border px-3 py-2.5 text-left transition ${selectedChapterId === chapter.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-transparent hover:border-white/10 hover:bg-white/[0.05]'}`}
                key={chapter.id}
                onClick={() => setSelectedChapterId(chapter.id)}
                type="button"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-white">{chapter.title}</span>
                  <StatusPill variant={statusVariant(chapter.status)}>{chapter.status}</StatusPill>
                </span>
                <span className="mt-1 block text-[11px] text-[var(--text-soft)]">{chapter.word_count.toLocaleString()} 字</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="relative min-h-0 min-w-0 overflow-hidden pb-[70px]">
          {selected ? (
            <div className={`grid h-full min-h-0 ${purpose === 'rewrite' && activeStage === 3 ? 'grid-cols-[minmax(0,1fr)_280px] max-xl:grid-cols-1' : 'grid-cols-1'}`}>
              <StageContent
                activeStage={activeStage}
                detail={chapterDetail}
                exportPlan={exportPlan}
                purpose={purpose}
                rewriteDraft={rewriteDraft}
                setExportPlan={setExportPlan}
                setRewriteDraft={setRewriteDraft}
                summaryOverview={summaryOverview}
                moveExportPlanItem={moveExportPlanItem}
              />
              {purpose === 'rewrite' && activeStage === 3 && (
                <RewriteConstraints
                  boundCharacterIds={boundCharacterIds}
                  boundOutlineId={boundOutlineId}
                  boundStyleId={boundStyleId}
                  busy={busy}
                  characterCards={characterCards}
                  onCharacterChange={toggleCharacterBinding}
                  onOutlineChange={handleOutlineBinding}
                  onStyleChange={handleStyleBinding}
                  outlineTemplates={outlineTemplates}
                  styleTemplates={styleTemplates}
                />
              )}
            </div>
          ) : (
            <EmptyState title="请选择章节" description="选择章节后查看当前阶段内容。" />
          )}

          <ActionDock>
            {activeStage === 0 && <StageButton onClick={() => setActiveStage(1)}>进入{stages[1]} <ChevronRight size={15} /></StageButton>}
            {activeStage === 1 && (
              <>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('总结本章', () => summarizeChapter(chapterId))}><Sparkles size={15} />总结本章</StageButton>
                <StageButton disabled={busy} onClick={() => runAction('总结全部章节', () => runProjectSummary(projectId))}><Play size={15} />总结全部</StageButton>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('重试总结', () => retryChapterStage(chapterId, 'summary'))}><RefreshCcw size={15} />重试</StageButton>
              </>
            )}
            {purpose === 'summary' && activeStage === 2 && <StageButton onClick={() => setActiveStage(1)}><RefreshCcw size={15} />返回章节总结</StageButton>}
            {purpose === 'rewrite' && activeStage === 2 && (
              <>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('识别本章', () => detectScene(chapterId))}><Sparkles size={15} />识别本章</StageButton>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('重试识别', () => retryChapterStage(chapterId, 'scene_detection'))}><RefreshCcw size={15} />重试</StageButton>
              </>
            )}
            {purpose === 'rewrite' && activeStage === 3 && (
              <>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('改写本章', () => rewriteChapter(chapterId))}><Sparkles size={15} />改写本章</StageButton>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('保存改写', () => saveChapterRewrite(chapterId, rewriteDraft))}><Save size={15} />保存</StageButton>
                <StageButton disabled={busy || !chapterId} onClick={() => chapterId && runAction('重试改写', () => retryChapterStage(chapterId, 'rewrite'))}><RefreshCcw size={15} />重试</StageButton>
                <StageButton disabled={busy} onClick={() => runAction('运行全部改写流程', () => runProjectPipeline(projectId))}><Play size={15} />运行全部</StageButton>
              </>
            )}
            {purpose === 'rewrite' && activeStage === 4 && (
              <>
                <StageButton disabled={busy} onClick={handleSaveExportPlan}><Save size={15} />保存设置</StageButton>
                <StageButton disabled={busy} onClick={() => handleExport('txt')}><Download size={15} />导出 TXT</StageButton>
                <StageButton disabled={busy} onClick={() => handleExport('epub')}><FileText size={15} />导出 EPUB</StageButton>
              </>
            )}
          </ActionDock>
        </section>
      </div>
    </div>
  );
}

function StageContent({
  activeStage,
  detail,
  exportPlan,
  moveExportPlanItem,
  purpose,
  rewriteDraft,
  setExportPlan,
  setRewriteDraft,
  summaryOverview,
}: {
  activeStage: number;
  detail: ChapterDetail | null;
  exportPlan: ExportPlanItem[];
  moveExportPlanItem: (index: number, delta: -1 | 1) => void;
  purpose: ProjectPurpose;
  rewriteDraft: string;
  setExportPlan: Dispatch<SetStateAction<ExportPlanItem[]>>;
  setRewriteDraft: (value: string) => void;
  summaryOverview: string;
}) {
  if (!detail) return null;
  const { chapter, ai_outputs: outputs } = detail;

  if (activeStage === 1) return <TextPane title="章节总结" text={outputs.plot_summary || '尚未生成本章总结。使用右下角“总结本章”或“总结全部”。'} />;
  if (purpose === 'summary' && activeStage === 2) return <TextPane title="全书汇总" text={summaryOverview || '尚无可汇总内容。请先完成章节总结。'} />;
  if (purpose === 'rewrite' && activeStage === 2) {
    return <TextPane title="识别结果" text={outputs.needs_rewrite === null ? '尚未识别本章。' : `是否需要改写：${outputs.needs_rewrite ? '是' : '否'}\n标签：${outputs.scene_labels?.join('、') || '无'}\n理由：${outputs.scene_reasoning || '无'}`} />;
  }
  if (purpose === 'rewrite' && activeStage === 3) {
    return (
      <div className="grid min-h-0 grid-cols-2 divide-x divide-white/10 max-lg:grid-cols-1 max-lg:divide-x-0">
        <TextPane title={`原文 · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />
        <div className="flex min-h-0 flex-col p-4">
          <h2 className="mb-3 shrink-0 text-sm font-semibold text-white">改写稿</h2>
          <textarea
            className="min-h-0 flex-1 resize-none overflow-y-auto rounded-xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-7 text-slate-100 outline-none focus:border-sky-300/35"
            placeholder="尚未生成改写文本。"
            value={rewriteDraft}
            onChange={(event) => setRewriteDraft(event.target.value)}
          />
        </div>
      </div>
    );
  }
  if (purpose === 'rewrite' && activeStage === 4) {
    return (
      <div className="h-full min-h-0 overflow-y-auto p-4">
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-white">导出章节</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">调整顺序、标题与是否包含，再使用右下角操作。</p>
        </div>
        <div className="space-y-2">
          {exportPlan.map((item, index) => (
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] p-2" key={item.chapter_id}>
              <input checked={item.include_in_export} onChange={(event) => setExportPlan((current) => current.map((currentItem) => currentItem.chapter_id === item.chapter_id ? { ...currentItem, include_in_export: event.target.checked } : currentItem))} type="checkbox" />
              <span className="w-12 shrink-0 text-xs text-[var(--text-soft)]">#{index + 1}</span>
              <input className="form-input py-2 text-sm" value={item.export_title} onChange={(event) => setExportPlan((current) => current.map((currentItem) => currentItem.chapter_id === item.chapter_id ? { ...currentItem, export_title: event.target.value } : currentItem))} />
              <span className="w-16 shrink-0 text-xs text-[var(--text-muted)]">{exportSourceLabel(item.source_status)}</span>
              <button className="stage-icon-button" disabled={index === 0} onClick={() => moveExportPlanItem(index, -1)} title="上移" type="button"><ArrowUp size={14} /></button>
              <button className="stage-icon-button" disabled={index === exportPlan.length - 1} onClick={() => moveExportPlanItem(index, 1)} title="下移" type="button"><ArrowDown size={14} /></button>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return <TextPane title={`${chapter.title} · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />;
}

function TextPane({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      <h2 className="mb-3 shrink-0 text-sm font-semibold text-white">{title}</h2>
      <pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-7 text-slate-100">{text}</pre>
    </div>
  );
}

function RewriteConstraints({
  boundCharacterIds,
  boundOutlineId,
  boundStyleId,
  busy,
  characterCards,
  onCharacterChange,
  onOutlineChange,
  onStyleChange,
  outlineTemplates,
  styleTemplates,
}: {
  boundCharacterIds: number[];
  boundOutlineId: number | null;
  boundStyleId: number | null;
  busy: boolean;
  characterCards: CharacterCard[];
  onCharacterChange: (id: number, checked: boolean) => void;
  onOutlineChange: (value: string) => void;
  onStyleChange: (value: string) => void;
  outlineTemplates: OutlineTemplate[];
  styleTemplates: StyleTemplate[];
}) {
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-white/10 bg-black/10 p-4 max-xl:hidden">
      <h2 className="mb-4 text-sm font-semibold text-white">改写约束</h2>
      <label className="form-label">剧情大纲</label>
      <select className="form-input mb-4 py-2 text-sm" disabled={busy} value={boundOutlineId ?? ''} onChange={(event) => onOutlineChange(event.target.value)}>
        <option value="">不使用大纲</option>
        {outlineTemplates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
      </select>
      <label className="form-label">风格模板</label>
      <select className="form-input mb-4 py-2 text-sm" disabled={busy} value={boundStyleId ?? ''} onChange={(event) => onStyleChange(event.target.value)}>
        <option value="">不使用风格</option>
        {styleTemplates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
      </select>
      <p className="form-label">角色</p>
      <div className="space-y-2">
        {characterCards.length === 0 && <p className="text-xs text-[var(--text-soft)]">尚未创建角色卡。</p>}
        {characterCards.map((card) => (
          <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-xs text-white" key={card.id}>
            <input checked={boundCharacterIds.includes(card.id)} disabled={busy} onChange={(event) => onCharacterChange(card.id, event.target.checked)} type="checkbox" />
            <span className="truncate">{card.name}</span>
          </label>
        ))}
      </div>
    </aside>
  );
}

function ActionDock({ children }: { children: ReactNode }) {
  return <div className="absolute bottom-3 right-3 z-20 flex max-w-[calc(100%-24px)] flex-wrap justify-end gap-2 rounded-xl border border-sky-300/20 bg-slate-950/90 p-2 shadow-xl shadow-black/30 backdrop-blur-xl">{children}</div>;
}

function StageButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.08] px-3 text-xs font-semibold text-white transition hover:border-sky-300/35 hover:bg-sky-300/10 disabled:cursor-not-allowed disabled:opacity-45" type="button" {...props}>{children}</button>;
}

function isPipelineRunResult(result: unknown): result is PipelineRunResult {
  return Boolean(result && typeof result === 'object' && 'processed' in result && 'failed' in result && 'skipped' in result && 'paused' in result);
}

function projectPurpose(detail: ProjectDetail | null): ProjectPurpose {
  return detail?.settings?.processing_mode === 'summary' ? 'summary' : 'rewrite';
}

function exportSourceLabel(status: ExportPlanItem['source_status']) {
  if (status === 'manual_rewrite') return '手动改写';
  if (status === 'ai_rewrite') return 'AI 改写';
  if (status === 'kept_original') return '保留原文';
  return '原文';
}
