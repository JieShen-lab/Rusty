import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { GitBranch, GitFork, ListTree, Plus, RefreshCw, Settings2 } from 'lucide-react';
import {
  applyCanonChange,
  confirmPlotGenerationSeams,
  confirmPlotGenerationSkeleton,
  confirmStorySkeleton,
  createStorySkeleton,
  createProjectFromLegacy,
  deleteStoryBranch,
  executePlotGeneration,
  executeProseRewrite,
  getCanonChangeRun,
  getChapterStorySkeleton,
  getLegacyAnalysisExport,
  getPlotGenerationRun,
  getProseRewriteRun,
  getStoryBranches,
  planProseRewrite,
  reviewCanonPatch,
  reviseStorySkeleton,
  scanCanonChange,
  startPlotGeneration,
} from '../api/client';
import type {
  CanonChangeRun,
  Chapter,
  PlotGenerationRun,
  ProseRewriteRun,
  SeamProposal,
  StoryBranch,
  StructuredSkeleton,
} from '../api/types';

type Operation = 'plot_generation' | 'prose_rewrite' | 'canon_change';
type GenerationMode = 'bounded_insert' | 'open_continuation' | 'fork' | 'fork_and_rejoin';

function usePersistedRun<T>(
  key: string,
  load: (id: number) => Promise<T>,
): [T | null, (value: T | null, id?: number) => void] {
  const [run, setRunState] = useState<T | null>(null);
  useEffect(() => {
    const id = Number(localStorage.getItem(key));
    if (id) void load(id).then(setRunState).catch(() => localStorage.removeItem(key));
  }, [key, load]);
  function setRun(value: T | null, id?: number) {
    setRunState(value);
    if (value && id) localStorage.setItem(key, String(id));
    if (!value) localStorage.removeItem(key);
  }
  return [run, setRun];
}

