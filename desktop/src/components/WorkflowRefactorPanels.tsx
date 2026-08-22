import { useEffect, useState } from 'react';
import { GitBranch, GitFork, Plus, RefreshCw } from 'lucide-react';
import {
  confirmStorySkeleton,
  createProjectFromLegacy,
  createStorySkeleton,
  getChapterStorySkeleton,
  getLegacyAnalysisExport,
  reviseStorySkeleton,
} from '../api/client';
import {
  cancelPlotGeneration,
  cancelProseRewrite,
  confirmPlotGenerationSkeleton,
  deleteStoryBranch,
  executePlotGeneration,
  executeProseRewrite,
  generateNextPlotScene,
  getBranchChapters,
  getChapterRewriteVersions,
  getRewriteVersionSkeleton,
  getPlotGenerationRun,
  getProseRewriteRun,
  getStoryBranches,
  planProseRewrite,
  retryPlotGeneration,
  retryProseRewrite,
  restoreChapterRewriteVersion,
  startPlotGeneration,
} from '../api/workflowClient';
import type {
  BranchChapterRecord,
  Chapter,
  ChapterRewriteVersion,
  ChapterSourceSelection,
  StoryAnchor,
  StoryBranch,
  StructuredSkeleton,
} from '../api/types';
import { StoryAnchorPicker } from './StoryAnchorPicker';
import { ModularSkeletonEditor } from './ModularSkeletonEditor';
import type { SkeletonVersionInfo } from './ModularSkeletonEditor';
import { usePersistedWorkflowRun } from '../hooks/usePersistedWorkflowRun';
import {
  OperationButton,
  plannedSceneCount,
  RewriteVersionHistory,
  RunStatus,
} from './WorkflowPanelShared';
export { ModularSkeletonEditor } from './ModularSkeletonEditor';

