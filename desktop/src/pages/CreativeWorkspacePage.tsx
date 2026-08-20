import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowLeft, BookOpenText, Check, ChevronRight, Plus, RefreshCw, Save, Sparkles, Trash2, WandSparkles } from 'lucide-react';
import { confirmChapterWorkflow, generateChapterWriting, getChapter, getChapters, getChapterWorkflow, getMaterials, resolveChapterStyle, runChapterSpecialAnalysis, runChapterSummary, saveChapterDirection, saveChapterSpecialAnalysis, saveChapterSummary, saveChapterWriting } from '../api/client';
import type { Chapter, ChapterCreativeIntent, ChapterDetail, ChapterSpecialAnalysis, ChapterSummary, ChapterWorkflowState, CreativeStrategy, CreativeWorkflowStage, Material, OutlineNode } from '../api/types';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';

type Props = { projectId: number; projectName: string; onNavigate: (path: string, state?: unknown) => void };
type UiStage = 'summary' | 'direction' | 'special_analysis' | 'style' | 'writing' | 'review';
const STAGES: Array<{ key: UiStage; label: string }> = [{ key: 'summary', label: '内容总结' }, { key: 'direction', label: '方向选择' }, { key: 'special_analysis', label: '专项分析' }, { key: 'style', label: '风格' }, { key: 'writing', label: '写作' }, { key: 'review', label: '审查' }];

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);
  const [workflow, setWorkflow] = useState<ChapterWorkflowState | null>(null);
  const [authors, setAuthors] = useState<Material[]>([]);
  const [activeStage, setActiveStage] = useState<UiStage>('summary');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getChapters(projectId), getMaterials({ material_type: 'author_style' })]).then(([items, profiles]) => {
      if (!cancelled) { setChapters(items); setAuthors(profiles); setSelectedId(items[0]?.id ?? null); }
    }).catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [projectId]);

  const refresh = useCallback(async (chapterId: number, moveTo?: UiStage) => {
    const [value, state] = await Promise.all([getChapter(chapterId), getChapterWorkflow(chapterId)]);
    setDetail(value); setWorkflow(state); setActiveStage(moveTo ?? stageForState(state.current_stage));
  }, []);

  useEffect(() => {
    if (!selectedId) { setDetail(null); setWorkflow(null); return; }
    let cancelled = false;
    void Promise.all([getChapter(selectedId), getChapterWorkflow(selectedId)]).then(([value, state]) => {
      if (!cancelled) { setDetail(value); setWorkflow(state); setActiveStage(stageForState(state.current_stage)); }
    }).catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [selectedId]);

  async function act(action: () => Promise<unknown>, next?: UiStage, success?: string) {
    if (!selectedId || busy) return;
    setBusy(true); setError(null); setMessage(null);
    try { await action(); await refresh(selectedId, next); if (success) setMessage(success); }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  return <div className="creative-workspace chapter-flow-page">
    <header className="creative-topbar"><div className="creative-project-title"><button className="button ghost" onClick={() => onNavigate('/library')} type="button"><ArrowLeft size={16} />工程</button><div><h1>{projectName}</h1><span>章节创作工作台</span></div></div><div className="creative-direction-marker">{workflow ? stageLabel(workflow.current_stage) : '正在读取'}</div></header>
    {error ? <div className="inline-alert error creative-alert" role="alert">{error}</div> : null}{message ? <div className="inline-alert success creative-alert" role="status">{message}</div> : null}{workflow?.source_changed ? <div className="inline-alert error creative-alert">章节原文已经变化，请从内容总结重新开始，避免沿用过期分析。</div> : null}
    <div className="creative-columns chapter-flow-columns">
      <StageProgress active={activeStage} availableIndex={workflow ? availableStageIndex(workflow) : 0} onSelect={setActiveStage} workflow={workflow} />
      <aside className="chapter-rail"><h2>章节</h2><div className="chapter-only-list">{chapters.map((chapter) => <button className={chapter.id === selectedId ? 'active' : ''} key={chapter.id} onClick={() => setSelectedId(chapter.id)} type="button"><span>第 {chapter.index} 章<br /><strong>{chapter.title}</strong></span><small>{chapter.word_count} 字</small></button>)}</div><div className="rail-save-state">{workflow?.current_stage === 'confirmed' ? '本章已确认' : '各阶段自动保存到当前章节'}</div></aside>
      <main className="chapter-workspace"><div className="chapter-workspace-head"><span>第 {detail?.chapter.index ?? '—'} 章</span><h1>{detail?.chapter.title ?? '请选择章节'}</h1></div>{!selectedId || !workflow ? <div className="stage-placeholder"><h2>正在读取章节工作流…</h2></div> : <StageContent active={activeStage} authors={authors} busy={busy} detail={detail} workflow={workflow} act={act} />}</main>
      <ContextPanel authors={authors} detail={detail} workflow={workflow} />
    </div>
  </div>;
}

function StageProgress({ active, availableIndex, onSelect, workflow }: { active: UiStage; availableIndex: number; onSelect: (stage: UiStage) => void; workflow: ChapterWorkflowState | null }) {
  return <nav aria-label="章节创作阶段" className="creative-workflow-progress creative-stage-rail">{STAGES.map((stage, index) => { const complete = workflow ? stageComplete(workflow, stage.key) : false; return <button className={`${active === stage.key ? 'active' : ''} ${complete ? 'complete' : ''}`} disabled={index > availableIndex} key={stage.key} onClick={() => onSelect(stage.key)} type="button"><span>{complete ? <Check size={9} /> : null}</span>{stage.label}</button>; })}</nav>;
}

function StageContent({ active, authors, busy, detail, workflow, act }: { active: UiStage; authors: Material[]; busy: boolean; detail: ChapterDetail | null; workflow: ChapterWorkflowState; act: (action: () => Promise<unknown>, next?: UiStage, success?: string) => Promise<void> }) {
  if (active === 'summary') return <SummaryStage busy={busy} value={workflow.summary} onRun={() => act(() => runChapterSummary(workflow.chapter_id), 'direction', '内容总结已生成。')} onSave={(value) => act(() => saveChapterSummary(workflow.chapter_id, value), 'direction', '内容总结已保存。')} />;
  if (active === 'direction') return <DirectionStage busy={busy} value={workflow.direction} onSave={(strategy, instruction) => act(() => saveChapterDirection(workflow.chapter_id, strategy, instruction), 'special_analysis', '创作方向已保存。')} />;
  if (active === 'special_analysis') return <AnalysisStage busy={busy} detail={detail} value={workflow.special_analysis} strategy={workflow.direction?.strategy} onRun={(level) => act(() => runChapterSpecialAnalysis(workflow.chapter_id, level), 'special_analysis', '专项分析已生成。')} onSave={(value) => act(() => saveChapterSpecialAnalysis(workflow.chapter_id, value), 'style', '目标大纲已保存。')} />;
  if (active === 'style') return <StyleStage authors={authors} busy={busy} workflow={workflow} onResolve={(value) => act(() => resolveChapterStyle(workflow.chapter_id, value), 'writing', '写作风格已确定。')} />;
  if (active === 'writing') return <WritingStage busy={busy} workflow={workflow} onGenerate={(replace) => act(() => generateChapterWriting(workflow.chapter_id, replace), 'review', '章节草稿已生成。')} />;
  return <ReviewStage busy={busy} detail={detail} workflow={workflow} onSave={(text) => act(() => saveChapterWriting(workflow.chapter_id, text), 'review', '修改稿已保存。')} onConfirm={(text) => act(async () => { await saveChapterWriting(workflow.chapter_id, text); await confirmChapterWorkflow(workflow.chapter_id); }, 'review', '本章已由人工确认，可进入下一章。')} />;
}

function SummaryStage({ busy, value, onRun, onSave }: { busy: boolean; value: ChapterSummary | null; onRun: () => void; onSave: (value: ChapterSummary) => void }) {
  const [draft, setDraft] = useState(value); useEffect(() => setDraft(value), [value]);
  if (!draft) return <EmptyStage icon={<Sparkles size={22} />} title="先理解这一章" description="AI 会总结剧情、人物、关键事件、重要事实和未解决线索，后续阶段都以这份总结为基础。" action={<PrimaryButton disabled={busy} onClick={onRun}><Sparkles size={15} />生成内容总结</PrimaryButton>} />;
  return <section className="flow-stage-card summary-stage"><StageHeading eyebrow="第一阶段" title="内容总结" action={<SecondaryButton disabled={busy} onClick={onRun}><RefreshCw size={14} />重新生成</SecondaryButton>} /><label className="flow-field"><span>剧情总结</span><textarea value={draft.plot_summary} onChange={(event) => setDraft({ ...draft, plot_summary: event.target.value })} /></label><InfoGrid items={[["主要人物", displayList(draft.main_characters)], ["关键事件", displayList(draft.key_events)], ["重要事实", displayList(draft.important_facts)], ["未解决线索", displayList(draft.open_threads)]]} /><footer><PrimaryButton disabled={busy || !draft.plot_summary.trim()} onClick={() => onSave(draft)}>保存并选择方向<ChevronRight size={15} /></PrimaryButton></footer></section>;
}

function DirectionStage({ busy, value, onSave }: { busy: boolean; value: ChapterCreativeIntent | null; onSave: (strategy: CreativeStrategy, instruction: string) => void }) {
  const [strategy, setStrategy] = useState<CreativeStrategy>(value?.strategy ?? 'plot_adjust'); const [instruction, setInstruction] = useState(value?.user_instruction ?? ''); useEffect(() => { if (value) { setStrategy(value.strategy); setInstruction(value.user_instruction); } }, [value]);
  const options: Array<[CreativeStrategy, string, string]> = [['plot_adjust', '调整剧情', '保留章节主干，修改、删除或插入局部情节。'], ['expansion', '扩写内容', '不改变核心事件，补足场景、动作、心理与细节。'], ['reimagine', '重新构思', '保留可用事实，以新的目标大纲和指定作者风格重写。']];
  return <section className="flow-stage-card direction-stage"><StageHeading eyebrow="第二阶段" title="选择本章怎么改" /><div className="strategy-grid compact">{options.map(([key, title, description]) => <button className={strategy === key ? 'active' : ''} key={key} onClick={() => setStrategy(key)} type="button"><strong>{title}</strong><span>{description}</span></button>)}</div><label className="flow-field"><span>你的具体要求</span><textarea placeholder="例如：保留人物相遇，但让冲突更早发生；不要改变已确认的世界观事实。" value={instruction} onChange={(event) => setInstruction(event.target.value)} /></label><footer><PrimaryButton disabled={busy} onClick={() => onSave(strategy, instruction)}>保存并开始分析<ChevronRight size={15} /></PrimaryButton></footer></section>;
}

function AnalysisStage({ busy, detail, value, strategy, onRun, onSave }: { busy: boolean; detail: ChapterDetail | null; value: ChapterSpecialAnalysis | null; strategy?: CreativeStrategy; onRun: (level?: 'brief' | 'detailed') => void; onSave: (value: ChapterSpecialAnalysis) => void }) {
  const [level, setLevel] = useState<'brief' | 'detailed'>('detailed'); const [draft, setDraft] = useState(value); useEffect(() => setDraft(value), [value]);
  if (!strategy) return <LockedStage text="请先完成方向选择。" />;
  if (!draft) return <EmptyStage icon={<WandSparkles size={22} />} title="生成专项分析" description={strategyDescription(strategy)} action={<div className="empty-stage-actions">{strategy === 'reimagine' ? <select value={level} onChange={(event) => setLevel(event.target.value as 'brief' | 'detailed')}><option value="brief">简要大纲</option><option value="detailed">详细大纲</option></select> : null}<PrimaryButton disabled={busy} onClick={() => onRun(strategy === 'reimagine' ? level : undefined)}><Sparkles size={15} />开始分析</PrimaryButton></div>} />;
  return <section className="flow-stage-card analysis-stage"><StageHeading eyebrow="第三阶段" title="专项分析" action={<SecondaryButton disabled={busy} onClick={() => onRun(draft.outline_detail_level ?? undefined)}><RefreshCw size={14} />重新分析</SecondaryButton>} /><div className="analysis-brief"><span>选择方向</span><strong>{strategyTitle(strategy)}</strong><span>具体要求</span><p>{draft.analysis_notes.length ? displayList(draft.analysis_notes) : '根据原文结构编辑目标大纲。'}</p></div><div className="outline-columns"><OutlineColumn editable={false} label="原始大纲" nodes={draft.source_outline} onChange={() => undefined} /><OutlineColumn editable label="目标大纲" nodes={draft.target_outline} onChange={(nodes) => setDraft({ ...draft, target_outline: nodes })} /></div><section className="analysis-source-text"><header><strong>来源正文</strong><span>{detail?.chapter.word_count ?? 0} 字</span></header><p>{detail?.chapter.original_text || '暂无原文'}</p></section><footer><PrimaryButton disabled={busy} onClick={() => onSave(draft)}>保存目标大纲<ChevronRight size={15} /></PrimaryButton></footer></section>;
}

function StyleStage({ authors, busy, workflow, onResolve }: { authors: Material[]; busy: boolean; workflow: ChapterWorkflowState; onResolve: (value: { source_scope?: 'document' | 'chapter'; author_style_material_id?: number | null }) => void }) {
  const reimagine = workflow.direction?.strategy === 'reimagine'; const usable = authors.filter((author) => author.analysis_status === 'analyzed'); const [authorId, setAuthorId] = useState<number | null>(workflow.style?.author_style_material_id ?? usable[0]?.id ?? null); const [scope, setScope] = useState<'document' | 'chapter'>(workflow.style?.source_scope ?? 'document');
  if (!workflow.special_analysis) return <LockedStage text="请先完成专项分析。" />;
  return <section className="flow-stage-card style-stage"><StageHeading eyebrow="第四阶段" title="确定写作风格" />{reimagine ? <><p className="stage-lead">重新构思需要选择一位已分析的作者，写作时会使用该作者档案的整体风格和各分析维度。</p><div className="author-choice-grid">{usable.map((author) => <button className={authorId === author.id ? 'active' : ''} key={author.id} onClick={() => setAuthorId(author.id)} type="button"><span className="author-profile-avatar"><BookOpenText size={18} /></span><strong>{author.name}</strong><small>{author.categories.join(' · ') || '作者档案'}</small></button>)}</div>{!usable.length ? <div className="inline-alert">还没有可用的已分析作者，请先到“作者”页面完成档案分析。</div> : null}</> : <><p className="stage-lead">当前方向会自动学习原作风格。你只需决定参考整部作品，还是仅参考当前章节。</p><div className="scope-choice"><button className={scope === 'document' ? 'active' : ''} onClick={() => setScope('document')} type="button"><strong>整部作品</strong><span>风格更稳定，适合大多数章节</span></button><button className={scope === 'chapter' ? 'active' : ''} onClick={() => setScope('chapter')} type="button"><strong>当前章节</strong><span>更贴近本章局部语气</span></button></div></>}{workflow.style?.generated_guidance ? <div className="style-guidance"><strong>已生成的写作指引</strong><p>{workflow.style.generated_guidance}</p></div> : null}<footer><PrimaryButton disabled={busy || (reimagine && !authorId)} onClick={() => onResolve(reimagine ? { author_style_material_id: authorId } : { source_scope: scope })}>{workflow.style ? '重新确定风格' : '确定风格'}<ChevronRight size={15} /></PrimaryButton></footer></section>;
}

function WritingStage({ busy, workflow, onGenerate }: { busy: boolean; workflow: ChapterWorkflowState; onGenerate: (replace: boolean) => void }) {
  if (!workflow.style) return <LockedStage text="请先确定写作风格。" />;
  if (!workflow.writing) return <EmptyStage icon={<WandSparkles size={22} />} title="生成章节草稿" description="系统会结合内容总结、目标结构、创作要求和风格指引，生成一版完整章节。" action={<PrimaryButton disabled={busy} onClick={() => onGenerate(false)}><Sparkles size={15} />开始写作</PrimaryButton>} />;
  return <section className="flow-stage-card writing-stage"><StageHeading eyebrow="第五阶段" title="章节草稿" action={<SecondaryButton disabled={busy} onClick={() => onGenerate(true)}><RefreshCw size={14} />重新生成</SecondaryButton>} /><article className="writing-paper">{workflow.writing.result_text}</article><p className="writing-next-hint">下一步进入人工审查，可对照原文直接编辑修改稿。</p><footer><PrimaryButton disabled={busy} onClick={() => onGenerate(true)}>重新生成草稿</PrimaryButton></footer></section>;
}

function ReviewStage({ busy, detail, workflow, onSave, onConfirm }: { busy: boolean; detail: ChapterDetail | null; workflow: ChapterWorkflowState; onSave: (text: string) => void; onConfirm: (text: string) => void }) {
  const [draft, setDraft] = useState(workflow.writing?.result_text ?? ''); useEffect(() => setDraft(workflow.writing?.result_text ?? ''), [workflow.writing?.result_text]);
  if (!workflow.writing) return <LockedStage text="请先生成章节草稿。" />;
  const saved = draft === workflow.writing.result_text;
  return <section className="flow-stage-card review-stage manual-review-stage"><StageHeading eyebrow="第六阶段 · 人工" title="原文与修改后对照" /><div className="manual-review-columns"><section><header><strong>原始正文</strong><span>{detail?.chapter.word_count ?? 0} 字 · 只读</span></header><article>{detail?.chapter.original_text || '暂无原文'}</article></section><section><header><strong>修改后正文</strong><span>{draft.trim().length} 字 · 可编辑</span></header><textarea aria-label="修改后正文" value={draft} onChange={(event) => setDraft(event.target.value)} /></section></div><p className="manual-review-note">这里由你人工审查。系统不会再次调用模型，也不会自动判定问题。</p><footer><SecondaryButton disabled={busy || saved || !draft.trim()} onClick={() => onSave(draft)}><Save size={14} />保存修改</SecondaryButton><PrimaryButton disabled={busy || !draft.trim() || workflow.current_stage === 'confirmed'} onClick={() => onConfirm(draft)}>{workflow.current_stage === 'confirmed' ? '本章已确认' : '保存并人工确认'}<Check size={15} /></PrimaryButton></footer></section>;
}

function ContextPanel({ authors, detail, workflow }: { authors: Material[]; detail: ChapterDetail | null; workflow: ChapterWorkflowState | null }) {
  const selectedAuthor = authors.find((author) => author.id === workflow?.style?.author_style_material_id);
  return <aside className="creative-context-panel"><h2>章节上下文</h2><section><h3>当前来源</h3><p>{workflow?.source_base_kind === 'rewrite_version' ? '已改写版本' : '原文章节'} · {detail?.chapter.word_count ?? 0} 字</p></section><section><h3>创作方向</h3><p>{workflow?.direction ? strategyTitle(workflow.direction.strategy) : '尚未选择'}</p></section><section><h3>风格来源</h3><p>{selectedAuthor?.name ?? (workflow?.style ? workflow.style.source_scope === 'chapter' ? '当前章节' : '整部原作' : '尚未确定')}</p></section><section><h3>重要事实</h3><ul className="context-fact-list">{workflow?.summary?.important_facts?.length ? workflow.summary.important_facts.slice(0, 6).map((item, index) => <li key={index}>{displayValue(item)}</li>) : <li>完成内容总结后显示</li>}</ul></section></aside>;
}

function OutlineColumn({ editable, label, nodes, onChange }: { editable: boolean; label: string; nodes: OutlineNode[]; onChange: (nodes: OutlineNode[]) => void }) { return <section className="outline-column"><header><h3>{label}</h3><span>{nodes.length} 条</span></header>{nodes.map((node, index) => <article key={node.id || index}><span className="outline-index">{index + 1}</span>{editable ? <><textarea value={outlineText(node)} onChange={(event) => onChange(nodes.map((item, itemIndex) => itemIndex === index ? patchOutlineText(item, event.target.value) : item))} /><select aria-label={`第 ${index + 1} 条操作`} className={`outline-operation ${String(node.operation ?? 'preserve')}`} value={String(node.operation ?? 'preserve')} onChange={(event) => onChange(nodes.map((item, itemIndex) => itemIndex === index ? { ...item, operation: event.target.value as OutlineNode['operation'] } : item))}><option value="preserve">保留</option><option value="modify">修改</option><option value="delete">删除</option><option value="insert">新增</option></select><button aria-label={`删除第 ${index + 1} 条目标大纲`} className="outline-delete" onClick={() => onChange(nodes.filter((_, itemIndex) => itemIndex !== index))} type="button"><Trash2 size={13} /></button></> : <><p>{outlineText(node)}</p><span className="outline-source-span">{String(node.source_span ?? node.source_reference ?? `原文节点 ${index + 1}`)}</span><span className={`outline-operation ${String(node.operation ?? 'preserve')}`}>{operationLabel(node.operation)}</span></>}</article>)}{editable ? <button className="outline-add" onClick={() => onChange([...nodes, { id: crypto.randomUUID(), operation: 'insert', summary: '' }])} type="button"><Plus size={14} />新增大纲</button> : null}</section>; }
function StageHeading({ action, eyebrow, title }: { action?: ReactNode; eyebrow: string; title: string }) { return <header className="flow-stage-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div>{action}</header>; }
function EmptyStage({ action, description, icon, title }: { action: ReactNode; description: string; icon: ReactNode; title: string }) { return <section className="flow-stage-card empty-stage"><span>{icon}</span><h2>{title}</h2><p>{description}</p>{action}</section>; }
function LockedStage({ text }: { text: string }) { return <section className="flow-stage-card empty-stage"><span><ChevronRight size={22} /></span><h2>前一步尚未完成</h2><p>{text}</p></section>; }
function InfoGrid({ items }: { items: Array<[string, string]> }) { return <div className="flow-info-grid">{items.map(([label, value]) => <section key={label}><span>{label}</span><p>{value || '暂无'}</p></section>)}</div>; }
function stageForState(stage: CreativeWorkflowStage): UiStage { return stage === 'not_started' ? 'summary' : stage === 'confirmed' ? 'review' : stage; }
function stageLabel(stage: CreativeWorkflowStage): string { return ({ not_started: '尚未开始', summary: '内容总结', direction: '方向选择', special_analysis: '专项分析', style: '风格', writing: '写作', review: '审查', confirmed: '已确认' })[stage]; }
function stageComplete(workflow: ChapterWorkflowState, stage: UiStage): boolean { return Boolean(stage === 'summary' ? workflow.summary : stage === 'direction' ? workflow.direction : stage === 'special_analysis' ? workflow.special_analysis : stage === 'style' ? workflow.style : stage === 'writing' ? workflow.writing : workflow.writing?.status === 'reviewed' || workflow.current_stage === 'confirmed'); }
function availableStageIndex(workflow: ChapterWorkflowState): number { const firstMissing = STAGES.findIndex((stage) => !stageComplete(workflow, stage.key)); return firstMissing < 0 ? 5 : firstMissing; }
function strategyTitle(value: CreativeStrategy): string { return ({ plot_adjust: '调整剧情', expansion: '扩写内容', reimagine: '重新构思' })[value]; }
function strategyDescription(value: CreativeStrategy): string { return ({ plot_adjust: '对照原文结构，标出保留、修改、删除和新增的节点，形成可执行的目标结构。', expansion: '识别需要补足的场景和细节，建立不改变核心事实的扩写方案。', reimagine: '从原文事实出发，生成新的目标大纲，为指定作者风格的重写做好准备。' })[value]; }
function displayList(value: unknown[]): string { return value.map(displayValue).filter(Boolean).join('；'); }
function displayValue(value: unknown): string { if (value == null) return ''; if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value); if (Array.isArray(value)) return value.map(displayValue).join('、'); if (typeof value === 'object') { const record = value as Record<string, unknown>; return String(record.name ?? record.title ?? record.summary ?? record.description ?? Object.values(record).map(displayValue).filter(Boolean).join(' · ')); } return String(value); }
function outlineText(node: OutlineNode): string { return String(node.summary ?? node.title ?? node.content ?? node.text ?? node.description ?? '未命名节点'); }
function patchOutlineText(node: OutlineNode, value: string): OutlineNode { if ('summary' in node) return { ...node, summary: value }; if ('title' in node) return { ...node, title: value }; if ('content' in node) return { ...node, content: value }; return { ...node, summary: value }; }
function operationLabel(value: OutlineNode['operation']): string { return ({ preserve: '保留', modify: '修改', delete: '删除', insert: '新增' } as Record<string, string>)[String(value)] ?? '原文'; }
function messageOf(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason); }