export function RewriteOperationPanel({
  chapter,
  projectId,
}: {
  chapter: Chapter | null;
  projectId: number;
}) {
  const [operation, setOperation] = useState<Operation>('plot_generation');
  const [direction, setDirection] = useState('');
  const [sourceSkeleton, setSourceSkeleton] = useState<StructuredSkeleton | null>(null);
  const [sourceSkeletonId, setSourceSkeletonId] = useState<number | null>(null);
  const [oldFact, setOldFact] = useState('');
  const [newFact, setNewFact] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plotRun, setPlotRun] = usePersistedRun(
    `rusty.plot-run.${projectId}`,
    getPlotGenerationRun,
  );
  const [proseRun, setProseRun] = usePersistedRun(
    `rusty.prose-run.${projectId}`,
    getProseRewriteRun,
  );
  const [canonRun, setCanonRun] = usePersistedRun(
    `rusty.canon-run.${projectId}`,
    getCanonChangeRun,
  );

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '工作流请求失败'); }
    finally { setBusy(false); }
  }

  async function beginPlot() {
    if (!chapter || !direction.trim()) return;
    const run = await startPlotGeneration({
      project_id: projectId,
      generation_mode: 'bounded_insert',
      start_anchor: { anchor_type: 'chapter_start', chapter_id: chapter.id },
      return_anchor: { anchor_type: 'chapter_end', chapter_id: chapter.id },
      user_direction: direction.trim(),
    });
    setPlotRun(run, run.id);
  }

  async function beginProse() {
    if (!chapter || !sourceSkeleton) return;
    const run = await planProseRewrite({
      project_id: projectId,
      chapter_id: chapter.id,
      source_skeleton: sourceSkeleton,
      preservation_policy: {
        events: true,
        event_order: true,
        character_motivations: true,
        behavior_results: true,
        knowledge_reveal_order: true,
        causal_links: true,
        foreshadowing: true,
        required_start_state: true,
        required_end_state: true,
        locked_node_ids: sourceSkeleton.event_nodes.filter((node) => node.locked).map((node) => node.id),
      },
      user_direction: direction,
    });
    setProseRun(run, run.id);
  }

  async function loadSkeleton() {
    if (!chapter) return;
    const loaded = await getChapterStorySkeleton(chapter.id);
    if (loaded.format !== 'structured' || !loaded.structured || !loaded.skeleton_id) {
      throw new Error('当前章节还没有结构化细纲，请先运行分析或增加剧情规划。');
    }
    setSourceSkeleton(loaded.structured);
    setSourceSkeletonId(loaded.skeleton_id);
  }

  async function saveSkeleton() {
    if (!chapter || !sourceSkeleton) return;
    if (sourceSkeletonId) {
      const version = await reviseStorySkeleton(
        sourceSkeletonId, undefined, '用户在模块化编辑器中修改', sourceSkeleton,
      );
      await confirmStorySkeleton(sourceSkeletonId, version.version);
      return;
    }
    const version = await createStorySkeleton({
      project_id: projectId,
      chapter_id: chapter.id,
      scope: 'chapter',
      source_kind: 'user_edit',
      structured_skeleton: sourceSkeleton,
    });
    setSourceSkeletonId(version.skeleton_id);
    await confirmStorySkeleton(version.skeleton_id, version.version);
  }

  async function beginCanon() {
    if (!chapter || !oldFact.trim() || !newFact.trim()) return;
    const run = await scanCanonChange({
      project_id: projectId,
      old_fact: { attribute: 'user_fact', value: oldFact.trim() },
      new_fact: { attribute: 'user_fact', value: newFact.trim() },
      effective_order: chapter.index,
    });
    setCanonRun(run, run.id);
  }

  return (
    <section className="workflow-operation-panel" aria-label="改写操作">
      <header><div><span>改写工程</span><h2>选择本次写作操作</h2></div></header>
      <div className="workflow-operation-grid">
        <OperationButton active={operation === 'plot_generation'} icon={<Plus size={18} />} label="增加剧情" onClick={() => setOperation('plot_generation')} />
        <OperationButton active={operation === 'prose_rewrite'} icon={<RefreshCw size={18} />} label="重写正文" onClick={() => setOperation('prose_rewrite')} />
        <OperationButton active={operation === 'canon_change'} icon={<Settings2 size={18} />} label="修改设定" onClick={() => setOperation('canon_change')} />
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {operation === 'plot_generation' ? (
        <div className="operation-fields">
          <label>起点<input readOnly value={chapter ? `${chapter.title} 开始` : '请选择章节'} /></label>
          <label>回接点<input readOnly value={chapter ? `${chapter.title} 结束` : '请选择章节'} /></label>
          <label className="wide">新增剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          {!plotRun ? <button disabled={busy || !chapter || !direction.trim()} onClick={() => void perform(beginPlot)} type="button">启动分析</button> : <RunStatus run={plotRun} />}
          {plotRun?.stage === 'confirm_target_skeleton' ? (
            <ModularSkeletonEditor
              onConfirm={(skeleton) => void perform(async () => setPlotRun(await confirmPlotGenerationSkeleton(plotRun.id, skeleton), plotRun.id))}
              skeleton={plotRun.target_skeleton}
            />
          ) : null}
          {plotRun?.stage === 'confirm_seams' && Array.isArray(plotRun.seams) && chapter ? (
            <SeamReview
              onConfirm={(seams) => void perform(async () => setPlotRun(await confirmPlotGenerationSeams(plotRun.id, { seams, current_source_text: chapter.original_text }), plotRun.id))}
              seams={plotRun.seams}
            />
          ) : null}
          {plotRun?.status === 'ready' ? <button disabled={busy} onClick={() => void perform(async () => setPlotRun(await executePlotGeneration(plotRun.id, {}), plotRun.id))} type="button">逐场景生成并检查</button> : null}
          {plotRun?.status === 'completed' ? <pre className="wide">{JSON.stringify(plotRun.result, null, 2)}</pre> : null}
          {plotRun?.status === 'blocked' ? <pre className="wide">{JSON.stringify(plotRun.issues, null, 2)}</pre> : null}
        </div>
      ) : null}
      {operation === 'prose_rewrite' ? (
        <div className="operation-fields">
          <label>范围<input readOnly value={chapter?.title ?? '请选择章节'} /></label>
          <label>源细纲<button disabled={busy || !chapter} onClick={() => void perform(loadSkeleton)} type="button">加载已确认版本</button></label>
          {sourceSkeleton ? <ModularSkeletonEditor onChange={setSourceSkeleton} skeleton={sourceSkeleton} /> : null}
          {sourceSkeleton ? <button disabled={busy} onClick={() => void perform(saveSkeleton)} type="button">保存并确认细纲版本</button> : null}
          <label className="wide">目标风格与说明<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          {!proseRun ? <button disabled={busy || !sourceSkeleton} onClick={() => void perform(beginProse)} type="button">生成重写计划</button> : <RunStatus run={proseRun} />}
          {proseRun?.status === 'planned' ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await executeProseRewrite(proseRun.id, { auto_repair: true }), proseRun.id))} type="button">生成正文并自动检查</button> : null}
          {proseRun ? <pre className="wide">{JSON.stringify(proseRun.issues, null, 2)}</pre> : null}
        </div>
      ) : null}
      {operation === 'canon_change' ? (
        <div className="operation-fields">
          <label>旧设定<input onChange={(event) => setOldFact(event.target.value)} value={oldFact} /></label>
          <label>新设定<input onChange={(event) => setNewFact(event.target.value)} value={newFact} /></label>
          <label>生效点<input readOnly value={chapter ? `第 ${chapter.index} 章` : '请选择章节'} /></label>
          <button disabled={busy || !oldFact.trim() || !newFact.trim()} onClick={() => void perform(beginCanon)} type="button">扫描下游影响</button>
          {canonRun ? <CanonPatchReview onChange={(run) => setCanonRun(run, run.id)} run={canonRun} /> : null}
          {canonRun?.patches.some((patch) => ['accepted', 'edited'].includes(patch.status)) ? <button disabled={busy} onClick={() => void perform(async () => setCanonRun(await applyCanonChange(canonRun.id), canonRun.id))} type="button">原子应用已接受补丁</button> : null}
        </div>
      ) : null}
    </section>
  );
}

