import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowLeft, BookOpenText, Check, ChevronRight, Download, RefreshCw, Save, Sparkles, WandSparkles } from 'lucide-react';
import { exportProject, generateChapterWriting, getChapter, getChapters, getChapterWorkflow, getMaterials, getProject, resolveChapterStyle, runChapterSpecialAnalysis, runChapterSummary, saveChapterDirection, saveChapterSpecialAnalysis, saveChapterSummary, saveChapterWriting } from '../api/client';
import type { Chapter, ChapterSpecialAnalysis, ChapterSummary, ChapterWorkflowState, CreativeStrategy, CreativeWorkflowStage, Material, StyleDimension, StyleProfile } from '../api/types';
import { FloatingNotice } from '../components/FloatingNotice';
import { ExportFormatDialog, LibraryDefinition } from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';

type Props = { projectId: number; projectName: string; onNavigate: (path: string, state?: unknown) => void };
type UiStage = 'summary' | 'direction' | 'special_analysis' | 'style' | 'writing' | 'review';
type StyleMode = 'document' | 'author';
const STAGES: Array<{ key: UiStage; label: string }> = [{ key: 'summary', label: '内容总结' }, { key: 'direction', label: '方向选择' }, { key: 'special_analysis', label: '专项分析' }, { key: 'style', label: '风格' }, { key: 'writing', label: '写作' }, { key: 'review', label: '审查' }];

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Chapter | null>(null);
  const [workflow, setWorkflow] = useState<ChapterWorkflowState | null>(null);
  const [authors, setAuthors] = useState<Material[]>([]);
  const [projectOriginalWordCount, setProjectOriginalWordCount] = useState(0);
  const [activeStage, setActiveStage] = useState<UiStage>('summary');
  const [busy, setBusy] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [summaryDraft, setSummaryDraft] = useState<ChapterSummary | null>(null);
  const [directionStrategy, setDirectionStrategy] = useState<CreativeStrategy>('plot_adjust');
  const [directionInstruction, setDirectionInstruction] = useState('');
  const [analysisDraft, setAnalysisDraft] = useState<ChapterSpecialAnalysis | null>(null);
  const [styleMode, setStyleMode] = useState<StyleMode>('document');
  const [authorId, setAuthorId] = useState<number | null>(null);
  const [reviewDraft, setReviewDraft] = useState('');

  useEffect(() => {
    let cancelled = false;
    setProjectOriginalWordCount(0);
    void Promise.all([getChapters(projectId), getMaterials(), getProject(projectId)]).then(([items, profiles, project]) => {
      if (!cancelled) { setChapters(items); setAuthors(profiles); setProjectOriginalWordCount(project.total_words); setSelectedId(items[0]?.id ?? null); }
    }).catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [projectId]);

  const refresh = useCallback(async (chapterId: number, moveTo?: UiStage) => {
    const [value, state, chapterItems] = await Promise.all([getChapter(chapterId), getChapterWorkflow(chapterId), getChapters(projectId)]);
    setDetail(value); setWorkflow(state); setChapters(chapterItems); setActiveStage(moveTo ?? stageForState(state.current_stage));
  }, [projectId]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); setWorkflow(null); return; }
    let cancelled = false;
    void Promise.all([getChapter(selectedId), getChapterWorkflow(selectedId)]).then(([value, state]) => {
      if (!cancelled) { setDetail(value); setWorkflow(state); setActiveStage(stageForState(state.current_stage)); }
    }).catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    setSummaryDraft(workflow?.summary ?? null);
    setDirectionStrategy(workflow?.direction?.strategy ?? 'plot_adjust');
    setDirectionInstruction(workflow?.direction?.user_instruction ?? '');
    setAnalysisDraft(workflow?.special_analysis ?? null);
    setStyleMode(workflow?.style?.style_mode === 'selected_author_style' ? 'author' : 'document');
    setAuthorId(workflow?.style?.author_style_material_id ?? authors[0]?.id ?? null);
    setReviewDraft(workflow?.writing?.result_text ?? '');
  }, [workflow, authors]);

  async function act(action: () => Promise<unknown>, next?: UiStage, success?: string) {
    if (!selectedId || busy) return;
    setBusy(true); setError(null); setMessage(null);
    try { await action(); await refresh(selectedId, next); if (success) setMessage(success); }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function exportProjectDocument(format: 'txt' | 'epub') {
    if (busy) return;
    try {
      const outputPath = await window.rustyDesktop?.selectDocumentExportPath?.(format, projectName);
      if (!outputPath) return;
      setBusy(true); setError(null); setMessage(null);
      const result = await exportProject(projectId, format, outputPath);
      setExportOpen(false);
      setMessage(`已导出到 ${result.output_path}`);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  const drafts: Drafts = { summaryDraft, directionStrategy, directionInstruction, analysisDraft, styleMode, authorId, reviewDraft };
  const setters: Setters = { setSummaryDraft, setDirectionStrategy, setDirectionInstruction, setAnalysisDraft, setStyleMode, setAuthorId, setReviewDraft };

  return <div className="creative-workspace chapter-flow-page">
    <FloatingNotice error={error ?? (workflow?.source_changed ? '章节原文已经变化，请从内容总结重新开始，避免沿用过期分析。' : null)} message={message} />
    <header className="creative-topbar"><div className="creative-topbar-side"><button className="button primary navigation-back-button" onClick={() => onNavigate('/library')} type="button"><ArrowLeft size={16} />工程</button></div><div className="creative-project-title"><h1 title={projectName}>{projectName}</h1></div><div aria-hidden="true" className="creative-topbar-side creative-topbar-spacer" /></header>
    <div className="creative-columns chapter-flow-columns">
      <StageProgress active={activeStage} availableIndex={workflow ? availableStageIndex(workflow) : 0} onSelect={setActiveStage} workflow={workflow} />
      <aside className="chapter-rail"><div className="binder-heading"><h2>章节</h2><span>共 {chapters.length} 章</span></div><nav className="chapter-list project-chapter-list">{chapters.map((chapter) => { const complete = chapter.workflow_stage === 'review' || chapter.workflow_stage === 'confirmed'; return <button aria-current={chapter.id === selectedId ? 'page' : undefined} className={`chapter-row ${chapter.id === selectedId ? 'selected' : ''}`} key={chapter.id} onClick={() => setSelectedId(chapter.id)} type="button"><span className="chapter-number">第 {chapter.index} 章</span><span className="chapter-name">{chapter.title || '未命名'}</span><span className={`chapter-state ${complete ? 'complete' : ''}`}>{complete ? '已完成' : '未完成'}</span></button>; })}</nav></aside>
      <main className={`chapter-workspace stage-${activeStage}`}>{!selectedId || !workflow ? <div className="stage-placeholder"><h2>正在读取章节工作流…</h2></div> : <StageContent active={activeStage} authors={authors} detail={detail} drafts={drafts} setters={setters} workflow={workflow} />}</main>
      <ContextPanel active={activeStage} act={act} authors={authors} busy={busy} chapters={chapters} detail={detail} drafts={drafts} onOpenExport={() => setExportOpen(true)} projectOriginalWordCount={projectOriginalWordCount} workflow={workflow} />
    </div>
    {exportOpen ? <ExportFormatDialog busy={busy} title={projectName} onClose={() => setExportOpen(false)} onExport={(format) => void exportProjectDocument(format)} /> : null}
  </div>;
}

function StageProgress({ active, availableIndex, onSelect, workflow }: { active: UiStage; availableIndex: number; onSelect: (stage: UiStage) => void; workflow: ChapterWorkflowState | null }) {
  return <nav aria-label="章节创作阶段" className="creative-workflow-progress creative-stage-rail">{STAGES.map((stage, index) => { const complete = workflow ? stageComplete(workflow, stage.key) : false; const showCheck = complete && active !== stage.key; return <button className={`${active === stage.key ? 'active' : ''} ${complete ? 'complete' : ''}`} disabled={index > availableIndex} key={stage.key} onClick={() => onSelect(stage.key)} type="button"><span>{showCheck ? <Check size={9} /> : null}</span>{stage.label}</button>; })}</nav>;
}

type Drafts = { summaryDraft: ChapterSummary | null; directionStrategy: CreativeStrategy; directionInstruction: string; analysisDraft: ChapterSpecialAnalysis | null; styleMode: StyleMode; authorId: number | null; reviewDraft: string };
type Setters = { setSummaryDraft: (value: ChapterSummary) => void; setDirectionStrategy: (value: CreativeStrategy) => void; setDirectionInstruction: (value: string) => void; setAnalysisDraft: (value: ChapterSpecialAnalysis) => void; setStyleMode: (value: StyleMode) => void; setAuthorId: (value: number | null) => void; setReviewDraft: (value: string) => void };

function StageContent({ active, authors, detail, drafts, setters, workflow }: { active: UiStage; authors: Material[]; detail: Chapter | null; drafts: Drafts; setters: Setters; workflow: ChapterWorkflowState }) {
  if (active === 'summary') return <SummaryStage draft={drafts.summaryDraft} onChange={setters.setSummaryDraft} />;
  if (active === 'direction') return <DirectionStage instruction={drafts.directionInstruction} onInstruction={setters.setDirectionInstruction} onStrategy={setters.setDirectionStrategy} strategy={drafts.directionStrategy} />;
  if (active === 'special_analysis') return <AnalysisStage draft={drafts.analysisDraft} instruction={workflow.direction?.user_instruction ?? ''} onChange={setters.setAnalysisDraft} strategy={workflow.direction?.strategy} />;
  if (active === 'style') return <StyleStage authorId={drafts.authorId} authors={authors} mode={drafts.styleMode} onAuthor={setters.setAuthorId} onMode={setters.setStyleMode} workflow={workflow} />;
  if (active === 'writing') return <WritingStage workflow={workflow} />;
  return <ReviewStage detail={detail} draft={drafts.reviewDraft} onChange={setters.setReviewDraft} workflow={workflow} />;
}

function SummaryStage({ draft, onChange }: { draft: ChapterSummary | null; onChange: (value: ChapterSummary) => void }) {
  if (!draft) return <EmptyStage icon={<Sparkles size={22} />} title="先理解这一章" />;
  return <section className="flow-stage-card summary-stage"><label className="flow-field"><span>剧情总结</span><textarea className="flow-text-surface" value={draft.plot_summary} onChange={(event) => onChange({ ...draft, plot_summary: event.target.value })} /></label><label className="flow-field"><span>关键事件</span><textarea className="flow-text-surface" value={draft.key_events} onChange={(event) => onChange({ ...draft, key_events: event.target.value })} /></label><label className="flow-field"><span>主要人物及设定</span><textarea className="flow-text-surface" value={draft.main_characters} onChange={(event) => onChange({ ...draft, main_characters: event.target.value })} /></label></section>;
}

function DirectionStage({ instruction, onInstruction, onStrategy, strategy }: { instruction: string; onInstruction: (value: string) => void; onStrategy: (value: CreativeStrategy) => void; strategy: CreativeStrategy }) {
  const options: Array<[CreativeStrategy, string, string]> = [
    ['plot_adjust', '调整剧情', '保留核心剧情，修改事件、顺序与细节。'],
    ['expansion', '增加剧情', '在当前章节之后创建新的承接章节，不改写原章节。'],
    ['plot_rewrite', '重写剧情', '保留必要设定与约束，重新组织本章剧情。'],
  ];
  return <section className="flow-stage-card direction-stage"><div className="strategy-grid compact">{options.map(([key, title, description]) => <button className={strategy === key ? 'active' : ''} key={key} onClick={() => onStrategy(key)} type="button"><strong>{title}</strong><span>{description}</span>{strategy === key ? <Check aria-hidden="true" className="strategy-check" size={16} /> : null}</button>)}</div><label className="flow-field"><span>具体要求</span><textarea className="flow-text-surface" placeholder="描述希望保留、调整或新增的剧情要求" value={instruction} onChange={(event) => onInstruction(event.target.value)} /></label></section>;
}

function AnalysisStage({ draft, instruction, onChange, strategy }: { draft: ChapterSpecialAnalysis | null; instruction: string; onChange: (value: ChapterSpecialAnalysis) => void; strategy?: CreativeStrategy }) {
  if (!strategy) return <LockedStage text="请先完成方向选择。" />;
  if (!draft) return <EmptyStage icon={<WandSparkles size={22} />} title="生成专项分析" />;
  return <section className="flow-stage-card analysis-stage"><label className="analysis-brief-instruction flow-field"><span>具体要求</span><textarea aria-label="具体要求" className="flow-text-surface" readOnly value={instruction || '未填写具体要求'} /></label>{strategy === 'plot_adjust' ? <OutlineTextComparison source={draft.source_outline} target={draft.target_outline} onChange={(target) => onChange({ ...draft, target_outline: target })} /> : <SingleOutlineEditor value={draft.target_outline} onChange={(target) => onChange({ ...draft, target_outline: target })} />}</section>;
}

function StyleStage({ authorId, authors, mode, onAuthor, onMode, workflow }: { authorId: number | null; authors: Material[]; mode: StyleMode; onAuthor: (value: number | null) => void; onMode: (value: StyleMode) => void; workflow: ChapterWorkflowState }) {
  const plotRewrite = workflow.direction?.strategy === 'plot_rewrite'; const selectingAuthor = plotRewrite || mode === 'author';
  if (!workflow.special_analysis) return <LockedStage text="请先完成专项分析。" />;
  return <section className="flow-stage-card style-stage">{!plotRewrite ? <div className="style-mode-choice"><button className={mode === 'document' ? 'active' : ''} onClick={() => onMode('document')} type="button"><strong>提取本文风格</strong></button><button className={mode === 'author' ? 'active' : ''} onClick={() => onMode('author')} type="button"><strong>使用已保存作者</strong></button></div> : null}{selectingAuthor ? <><div className="author-choice-grid">{authors.map((author) => <button className={authorId === author.id ? 'active' : ''} key={author.id} onClick={() => onAuthor(author.id)} type="button"><span className="author-profile-avatar"><BookOpenText size={18} /></span><strong>{author.name}</strong><small>{String(author.content.work || '').trim() || '尚未填写作品'}</small></button>)}</div>{!authors.length ? <div className="inline-alert">还没有可用的已分析作者，请先到“作者”页面完成档案分析。</div> : null}</> : null}{workflow.style ? <StyleGuidanceView generatedGuidance={workflow.style.generated_guidance} snapshot={workflow.style.style_snapshot} /> : null}</section>;
}

function StyleGuidanceView({ generatedGuidance, snapshot }: { generatedGuidance: string; snapshot: unknown }) {
  const structured = normalizeStyleProfile(snapshot) ?? parseStyleProfile(generatedGuidance);
  if (structured) return <section aria-labelledby="style-guidance-title" className="style-guidance"><header className="style-guidance-heading"><div><span className="stage-eyebrow">风格</span><h2 id="style-guidance-title">写作指引</h2></div>{structured.work ? <small>参考作品：{structured.work}</small> : null}</header><div className="style-guidance-content">{structured.overall_style ? <article className="style-guidance-block"><h3>整体风格</h3><p className="flow-text-surface">{structured.overall_style}</p></article> : null}{structured.dimensions?.map((dimension, index) => <StyleDimensionView dimension={dimension} key={dimension.id || dimension.name || index} />)}</div></section>;

  const fallback = parseLegacyGuidance(generatedGuidance);
  if (!fallback) return null;
  return <section aria-labelledby="style-guidance-title" className="style-guidance"><header className="style-guidance-heading"><div><span className="stage-eyebrow">风格</span><h2 id="style-guidance-title">写作指引</h2></div></header><p className="style-guidance-fallback flow-text-surface">{fallback}</p></section>;
}

function StyleDimensionView({ dimension }: { dimension: StyleDimension }) {
  const name = textValue(dimension.name);
  const analysis = textValue(dimension.analysis);
  const features = dimension.features?.map(textValue).filter(Boolean) ?? [];
  const examples = dimension.examples?.map(textValue).filter(Boolean) ?? [];
  if (!name || (!analysis && !features.length && !examples.length)) return null;
  return <article className="style-guidance-block style-dimension"><h3>{name}</h3>{analysis ? <p className="style-dimension-analysis flow-text-surface">{analysis}</p> : null}{features.length ? <div className="style-guidance-list"><span>主要特征</span><ul>{features.map((feature) => <li key={feature}>{feature}</li>)}</ul></div> : null}{examples.length ? <div className="style-guidance-examples"><span>参考表现</span>{examples.map((example) => <p key={example}>{example}</p>)}</div> : null}</article>;
}

function normalizeStyleProfile(snapshot: unknown): StyleProfile | null {
  if (!isRecord(snapshot)) return null;
  const profileSource = isRecord(snapshot.profile) ? snapshot.profile : snapshot;
  const dimensions = Array.isArray(profileSource.dimensions) ? profileSource.dimensions.flatMap((value) => {
    if (!isRecord(value)) return [];
    const name = textValue(value.name);
    if (!name) return [];
    return [{ id: textValue(value.id), name, analysis: textValue(value.analysis), features: stringList(value.features), examples: stringList(value.examples) }];
  }) : [];
  const profile: StyleProfile = {
    work: textValue(profileSource.work) || textValue(snapshot.work),
    overall_style: textValue(profileSource.overall_style) || textValue(snapshot.overall_style),
    dimensions,
  };
  return profile.overall_style || dimensions.length ? profile : null;
}

function parseLegacyGuidance(value: string): string {
  const source = value.trim();
  if (!source) return '';
  try {
    const parsed = JSON.parse(source) as unknown;
    return normalizeStyleProfile(parsed) ? '' : typeof parsed === 'string' ? parsed.trim() : '';
  } catch {
    return source;
  }
}

function parseStyleProfile(value: string): StyleProfile | null {
  try { return normalizeStyleProfile(JSON.parse(value)); } catch { return null; }
}

function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value); }
function textValue(value: unknown): string { return typeof value === 'string' ? value.trim() : ''; }
function stringList(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').map((item) => item.trim()).filter(Boolean) : []; }

function WritingStage({ workflow }: { workflow: ChapterWorkflowState }) {
  if (!workflow.style) return <LockedStage text="请先确定写作风格。" />;
  if (!workflow.writing) return <EmptyStage icon={<WandSparkles size={22} />} title="生成章节草稿" />;
  return <section className="flow-stage-card writing-stage"><article className="writing-paper flow-text-surface">{workflow.writing.result_text}</article></section>;
}

function ReviewStage({ detail, draft, onChange, workflow }: { detail: Chapter | null; draft: string; onChange: (value: string) => void; workflow: ChapterWorkflowState }) {
  if (!workflow.writing) return <LockedStage text="请先生成章节草稿。" />;
  return <section className="flow-stage-card review-stage manual-review-stage"><DiffEditor draft={draft} original={detail?.original_text ?? ''} expansion={workflow.writing.strategy === 'expansion'} onChange={onChange} /></section>;
}

function ContextPanel({ active, act, authors, busy, chapters, detail, drafts, onOpenExport, projectOriginalWordCount, workflow }: { active: UiStage; act: (action: () => Promise<unknown>, next?: UiStage, success?: string) => Promise<void>; authors: Material[]; busy: boolean; chapters: Chapter[]; detail: Chapter | null; drafts: Drafts; onOpenExport: () => void; projectOriginalWordCount: number; workflow: ChapterWorkflowState | null }) {
  const selectedAuthor = authors.find((author) => author.id === workflow?.style?.author_style_material_id);
  const review = active === 'review';
  return <aside className={`creative-context-panel document-detail-panel ${review ? 'review-export-context' : ''}`}><header><h2>{review ? '导出统计' : '章节信息'}</h2></header>{review ? <ReviewExportSummary chapters={chapters} originalWordCount={projectOriginalWordCount} /> : <div className="document-detail-scroll"><section className="document-detail-metadata"><LibraryDefinition label="当前来源" value={workflow?.source_base_kind === 'rewrite_version' ? '已改写版本' : '原文章节'} /><LibraryDefinition label="字数" value={`${detail?.current_word_count ?? 0} 字`} /><LibraryDefinition label="创作方向" value={workflow?.direction ? strategyTitle(workflow.direction.strategy) : '尚未选择'} /><LibraryDefinition label="风格来源" value={workflow?.style?.style_mode === 'selected_author_style' ? selectedAuthor?.name ?? '已保存作者' : workflow?.style ? '整部原作' : '尚未确定'} /></section></div>}<footer className="creative-detail-footer">{workflow ? <StageActions active={active} act={act} busy={busy} drafts={drafts} workflow={workflow} /> : null}{review && workflow?.writing ? <SecondaryButton disabled={busy} onClick={onOpenExport}><Download size={15} />导出文档</SecondaryButton> : null}</footer></aside>;
}

function ReviewExportSummary({ chapters, originalWordCount }: { chapters: Chapter[]; originalWordCount: number }) {
  const exportedWordCount = chapters.reduce((total, chapter) => total + chapter.current_word_count, 0);
  const wordDelta = chapters.reduce((total, chapter) => total + chapter.word_delta, 0);
  const modifiedCount = chapters.filter((chapter) => Boolean(chapter.rewritten_text?.trim()) || chapter.is_added_chapter).length;
  const unmodifiedCount = Math.max(chapters.length - modifiedCount, 0);
  const modifiedRatio = chapters.length ? (modifiedCount / chapters.length) * 100 : 0;
  const unmodifiedRatio = chapters.length ? (unmodifiedCount / chapters.length) * 100 : 0;
  return <div className="document-detail-scroll review-export-scroll"><div className="review-export-stats"><section className="review-export-card review-export-total"><div className="review-export-delta"><span aria-hidden="true" className="review-export-delta-line" /><strong>{formatSignedCount(wordDelta)}</strong></div><div className="review-export-compare"><div><span>原书</span><strong>{formatExportCount(originalWordCount)}</strong></div><ChevronRight aria-hidden="true" size={18} /><div><span>导出</span><strong>{formatExportCount(exportedWordCount)}</strong></div></div></section><section className="review-export-card review-export-breakdown"><div aria-label={`已修改 ${modifiedCount} 章，未修改 ${unmodifiedCount} 章`} className="review-export-bar"><span className="review-export-bar-modified" style={{ width: `${modifiedRatio}%` }} /><span className="review-export-bar-unmodified" style={{ width: `${unmodifiedRatio}%` }} /></div><div className="review-export-legend"><span><i className="review-export-dot review-export-dot-current" />已修改 {modifiedCount} 章</span><span><i className="review-export-dot review-export-dot-source" />未修改 {unmodifiedCount} 章</span></div></section></div></div>;
}

function StageActions({ active, act, busy, drafts, workflow }: { active: UiStage; act: (action: () => Promise<unknown>, next?: UiStage, success?: string) => Promise<void>; busy: boolean; drafts: Drafts; workflow: ChapterWorkflowState }) {
  if (active === 'summary') return <>{drafts.summaryDraft ? <SecondaryButton disabled={busy} onClick={() => void act(() => runChapterSummary(workflow.chapter_id), 'summary', '内容总结已生成。')}><RefreshCw size={14} />重新生成</SecondaryButton> : <PrimaryButton disabled={busy} onClick={() => void act(() => runChapterSummary(workflow.chapter_id), 'summary', '内容总结已生成。')}><Sparkles size={15} />生成内容总结</PrimaryButton>}{drafts.summaryDraft ? <PrimaryButton disabled={busy || !drafts.summaryDraft.plot_summary.trim()} onClick={() => void act(() => saveChapterSummary(workflow.chapter_id, drafts.summaryDraft!), 'direction', '内容总结已保存。')}>保存并选择方向<ChevronRight size={15} /></PrimaryButton> : null}</>;
  if (active === 'direction') return <PrimaryButton disabled={busy} onClick={() => void act(() => saveChapterDirection(workflow.chapter_id, drafts.directionStrategy, drafts.directionInstruction), 'special_analysis', '创作方向已保存。')}>保存并开始分析<ChevronRight size={15} /></PrimaryButton>;
  if (active === 'special_analysis') return <>{drafts.analysisDraft ? <SecondaryButton disabled={busy} onClick={() => void act(() => runChapterSpecialAnalysis(workflow.chapter_id), 'special_analysis', '专项分析已生成。')}><RefreshCw size={14} />重新分析</SecondaryButton> : <PrimaryButton disabled={busy || !workflow.direction} onClick={() => void act(() => runChapterSpecialAnalysis(workflow.chapter_id), 'special_analysis', '专项分析已生成。')}><Sparkles size={15} />开始分析</PrimaryButton>}{drafts.analysisDraft ? <PrimaryButton disabled={busy || !drafts.analysisDraft.target_outline.trim()} onClick={() => void act(() => saveChapterSpecialAnalysis(workflow.chapter_id, drafts.analysisDraft!), 'style', '新大纲已保存。')}>保存新大纲<ChevronRight size={15} /></PrimaryButton> : null}</>;
  if (active === 'style') { const selectingAuthor = workflow.direction?.strategy === 'plot_rewrite' || drafts.styleMode === 'author'; return <PrimaryButton disabled={busy || !workflow.special_analysis || (selectingAuthor && !drafts.authorId)} onClick={() => void act(() => resolveChapterStyle(workflow.chapter_id, { author_style_material_id: selectingAuthor ? drafts.authorId : null }), 'writing', '写作风格已确定。')}>{workflow.style ? '重新确定风格' : selectingAuthor ? '使用所选作者风格' : '提取并使用本文风格'}<ChevronRight size={15} /></PrimaryButton>; }
  if (active === 'writing') return <PrimaryButton disabled={busy || !workflow.style} onClick={() => void act(() => generateChapterWriting(workflow.chapter_id, Boolean(workflow.writing)), 'review', '章节草稿已生成。')}>{workflow.writing ? <><RefreshCw size={14} />重新生成草稿</> : <><Sparkles size={15} />开始写作</>}</PrimaryButton>;
  if (!workflow.writing) return null;
  const saved = drafts.reviewDraft === workflow.writing.result_text;
  return <SecondaryButton disabled={busy || saved || !drafts.reviewDraft.trim()} onClick={() => void act(() => saveChapterWriting(workflow.chapter_id, drafts.reviewDraft), 'review', '修改稿已保存。')}><Save size={14} />保存修改</SecondaryButton>;
}

type DiffPart = { text: string; changed: boolean };
function DiffEditor({ draft, expansion, onChange, original }: { draft: string; expansion: boolean; onChange: (value: string) => void; original: string }) {
  const highlighted = useMemo(() => sentenceDiff(original, draft), [original, draft]); const previewRef = useRef<HTMLElement>(null);
  return <div className="manual-review-columns"><section><header><strong>{expansion ? '前一章原文' : '原始正文'}</strong><span>只读</span></header><article className="flow-text-surface">{renderDiff(highlighted.original, 'removed')}</article></section><section><header><strong>{expansion ? '新增章节正文' : '修改后正文'}</strong><span>可编辑</span></header><div className="review-diff-editor"><article aria-hidden="true" className="flow-text-surface" ref={previewRef}>{renderDiff(highlighted.draft, 'added')}</article><textarea aria-label={expansion ? '新增章节正文' : '修改后正文'} className="flow-text-surface" value={draft} onChange={(event) => onChange(event.target.value)} onScroll={(event) => { if (previewRef.current) { previewRef.current.scrollTop = event.currentTarget.scrollTop; previewRef.current.scrollLeft = event.currentTarget.scrollLeft; } }} /></div></section></div>;
}
function renderDiff(parts: DiffPart[], kind: 'added' | 'removed'): ReactNode { return parts.map((part, index) => part.changed ? <mark className={`review-diff-${kind}`} key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>); }
function sentenceDiff(original: string, draft: string): { original: DiffPart[]; draft: DiffPart[] } {
  const left = diffTokens(original); const right = diffTokens(draft); const table = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i -= 1) for (let j = right.length - 1; j >= 0; j -= 1) table[i][j] = left[i] === right[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
  const source: DiffPart[] = []; const target: DiffPart[] = []; let i = 0; let j = 0;
  while (i < left.length || j < right.length) { if (i < left.length && j < right.length && left[i] === right[j]) { source.push({ text: left[i], changed: false }); target.push({ text: right[j], changed: false }); i += 1; j += 1; } else if (i < left.length && (j >= right.length || table[i + 1][j] >= table[i][j + 1])) { source.push({ text: left[i], changed: true }); i += 1; } else { target.push({ text: right[j], changed: true }); j += 1; } }
  return { original: source, draft: target };
}
function diffTokens(text: string): string[] { return text.match(/[^。！？!?；;\n]+[。！？!?；;\n]*|[。！？!?；;\n]+/g) ?? (text ? [text] : []); }
function OutlineTextComparison({ source, target, onChange }: { source: string; target: string; onChange: (value: string) => void }) { return <section className="outline-text-comparison"><header><div><h3>旧大纲</h3><span>只读</span></div><div><h3>新大纲及细节</h3><span>可修改</span></div></header><div className="outline-text-columns"><textarea aria-label="旧大纲" className="outline-editor-surface flow-text-surface" readOnly value={source || '暂无旧大纲'} /><textarea aria-label="新大纲及细节" className="outline-editor-surface flow-text-surface" onChange={(event) => onChange(event.target.value)} value={target} /></div></section>; }
function SingleOutlineEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) { return <label className="flow-field single-outline-editor"><span>新大纲</span><textarea aria-label="新大纲" className="outline-editor-surface flow-text-surface" value={value} onChange={(event) => onChange(event.target.value)} /></label>; }
function EmptyStage({ icon, title }: { icon: ReactNode; title: string }) { return <section className="flow-stage-card empty-stage"><span>{icon}</span><h2>{title}</h2><p>请使用右侧操作继续。</p></section>; }
function LockedStage({ text }: { text: string }) { return <section className="flow-stage-card empty-stage"><span><ChevronRight size={22} /></span><h2>前一步尚未完成</h2><p>{text}</p></section>; }
function stageForState(stage: CreativeWorkflowStage): UiStage { return stage === 'not_started' ? 'summary' : stage === 'confirmed' ? 'review' : stage; }
function stageComplete(workflow: ChapterWorkflowState, stage: UiStage): boolean { return Boolean(stage === 'summary' ? workflow.summary : stage === 'direction' ? workflow.direction : stage === 'special_analysis' ? workflow.special_analysis : stage === 'style' ? workflow.style : stage === 'writing' ? workflow.writing : workflow.writing?.status === 'reviewed' || workflow.current_stage === 'confirmed'); }
function availableStageIndex(workflow: ChapterWorkflowState): number { const firstMissing = STAGES.findIndex((stage) => !stageComplete(workflow, stage.key)); return firstMissing < 0 ? 5 : firstMissing; }
function strategyTitle(value: CreativeStrategy): string { return ({ plot_adjust: '调整剧情', expansion: '增加剧情', plot_rewrite: '重写剧情' })[value]; }
function formatExportCount(value: number): string { return value >= 10000 ? `${(value / 10000).toFixed(value % 10000 ? 1 : 0)}万` : value.toLocaleString('zh-CN'); }
function formatSignedCount(value: number): string { return `${value >= 0 ? '+' : '-'}${formatExportCount(Math.abs(value))}`; }
function messageOf(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason); }