type Operation = 'plot_generation' | 'prose_rewrite';
type GenerationMode = 'bounded_insert' | 'open_continuation' | 'fork';

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
  const [sourceSkeletonVersionId, setSourceSkeletonVersionId] = useState<number | null>(null);
  const [sourceSkeletonInfo, setSourceSkeletonInfo] = useState<SkeletonVersionInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plotRun, setPlotRun, clearPlotRun] = usePersistedWorkflowRun(
    `rusty.plot-run.${projectId}`,
    getPlotGenerationRun,
  );
  const [proseRun, setProseRun, clearProseRun] = usePersistedWorkflowRun(
    `rusty.prose-run.${projectId}`,
    getProseRewriteRun,
  );
  const [rewriteVersions, setRewriteVersions] = useState<ChapterRewriteVersion[]>([]);
  const [workflowSource, setWorkflowSource] = useState<ChapterSourceSelection>({ kind: 'current' });
  const [viewedVersion, setViewedVersion] = useState<ChapterRewriteVersion | null>(null);
  const selectedRewriteVersion = workflowSource.kind === 'rewrite_version'
    ? rewriteVersions.find((item) => item.id === workflowSource.version_id) ?? null
    : workflowSource.kind === 'current'
      ? rewriteVersions.find((item) => item.is_current) ?? null
      : null;
  const sourceLabel = workflowSource.kind === 'original'
    ? '原始基线'
    : workflowSource.kind === 'rewrite_version'
      ? `历史版本 v${selectedRewriteVersion?.version ?? '?'}`
      : selectedRewriteVersion
        ? `当前版本 v${selectedRewriteVersion.version}`
        : '原始基线';
  const sourceKey = workflowSource.kind === 'rewrite_version'
    ? `rewrite:${workflowSource.version_id}`
    : workflowSource.kind;

  useEffect(() => {
    setSourceSkeleton(null);
    setSourceSkeletonId(null);
    setSourceSkeletonVersionId(null);
    setSourceSkeletonInfo(null);
  }, [chapter?.id, sourceKey]);

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
  }, [chapter?.id, plotRun?.status, proseRun?.status]);

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
    if (!chapter || !sourceSkeleton || !sourceSkeletonVersionId) return;
    const run = await planProseRewrite({
      project_id: projectId,
      chapter_id: chapter.id,
      source_skeleton: sourceSkeleton,
      source_skeleton_version_id: sourceSkeletonVersionId,
      preservation_policy: {
        events: true,
        event_order: true,
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
    if (selectedRewriteVersion) {
      const versionStructure = await getRewriteVersionSkeleton(selectedRewriteVersion.id);
      setSourceSkeleton(versionStructure.structured);
      setSourceSkeletonId(versionStructure.skeleton_id);
      setSourceSkeletonVersionId(versionStructure.skeleton_version_id);
      setSourceSkeletonInfo({
        version: 1,
        status: versionStructure.status === 'confirmed' ? 'confirmed' : 'draft',
        previousVersion: null,
      });
      return;
    }
    const loaded = await getChapterStorySkeleton(chapter.id);
    if (loaded.format !== 'structured' || !loaded.structured || !loaded.skeleton_id || !loaded.version_id) {
      throw new Error('当前章节还没有结构化细纲，请先运行分析或增加剧情规划。');
    }
    setSourceSkeleton(loaded.structured);
    setSourceSkeletonId(loaded.skeleton_id);
    setSourceSkeletonVersionId(loaded.version_id);
    setSourceSkeletonInfo({ version: loaded.version ?? 1, status: loaded.status ?? 'draft', previousVersion: (loaded.version ?? 1) > 1 ? (loaded.version ?? 1) - 1 : null });
  }

  async function saveSkeleton() {
    if (!chapter || !sourceSkeleton) return;
    if (sourceSkeletonId) {
      const version = await reviseStorySkeleton(
        sourceSkeletonId, undefined, '用户在模块化编辑器中修改', sourceSkeleton,
      );
      const confirmed = await confirmStorySkeleton(sourceSkeletonId, version.version);
      setSourceSkeletonVersionId(confirmed.version_id);
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
    setSourceSkeletonVersionId(version.version_id);
    const confirmed = await confirmStorySkeleton(version.skeleton_id, version.version);
    setSourceSkeletonInfo({ version: confirmed.version, status: confirmed.status, previousVersion: confirmed.version > 1 ? confirmed.version - 1 : null });
  }

  async function restoreVersion(version: ChapterRewriteVersion) {
    await restoreChapterRewriteVersion(version.id);
    if (chapter) setRewriteVersions(await getChapterRewriteVersions(chapter.id));
    setWorkflowSource({ kind: 'current' });
  }

  return (
    <section className="workflow-operation-panel" aria-label="改写操作">
      <header><div><span>改写工程</span><h2>选择本次写作操作</h2></div></header>
      <div className="workflow-operation-grid">
        <OperationButton active={operation === 'plot_generation'} icon={<Plus size={18} />} label="增加剧情" onClick={() => setOperation('plot_generation')} />
        <OperationButton active={operation === 'prose_rewrite'} icon={<RefreshCw size={18} />} label="重写正文" onClick={() => setOperation('prose_rewrite')} />
      </div>
      {chapter ? (
        <RewriteVersionHistory
          onSelectSource={(version) => setWorkflowSource({ kind: 'rewrite_version', version_id: version.id })}
          onRestore={(version) => void perform(() => restoreVersion(version))}
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
          {chapter ? <StoryAnchorPicker chapters={[chapter]} label="插入点" onChange={setStartAnchor} projectId={projectId} source={workflowSource} sourceVersionId={selectedRewriteVersion?.id ?? null} value={startAnchor} /> : null}
          {rangeOperation === 'replace_range' && chapter ? <StoryAnchorPicker chapters={[chapter]} label="范围终点" onChange={setReturnAnchor} projectId={projectId} source={workflowSource} sourceVersionId={selectedRewriteVersion?.id ?? null} value={returnAnchor} /> : null}
          <label className="wide">新增剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          <p className="wide">本次来源：{sourceLabel}</p>
          {!plotRun ? <button disabled={busy || !chapter || !direction.trim()} onClick={() => void perform(beginPlot)} type="button">启动分析</button> : <RunStatus run={plotRun} />}
          {plotRun?.stage === 'confirm_target_skeleton' ? (
            <ModularSkeletonEditor
              onConfirm={(skeleton) => void perform(async () => setPlotRun(await confirmPlotGenerationSkeleton(plotRun.id, skeleton), plotRun.id))}
              skeleton={plotRun.target_skeleton}
            />
          ) : null}
          {plotRun && ['ready', 'generating'].includes(plotRun.status) ? <><p className="wide">已完成 {plotRun.next_scene_cursor} / {plannedSceneCount(plotRun)} 个场景</p><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await generateNextPlotScene(plotRun.id), plotRun.id))} type="button">生成下一场景</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await executePlotGeneration(plotRun.id, {}), plotRun.id))} type="button">生成全部剩余场景</button></> : null}
          {plotRun?.status === 'completed' ? <><p className="wide">新正文版本已经保存。</p>{Array.isArray(plotRun.issues) && plotRun.issues.length ? <p className="wide">生成结果有一些创作建议，您可以查看正文后决定是否再次调整。</p> : null}<button onClick={clearPlotRun} type="button">开始新的创作</button></> : null}
          {plotRun?.status === 'cancelled' ? <><p className="wide">本次运行已取消</p><button onClick={clearPlotRun} type="button">开始新的运行</button></> : null}
          {plotRun?.status === 'repair_required' ? <><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await retryPlotGeneration(plotRun.id), plotRun.id))} type="button">重新生成</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">放弃本次运行</button></> : null}
          {plotRun?.status === 'planning_blocked' ? <button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">放弃本次运行</button> : null}
          {plotRun && ['awaiting_skeleton', 'awaiting_seams', 'ready', 'generating'].includes(plotRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">取消运行</button> : null}
          {plotRun?.status === 'failed' ? <><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await retryPlotGeneration(plotRun.id), plotRun.id))} type="button">重试</button><button disabled={busy} onClick={() => void perform(async () => setPlotRun(await cancelPlotGeneration(plotRun.id), plotRun.id))} type="button">取消运行</button></> : null}
          {plotRun && Array.isArray(plotRun.issues) && plotRun.issues.length ? <p className="wide">请检查生成结果中的连续性提示。</p> : null}
        </div>
      ) : null}
      {operation === 'prose_rewrite' ? (
        <div className="operation-fields">
          <label>范围<input readOnly value={chapter?.title ?? '请选择章节'} /></label>
          <label>源细纲<button disabled={busy || !chapter} onClick={() => void perform(loadSkeleton)} type="button">加载已确认版本</button></label>
          {sourceSkeleton ? <ModularSkeletonEditor onChange={setSourceSkeleton} skeleton={sourceSkeleton} versionInfo={sourceSkeletonInfo} /> : null}
          {sourceSkeleton ? <button disabled={busy} onClick={() => void perform(saveSkeleton)} type="button">保存并确认细纲版本</button> : null}
          <label className="wide">目标风格与说明<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
          <p className="wide">本次来源：{sourceLabel}</p>
          {!proseRun ? <button disabled={busy || !sourceSkeleton || !sourceSkeletonVersionId} onClick={() => void perform(beginProse)} type="button">生成重写计划</button> : <RunStatus run={proseRun} />}
          {proseRun?.status === 'planned' ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await executeProseRewrite(proseRun.id, {}), proseRun.id))} type="button">生成正文并检查</button> : null}
          {proseRun?.issues.length ? <p className="wide">正文已保存，但存在创作一致性提示；您可以接受结果或调整要求后重新创作。</p> : null}
          {proseRun?.status === 'completed' ? <button onClick={clearProseRun} type="button">开始新的运行</button> : null}
          {proseRun && ['planned', 'generating', 'blocked', 'failed'].includes(proseRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await cancelProseRewrite(proseRun.id), proseRun.id))} type="button">Cancel run</button> : null}
          {proseRun && ['blocked', 'failed'].includes(proseRun.status) ? <button disabled={busy} onClick={() => void perform(async () => setProseRun(await retryProseRewrite(proseRun.id), proseRun.id))} type="button">Retry run</button> : null}
          {proseRun?.status === 'cancelled' ? <button onClick={clearProseRun} type="button">Start new run</button> : null}
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
  const [branchChapters, setBranchChapters] = useState<BranchChapterRecord[]>([]);
  const [startAnchor, setStartAnchor] = useState<StoryAnchor>({ anchor_type: 'document_end' });
  const [direction, setDirection] = useState('');
  const [run, setRun, clearRun] = usePersistedWorkflowRun(`rusty.plot-run.${projectId}`, getPlotGenerationRun);
  const [error, setError] = useState('');

  useEffect(() => {
    void getStoryBranches(projectId).then(setBranches).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取分支'));
  }, [projectId]);

  useEffect(() => {
    if (selectedBranchId == null) {
      setBranchChapters([]);
      return;
    }
    void getBranchChapters(selectedBranchId)
      .then(setBranchChapters)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取续写内容'));
  }, [selectedBranchId, run?.status]);

  async function begin() {
    if (!direction.trim()) return;
    try {
      let effectiveAnchor = startAnchor;
      if (mode === 'open_continuation' && selectedBranchId) {
        const lastChapter = branchChapters.at(-1);
        const lastScene = lastChapter?.scenes.at(-1);
        if (!lastChapter) throw new Error('这条路线还没有可继续的正文，请先删除空路线并重新创建。');
        effectiveAnchor = lastScene
          ? { anchor_type: 'branch_scene', branch_scene_id: lastScene.id, source_version_id: lastScene.version_id, side: 'after' }
          : { anchor_type: 'branch_chapter', branch_chapter_id: lastChapter.id, source_version_id: lastChapter.version_id, side: 'after' };
      } else if (mode === 'open_continuation') {
        effectiveAnchor = { anchor_type: 'document_end' };
      }
      const next = await startPlotGeneration({
        project_id: projectId,
        generation_mode: mode,
        start_anchor: effectiveAnchor,
        branch_id: mode === 'open_continuation' ? selectedBranchId : null,
        user_direction: direction.trim(),
        branch_name: mode === 'open_continuation' ? `我的续写 ${branches.length + 1}` : `另一种发展 ${branches.length + 1}`,
      });
      setRun(next, next.id);
      setBranches(await getStoryBranches(projectId));
      setSelectedBranchId(next.branch_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '启动失败'); }
  }

  async function removeCurrentBranch() {
    if (!selectedBranchId) return;
    try {
      await deleteStoryBranch(selectedBranchId);
      setBranches(await getStoryBranches(projectId));
      setSelectedBranchId(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败'); }
  }

  return (
    <div className="branch-workspace">
      <header><div><span>扩写工程</span><h1>{projectName}</h1></div></header>
      <div className="branch-action-grid" aria-label="扩写入口">
        <OperationButton active={mode === 'open_continuation'} icon={<GitBranch size={18} />} label="继续写" onClick={() => setMode('open_continuation')} />
        <OperationButton active={mode === 'fork'} icon={<GitFork size={18} />} label="写另一种发展" onClick={() => setMode('fork')} />
      </div>
      <div className="branch-layout">
        <aside aria-label="创作路线">
          <h2>创作路线</h2>
          <ul><li><button onClick={() => setSelectedBranchId(null)} type="button">原文</button></li>{branches.map((branch) => <li key={branch.id}><button aria-current={branch.id === selectedBranchId ? 'true' : undefined} onClick={() => setSelectedBranchId(branch.id)} type="button">{branch.name}</button></li>)}</ul>
          <button onClick={() => { setSelectedBranchId(null); setMode('open_continuation'); }} type="button">创建新的续写路线</button>
          {selectedBranchId ? <button className="button ghost" onClick={() => void removeCurrentBranch()} type="button">删除未使用分支</button> : null}
        </aside>
        <main>
          {error ? <p role="alert">{error}</p> : null}
          <div className="operation-fields">
            <p className="wide">本次来源：{mode === 'open_continuation' && selectedBranchId ? branches.find((branch) => branch.id === selectedBranchId)?.name : '原文'}</p>
            {mode === 'fork' ? <StoryAnchorPicker chapters={chapters} label="从这里开始" onChange={setStartAnchor} projectId={projectId} value={startAnchor} /> : null}
            <label className="wide">剧情目标<textarea onChange={(event) => setDirection(event.target.value)} value={direction} /></label>
            {!run ? <button className="button primary" disabled={!direction.trim()} onClick={() => void begin()} type="button">开始规划</button> : <RunStatus run={run} />}
            {run?.stage === 'confirm_target_skeleton' ? <ModularSkeletonEditor onConfirm={(skeleton) => void confirmPlotGenerationSkeleton(run.id, skeleton).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} skeleton={run.target_skeleton} /> : null}
            {run && ['ready', 'generating'].includes(run.status) ? <><p className="wide">已完成 {run.next_scene_cursor} / {plannedSceneCount(run)} 个场景</p><button onClick={() => void generateNextPlotScene(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">生成下一场景</button><button onClick={() => void executePlotGeneration(run.id, {}).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">生成全部剩余场景</button></> : null}
            {run?.status === 'completed' ? <><p className="wide">新内容已经保存到这条路线。</p>{Array.isArray(run.issues) && run.issues.length ? <p className="wide">生成结果有连续性提示，请查看正文后决定是否继续调整。</p> : null}<button onClick={clearRun} type="button">继续创作</button></> : null}
            {run?.status === 'cancelled' ? <><p className="wide">本次运行已取消</p><button onClick={clearRun} type="button">开始新的运行</button></> : null}
            {run?.status === 'repair_required' ? <><button onClick={() => void retryPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">重新生成</button><button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">放弃本次运行</button></> : null}
            {run?.status === 'planning_blocked' ? <button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">放弃本次运行</button> : null}
            {run && ['awaiting_skeleton', 'awaiting_seams', 'ready', 'generating'].includes(run.status) ? <button onClick={() => void cancelPlotGeneration(run.id).then((next) => setRun(next, next.id)).catch((reason) => setError(String(reason)))} type="button">取消运行</button> : null}
            {run && Array.isArray(run.issues) && run.issues.length ? <p className="wide">请检查生成结果中的连续性提示。</p> : null}
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
      <div><button className="button secondary" onClick={() => void exportAnalysis()} type="button">导出已有分析</button><button className="button primary" onClick={() => setCreating(true)} type="button">基于此项目创建新工程</button></div>
      {creating ? <section aria-label="创建派生工程" className="operation-fields"><label>工程类型<select onChange={(event) => setTargetKind(event.target.value as 'rewrite' | 'branch')} value={targetKind}><option value="rewrite">改写工程</option><option value="branch">扩写工程</option></select></label><label><input checked={copyAnalysis} onChange={(event) => setCopyAnalysis(event.target.checked)} type="checkbox" />复制已有分析结果</label><button onClick={() => void createDerivedProject()} type="button">创建并打开</button></section> : null}
      {message ? <p role="status">{message}</p> : null}
      <small>当前工作区只读，旧提取主流程已停用。</small>
    </div>
  );
}