export function BranchWorkspacePanel({
  chapters,
  projectId,
  projectName,
}: {
  chapters: Chapter[];
  projectId: number;
  projectName: string;
}) {
  const [mode, setMode] = useState<Exclude<GenerationMode, 'bounded_insert'>>('open_continuation');
  const [branches, setBranches] = useState<StoryBranch[]>([]);
  const [currentBranchId, setCurrentBranchId] = useState<number | null>(null);
  const [startChapterId, setStartChapterId] = useState<number | null>(chapters[0]?.id ?? null);
  const [returnChapterId, setReturnChapterId] = useState<number | null>(chapters.at(-1)?.id ?? null);
  const [direction, setDirection] = useState('');
  const [characterIds, setCharacterIds] = useState('');
  const [materialIds, setMaterialIds] = useState('');
  const [styleId, setStyleId] = useState('');
  const [run, setRun] = usePersistedRun(`rusty.plot-run.${projectId}`, getPlotGenerationRun);
  const [error, setError] = useState('');
  const sourceChapter = chapters.find((item) => item.id === startChapterId) ?? chapters.at(-1);

  useEffect(() => {
    void getStoryBranches(projectId).then(setBranches).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取分支'));
  }, [projectId]);

  async function begin() {
    if (!sourceChapter || !direction.trim()) return;
    const startAnchor = mode === 'open_continuation'
      ? { anchor_type: 'document_end' as const }
      : { anchor_type: 'chapter_end' as const, chapter_id: sourceChapter.id };
    const returnAnchor = mode === 'fork_and_rejoin'
      ? { anchor_type: 'chapter_start' as const, chapter_id: returnChapterId ?? sourceChapter.id }
      : null;
    try {
      const next = await startPlotGeneration({
        project_id: projectId,
        generation_mode: mode,
        start_anchor: startAnchor,
        return_anchor: returnAnchor,
        parent_branch_id: currentBranchId,
        user_direction: direction.trim(),
        selected_character_ids: parseIds(characterIds),
        selected_material_ids: parseIds(materialIds),
        style_profile_id: Number(styleId) || null,
        branch_name: `分支 ${branches.length + 1}`,
      });
      setRun(next, next.id);
      setBranches(await getStoryBranches(projectId));
      setCurrentBranchId(next.branch_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '启动失败'); }
  }

  async function removeCurrentBranch() {
    if (!currentBranchId) return;
    try {
      await deleteStoryBranch(currentBranchId);
      setBranches(await getStoryBranches(projectId));
      setCurrentBranchId(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败'); }
  }

  return (
    <div className="branch-workspace">
      <header><div><span>扩写工程</span><h1>{projectName}</h1><p>新路线与原始基线独立保存，可从原文或已有分支继续派生。</p></div></header>
      <div className="branch-action-grid" aria-label="扩写入口">
        <OperationButton active={mode === 'open_continuation'} icon={<GitBranch size={18} />} label="从原文末尾续写" onClick={() => setMode('open_continuation')} />
        <OperationButton active={mode === 'fork'} icon={<GitFork size={18} />} label="从指定节点建立分支" onClick={() => setMode('fork')} />
        <OperationButton active={mode === 'fork_and_rejoin'} icon={<ListTree size={18} />} label="建立分支并接回原文" onClick={() => setMode('fork_and_rejoin')} />
      </div>
      <div className="branch-layout">
        <aside aria-label="分支树">
          <h2>分支树</h2>
          <ul><li><button onClick={() => setCurrentBranchId(null)} type="button">原文</button></li>{branches.map((branch) => <li key={branch.id}><button aria-current={branch.id === currentBranchId ? 'true' : undefined} onClick={() => setCurrentBranchId(branch.id)} type="button">{branch.parent_branch_id ? '  └─ ' : '├─ '}{branch.name}</button></li>)}</ul>
          {currentBranchId ? <button className="button ghost" onClick={() => void removeCurrentBranch()} type="button">删除未使用分支</button> : null}
        </aside>
        <main>
          {error ? <p role="alert">{error}</p> : null}
          <div className="operation-fields">
            <label>起点<select disabled={mode === 'open_continuation'} onChange={(event) => setStartChapterId(Number(event.target.value))} value={startChapterId ?? ''}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title} 末尾</option>)}</select></label>
            {mode === 'fork_and_rejoin' ? <label>回接点<select onChange={(event) => setReturnChapterId(Number(event.target.value))} value={returnChapterId ?? ''}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title} 开始</option>)}</select></label> : null}
            <label className="wide">剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
            <label>人物 ID<input onChange={(event) => setCharacterIds(event.target.value)} placeholder="逗号分隔" value={characterIds} /></label>
            <label>素材 ID<input onChange={(event) => setMaterialIds(event.target.value)} placeholder="逗号分隔" value={materialIds} /></label>
            <label>风格 ID<input onChange={(event) => setStyleId(event.target.value)} value={styleId} /></label>
            {!run ? <button className="button primary" disabled={!direction.trim()} onClick={() => void begin()} type="button">启动分析并创建分支</button> : <RunStatus run={run} />}
            {run?.stage === 'confirm_target_skeleton' ? <ModularSkeletonEditor onConfirm={(skeleton) => void confirmPlotGenerationSkeleton(run.id, skeleton).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} skeleton={run.target_skeleton} /> : null}
            {run?.stage === 'confirm_seams' && Array.isArray(run.seams) && sourceChapter ? <SeamReview onConfirm={(seams) => void confirmPlotGenerationSeams(run.id, { seams, current_source_text: sourceChapter.original_text }).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} seams={run.seams} /> : null}
            {run?.status === 'ready' ? <button onClick={() => void executePlotGeneration(run.id, {}).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">逐场景生成并检查</button> : null}
            {run?.status === 'completed' ? <pre className="wide">{JSON.stringify(run.result, null, 2)}</pre> : null}
            {run?.status === 'blocked' ? <pre className="wide">{JSON.stringify(run.issues, null, 2)}</pre> : null}
          </div>
        </main>
      </div>
    </div>
  );
}

