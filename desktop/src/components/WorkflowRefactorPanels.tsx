import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { GitBranch, GitFork, ListTree, Plus, RefreshCw, Settings2 } from 'lucide-react';
import {
  applyCanonChange,
  cancelCanonChange,
  cancelPlotGeneration,
  cancelProseRewrite,
  confirmPlotGenerationSeams,
  confirmPlotGenerationSkeleton,
  confirmStorySkeleton,
  createStorySkeleton,
  createProjectFromLegacy,
  deleteStoryBranch,
  executePlotGeneration,
  executeProseRewrite,
  generateNextPlotScene,
  getCanonChangeRun,
  getChapterStorySkeleton,
  getChapterRewriteVersions,
  getLegacyAnalysisExport,
  getPlotGenerationRun,
  getPlotGenerationRuns,
  getProseRewriteRun,
  getProseRewriteRuns,
  getCanonChangeRuns,
  getStoryBranches,
  planProseRewrite,
  reviewCanonPatch,
  retryPlotGeneration,
  retryProseRewrite,
  reviseStorySkeleton,
  scanCanonChange,
  startPlotGeneration,
} from '../api/client';
import type {
  CanonChangeRun,
  Chapter,
  ChapterRewriteVersion,
  ChapterSourceSelection,
  PlotGenerationRun,
  ProseRewriteRun,
  SeamProposal,
  StoryAnchor,
  StoryBranch,
  StructuredSkeleton,
} from '../api/types';
import { StoryAnchorPicker } from './StoryAnchorPicker';
import { ModularSkeletonEditor } from './ModularSkeletonEditor';
import type { SkeletonVersionInfo } from './ModularSkeletonEditor';
export { ModularSkeletonEditor } from './ModularSkeletonEditor';

type Operation = 'plot_generation' | 'prose_rewrite' | 'canon_change';
type GenerationMode = 'bounded_insert' | 'open_continuation' | 'fork' | 'fork_and_rejoin';

