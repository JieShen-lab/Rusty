import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { ChevronLeft, ChevronRight, Download, Eye, EyeOff, Save, Sparkles } from 'lucide-react';
import {
  analyzeChapterStyle,
  confirmChapterRewrite,
  detectScene,
  expandChapterPlot,
  exportEpub,
  exportPromptPackage,
  exportTxt,
  getAnalysisPrompts,
  getChapter,
  getChapters,
  getProject,
  getProjectExportPlan,
  getProjectStyleSynthesis,
  getPrompts,
  reviewChapterStyle,
  rewriteChapter,
  saveChapterRewrite,
  saveProjectExportPlan,
  saveTargetSkeleton,
  summarizeChapter,
  synthesizeProjectStyle,
} from '../api/client';
import type {
  AnalysisPromptTemplate,
  Chapter,
  ChapterDetail,
  ExportPlanItem,
  ProjectDetail,
  ProjectPurpose,
  PromptTemplate,
} from '../api/types';

type Props = { onNavigate: (path: string) => void; projectId: number };

const rewriteStages = ['原文', '剧情与人物', '目标骨架', '改写对照', '导出检查'];
const extractStages = ['原文', '章节风格分析', '人工审查', '全书归纳', '提示词预览', '导出 JSON'];

export function ProjectWorkspacePage({ onNavigate, projectId }: Props) {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [rewritePrompts, setRewritePrompts] = useState<PromptTemplate[]>([]);
  const [analysisPrompts, setAnalysisPrompts] = useState<AnalysisPromptTemplate[]>([]);
  const [generatedPrompt, setGeneratedPrompt] = useState<PromptTemplate | null>(null);
  const [exportPlan, setExportPlan] = useState<ExportPlanItem[]>([]);
  const [stage, setStage] = useState(0);
  const [targetSkeleton, setTargetSkeleton] = useState('');
  const [rewriteDraft, setRewriteDraft] = useState('');
  const [analysisDraft, setAnalysisDraft] = useState('{}');
  const [binderVisible, setBinderVisible] = useState(true);
  const [inspectorVisible, setInspectorVisible] = useState(true);
  const [binderWidth, setBinderWidth] = useState(240);
  const [inspectorWidth, setInspectorWidth] = useState(300);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const purpose: ProjectPurpose = project?.settings?.processing_mode === 'extract' ? 'extract' : 'rewrite';
  const stages = purpose === 'rewrite' ? rewriteStages : extractStages;
  const selectedIndex = chapters.findIndex((item) => item.id === selectedChapterId);
  const selectedChapter = detail?.chapter ?? null;
  const settingsPromptId = numberValue(project?.settings?.prompt_template_id);
  const settingsAnalysisPromptId = numberValue(project?.settings?.analysis_prompt_template_id);
  const selectedRewritePrompt = rewritePrompts.find((item) => item.id === settingsPromptId) ?? null;
  const selectedAnalysisPrompt = analysisPrompts.find((item) => item.id === settingsAnalysisPromptId) ?? null;

  const loadProject = useCallback(async () => {
    setError(null);
    try {
      const [projectResult, chapterItems, prompts, analyses, plan, synthesis] = await Promise.all([
        getProject(projectId), getChapters(projectId), getPrompts(), getAnalysisPrompts(), getProjectExportPlan(projectId), getProjectStyleSynthesis(projectId),
      ]);
      setProject(projectResult);
      setChapters(chapterItems);
      setRewritePrompts(prompts);
      setAnalysisPrompts(analyses);
      setExportPlan(plan);
      setGeneratedPrompt(prompts.find((item) => item.id === synthesis.prompt_template_id) ?? null);
      setSelectedChapterId((current) => current && chapterItems.some((item) => item.id === current) ? current : chapterItems[0]?.id ?? null);
    } catch (reason) { setError(messageOf(reason)); }
  }, [projectId]);

  const loadChapter = useCallback(async (chapterId: number) => {
    try {
      const next = await getChapter(chapterId);
      setDetail(next);
      setTargetSkeleton(next.ai_outputs.expanded_plot || next.ai_outputs.plot_summary || '');
      setRewriteDraft(next.chapter.rewritten_text || '');
      const reviewed = next.ai_outputs.reviewed_style_analysis;
      const raw = next.ai_outputs.style_analysis;
      setAnalysisDraft(JSON.stringify(Object.keys(reviewed || {}).length ? reviewed : raw || {}, null, 2));
    } catch (reason) { setError(messageOf(reason)); }
  }, []);

  useEffect(() => { void loadProject(); }, [loadProject]);
  useEffect(() => { if (selectedChapterId) void loadChapter(selectedChapterId); }, [loadChapter, selectedChapterId]);
  useEffect(() => { setStage(0); }, [purpose]);

  async function run(label: string, action: () => Promise<unknown>, nextStage?: number) {
    setBusy(true); setError(null); setMessage(null);
    try {
      await action();
      if (selectedChapterId) await loadChapter(selectedChapterId);
      await loadProject();
      if (nextStage !== undefined) setStage(nextStage);
      setMessage(`${label}完成。`);
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function identifyAndRewrite() {
    if (!selectedChapterId) return;
    await run('识别与改写', async () => { await detectScene(selectedChapterId); await rewriteChapter(selectedChapterId); }, 3);
  }

  async function saveRewrite(confirm = false) {
    if (!selectedChapterId) return;
    await run(confirm ? '确认本章' : '保存改写稿', async () => {
      await saveChapterRewrite(selectedChapterId, rewriteDraft);
      if (confirm) await confirmChapterRewrite(selectedChapterId);
    });
  }

  async function reviewAnalysis() {
    if (!selectedChapterId) return;
    let reviewed: Record<string, unknown>;
    try { reviewed = JSON.parse(analysisDraft) as Record<string, unknown>; }
    catch { setError('人工审查内容必须是有效的 JSON 对象。'); return; }
    await run('确认本章分析', () => reviewChapterStyle(selectedChapterId, reviewed), 3);
  }

  async function synthesize() {
    await run('全书风格归纳', async () => { const result = await synthesizeProjectStyle(projectId); setGeneratedPrompt(result); }, 4);
  }

  async function exportGeneratedPrompt() {
    const prompt = generatedPrompt;
    if (!prompt) return;
    setBusy(true); setError(null);
    try {
      const { content } = await exportPromptPackage(prompt.id);
      download(content, `${safeName(prompt.name)}.json`, 'application/json;charset=utf-8');
      setMessage('改写提示词 JSON 已导出，可直接回到提示词管理导入。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function exportBook(format: 'txt' | 'epub') {
    await run(`导出 ${format.toUpperCase()}`, async () => {
      await saveProjectExportPlan(projectId, { items: exportPlan.map((item, index) => ({ ...item, export_order: index + 1 })) });
      await (format === 'txt' ? exportTxt(projectId) : exportEpub(projectId));
    });
  }

  function selectRelative(delta: -1 | 1) {
    const next = chapters[selectedIndex + delta];
    if (next) setSelectedChapterId(next.id);
  }

  function beginResize(side: 'binder' | 'inspector', event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === 'binder' ? binderWidth : inspectorWidth;
    const move = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      if (side === 'binder') setBinderWidth(clamp(startWidth + delta, 196, 360));
      else setInspectorWidth(clamp(startWidth - delta, 260, 420));
    };
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop);
  }

  const chapterStatus = useMemo(() => detail ? effectiveStatus(detail, purpose) : '未处理', [detail, purpose]);

  return (
    <div className="project-workbench">
      <header className="workbench-toolbar">
        <div className="project-heading"><button className="back-link" onClick={() => onNavigate('/home')} type="button">‹ 返回工程</button><strong>{project?.project.name || '加载中…'}</strong><span>{purpose === 'rewrite' ? '改写工程' : '提取工程'}</span></div>
        <div className="chapter-heading"><button aria-label="上一章" className="icon-button" disabled={selectedIndex <= 0} onClick={() => selectRelative(-1)} type="button"><ChevronLeft size={18} /></button><div><strong>{selectedChapter?.title || '暂无章节'}</strong><span>{selectedChapter ? `${selectedChapter.word_count.toLocaleString()} 字 · ${chapterStatus}` : ''}</span></div><button aria-label="下一章" className="icon-button" disabled={selectedIndex < 0 || selectedIndex >= chapters.length - 1} onClick={() => selectRelative(1)} type="button"><ChevronRight size={18} /></button></div>
        <div className="toolbar-actions"><button aria-label={binderVisible ? '隐藏章节目录' : '显示章节目录'} className="button ghost" onClick={() => setBinderVisible((value) => !value)} type="button">{binderVisible ? <EyeOff size={16} /> : <Eye size={16} />}目录</button><button aria-label={inspectorVisible ? '隐藏检查器' : '显示检查器'} className="button ghost" onClick={() => setInspectorVisible((value) => !value)} type="button">{inspectorVisible ? <EyeOff size={16} /> : <Eye size={16} />}检查器</button></div>
      </header>

      <nav className="workflow-rail" aria-label="工程阶段">{stages.map((label, index) => <button aria-current={stage === index ? 'step' : undefined} className={stage === index ? 'active' : ''} key={label} onClick={() => setStage(index)} type="button"><span>{index + 1}</span>{label}</button>)}</nav>
      <div className="workbench-feedback">
        {(error || message) ? <div className={`inline-alert workbench-alert ${error ? 'error' : 'success'}`} role={error ? 'alert' : 'status'}>{error || message}</div> : null}
      </div>

      <div className="workbench-grid" style={{ gridTemplateColumns: `${binderVisible ? `${binderWidth}px 8px` : ''} minmax(0,1fr) ${inspectorVisible ? `8px ${inspectorWidth}px` : ''}` }}>
        {binderVisible ? <><ChapterBinder chapters={chapters} currentId={selectedChapterId} detail={detail} purpose={purpose} onSelect={setSelectedChapterId} /><div aria-label="调整章节目录宽度" className="panel-resizer" onPointerDown={(event) => beginResize('binder', event)} role="separator" /></> : null}
        <main className="workspace-center"><WorkspaceContent analysisDraft={analysisDraft} detail={detail} exportPlan={exportPlan} generatedPrompt={generatedPrompt} purpose={purpose} rewriteDraft={rewriteDraft} setAnalysisDraft={setAnalysisDraft} setExportPlan={setExportPlan} setRewriteDraft={setRewriteDraft} setTargetSkeleton={setTargetSkeleton} stage={stage} targetSkeleton={targetSkeleton} /></main>
        {inspectorVisible ? <><div aria-label="调整检查器宽度" className="panel-resizer" onPointerDown={(event) => beginResize('inspector', event)} role="separator" /><Inspector actions={<InspectorActions busy={busy} detail={detail} generatedPrompt={generatedPrompt} onAnalyze={() => selectedChapterId && run('章节风格分析', () => analyzeChapterStyle(selectedChapterId), 2)} onConfirmAnalysis={() => void reviewAnalysis()} onConfirmRewrite={() => void saveRewrite(true)} onExpand={() => selectedChapterId && run('目标骨架生成', () => expandChapterPlot(selectedChapterId, true), 2)} onExportBook={exportBook} onExportPrompt={() => void exportGeneratedPrompt()} onReviewPrompt={() => onNavigate('/prompts')} onRewrite={() => void identifyAndRewrite()} onSaveRewrite={() => void saveRewrite(false)} onSaveSkeleton={() => selectedChapterId && run('目标骨架保存', () => saveTargetSkeleton(selectedChapterId, targetSkeleton))} onSummarize={() => selectedChapterId && run('剧情与人物提取', () => summarizeChapter(selectedChapterId), 1)} onSynthesize={() => void synthesize()} purpose={purpose} stage={stage} />} analysisPrompt={selectedAnalysisPrompt} detail={detail} purpose={purpose} rewritePrompt={selectedRewritePrompt} /></> : null}
      </div>

      <footer className="workbench-status"><span>{selectedChapter ? `字数 ${selectedChapter.word_count.toLocaleString()}${rewriteDraft ? ` / ${countText(rewriteDraft).toLocaleString()}` : ''}` : '无章节'}</span><span>章节 {selectedIndex >= 0 ? selectedIndex + 1 : 0} / {chapters.length}</span><span>阶段：{stages[stage]}</span><span className="status-spacer" /><span>{busy ? '正在处理…' : '本地保存'}</span><span className="status-dot" /> </footer>
    </div>
  );
}

function ChapterBinder({ chapters, currentId, detail, onSelect, purpose }: { chapters: Chapter[]; currentId: number | null; detail: ChapterDetail | null; onSelect: (id: number) => void; purpose: ProjectPurpose }) {
  return <aside className="chapter-binder"><div className="binder-heading"><h2>章节目录</h2><span>{chapters.length} 章</span></div><div className="chapter-list">{chapters.map((chapter) => { const status = chapter.id === currentId && detail ? effectiveStatus(detail, purpose) : statusFromChapter(chapter.status, purpose); return <button aria-current={chapter.id === currentId ? 'page' : undefined} className={`chapter-row ${chapter.id === currentId ? 'selected' : ''}`} key={chapter.id} onClick={() => onSelect(chapter.id)} type="button"><span className="chapter-number">{chapter.index}</span><span className="chapter-name" title={chapter.title}>{chapter.title}</span><span className={`chapter-state ${statusTone(status)}`}>{status}</span></button>; })}{chapters.length === 0 ? <div className="compact-empty">工程中没有章节。</div> : null}</div><div className="binder-footer">共 {chapters.length} 章</div></aside>;
}

function WorkspaceContent({ analysisDraft, detail, exportPlan, generatedPrompt, purpose, rewriteDraft, setAnalysisDraft, setExportPlan, setRewriteDraft, setTargetSkeleton, stage, targetSkeleton }: { analysisDraft: string; detail: ChapterDetail | null; exportPlan: ExportPlanItem[]; generatedPrompt: PromptTemplate | null; purpose: ProjectPurpose; rewriteDraft: string; setAnalysisDraft: (value: string) => void; setExportPlan: (value: ExportPlanItem[]) => void; setRewriteDraft: (value: string) => void; setTargetSkeleton: (value: string) => void; stage: number; targetSkeleton: string }) {
  if (!detail) return <div className="workspace-empty">选择一个章节开始工作。</div>;
  const { chapter, ai_outputs: output } = detail;
  if (stage === 0) return <ManuscriptPane title="原文" text={chapter.original_text} words={chapter.word_count} />;
  if (purpose === 'rewrite') {
    if (stage === 1) return <div className="derived-layout"><EditablePanel label="原始剧情骨架" placeholder="点击右侧“提取剧情与人物”" value={output.plot_summary || ''} readOnly /><EditablePanel label="本章人物卡" placeholder="尚未提取人物卡" value={JSON.stringify(output.plot_characters || [], null, 2)} readOnly /></div>;
    if (stage === 2) return <EditablePanel label="目标剧情骨架" placeholder="可以先编辑原始骨架，或让 AI 优化、扩充情节。" value={targetSkeleton} onChange={setTargetSkeleton} />;
    if (stage === 3) return <div className="comparison-layout"><ManuscriptPane title="原文" text={chapter.original_text} words={chapter.word_count} /><EditablePanel label="改写稿" placeholder="点击右侧“识别并改写”生成正文" value={rewriteDraft} onChange={setRewriteDraft} manuscript /></div>;
    return <ExportPlan items={exportPlan} onChange={setExportPlan} />;
  }
  if (stage === 1) return <AnalysisReview original={chapter.original_text} title="章节风格分析" value={JSON.stringify(output.style_analysis || {}, null, 2)} readOnly />;
  if (stage === 2) return <AnalysisReview original={chapter.original_text} title="人工审查（JSON 可编辑）" value={analysisDraft} onChange={setAnalysisDraft} />;
  if (stage === 3) return <div className="workspace-message"><h2>全书风格归纳</h2><p>系统会使用已确认的章节分析，跨章去重、处理冲突并去除人物名与具体剧情，生成可复用的改写提示词。</p><strong>已确认本章：{output.style_analysis_status === 'confirmed' ? '是' : '否'}</strong></div>;
  if (stage === 4) return <PromptPreview prompt={generatedPrompt} />;
  return <div className="workspace-message"><h2>导出改写提示词 JSON</h2><p>导出的文件使用 rusty.rewrite_prompt v2，可直接到“提示词管理 → 改写提示词 → 导入 JSON”使用。</p><strong>{generatedPrompt ? generatedPrompt.name : '请先完成全书归纳'}</strong></div>;
}

function Inspector({ actions, analysisPrompt, detail, purpose, rewritePrompt }: { actions: ReactNode; analysisPrompt: AnalysisPromptTemplate | null; detail: ChapterDetail | null; purpose: ProjectPurpose; rewritePrompt: PromptTemplate | null }) {
  const output = detail?.ai_outputs;
  return <aside className="workbench-inspector"><div className="inspector-heading"><h2>{purpose === 'rewrite' ? '本章检查器' : '分析检查器'}</h2><span>{detail?.chapter.title || ''}</span></div><div className="inspector-scroll"><section><h3>当前提示词</h3><strong>{purpose === 'rewrite' ? rewritePrompt?.name || '未绑定' : analysisPrompt?.name || '未绑定'}</strong><p>{purpose === 'rewrite' ? rewritePrompt?.description || '基础、识别和改写规则' : analysisPrompt?.description || '分析维度、证据规则和归纳输出'}</p></section>{purpose === 'rewrite' ? <><section><h3>剧情骨架</h3><p>{output?.expanded_plot || output?.plot_summary || '尚未提取'}</p></section><section><h3>相关人物</h3><p>{(output?.plot_characters || []).map((item) => String(item.name || item.role || '未命名人物')).join('、') || '尚未提取'}</p></section></> : <section><h3>分析状态</h3><Definition label="本章分析" value={output?.style_analysis ? '已生成' : '未分析'} /><Definition label="人工审查" value={output?.style_analysis_status === 'confirmed' ? '已确认' : '待确认'} /></section>}</div><div className="inspector-action-area">{actions}</div></aside>;
}

function InspectorActions(props: { busy: boolean; detail: ChapterDetail | null; generatedPrompt: PromptTemplate | null; onAnalyze: () => void; onConfirmAnalysis: () => void; onConfirmRewrite: () => void; onExpand: () => void; onExportBook: (format: 'txt' | 'epub') => void; onExportPrompt: () => void; onReviewPrompt: () => void; onRewrite: () => void; onSaveRewrite: () => void; onSaveSkeleton: () => void; onSummarize: () => void; onSynthesize: () => void; purpose: ProjectPurpose; stage: number }) {
  const { busy, detail, generatedPrompt, purpose, stage } = props;
  if (purpose === 'rewrite') {
    if (stage === 1) return <ActionButton busy={busy} label="提取剧情与人物" onClick={props.onSummarize} />;
    if (stage === 2) return <><ActionButton busy={busy} label="AI 优化 / 扩充骨架" onClick={props.onExpand} /><button className="button secondary full" disabled={busy} onClick={props.onSaveSkeleton} type="button"><Save size={16} />保存目标骨架</button></>;
    if (stage === 3) return <><ActionButton busy={busy} label="识别并改写" onClick={props.onRewrite} /><button className="button secondary full" disabled={busy} onClick={props.onSaveRewrite} type="button"><Save size={16} />保存改写稿</button><button className="button secondary full" disabled={busy || !detail?.chapter.rewritten_text} onClick={props.onConfirmRewrite} type="button">确认本章</button></>;
    if (stage === 4) return <><button className="button primary full" disabled={busy} onClick={() => props.onExportBook('txt')} type="button"><Download size={16} />导出 TXT</button><button className="button secondary full" disabled={busy} onClick={() => props.onExportBook('epub')} type="button"><Download size={16} />导出 EPUB</button></>;
    return <div className="inspector-hint">进入“剧情与人物”开始处理本章。</div>;
  }
  if (stage === 1) return <ActionButton busy={busy} label="分析本章风格" onClick={props.onAnalyze} />;
  if (stage === 2) return <ActionButton busy={busy} label="确认本章分析" onClick={props.onConfirmAnalysis} />;
  if (stage === 3) return <ActionButton busy={busy} label="归纳全书并生成提示词" onClick={props.onSynthesize} />;
  if (stage >= 4) return <><button className="button secondary full" disabled={busy || !generatedPrompt} onClick={props.onReviewPrompt} type="button">到提示词管理审查</button><button className="button primary full" disabled={busy || !generatedPrompt} onClick={props.onExportPrompt} type="button"><Download size={16} />导出 JSON</button></>;
  return <div className="inspector-hint">进入“章节风格分析”开始处理本章。</div>;
}

function ActionButton({ busy, label, onClick }: { busy: boolean; label: string; onClick: () => void }) { return <button className="button primary full" disabled={busy} onClick={onClick} type="button"><Sparkles size={16} />{busy ? '处理中…' : label}</button>; }
function ManuscriptPane({ text, title, words }: { text: string; title: string; words: number }) { return <section className="manuscript-pane"><header><h2>{title}</h2><span>{words.toLocaleString()} 字</span></header><div className="manuscript-text">{text}</div></section>; }
function EditablePanel({ label, manuscript = false, onChange, placeholder, readOnly = false, value }: { label: string; manuscript?: boolean; onChange?: (value: string) => void; placeholder: string; readOnly?: boolean; value: string }) { return <label className={`editable-panel ${manuscript ? 'manuscript-editor' : ''}`}><span><strong>{label}</strong><small>{countText(value).toLocaleString()} 字</small></span><textarea placeholder={placeholder} readOnly={readOnly} value={value} onChange={(event) => onChange?.(event.target.value)} /></label>; }
function AnalysisReview({ onChange, original, readOnly = false, title, value }: { onChange?: (value: string) => void; original: string; readOnly?: boolean; title: string; value: string }) { return <div className="analysis-review"><ManuscriptPane text={original} title="原文（证据来源）" words={countText(original)} /><EditablePanel label={title} placeholder="尚未生成分析" readOnly={readOnly} value={value} onChange={onChange} /></div>; }
function PromptPreview({ prompt }: { prompt: PromptTemplate | null }) { if (!prompt) return <div className="workspace-message"><h2>提示词预览</h2><p>请先完成全书归纳。</p></div>; const recognitionRules = prompt.scene_rules.map((rule) => `[${rule.display_name}]\n${rule.detection_prompt}`).join('\n\n'); return <div className="prompt-preview"><section><h3>基础规则</h3><pre>{prompt.global_rules || '暂无'}</pre></section><section><h3>识别规则</h3><pre>{recognitionRules || '暂无'}</pre></section><section><h3>改写规则</h3><pre>{prompt.rewrite_rules || '暂无'}{prompt.scene_rules.map((rule) => `\n\n[${rule.display_name}]\n${rule.rewrite_prompt}`).join('')}</pre></section></div>; }
function ExportPlan({ items, onChange }: { items: ExportPlanItem[]; onChange: (items: ExportPlanItem[]) => void }) { return <div className="export-plan"><div className="section-heading"><div><strong>导出检查</strong><span>检查标题、顺序、包含状态和正文来源</span></div></div>{items.map((item, index) => <div className="export-row" key={item.chapter_id}><input aria-label={`包含第 ${index + 1} 章`} checked={item.include_in_export} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, include_in_export: event.target.checked } : current))} type="checkbox" /><span>{index + 1}</span><input aria-label="导出标题" value={item.export_title} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, export_title: event.target.value } : current))} /><small>{sourceLabel(item.source_status)}</small></div>)}</div>; }
function Definition({ label, value }: { label: string; value: string }) { return <div className="definition"><span>{label}</span><strong>{value}</strong></div>; }
function effectiveStatus(detail: ChapterDetail, purpose: ProjectPurpose) { if (purpose === 'extract') return detail.ai_outputs.style_analysis_status === 'confirmed' ? '已确认' : detail.ai_outputs.style_analysis ? '待审查' : '未分析'; if (detail.chapter.status === 'confirmed') return '已确认'; if (detail.chapter.rewritten_text) return '已改写'; if (detail.ai_outputs.plot_summary) return '已提取'; return '未处理'; }
function statusFromChapter(status: string, purpose: ProjectPurpose) { if (purpose === 'extract') return '未分析'; if (status === 'confirmed') return '已确认'; if (status === 'rewritten') return '已改写'; if (status === 'kept_original') return '保留原文'; return '未处理'; }
function statusTone(status: string) { if (status === '已确认') return 'success'; if (status === '待审查' || status === '已提取') return 'warning'; if (status === '已改写') return 'info'; return 'muted'; }
function sourceLabel(status: ExportPlanItem['source_status']) { if (status === 'manual_rewrite') return '手动改写'; if (status === 'ai_rewrite') return 'AI 改写'; if (status === 'kept_original') return '保留原文'; return '原文'; }
function numberValue(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
function countText(value: string) { return value.replace(/\s/g, '').length; }
function clamp(value: number, min: number, max: number) { return Math.min(max, Math.max(min, value)); }
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function safeName(value: string) { return value.replace(/[\\/:*?"<>|]/g, '_').trim() || 'rewrite-prompt'; }
function download(content: string, fileName: string, type: string) { const url = URL.createObjectURL(new Blob([content], { type })); const link = document.createElement('a'); link.href = url; link.download = fileName; link.click(); URL.revokeObjectURL(url); }