export function LegacyExtractPanel({
  onCreated,
  projectId,
  projectName,
}: {
  onCreated: (projectId: number) => void;
  projectId: number;
  projectName: string;
}) {
  const [creating, setCreating] = useState(false);
  const [targetKind, setTargetKind] = useState<'rewrite' | 'branch'>('rewrite');
  const [copyAnalysis, setCopyAnalysis] = useState(true);
  const [message, setMessage] = useState('');
  async function exportAnalysis() {
    try {
      const analysis = await getLegacyAnalysisExport(projectId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${projectName}-analysis.json`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage('分析结果已导出。');
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : '导出失败'); }
  }
  async function createDerivedProject() {
    try {
      const created = await createProjectFromLegacy(projectId, { target_project_kind: targetKind, copy_source_text: true, copy_analysis_results: copyAnalysis });
      onCreated(created.id);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : '创建失败'); }
  }
  return (
    <div className="legacy-extract-panel">
      <span>旧版兼容</span><h1>{projectName}</h1>
      <p>此项目属于旧版分析工程。<br />可以查看和导出已有分析结果，<br />或基于原文创建新的改写工程或扩写工程。</p>
      <div><button className="button secondary" onClick={() => void exportAnalysis()} type="button">导出已有分析</button><button className="button primary" onClick={() => setCreating(true)} type="button">基于此项目创建新工程</button></div>
      {creating ? <section aria-label="创建派生工程" className="operation-fields"><label>工程类型<select onChange={(event) => setTargetKind(event.target.value as 'rewrite' | 'branch')} value={targetKind}><option value="rewrite">改写工程</option><option value="branch">扩写工程</option></select></label><label><input checked={copyAnalysis} onChange={(event) => setCopyAnalysis(event.target.checked)} type="checkbox" />复制已有分析结果</label><button onClick={() => void createDerivedProject()} type="button">创建并打开</button></section> : null}
      {message ? <p role="status">{message}</p> : null}
      <small>当前工作区只读，旧提取主流程已停用。</small>
    </div>
  );
}

export function ModularSkeletonEditor({
  onChange,
  onConfirm,
  skeleton,
}: {
  onChange?: (skeleton: StructuredSkeleton) => void;
  onConfirm?: (skeleton: StructuredSkeleton) => void;
  skeleton?: StructuredSkeleton;
}) {
  const [value, setValue] = useState<StructuredSkeleton | null>(skeleton ?? null);
  useEffect(() => setValue(skeleton ?? null), [skeleton]);
  function update(next: StructuredSkeleton) { setValue(next); onChange?.(next); }
  if (!value) return <section className="modular-skeleton-editor" aria-label="模块化细纲编辑器"><p>尚未加载结构化细纲。</p></section>;
  const current = value;
  function reorder(from: number, to: number) {
    const nodes = [...current.event_nodes];
    const [moved] = nodes.splice(from, 1);
    nodes.splice(to, 0, moved);
    update({ ...current, event_nodes: nodes.map((node, index) => ({ ...node, order: index + 1 })) });
  }
  return (
    <section className="modular-skeleton-editor wide" aria-label="模块化细纲编辑器">
      <header><div><span>模块化细纲</span><h3>事件链</h3></div><button onClick={() => update({ ...current, event_nodes: [...current.event_nodes, emptyEvent(current.event_nodes.length + 1)] })} type="button">插入事件</button></header>
      {current.event_nodes.map((node, index) => <article draggable key={node.id} onDragOver={(event) => event.preventDefault()} onDragStart={(event) => event.dataTransfer.setData('text/plain', String(index))} onDrop={(event) => reorder(Number(event.dataTransfer.getData('text/plain')), index)}><span aria-label="拖拽排序">⋮</span><strong>{index + 1}</strong><input aria-label={`事件 ${index + 1}`} onChange={(event) => update({ ...current, event_nodes: current.event_nodes.map((item) => item.id === node.id ? { ...item, summary: event.target.value } : item) })} value={node.summary} /><label><input checked={node.locked} onChange={(event) => update({ ...current, event_nodes: current.event_nodes.map((item) => item.id === node.id ? { ...item, locked: event.target.checked } : item) })} type="checkbox" />锁定</label><button disabled={node.locked} onClick={() => update({ ...current, event_nodes: current.event_nodes.filter((item) => item.id !== node.id) })} type="button">删除</button><small>来源与因果：{node.causes.join('、') || '无'}</small></article>)}
      <div className="skeleton-module-grid">{['人物状态', '时间与地点', '物品变化', '知识变化', '关系变化', '伏笔', '未解决线索', '开始状态', '结束状态', '插入点', '回接条件'].map((label) => <span key={label}>{label}</span>)}</div>
      {onConfirm ? <button className="button primary" onClick={() => onConfirm(current)} type="button">确认目标细纲</button> : null}
    </section>
  );
}

export function SeamReview({
  onConfirm,
  seams = [],
}: {
  onConfirm?: (seams: SeamProposal[]) => void;
  seams?: SeamProposal[];
}) {
  const [items, setItems] = useState(seams);
  useEffect(() => setItems(seams), [seams]);
  return (
    <section className="seam-review wide" aria-label="接缝审查">
      <h3>接缝审查</h3>
      {items.length === 0 ? <p>尚未生成接缝提议。</p> : items.map((seam, index) => <article key={seam.id ?? index}><strong>{seam.seam_kind === 'entry' ? '进入接缝' : '回接接缝'}</strong><p>原文：{seam.original_text}</p><label>建议修改<textarea onChange={(event) => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, proposed_text: event.target.value } : item))} value={seam.proposed_text} /></label><p>{seam.reason}</p><button onClick={() => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'confirmed' } : item))} type="button">确认</button><button onClick={() => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'rejected' } : item))} type="button">拒绝</button><span>{seam.status}</span></article>)}
      {items.length ? <button disabled={items.some((item) => item.status === 'draft')} onClick={() => onConfirm?.(items)} type="button">提交接缝审查</button> : null}
    </section>
  );
}

function CanonPatchReview({ onChange, run }: { onChange: (run: CanonChangeRun) => void; run: CanonChangeRun }) {
  async function decide(patchId: number, decision: 'accepted' | 'rejected' | 'skipped', replacementText?: string) {
    await reviewCanonPatch(patchId, { decision, replacement_text: replacementText ?? null });
    onChange(await getCanonChangeRun(run.id));
  }
  const groups = run.patches.reduce<Record<string, typeof run.patches>>((result, patch) => {
    (result[patch.impact_type] ??= []).push(patch);
    return result;
  }, {});
  return <section className="canon-patch-review wide" aria-label="设定变更影响列表">{Object.entries(groups).map(([impactType, patches]) => <div key={impactType}><h3>{impactType}</h3>{patches.map((patch) => <article key={patch.id}><p>{patch.original_text}</p><textarea defaultValue={patch.replacement_text} onBlur={(event) => { if (event.target.value !== patch.replacement_text) void reviewCanonPatch(patch.id, { decision: 'edited', replacement_text: event.target.value }).then(() => getCanonChangeRun(run.id)).then(onChange); }} /><small>{patch.reason} · {Math.round(patch.confidence * 100)}%</small><button onClick={() => void decide(patch.id, 'accepted')} type="button">接受</button><button onClick={() => void decide(patch.id, 'rejected')} type="button">拒绝</button><button onClick={() => void decide(patch.id, 'skipped')} type="button">跳过</button><span>{patch.status}</span></article>)}</div>)}</section>;
}

function RunStatus({ run }: { run: { id: number; status: string; stage?: string } }) {
  return <p className="wide" role="status">运行 #{run.id} · {run.stage ? `${run.stage} · ` : ''}{run.status}</p>;
}

function emptyEvent(order: number): StructuredSkeleton['event_nodes'][number] {
  return { id: crypto.randomUUID(), order, event_type: 'user_event', summary: '', participants: [], location: '', time_state: {}, causes: [], effects: [], locked: false, source_span: null, confidence: 1 };
}

function parseIds(value: string): number[] {
  return value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0);
}

function OperationButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-pressed={active} className={active ? 'active' : ''} onClick={onClick} type="button">{icon}<strong>{label}</strong></button>;
}