function usePersistedRun<T>(
  key: string,
  load: (id: number) => Promise<T>,
): [T | null, (value: T | null, id?: number) => void, () => void] {
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
  return [run, setRun, () => setRun(null)];
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
  const [rangeOperation, setRangeOperation] = useState<'insert_between' | 'replace_range'>('insert_between');
  const [startAnchor, setStartAnchor] = useState<StoryAnchor>(chapter
    ? { anchor_type: 'chapter_end', chapter_id: chapter.id }
    : { anchor_type: 'document_end' });
  const [returnAnchor, setReturnAnchor] = useState<StoryAnchor>(chapter
    ? { anchor_type: 'chapter_end', chapter_id: chapter.id }
    : { anchor_type: 'document_end' });
  const [sourceSkeleton, setSourceSkeleton] = useState<StructuredSkeleton | null>(null);
  const [sourceSkeletonId, setSourceSkeletonId] = useState<number | null>(null);
  const [sourceSkeletonInfo, setSourceSkeletonInfo] = useState<SkeletonVersionInfo | null>(null);
  const [oldFact, setOldFact] = useState('');
  const [newFact, setNewFact] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plotRun, setPlotRun, clearPlotRun] = usePersistedRun(
    `rusty.plot-run.${projectId}`,
    getPlotGenerationRun,
  );
  const [proseRun, setProseRun, clearProseRun] = usePersistedRun(
    `rusty.prose-run.${projectId}`,
    getProseRewriteRun,
  );
  const [canonRun, setCanonRun, clearCanonRun] = usePersistedRun(
    `rusty.canon-run.${projectId}`,
    getCanonChangeRun,
  );
  const [plotHistory, setPlotHistory] = useState<PlotGenerationRun[]>([]);
  const [proseHistory, setProseHistory] = useState<ProseRewriteRun[]>([]);
  const [canonHistory, setCanonHistory] = useState<CanonChangeRun[]>([]);
  const [rewriteVersions, setRewriteVersions] = useState<ChapterRewriteVersion[]>([]);
  const [workflowSource, setWorkflowSource] = useState<ChapterSourceSelection>({ kind: 'current' });
  const [viewedVersion, setViewedVersion] = useState<ChapterRewriteVersion | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      getPlotGenerationRuns(projectId),
      getProseRewriteRuns(projectId),
      getCanonChangeRuns(projectId),
    ]).then(([plots, prose, canon]) => {
      if (!active) return;
      setPlotHistory(plots);
      setProseHistory(prose);
      setCanonHistory(canon);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [canonRun?.status, plotRun?.status, proseRun?.status, projectId]);

  useEffect(() => {
    let active = true;
    setWorkflowSource({ kind: 'current' });
    setViewedVersion(null);
    if (!chapter) {
      setRewriteVersions([]);
      return () => { active = false; };
    }
    void getChapterRewriteVersions(chapter.id)
      .then((versions) => { if (active) setRewriteVersions(versions); })
      .catch(() => { if (active) setRewriteVersions([]); });
    return () => { active = false; };
  }, [chapter?.id, canonRun?.status, plotRun?.status, proseRun?.status]);

  useEffect(() => {
    if (!chapter) return;
    setStartAnchor((current) => current.anchor_type === 'document_end'
      ? { anchor_type: 'chapter_end', chapter_id: chapter.id }
      : current);
    setReturnAnchor((current) => current.anchor_type === 'document_end'
      ? { anchor_type: 'chapter_end', chapter_id: chapter.id }
      : current);
  }, [chapter]);

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
      range_operation: rangeOperation,
      start_anchor: startAnchor,
      return_anchor: rangeOperation === 'replace_range'
        ? returnAnchor
        : startAnchor,
      user_direction: direction.trim(),
      source: workflowSource,
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
      source: workflowSource,
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
    setSourceSkeletonInfo({ version: loaded.version ?? 1, status: loaded.status ?? 'draft', previousVersion: (loaded.version ?? 1) > 1 ? (loaded.version ?? 1) - 1 : null });
  }

  async function saveSkeleton() {
    if (!chapter || !sourceSkeleton) return;
    if (sourceSkeletonId) {
      const version = await reviseStorySkeleton(
        sourceSkeletonId, undefined, '用户在模块化编辑器中修改', sourceSkeleton,
      );
      const confirmed = await confirmStorySkeleton(sourceSkeletonId, version.version);
      setSourceSkeletonInfo({ version: confirmed.version, status: confirmed.status, previousVersion: confirmed.version > 1 ? confirmed.version - 1 : null });
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
    const confirmed = await confirmStorySkeleton(version.skeleton_id, version.version);
    setSourceSkeletonInfo({ version: confirmed.version, status: confirmed.status, previousVersion: confirmed.version > 1 ? confirmed.version - 1 : null });
  }

  async function beginCanon() {
    if (!chapter || !oldFact.trim() || !newFact.trim()) return;
    const run = await scanCanonChange({
      project_id: projectId,
      old_fact: { attribute: 'user_fact', value: oldFact.trim() },
      new_fact: { attribute: 'user_fact', value: newFact.trim() },
      effective_order: chapter.index,
      source: workflowSource,
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
      {chapter ? (
        <RewriteVersionHistory
          onSelectSource={(version) => setWorkflowSource({ kind: 'rewrite_version', version_id: version.id })}
          onUseCurrent={() => setWorkflowSource({ kind: 'current' })}
          onUseOriginal={() => setWorkflowSource({ kind: 'original' })}
          onView={setViewedVersion}
          selectedSource={workflowSource}
          versions={rewriteVersions}
          viewedVersion={viewedVersion}
        />
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {operation === 'plot_generation' ? (
        <div className="operation-fields">
          <label>插入方式<select aria-label="插入方式" onChange={(event) => setRangeOperation(event.target.value as typeof rangeOperation)} value={rangeOperation}><option value="insert_between">在节点后插入</option><option value="replace_range">替换选定范围</option></select></label>
          {chapter ? <StoryAnchorPicker chapters={[chapter]} label="插入点" onChange={setStartAnchor} value={startAnchor} /> : null}
          {rangeOperation === 'replace_range' && chapter ? <StoryAnchorPicker chapters={[chapter]} label="范围终点" onChange={setReturnAnchor} value={returnAnchor} /> : <label>回接点<input readOnly value="插入点后原文" /></label>}
          <label className="wide">新增剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          <p className="wide">本次运行明确以不可变原始基线为来源；历史改写结果可查看，但不会被隐式串入新任务。</p>
          {!plotRun ? <button disabled={busy || !chapter || !direction.trim()} onClick={() => void perform(beginPlot)} type="button">启动分析</button> : <RunStatus run={plotRun} />}
          {plotRun?.stage === 'confirm_target_skeleton' ? (
            <ModularSkeletonEditor
              onConfirm={(skeleton) => void perform(async () => setPlotRun(await confirmPlotGenerationSkeleton(plotRun.id, skeleton), plotRun.id))}
              skeleton={plotRun.target_skeleton}
            />
          ) : null}
          {plotRun?.stage === 'confirm_seams' && Array.isArray(plotRun.seams) && chapter ? (
            <SeamReview
              onConfirm={(seams) => void perform(async () => setPlotRun(await confirmPlotGenerationSeams(plotRun.id, { reviews: seamReviews(seams) }), plotRun.id))}
              seams={plotRun.seams}
            />
          ) : null}
          {plotRun && ['ready', 'generating'].includes(plotRun.status) ? <><p className="wide">已完成 {plotRun.next_scene_cursor} / {plannedSceneCount(plotRun)} 个场景</p><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await generateNextPlotScene(plotRun.id), plotRun.id))} type="button">生成下一场景</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await executePlotGeneration(plotRun.id, {}), plotRun.id))} type="button">生成全部剩余场景</button></> : null}
          {plotRun?.status === 'completed' ? <><p className="wide">本次运行已完成</p><pre className="wide">{JSON.stringify(plotRun.result, null, 2)}</pre><button onClick={clearPlotRun} type="button">开始新的运行</button></> : null}
          {plotRun?.status === 'cancelled' ? <><p className="wide">本次运行已取消</p><button onClick={clearPlotRun} type="button">开始新的运行</button></> : null}
          {plotRun?.status === 'repair_required' ? <><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await retryPlotGeneration(plotRun.id), plotRun.id))} type="button">重新生成</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">放弃本次运行</button></> : null}
          {plotRun?.status === 'planning_blocked' ? <button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">放弃本次运行</button> : null}
          {plotRun && ['awaiting_skeleton', 'awaiting_seams', 'ready', 'generating'].includes(plotRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">取消运行</button> : null}
          {plotRun?.status === 'failed' ? <><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await retryPlotGeneration(plotRun.id), plotRun.id))} type="button">重试</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">取消运行</button></> : null}
          {plotRun && ['planning_blocked', 'repair_required'].includes(plotRun.status) ? <pre className="wide">{JSON.stringify(plotRun.issues, null, 2)}</pre> : null}
          <RunHistory label="剧情生成历史" runs={plotHistory} onSelect={(selected) => setPlotRun(selected, selected.id)} />
        </div>
      ) : null}
      {operation === 'prose_rewrite' ? (
        <div className="operation-fields">
          <label>范围<input readOnly value={chapter?.title ?? '请选择章节'} /></label>
          <label>源细纲<button disabled={busy || !chapter} onClick={() => void perform(loadSkeleton)} type="button">加载已确认版本</button></label>
          {sourceSkeleton ? <ModularSkeletonEditor onChange={setSourceSkeleton} skeleton={sourceSkeleton} versionInfo={sourceSkeletonInfo} /> : null}
          {sourceSkeleton ? <button disabled={busy} onClick={() => void perform(saveSkeleton)} type="button">保存并确认细纲版本</button> : null}
          <label className="wide">目标风格与说明<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          {!proseRun ? <button disabled={busy || !sourceSkeleton} onClick={() => void perform(beginProse)} type="button">生成重写计划</button> : <RunStatus run={proseRun} />}
          {proseRun?.status === 'planned' ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await executeProseRewrite(proseRun.id, { auto_repair: true }), proseRun.id))} type="button">生成正文并自动检查</button> : null}
          {proseRun ? <pre className="wide">{JSON.stringify(proseRun.issues, null, 2)}</pre> : null}
          {proseRun?.status === 'completed' ? <button onClick={clearProseRun} type="button">开始新的运行</button> : null}
          {proseRun && ['planned', 'generating', 'blocked', 'failed'].includes(proseRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await cancelProseRewrite(proseRun.id), proseRun.id))} type="button">Cancel run</button> : null}
          {proseRun && ['blocked', 'failed'].includes(proseRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await retryProseRewrite(proseRun.id), proseRun.id))} type="button">Retry run</button> : null}
          {proseRun?.status === 'cancelled' ? <button onClick={clearProseRun} type="button">Start new run</button> : null}
          <RunHistory label="正文重写历史" runs={proseHistory} onSelect={(selected) => setProseRun(selected, selected.id)} />
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
          {canonRun?.status === 'applied' ? <button onClick={clearCanonRun} type="button">开始新的运行</button> : null}
          {canonRun && ['scanning', 'reviewing', 'blocked', 'ready_to_apply', 'failed'].includes(canonRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setCanonRun(await cancelCanonChange(canonRun.id), canonRun.id))} type="button">Cancel run</button> : null}
          {canonRun?.status === 'cancelled' ? <button onClick={clearCanonRun} type="button">Start new run</button> : null}
          <RunHistory label="设定变更历史" runs={canonHistory} onSelect={(selected) => setCanonRun(selected, selected.id)} />
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
  const [selectedBranchId, setSelectedBranchId] = useState<number | null>(null);
  const [sourceParentBranchId, setSourceParentBranchId] = useState<number | null>(null);
  const [activeRunBranchId, setActiveRunBranchId] = useState<number | null>(null);
  const [startAnchor, setStartAnchor] = useState<StoryAnchor>({ anchor_type: 'document_end' });
  const [returnAnchor, setReturnAnchor] = useState<StoryAnchor>(chapters.at(-1)
    ? { anchor_type: 'chapter_end', chapter_id: chapters.at(-1)!.id }
    : { anchor_type: 'document_end' });
  const [direction, setDirection] = useState('');
  const [characterIds, setCharacterIds] = useState('');
  const [materialIds, setMaterialIds] = useState('');
  const [styleId, setStyleId] = useState('');
  const [run, setRun, clearRun] = usePersistedRun(`rusty.plot-run.${projectId}`, getPlotGenerationRun);
  const [runHistory, setRunHistory] = useState<PlotGenerationRun[]>([]);
  const [error, setError] = useState('');
  const sourceChapter = chapters.find((item) => item.id === startAnchor.chapter_id) ?? chapters.at(-1);

  useEffect(() => {
    void getStoryBranches(projectId).then(setBranches).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取分支'));
  }, [projectId]);

  useEffect(() => {
    void getPlotGenerationRuns(projectId).then(setRunHistory).catch(() => undefined);
  }, [projectId, run?.status]);

  useEffect(() => {
    if (run?.status === 'completed' && activeRunBranchId) {
      setSelectedBranchId(activeRunBranchId);
    }
  }, [activeRunBranchId, run?.status]);

  async function begin() {
    if (!direction.trim()) return;
    try {
      const next = await startPlotGeneration({
        project_id: projectId,
        generation_mode: mode,
        start_anchor: startAnchor,
        return_anchor: mode === 'fork_and_rejoin' ? returnAnchor : null,
        parent_branch_id: sourceParentBranchId,
        user_direction: direction.trim(),
        selected_character_ids: parseIds(characterIds),
        selected_material_ids: parseIds(materialIds),
        style_profile_id: Number(styleId) || null,
        branch_name: `分支 ${branches.length + 1}`,
      });
      setRun(next, next.id);
      setBranches(await getStoryBranches(projectId));
      setActiveRunBranchId(next.branch_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '启动失败'); }
  }

  async function removeCurrentBranch() {
    if (!selectedBranchId) return;
    try {
      await deleteStoryBranch(selectedBranchId);
      setBranches(await getStoryBranches(projectId));
      setSelectedBranchId(null);
      if (sourceParentBranchId === selectedBranchId) setSourceParentBranchId(null);
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
          <ul><li><button onClick={() => setSelectedBranchId(null)} type="button">原文</button></li>{branches.map((branch) => <li key={branch.id}><button aria-current={branch.id === selectedBranchId ? 'true' : undefined} onClick={() => setSelectedBranchId(branch.id)} type="button">{branch.parent_branch_id ? '  └─ ' : '├─ '}{branch.name}</button></li>)}</ul>
          <button onClick={() => { setSourceParentBranchId(null); setStartAnchor({ anchor_type: 'document_end' }); }} type="button">从原文创建新分支</button>
          {selectedBranchId ? <button onClick={() => setSourceParentBranchId(selectedBranchId)} type="button">从此分支继续派生</button> : null}
          {selectedBranchId ? <button className="button ghost" onClick={() => void removeCurrentBranch()} type="button">删除未使用分支</button> : null}
        </aside>
        <main>
          {error ? <p role="alert">{error}</p> : null}
          <div className="operation-fields">
            <p className="wide">生成来源：{sourceParentBranchId ? `父分支 #${sourceParentBranchId}` : '原始基线'}</p>
            <StoryAnchorPicker allowDocumentEnd chapters={chapters} label="起点" onChange={setStartAnchor} parentBranchId={sourceParentBranchId} value={startAnchor} />
            {mode === 'fork_and_rejoin' ? <StoryAnchorPicker chapters={chapters} label="回接点" onChange={setReturnAnchor} value={returnAnchor} /> : null}
            <label className="wide">剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
            <label>人物 ID<input onChange={(event) => setCharacterIds(event.target.value)} placeholder="逗号分隔" value={characterIds} /></label>
            <label>素材 ID<input onChange={(event) => setMaterialIds(event.target.value)} placeholder="逗号分隔" value={materialIds} /></label>
            <label>风格 ID<input onChange={(event) => setStyleId(event.target.value)} value={styleId} /></label>
            {!run ? <button className="button primary" disabled={!direction.trim()} onClick={() => void begin()} type="button">启动分析并创建分支</button> : <RunStatus run={run} />}
            {run?.stage === 'confirm_target_skeleton' ? <ModularSkeletonEditor onConfirm={(skeleton) => void confirmPlotGenerationSkeleton(run.id, skeleton).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} skeleton={run.target_skeleton} /> : null}
            {run?.stage === 'confirm_seams' && Array.isArray(run.seams) && sourceChapter ? <SeamReview onConfirm={(seams) => void confirmPlotGenerationSeams(run.id, { reviews: seamReviews(seams) }).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} seams={run.seams} /> : null}
            {run && ['ready', 'generating'].includes(run.status) ? <><p className="wide">已完成 {run.next_scene_cursor} / {plannedSceneCount(run)} 个场景</p><button onClick={() => void generateNextPlotScene(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">生成下一场景</button><button onClick={() => void executePlotGeneration(run.id, {}).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">生成全部剩余场景</button></> : null}
            {run?.status === 'completed' ? <><p className="wide">本次运行已完成</p><pre className="wide">{JSON.stringify(run.result, null, 2)}</pre><button onClick={clearRun} type="button">开始新的运行</button></> : null}
            {run?.status === 'cancelled' ? <><p className="wide">本次运行已取消</p><button onClick={clearRun} type="button">开始新的运行</button></> : null}
            {run?.status === 'repair_required' ? <><button onClick={() => void retryPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">重新生成</button><button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">放弃本次运行</button></> : null}
            {run?.status === 'planning_blocked' ? <button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">放弃本次运行</button> : null}
            {run && ['awaiting_skeleton', 'awaiting_seams', 'ready', 'generating'].includes(run.status) ? <button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">取消运行</button> : null}
            {run && ['planning_blocked', 'repair_required'].includes(run.status) ? <pre className="wide">{JSON.stringify(run.issues, null, 2)}</pre> : null}
            <RunHistory label="剧情生成历史" runs={runHistory} onSelect={(selected) => { setRun(selected, selected.id); setActiveRunBranchId(selected.branch_id); }} />
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

function RewriteVersionHistory({
  onSelectSource,
  onUseCurrent,
  onUseOriginal,
  onView,
  selectedSource,
  versions,
  viewedVersion,
}: {
  onSelectSource: (version: ChapterRewriteVersion) => void;
  onUseCurrent: () => void;
  onUseOriginal: () => void;
  onView: (version: ChapterRewriteVersion) => void;
  selectedSource: ChapterSourceSelection;
  versions: ChapterRewriteVersion[];
  viewedVersion: ChapterRewriteVersion | null;
}) {
  return (
    <section className="rewrite-version-history" aria-label="rewrite versions">
      <h3>&#27491;&#25991;&#29256;&#26412;</h3>
      <p>Source: {selectedSource.kind === 'rewrite_version' ? `v${selectedSource.version_id}` : selectedSource.kind}</p>
      <button onClick={onUseCurrent} type="button">&#24403;&#21069;&#29256;&#26412;</button>
      <button onClick={onUseOriginal} type="button">&#21407;&#22987;&#22522;&#32447;</button>
      {versions.length === 0 ? <p>No rewrite versions.</p> : (
        <ul>
          {versions.map((version) => (
            <li key={version.id}>
              <button onClick={() => onView(version)} type="button">
                v{version.version} · {version.source_operation} · parent {version.parent_version_id ?? 'original'}
                {version.is_current ? ' · current' : ''}
              </button>
              <button onClick={() => onSelectSource(version)} type="button">
                &#22522;&#20110;&#27492;&#29256;&#26412;&#21019;&#24314;&#26032;&#25805;&#20316;
              </button>
              <time>{version.created_at}</time>
            </li>
          ))}
        </ul>
      )}
      {viewedVersion ? <pre>{viewedVersion.rewritten_text}</pre> : null}
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

function RunHistory<T extends { id: number; status: string }>({
  label,
  onSelect,
  runs,
}: {
  label: string;
  onSelect: (run: T) => void;
  runs: T[];
}) {
  return (
    <section className="wide" aria-label={label}>
      <h3>历史运行</h3>
      {runs.length === 0 ? <p>暂无历史运行。</p> : (
        <ul>{runs.map((run) => <li key={run.id}><button onClick={() => onSelect(run)} type="button">运行 #{run.id} · {run.status}</button></li>)}</ul>
      )}
    </section>
  );
}

function plannedSceneCount(run: PlotGenerationRun): number {
  const chapters = Array.isArray(run.scene_plan.chapters) ? run.scene_plan.chapters : [];
  return chapters.reduce((count, chapter) => {
    if (!chapter || typeof chapter !== 'object') return count;
    const scenes = (chapter as { scenes?: unknown }).scenes;
    return count + (Array.isArray(scenes) ? scenes.length : 0);
  }, 0);
}

function parseIds(value: string): number[] {
  return value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0);
}

function seamReviews(seams: SeamProposal[]) {
  return seams.map((seam) => {
    if (!seam.id || seam.status === 'draft') throw new Error('所有接缝必须先确认或拒绝。');
    return {
      seam_id: seam.id,
      decision: seam.status,
      proposed_text: seam.proposed_text,
    };
  });
}

function OperationButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-pressed={active} className={active ? 'active' : ''} onClick={onClick} type="button">{icon}<strong>{label}</strong></button>;
}
