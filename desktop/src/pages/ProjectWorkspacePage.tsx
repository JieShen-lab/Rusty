import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowUpToLine, ChevronRight, Download, Eye, EyeOff, Save, Settings2, Sparkles, X } from 'lucide-react';
import {
  analyzeChapterStyle,
  confirmChapterRewrite,
  createCharacterFromSelection,
  detectScene,
  expandChapterPlot,
  exportEpub,
  exportPromptPackage,
  exportTxt,
  getAnalysisPrompts,
  getChapter,
  getChapterGenerationAttempts,
  getChapterPromptPreview,
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
  getChapterScenes,
  analyzeChapterScenes,
  confirmChapterScenes,
  startSceneWorkflow,
  generateSceneWorkflowPlan,
  executeSceneWorkflow,
  confirmStorySkeleton,
  confirmRewritePlan,
  getSceneRewriteHistory,
  reviseStorySkeleton,
  adjustChapterScenes,
  getProjectMaterials,
  getMaterialTags,
  getMaterials,
  getProjectMaterialFilters,
  setProjectMaterialFilter,
  getCharacterCards,
  restoreSceneRewriteVersion,
} from '../api/client';
import type {
  AnalysisPromptTemplate,
  Chapter,
  ChapterDetail,
  CompiledPromptPreview,
  ExportPlanItem,
  GenerationAttempt,
  ProjectDetail,
  PromptTemplate,
  SceneRecord,
  SceneWorkflowRun,
  CharacterCard,
  Material,
  ProjectMaterialFilter,
  ResourceTag,
} from '../api/types';
import {
  BranchWorkspacePanel,
  LegacyExtractPanel,
  RewriteOperationPanel,
} from '../components/WorkflowRefactorPanels';
import { CreativeWorkspacePage } from './CreativeWorkspacePage';

type Props = { onNavigate: (path: string, state?: unknown) => void; projectId: number };
type SelectionKind = 'scene' | 'plot' | 'character';
type ProjectPurpose = 'rewrite' | 'legacy_extract';
type SelectionCapture = { text: string; startOffset: number; endOffset: number; x: number; y: number };

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
  const [promptPreview, setPromptPreview] = useState<CompiledPromptPreview | null>(null);
  const [generationAttempts, setGenerationAttempts] = useState<GenerationAttempt[]>([]);
  const [binderVisible, setBinderVisible] = useState(true);
  const [inspectorVisible, setInspectorVisible] = useState(true);
  const [binderWidth, setBinderWidth] = useState(240);
  const [inspectorWidth, setInspectorWidth] = useState(300);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectionMenu, setSelectionMenu] = useState<SelectionCapture | null>(null);
  const [selectionKind, setSelectionKind] = useState<SelectionKind | null>(null);
  const [scenePanel, setScenePanel] = useState(false);
  const [scenes, setScenes] = useState<SceneRecord[]>([]);

  const purpose: ProjectPurpose = project?.project?.project_kind === 'legacy_extract' ? 'legacy_extract' : 'rewrite';
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

  const loadRewriteTrace = useCallback(async (chapterId: number) => {
    try {
      const [preview, attempts] = await Promise.all([
        getChapterPromptPreview(chapterId, 'rewrite'),
        getChapterGenerationAttempts(chapterId, 'rewrite'),
      ]);
      setPromptPreview(preview);
      setGenerationAttempts(attempts);
    } catch {
      setPromptPreview(null);
      setGenerationAttempts([]);
    }
  }, []);

  useEffect(() => { void loadProject(); }, [loadProject]);
  useEffect(() => { if (selectedChapterId) void loadChapter(selectedChapterId); }, [loadChapter, selectedChapterId]);
  useEffect(() => {
    if (window.innerWidth < 960) {
      setBinderVisible(false);
      setInspectorVisible(false);
    }
  }, []);
  useEffect(() => {
    if (selectedChapterId && purpose === 'rewrite') void loadRewriteTrace(selectedChapterId);
    else { setPromptPreview(null); setGenerationAttempts([]); }
  }, [loadRewriteTrace, purpose, selectedChapterId]);
  useEffect(() => { setStage(0); }, [purpose]);
  async function run(label: string, action: () => Promise<unknown>, nextStage?: number) {
    setBusy(true); setError(null); setMessage(null);
    try {
      await action();
      if (selectedChapterId) await loadChapter(selectedChapterId);
      if (selectedChapterId && purpose === 'rewrite') await loadRewriteTrace(selectedChapterId);
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

  async function saveSelection(kind: SelectionKind) {
    if (!selectionMenu || !selectedChapter) return;
    if (kind !== 'character') {
      onNavigate('/materials', {
        materialExtraction: {
          materialType: kind === 'plot' ? 'plot_skeleton' : 'scene_reference',
          taskType: kind === 'scene' ? 'source_text_to_scene_material' : undefined,
          selectedText: selectionMenu.text,
          sourceMetadata: {
            source_kind: 'project_selection',
            source_type: 'project',
            project_id: projectId,
            chapter_id: selectedChapter.id,
            start_offset: selectionMenu.startOffset,
            end_offset: selectionMenu.endOffset,
            project_name: project?.project.name ?? '',
            chapter_title: selectedChapter.title,
          },
        },
      });
      return;
    }
    setSelectionKind(kind);
  }

  async function confirmSelection(name: string) {
    if (!selectionMenu || !selectionKind || !selectedChapter || !name.trim()) return;
    const payload = {
      source_kind: 'project' as const,
      selected_text: selectionMenu.text,
      name: name.trim(),
      project_id: projectId,
      chapter_id: selectedChapter.id,
      start_offset: selectionMenu.startOffset,
      end_offset: selectionMenu.endOffset,
    };
    setError(null);
    try {
      if (selectionKind === 'character') await createCharacterFromSelection(payload);
      setSelectionMenu(null);
      setSelectionKind(null);
      setMessage('选区已保存，状态为未分析。工程素材默认保存到当前工程。');
    } catch (reason) {
      setError(messageOf(reason));
    }
  }

  async function openScenePanel() {
    if (!selectedChapterId) return;
    setScenePanel(true);
    try {
      let items = await getChapterScenes(selectedChapterId);
      if (!items.length) items = await analyzeChapterScenes(selectedChapterId, { source: 'ai', confirm: false });
      setScenes(items);
    } catch (reason) { setError(messageOf(reason)); }
  }

  function showSelectionMenu(capture: SelectionCapture) {
    if (capture.text.length > 50000) {
      setSelectionMenu(null);
      setError('选区不能超过 50,000 字符。');
      return;
    }
    setSelectionMenu(capture);
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

  const backendConnectionError = Boolean(error && (error.includes('Rusty 后端') || error.includes('Failed to fetch')));
  const modelAuthError = Boolean(error && error.includes('模型服务鉴权失败'));

  if (project?.project?.project_kind === 'legacy_extract') {
    return (
      <LegacyExtractPanel
        onCreated={(createdId) => onNavigate(`/workspace/${createdId}`)}
        projectId={project.project.id}
        projectName={project.project.name}
      />
    );
  }
  if (project?.project) {
    return <CreativeWorkspacePage onNavigate={onNavigate} projectId={projectId} projectName={project.project.name} />;
  }
  if (project?.project?.project_kind === 'branch') {
    return <BranchWorkspacePanel chapters={chapters} projectId={projectId} projectName={project.project.name} />;
  }

  return (
    <div className="project-workbench">
      <header className="workbench-toolbar">
        <div className="project-heading"><button className="button ghost workbench-back-button" onClick={() => onNavigate('/library')} type="button"><ArrowLeft size={16} />工程列表</button></div>
        <div className="chapter-heading"><div><strong>{selectedChapter?.title || '暂无章节'}</strong>{selectedChapter ? <span className="chapter-meta"><span>{selectedChapter.word_count.toLocaleString()} 字</span><span>章节 {selectedIndex + 1}/{chapters.length}</span><span>{busy ? '正在处理…' : '本地保存'}<i className={`status-dot ${busy ? 'busy' : ''}`} /></span></span> : <span className="chapter-meta">无章节</span>}</div></div>
        <div className="toolbar-actions"><button className="button ghost" disabled={!selectedChapterId} onClick={() => void openScenePanel()} type="button"><Sparkles size={16} />场景改写</button><button aria-label={binderVisible ? '隐藏章节目录' : '显示章节目录'} className="button ghost" onClick={() => setBinderVisible((value) => !value)} type="button">{binderVisible ? <EyeOff size={16} /> : <Eye size={16} />}目录</button><button aria-label={inspectorVisible ? '隐藏检查器' : '显示检查器'} className="button ghost" onClick={() => setInspectorVisible((value) => !value)} type="button">{inspectorVisible ? <EyeOff size={16} /> : <Eye size={16} />}检查器</button></div>
      </header>

      <nav className="workflow-rail" aria-label="工程阶段">{stages.map((label, index) => <button aria-current={stage === index ? 'step' : undefined} className={stage === index ? 'active' : ''} key={label} onClick={() => setStage(index)} type="button"><span>{index + 1}</span>{label}</button>)}</nav>
      <div className="workbench-feedback">
        {(error || message) ? <div className={`inline-alert workbench-alert ${error ? 'error' : 'success'}`} role={error ? 'alert' : 'status'}><span>{error || message}</span>{backendConnectionError ? <button disabled={busy} onClick={() => void loadProject()} type="button">重新连接</button> : modelAuthError ? <button onClick={() => onNavigate('/models')} type="button">模型设置</button> : null}</div> : null}
      </div>

      <div className="workbench-grid" style={{ gridTemplateColumns: `${binderVisible ? `${binderWidth}px 8px` : ''} minmax(0,1fr) ${inspectorVisible ? `8px ${inspectorWidth}px` : ''}` }}>
        {binderVisible ? <><ChapterBinder chapters={chapters} currentId={selectedChapterId} detail={detail} purpose={purpose} onSelect={setSelectedChapterId} /><div aria-label="调整章节目录宽度" className="panel-resizer" onPointerDown={(event) => beginResize('binder', event)} role="separator" /></> : null}
        <main className="workspace-center">
          <RewriteOperationPanel chapter={selectedChapter} projectId={projectId} />
          <WorkspaceContent analysisDraft={analysisDraft} detail={detail} exportPlan={exportPlan} generatedPrompt={generatedPrompt} onSelection={showSelectionMenu} purpose={purpose} rewriteDraft={rewriteDraft} setAnalysisDraft={setAnalysisDraft} setExportPlan={setExportPlan} setRewriteDraft={setRewriteDraft} setTargetSkeleton={setTargetSkeleton} stage={stage} targetSkeleton={targetSkeleton} />
          {purpose === 'rewrite' && stage === 3 ? <RewriteTrace attempts={generationAttempts} preview={promptPreview} /> : null}
        </main>
        {inspectorVisible ? <><div aria-label="调整检查器宽度" className="panel-resizer" onPointerDown={(event) => beginResize('inspector', event)} role="separator" /><Inspector actions={<><InspectorActions busy={busy} detail={detail} generatedPrompt={generatedPrompt} onAnalyze={() => selectedChapterId && run('章节风格分析', () => analyzeChapterStyle(selectedChapterId), 2)} onConfirmAnalysis={() => void reviewAnalysis()} onConfirmRewrite={() => void saveRewrite(true)} onExpand={() => selectedChapterId && run('目标骨架生成', () => expandChapterPlot(selectedChapterId, true), 2)} onExportBook={exportBook} onExportPrompt={() => void exportGeneratedPrompt()} onReviewPrompt={() => onNavigate('/prompts')} onRewrite={() => void identifyAndRewrite()} onSaveRewrite={() => void saveRewrite(false)} onSaveSkeleton={() => selectedChapterId && run('目标骨架保存', () => saveTargetSkeleton(selectedChapterId, targetSkeleton))} onSummarize={() => selectedChapterId && run('剧情与人物提取', () => summarizeChapter(selectedChapterId), 1)} onSynthesize={() => void synthesize()} purpose={purpose} stage={stage} />{stage < stages.length - 1 ? <button className="button primary full inspector-next-button" disabled={busy} onClick={() => setStage((current) => Math.min(current + 1, stages.length - 1))} onKeyDown={blockEnterActivation} type="button">下一步<ChevronRight className="button-trailing-icon" size={16} /></button> : null}</>} analysisPrompt={selectedAnalysisPrompt} detail={detail} purpose={purpose} rewritePrompt={selectedRewritePrompt} /></> : null}
      </div>
      {selectionMenu ? (
        <div className="selection-resource-menu" style={{ left: selectionMenu.x, top: selectionMenu.y }}>
          <button onClick={() => void saveSelection('plot')} type="button">添加为剧情骨架来源</button>
          <button onClick={() => void saveSelection('scene')} type="button">添加为场景素材来源</button>
          <button onClick={() => void saveSelection('character')} type="button">添加到公共角色卡</button>
        </div>
      ) : null}
      {selectionKind && selectionMenu ? <SelectionDialog initialName={selectionMenu.text.slice(0, 24)} kind={selectionKind} onClose={() => setSelectionKind(null)} onSave={(name) => void confirmSelection(name)} /> : null}
      {scenePanel && selectedChapterId ? <SceneRewritePanel busy={busy} chapterId={selectedChapterId} scenes={scenes} setBusy={setBusy} setError={setError} setMessage={setMessage} setScenes={setScenes} onClose={() => setScenePanel(false)} /> : null}
    </div>
  );
}

function SelectionDialog({ initialName, kind, onClose, onSave }: { initialName: string; kind: SelectionKind; onClose: () => void; onSave: (name: string) => void }) {
  const [name, setName] = useState(initialName);
  return <div className="document-processing-backdrop"><form className="document-tag-dialog" role="dialog" onSubmit={(event) => { event.preventDefault(); onSave(name); }}><header><h2>{kind === 'character' ? '添加到公共角色卡' : kind === 'scene' ? '添加为场景素材' : '添加为剧情骨架'}</h2><button className="icon-button" onClick={onClose} type="button"><X size={16} /></button></header><label><span>名称</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></label><footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={!name.trim()} type="submit">保存</button></footer></form></div>;
}

function SceneRewritePanel(props: {
  busy: boolean;
  chapterId: number;
  scenes: SceneRecord[];
  setBusy: (value: boolean) => void;
  setError: (value: string | null) => void;
  setMessage: (value: string | null) => void;
  setScenes: (value: SceneRecord[]) => void;
  onClose: () => void;
}) {
  const [sceneId, setSceneId] = useState(props.scenes[0]?.id ?? 0);
  const [mode, setMode] = useState<'skeleton_rewrite' | 'expansion'>('skeleton_rewrite');
  const [instruction, setInstruction] = useState('');
  const [characterIds, setCharacterIds] = useState<number[]>([]);
  const [plotMaterialIds, setPlotMaterialIds] = useState<number[]>([]);
  const [sceneMaterialIds, setSceneMaterialIds] = useState<number[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [plotMaterials, setPlotMaterials] = useState<Material[]>([]);
  const [sceneMaterials, setSceneMaterials] = useState<Material[]>([]);
  const [materialFilterOpen, setMaterialFilterOpen] = useState(false);
  const [resourceQuery, setResourceQuery] = useState('');
  const [insertion, setInsertion] = useState('__start__');
  const [run, setRun] = useState<SceneWorkflowRun | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [diffView, setDiffView] = useState<{ title: string; text: string } | null>(null);
  const [consistency, setConsistency] = useState<Record<string, unknown> | null>(null);
  const [skeletonJson, setSkeletonJson] = useState('[]');
  const parsedSkeleton = useMemo(() => parseEditableSkeleton(skeletonJson), [skeletonJson]);
  const selected = props.scenes.find((item) => item.id === sceneId) ?? props.scenes[0];
  useEffect(() => {
    if (
      insertion !== '__start__'
      && insertion !== '__end__'
      && !parsedSkeleton.nodes.some((node) => node.id === insertion)
    ) {
      setInsertion('__start__');
    }
  }, [insertion, parsedSkeleton.nodes]);
  useEffect(() => {
    const projectId = props.scenes[0]?.project_id;
    if (!projectId) return;
    void Promise.all([
      getCharacterCards('public'),
      getCharacterCards('project', projectId),
      getProjectMaterials(projectId, 'plot_skeleton'),
      getProjectMaterials(projectId, 'scene_reference'),
    ]).then(([publicCharacters, projectCharacters, projectPlots, projectScenes]) => {
      setCharacters(dedupeResources([...projectCharacters, ...publicCharacters]));
      setPlotMaterials(projectPlots.filter((item) => item.material_type === 'plot_skeleton'));
      setSceneMaterials(projectScenes.filter((item) => item.material_type === 'scene_reference'));
    }).catch((reason) => props.setError(messageOf(reason)));
  }, [props.scenes]);
  async function reloadProjectMaterials(projectId: number) {
    const [projectPlots, projectScenes] = await Promise.all([
      getProjectMaterials(projectId, 'plot_skeleton'),
      getProjectMaterials(projectId, 'scene_reference'),
    ]);
    setPlotMaterials(projectPlots);
    setSceneMaterials(projectScenes);
  }
  useEffect(() => {
    if (!selected?.id) {
      setHistory([]);
      return;
    }
    void getSceneRewriteHistory(selected.id).then(setHistory).catch((reason) => props.setError(messageOf(reason)));
  }, [selected?.id]);
  async function perform(action: () => Promise<void>) {
    props.setBusy(true); props.setError(null);
    try { await action(); } catch (reason) { props.setError(messageOf(reason)); }
    finally { props.setBusy(false); }
  }
  async function confirmBoundaries() {
    await perform(async () => {
      const items = await confirmChapterScenes(props.chapterId);
      props.setScenes(items);
      props.setMessage('场景边界已确认。');
    });
  }
  async function start() {
    if (!selected) return;
    await perform(async () => {
      const next = await startSceneWorkflow(selected.id, { mode, user_instruction: instruction, character_ids: characterIds, material_ids: [...plotMaterialIds, ...sceneMaterialIds] });
      setRun(next);
      setSkeletonJson(JSON.stringify(next.skeleton_nodes ?? [], null, 2));
      props.setMessage('场景分析和骨架提取完成，等待确认骨架。');
    });
  }
  async function confirmSkeletonAndPlan() {
    if (!run?.skeleton_id || !run.skeleton_version_id) return;
    if (parsedSkeleton.error) {
      props.setError(parsedSkeleton.error);
      return;
    }
    if (mode === 'expansion' && !plotMaterialIds.length) {
      props.setError('扩写模式至少需要选择一个剧情骨架素材。');
      return;
    }
    const currentRun = run;
    await perform(async () => {
      const nodes = parsedSkeleton.nodes;
      const revised = await reviseStorySkeleton(currentRun.skeleton_id!, nodes, '用户在工作台确认前编辑');
      const skeleton = await confirmStorySkeleton(currentRun.skeleton_id!, revised.version);
      const mappings = mode === 'expansion' ? plotMaterialIds.map((materialId) => ({ material_id: materialId, insertion_after_node: insertion, usage_mode: 'required' })) : [];
      const next = await generateSceneWorkflowPlan(currentRun.id, { skeleton_version_id: skeleton.version_id, user_instruction: instruction, character_ids: characterIds, material_mappings: mappings, scene_reference_ids: sceneMaterialIds });
      setRun(next);
      props.setMessage('改写规划已生成，等待确认。');
    });
  }
  async function saveBoundaries() {
    await perform(async () => {
      const items = await adjustChapterScenes(props.chapterId, props.scenes.map((scene) => ({
        start_offset: scene.original_start_offset,
        end_offset: scene.original_end_offset,
        title: scene.title,
        reasons: scene.boundary_reasons,
      })));
      props.setScenes(items);
      props.setMessage('手动调整后的场景边界已保存并确认。');
    });
  }
  async function confirmPlanAndExecute() {
    if (!run?.plan_id || !selected) return;
    await perform(async () => {
      await confirmRewritePlan(run.plan_id!);
      const result = await executeSceneWorkflow(run.id, {
        user_instruction: instruction,
        character_ids: characterIds,
        plot_skeleton_material_ids: plotMaterialIds,
        scene_reference_ids: sceneMaterialIds,
      });
      setRun(result);
      setConsistency((result as SceneWorkflowRun & { consistency?: Record<string, unknown> }).consistency ?? null);
      setHistory(await getSceneRewriteHistory(selected.id));
      props.setMessage('场景正文生成、一致性检查和必要的定向修复已完成。');
    });
  }
  async function restoreHistoryVersion(item: Record<string, unknown>) {
    if (!selected || !window.confirm(`确认将版本 ${String(item.version ?? '')} 恢复为一个新版本？历史版本不会被覆盖。`)) return;
    await perform(async () => {
      await restoreSceneRewriteVersion(selected.id, Number(item.id));
      setHistory(await getSceneRewriteHistory(selected.id));
      props.setMessage('已从所选历史内容创建新的恢复版本。');
    });
  }
  return (
    <div className="document-processing-backdrop">
      <section className="scene-rewrite-dialog" role="dialog" aria-modal="true">
        <header><div><span>场景级长篇改写</span><h2>场景工作流</h2></div><button className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        <div className="scene-workflow-grid">
          <aside><h3>场景列表</h3>{props.scenes.map((scene) => <div className={scene.id === sceneId ? 'scene-boundary-row selected' : 'scene-boundary-row'} key={scene.id}><button onClick={() => setSceneId(scene.id)} type="button"><strong>{scene.scene_index}. {scene.title || '未命名场景'}</strong></button><label>起<input type="number" value={scene.original_start_offset} onChange={(event) => props.setScenes(props.scenes.map((item) => item.id === scene.id ? { ...item, original_start_offset: Number(event.target.value) } : item))} /></label><label>止<input type="number" value={scene.original_end_offset} onChange={(event) => props.setScenes(props.scenes.map((item) => item.id === scene.id ? { ...item, original_end_offset: Number(event.target.value) } : item))} /></label></div>)}<button className="button secondary" disabled={props.busy || !props.scenes.length} onClick={() => void saveBoundaries()} type="button">保存手动边界</button><button className="button secondary" disabled={props.busy || !props.scenes.length} onClick={() => void confirmBoundaries()} type="button">确认全部边界</button></aside>
          <main>
            <section><h3>边界预览与原文</h3><pre>{selected?.original_text ?? '暂无场景'}</pre></section>
            <section className="scene-workflow-form">
              <label><span>模式</span><select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="skeleton_rewrite">骨架重写</option><option value="expansion">扩写</option></select></label>
              <label className="wide"><span>搜索可用资源</span><input value={resourceQuery} onChange={(event) => setResourceQuery(event.target.value)} placeholder="按名称、身份或标签搜索" /></label>
              <button className="button secondary" onClick={() => setMaterialFilterOpen(true)} type="button"><Settings2 size={15} />配置工程素材筛选</button>
              <ResourcePicker
                label="角色"
                items={characters.filter((item) => resourceMatches(item.name, item.identity, item.tags, resourceQuery))}
                selected={characterIds}
                onChange={setCharacterIds}
                describe={(item) => `${item.identity || '身份未填写'} · ${item.tags.join('、') || '无标签'}`}
              />
              {mode === 'expansion' ? <ResourcePicker
                label="剧情骨架（产生新增事件）"
                items={plotMaterials.filter((item) => resourceMatches(item.name, item.description, item.tags, resourceQuery))}
                selected={plotMaterialIds}
                onChange={setPlotMaterialIds}
                describe={(item) => `${item.scope === 'project' ? '当前工程' : '公共库'} · ${item.tags.join('、') || '无标签'}`}
              /> : null}
              <ResourcePicker
                label="场景素材（仅写法参考，不产生新增剧情事件）"
                items={sceneMaterials.filter((item) => resourceMatches(item.name, item.description, item.tags, resourceQuery))}
                selected={sceneMaterialIds}
                onChange={setSceneMaterialIds}
                describe={(item) => `${item.scope === 'project' ? '当前工程' : '公共库'} · ${item.tags.join('、') || '无标签'}`}
              />
              {mode === 'expansion' ? <label><span>插入位置</span><select value={insertion} onChange={(event) => setInsertion(event.target.value)}><option value="__start__">场景开头</option>{parsedSkeleton.nodes.map((node) => <option key={node.id} value={node.id}>在“{node.event}”之后</option>)}<option value="__end__">场景结尾</option></select></label> : null}
              <label className="wide"><span>本次用户要求</span><textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="留空时使用默认执行要求" /></label>
            </section>
            <section><h3>确认流程与执行进度</h3><p>{run ? `${run.current_stage} · ${run.status}` : '尚未开始'}</p><div className="scene-workflow-actions"><button className="button secondary" disabled={props.busy || !selected?.user_confirmed} onClick={() => void start()} type="button">1. 分析并提取骨架</button><button className="button secondary" disabled={props.busy || !run?.skeleton_id} onClick={() => void confirmSkeletonAndPlan()} type="button">2. 确认骨架并生成规划</button><button className="button primary" disabled={props.busy || !run?.plan_id} onClick={() => void confirmPlanAndExecute()} type="button">3. 确认规划并执行</button></div></section>
            {run?.skeleton_id ? <section><h3>骨架编辑器</h3><textarea value={skeletonJson} onChange={(event) => { setSkeletonJson(event.target.value); props.setError(null); }} />{parsedSkeleton.error ? <p role="alert">{parsedSkeleton.error}</p> : null}</section> : null}
            {run?.plan ? <section><h3>改写规划预览</h3><pre>{JSON.stringify(run.plan, null, 2)}</pre></section> : null}
            {consistency ? <section><h3>一致性问题 / 定向修复</h3><pre>{JSON.stringify(consistency, null, 2)}</pre></section> : null}
            {diffView ? <section><h3>{diffView.title}</h3><pre className="scene-diff">{diffView.text}</pre><button className="button secondary" onClick={() => setDiffView(null)} type="button">关闭对比</button></section> : null}
            {history.length ? <section><h3>版本历史（原文不被覆盖）</h3>{history.map((item, index) => {
              const previous = history[index + 1];
              const currentText = String(item.rewritten_text ?? '');
              return <details key={String(item.id ?? index)}><summary>版本 {String(item.version ?? index + 1)} · {String(item.mode ?? item.revision_kind ?? 'rewrite')} · {String(item.created_at ?? '')}</summary><p>父版本：{String(item.parent_version_id ?? '无')} · {item.revision_kind === 'targeted_repair' ? '经过定向修复' : '未标记修复'}</p><pre>{currentText.slice(0, 1200)}</pre><div className="scene-workflow-actions"><button className="button secondary" onClick={() => setDiffView({ title: '与原文对比', text: simpleDiff(selected?.original_text ?? '', currentText) })} type="button">与原文对比</button><button className="button secondary" disabled={!previous} onClick={() => previous && setDiffView({ title: '与上一版本对比', text: simpleDiff(String(previous.rewritten_text ?? ''), currentText) })} type="button">与上一版本对比</button><button className="button secondary" onClick={() => void restoreHistoryVersion(item)} type="button">恢复为新版本</button></div></details>;
            })}</section> : null}
          </main>
        </div>
      </section>
      {materialFilterOpen && selected ? (
        <ProjectMaterialFilterDialog
          projectId={selected.project_id}
          onClose={() => setMaterialFilterOpen(false)}
          onError={props.setError}
          onSaved={async () => {
            await reloadProjectMaterials(selected.project_id);
            setMaterialFilterOpen(false);
            props.setMessage('工程素材筛选已更新。');
          }}
        />
      ) : null}
    </div>
  );
}

function ProjectMaterialFilterDialog({
  onClose,
  onError,
  onSaved,
  projectId,
}: {
  onClose: () => void;
  onError: (value: string | null) => void;
  onSaved: () => Promise<void>;
  projectId: number;
}) {
  const [filters, setFilters] = useState<ProjectMaterialFilter[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    void Promise.all([
      getProjectMaterialFilters(projectId),
      getMaterialTags(),
      getMaterials({ analysis_status: 'analyzed' }),
    ]).then(([filterItems, tagItems, materialItems]) => {
      setFilters(filterItems);
      setTags(tagItems);
      setMaterials(materialItems);
    }).catch((reason) => onError(messageOf(reason)));
  }, [onError, projectId]);
  const patch = (type: Material['material_type'], value: Partial<ProjectMaterialFilter>) => {
    setFilters((items) => items.map((item) => item.material_type === type ? { ...item, ...value } : item));
  };
  async function save() {
    setSaving(true);
    onError(null);
    try {
      await Promise.all(filters.map((filterValue) => setProjectMaterialFilter(
        projectId,
        filterValue.material_type,
        {
          match_mode: filterValue.match_mode,
          tag_ids: filterValue.tag_ids,
          manual_material_ids: filterValue.manual_material_ids,
          include_scene_keywords: filterValue.include_scene_keywords,
          include_applicable_scene_tags: filterValue.include_applicable_scene_tags,
        },
      )));
      await onSaved();
    } catch (reason) {
      onError(messageOf(reason));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="document-processing-backdrop material-project-filter-backdrop">
      <section className="document-processing-dialog material-project-filter-dialog" role="dialog" aria-modal="true">
        <header><div><span>工程素材</span><h2>按标签配置素材范围</h2></div><button className="icon-button" onClick={onClose} type="button"><X size={16} /></button></header>
        <div className="document-processing-body">
          {filters.map((filterValue) => (
            <section className="material-project-filter-section" key={filterValue.material_type}>
              <header>
                <h3>{filterValue.material_type === 'plot_skeleton' ? '剧情骨架' : '场景素材'}</h3>
                <select value={filterValue.match_mode} onChange={(event) => patch(filterValue.material_type, { match_mode: event.target.value as 'any' | 'all' })}>
                  <option value="any">匹配任一标签</option>
                  <option value="all">匹配全部标签</option>
                </select>
              </header>
              {(['general', 'applicable_scene'] as const).map((group) => (
                <fieldset key={group}>
                  <legend>{group === 'general' ? '通用标签' : '适用场景标签'}</legend>
                  {tags.filter((tagItem) => (tagItem.tag_group ?? 'general') === group).map((tagItem) => (
                    <label key={tagItem.id}><input checked={filterValue.tag_ids.includes(tagItem.id)} onChange={(event) => patch(filterValue.material_type, {
                      tag_ids: event.target.checked ? [...filterValue.tag_ids, tagItem.id] : filterValue.tag_ids.filter((id) => id !== tagItem.id),
                    })} type="checkbox" />{tagItem.name}</label>
                  ))}
                </fieldset>
              ))}
              <fieldset>
                <legend>手动固定素材</legend>
                {materials.filter((item) => item.material_type === filterValue.material_type).map((material) => (
                  <label key={material.id}><input checked={filterValue.manual_material_ids.includes(material.id)} onChange={(event) => patch(filterValue.material_type, {
                    manual_material_ids: event.target.checked ? [...filterValue.manual_material_ids, material.id] : filterValue.manual_material_ids.filter((id) => id !== material.id),
                  })} type="checkbox" />{material.name}</label>
                ))}
              </fieldset>
              <label><input checked={filterValue.include_scene_keywords} onChange={(event) => patch(filterValue.material_type, { include_scene_keywords: event.target.checked })} type="checkbox" />允许当前场景关键词补充检索</label>
              <label><input checked={filterValue.include_applicable_scene_tags} onChange={(event) => patch(filterValue.material_type, { include_applicable_scene_tags: event.target.checked })} type="checkbox" />允许适用场景标签补充检索</label>
            </section>
          ))}
        </div>
        <footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={saving || !filters.length} onClick={() => void save()} type="button">保存筛选</button></footer>
      </section>
    </div>
  );
}

type SelectableResource = CharacterCard | Material;

function ResourcePicker<T extends SelectableResource>({ label, items, selected, onChange, describe }: {
  label: string;
  items: T[];
  selected: number[];
  onChange: (ids: number[]) => void;
  describe: (item: T) => string;
}) {
  return <fieldset className="wide scene-resource-picker"><legend>{label}</legend>{items.length ? items.map((item) => <label key={item.id}><input checked={selected.includes(item.id)} onChange={(event) => onChange(event.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))} type="checkbox" /><span><strong>{item.name}</strong><small>{describe(item)}</small></span></label>) : <p>没有匹配的可用资源。</p>}</fieldset>;
}

function resourceMatches(name: string, description: string, tags: string[], query: string) {
  const needle = query.trim().toLocaleLowerCase();
  return !needle || [name, description, ...tags].join(' ').toLocaleLowerCase().includes(needle);
}

function parseEditableSkeleton(value: string): {
  nodes: Array<Record<string, unknown> & { id: string; event: string }>;
  error: string | null;
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return { nodes: [], error: '骨架 JSON 格式无效，请修正后再生成规划。' };
  }
  if (!Array.isArray(parsed) || !parsed.length) {
    return { nodes: [], error: '骨架必须是非空数组。' };
  }
  const nodes: Array<Record<string, unknown> & { id: string; event: string }> = [];
  const ids = new Set<string>();
  for (let index = 0; index < parsed.length; index += 1) {
    const candidate = parsed[index];
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
      return { nodes: [], error: `骨架节点 ${index + 1} 必须是对象。` };
    }
    const node = candidate as Record<string, unknown>;
    const id = String(node.id ?? '').trim();
    const event = String(node.event ?? '').trim();
    if (!id) return { nodes: [], error: `骨架节点 ${index + 1} 缺少非空 id。` };
    if (!event) return { nodes: [], error: `骨架节点 ${index + 1} 缺少非空 event。` };
    if (ids.has(id)) return { nodes: [], error: `骨架节点 id 重复：${id}` };
    ids.add(id);
    nodes.push({ ...node, id, event });
  }
  return { nodes, error: null };
}

function dedupeResources<T extends SelectableResource>(items: T[]): T[] {
  return [...new Map(items.map((item) => [item.id, item])).values()];
}

function simpleDiff(before: string, after: string) {
  const left = before.split(/\r?\n/);
  const right = after.split(/\r?\n/);
  const lines: string[] = [];
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    if (left[index] === right[index]) lines.push(`  ${left[index] ?? ''}`);
    else {
      if (left[index] !== undefined) lines.push(`- ${left[index]}`);
      if (right[index] !== undefined) lines.push(`+ ${right[index]}`);
    }
  }
  return lines.join('\n');
}

function ChapterBinder({ chapters, currentId, detail, onSelect, purpose }: { chapters: Chapter[]; currentId: number | null; detail: ChapterDetail | null; onSelect: (id: number) => void; purpose: ProjectPurpose }) {
  const listRef = useRef<HTMLDivElement>(null);
  return <aside className="chapter-binder"><div className="binder-heading"><h2>章节目录</h2><span>共 {chapters.length} 章</span></div><div className="chapter-list" ref={listRef}>{chapters.map((chapter) => { const status = chapter.id === currentId && detail ? effectiveStatus(detail, purpose) : statusFromChapter(chapter.status, purpose); return <button aria-current={chapter.id === currentId ? 'page' : undefined} className={`chapter-row ${chapter.id === currentId ? 'selected' : ''}`} key={chapter.id} onClick={() => onSelect(chapter.id)} type="button"><span className="chapter-number">{chapter.index}</span><span className="chapter-name" title={chapter.title}>{chapter.title}</span><span className={`chapter-state ${statusTone(status)}`}>{status}</span></button>; })}{chapters.length === 0 ? <div className="compact-empty">工程中没有章节。</div> : null}</div><div className="binder-footer"><button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: 0 })} type="button"><ArrowUpToLine size={14} />回到顶部</button><button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: listRef.current.scrollHeight })} type="button"><ArrowDownToLine size={14} />回到底部</button></div></aside>;
}

function WorkspaceContent({ analysisDraft, detail, exportPlan, generatedPrompt, onSelection, purpose, rewriteDraft, setAnalysisDraft, setExportPlan, setRewriteDraft, setTargetSkeleton, stage, targetSkeleton }: { analysisDraft: string; detail: ChapterDetail | null; exportPlan: ExportPlanItem[]; generatedPrompt: PromptTemplate | null; onSelection: (capture: SelectionCapture) => void; purpose: ProjectPurpose; rewriteDraft: string; setAnalysisDraft: (value: string) => void; setExportPlan: (value: ExportPlanItem[]) => void; setRewriteDraft: (value: string) => void; setTargetSkeleton: (value: string) => void; stage: number; targetSkeleton: string }) {
  if (!detail) return <div className="workspace-empty">选择一个章节开始工作。</div>;
  const { chapter, ai_outputs: output } = detail;
  if (stage === 0) return <ManuscriptPane onSelection={onSelection} title="原文" text={chapter.original_text} words={chapter.word_count} />;
  if (purpose === 'rewrite') {
    if (stage === 1) return <div className="derived-layout"><EditablePanel label="原始剧情骨架" placeholder="点击右侧“提取剧情与人物”" value={output.plot_summary || ''} readOnly /><EditablePanel label="本章人物卡" placeholder="尚未提取人物卡" value={JSON.stringify(output.plot_characters || [], null, 2)} readOnly /></div>;
    if (stage === 2) return <EditablePanel label="目标剧情骨架" placeholder="可以先编辑原始骨架，或让 AI 优化、扩充情节。" value={targetSkeleton} onChange={setTargetSkeleton} />;
    if (stage === 3) return <div className="comparison-layout"><ManuscriptPane onSelection={onSelection} title="原文" text={chapter.original_text} words={chapter.word_count} /><EditablePanel label="改写稿" onSelection={onSelection} placeholder="点击右侧“识别并改写”生成正文" value={rewriteDraft} onChange={setRewriteDraft} manuscript /></div>;
    return <ExportPlan items={exportPlan} onChange={setExportPlan} />;
  }
  if (stage === 1) return <AnalysisReview onSelection={onSelection} original={chapter.original_text} title="章节风格分析" value={JSON.stringify(output.style_analysis || {}, null, 2)} readOnly />;
  if (stage === 2) return <AnalysisReview onSelection={onSelection} original={chapter.original_text} title="人工审查（JSON 可编辑）" value={analysisDraft} onChange={setAnalysisDraft} />;
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
    if (stage === 2) return <><ActionButton busy={busy} label="AI 优化 / 扩充骨架" onClick={props.onExpand} /><button className="button secondary full" disabled={busy} onClick={props.onSaveSkeleton} type="button"><Save className="button-leading-icon" size={16} />保存目标骨架</button></>;
    if (stage === 3) return <><ActionButton busy={busy} label="识别并改写" onClick={props.onRewrite} /><button className="button secondary full" disabled={busy} onClick={props.onSaveRewrite} type="button"><Save className="button-leading-icon" size={16} />保存改写稿</button><button className="button secondary full" disabled={busy || !detail?.chapter.rewritten_text} onClick={props.onConfirmRewrite} type="button">确认本章</button></>;
    if (stage === 4) return <><button className="button primary full" disabled={busy} onClick={() => props.onExportBook('txt')} type="button"><Download className="button-leading-icon" size={16} />导出 TXT</button><button className="button secondary full" disabled={busy} onClick={() => props.onExportBook('epub')} type="button"><Download className="button-leading-icon" size={16} />导出 EPUB</button></>;
    return null;
  }
  if (stage === 1) return <ActionButton busy={busy} label="分析本章风格" onClick={props.onAnalyze} />;
  if (stage === 2) return <ActionButton busy={busy} label="确认本章分析" onClick={props.onConfirmAnalysis} />;
  if (stage === 3) return <ActionButton busy={busy} label="归纳全书并生成提示词" onClick={props.onSynthesize} />;
  if (stage >= 4) return <><button className="button secondary full" disabled={busy || !generatedPrompt} onClick={props.onReviewPrompt} type="button">到提示词管理审查</button><button className="button primary full" disabled={busy || !generatedPrompt} onClick={props.onExportPrompt} type="button"><Download className="button-leading-icon" size={16} />导出 JSON</button></>;
  return null;
}

function RewriteTrace({ attempts, preview }: { attempts: GenerationAttempt[]; preview: CompiledPromptPreview | null }) {
  const latest = attempts[attempts.length - 1];
  const shown = latest?.request || preview;
  return <details className="rewrite-trace"><summary>查看 Rusty 实际请求与生成记录</summary>{shown ? <><section><h3>规则来源</h3><pre>{`Rusty 自有规则：${shown.ruleset_id}\n用户提示词：模板 #${String(shown.provenance.template_id ?? '未绑定')}\n输出契约：${shown.expected_output}`}</pre></section>{shown.messages.map((message, index) => <section key={`${message.role}-${index}`}><h3>{message.role === 'system' ? 'System 请求' : message.role === 'assistant' ? '模型上次输出' : 'User 请求'}</h3><pre>{message.content}</pre></section>)}</> : <section><p>当前章节暂时无法编译改写请求。</p></section>}<section><h3>最近生成记录</h3><pre>{latest ? `第 ${latest.attempt_number} 次 · ${latest.error_type || '成功'}\n${latest.error_message || latest.response_text}` : '尚未生成'}</pre></section></details>;
}
function ActionButton({ busy, label, onClick }: { busy: boolean; label: string; onClick: () => void }) { return <button className="button primary full" disabled={busy} onClick={onClick} type="button"><Sparkles className="button-leading-icon" size={16} />{busy ? '处理中…' : label}</button>; }
function ManuscriptPane({ onSelection, text, title, words }: { onSelection?: (capture: SelectionCapture) => void; text: string; title: string; words: number }) {
  function openSelectionMenu(event: ReactMouseEvent<HTMLDivElement>) {
    if (!onSelection) return;
    const offsets = selectionOffsetsWithin(event.currentTarget);
    if (!offsets) return;
    event.preventDefault();
    onSelection({ ...offsets, x: event.clientX, y: event.clientY });
  }
  return <section className="manuscript-pane"><header><h2>{title}</h2><span>{words.toLocaleString()} 字</span></header><div className="manuscript-text" onContextMenu={openSelectionMenu}>{text}</div></section>;
}
function EditablePanel({ label, manuscript = false, onChange, onSelection, placeholder, readOnly = false, value }: { label: string; manuscript?: boolean; onChange?: (value: string) => void; onSelection?: (capture: SelectionCapture) => void; placeholder: string; readOnly?: boolean; value: string }) {
  function openSelectionMenu(event: ReactMouseEvent<HTMLTextAreaElement>) {
    if (!onSelection) return;
    const target = event.currentTarget;
    const rawText = target.value.slice(target.selectionStart, target.selectionEnd);
    const text = rawText.trim();
    if (!text) return;
    event.preventDefault();
    const leadingWhitespace = rawText.length - rawText.trimStart().length;
    const startOffset = target.selectionStart + leadingWhitespace;
    onSelection({ text, startOffset, endOffset: startOffset + text.length, x: event.clientX, y: event.clientY });
  }
  return <label className={`editable-panel ${manuscript ? 'manuscript-editor' : ''}`}><span><strong>{label}</strong><small>{countText(value).toLocaleString()} 字</small></span><textarea onContextMenu={openSelectionMenu} placeholder={placeholder} readOnly={readOnly} value={value} onChange={(event) => onChange?.(event.target.value)} /></label>;
}
function AnalysisReview({ onChange, onSelection, original, readOnly = false, title, value }: { onChange?: (value: string) => void; onSelection?: (capture: SelectionCapture) => void; original: string; readOnly?: boolean; title: string; value: string }) { return <div className="analysis-review"><ManuscriptPane onSelection={onSelection} text={original} title="原文（证据来源）" words={countText(original)} /><EditablePanel label={title} placeholder="尚未生成分析" readOnly={readOnly} value={value} onChange={onChange} /></div>; }
function PromptPreview({ prompt }: { prompt: PromptTemplate | null }) { if (!prompt) return <div className="workspace-message"><h2>提示词预览</h2><p>请先完成全书归纳。</p></div>; const recognitionRules = prompt.scene_rules.map((rule) => `[${rule.display_name}]\n${rule.detection_prompt}`).join('\n\n'); return <div className="prompt-preview"><section><h3>基础规则</h3><pre>{prompt.global_rules || '暂无'}</pre></section><section><h3>识别规则</h3><pre>{recognitionRules || '暂无'}</pre></section><section><h3>改写规则</h3><pre>{prompt.rewrite_rules || '暂无'}{prompt.scene_rules.map((rule) => `\n\n[${rule.display_name}]\n${rule.rewrite_prompt}`).join('')}</pre></section></div>; }
function ExportPlan({ items, onChange }: { items: ExportPlanItem[]; onChange: (items: ExportPlanItem[]) => void }) { return <div className="export-plan"><div className="section-heading"><div><strong>导出检查</strong><span>检查标题、顺序、包含状态和正文来源</span></div></div>{items.map((item, index) => <div className="export-row" key={item.chapter_id}><input aria-label={`包含第 ${index + 1} 章`} checked={item.include_in_export} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, include_in_export: event.target.checked } : current))} type="checkbox" /><span>{index + 1}</span><input aria-label="导出标题" value={item.export_title} onChange={(event) => onChange(items.map((current) => current.chapter_id === item.chapter_id ? { ...current, export_title: event.target.value } : current))} /><small>{sourceLabel(item.source_status)}</small></div>)}</div>; }
function Definition({ label, value }: { label: string; value: string }) { return <div className="definition"><span>{label}</span><strong>{value}</strong></div>; }
function effectiveStatus(detail: ChapterDetail, purpose: ProjectPurpose) { if (purpose === 'legacy_extract') return detail.ai_outputs.style_analysis_status === 'confirmed' ? '已确认' : detail.ai_outputs.style_analysis ? '待审查' : '未分析'; if (detail.chapter.status === 'confirmed') return '已确认'; if (detail.chapter.rewritten_text) return '已改写'; if (detail.ai_outputs.plot_summary) return '已提取'; return '未处理'; }
function statusFromChapter(status: string, purpose: ProjectPurpose) { if (purpose === 'legacy_extract') return '未分析'; if (status === 'confirmed') return '已确认'; if (status === 'rewritten') return '已改写'; if (status === 'kept_original') return '保留原文'; return '未处理'; }
function statusTone(status: string) { if (status === '已确认') return 'success'; if (status === '待审查' || status === '已提取') return 'warning'; if (status === '已改写') return 'info'; return 'muted'; }
function sourceLabel(status: ExportPlanItem['source_status']) { if (status === 'manual_rewrite') return '手动改写'; if (status === 'ai_rewrite') return 'AI 改写'; if (status === 'kept_original') return '保留原文'; return '原文'; }
function numberValue(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
function blockEnterActivation(event: ReactKeyboardEvent<HTMLButtonElement>) { if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); } }
function countText(value: string) { return value.replace(/\s/g, '').length; }
function selectionOffsetsWithin(container: HTMLElement) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;
  const before = document.createRange();
  before.selectNodeContents(container);
  before.setEnd(range.startContainer, range.startOffset);
  const rawText = range.toString();
  const text = rawText.trim();
  if (!text) return null;
  const leadingWhitespace = rawText.length - rawText.trimStart().length;
  const startOffset = before.toString().length + leadingWhitespace;
  return { text, startOffset, endOffset: startOffset + text.length };
}
function clamp(value: number, min: number, max: number) { return Math.min(max, Math.max(min, value)); }
function messageOf(reason: unknown) {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (/\b401\b|unauthorized/i.test(message)) {
    return '模型服务鉴权失败：当前模型没有有效的 API Key，请前往“模型”设置后重新测试连接。';
  }
  if (/read operation timed out|readtimeout/i.test(message)) {
    return '模型响应超时：模型未能在设定时间内返回结果。请在“模型”设置中适当增大 Timeout seconds 后重试本阶段。';
  }
  return message;
}
function safeName(value: string) { return value.replace(/[\\/:*?"<>|]/g, '_').trim() || 'rewrite-prompt'; }
function download(content: string, fileName: string, type: string) { const url = URL.createObjectURL(new Blob([content], { type })); const link = document.createElement('a'); link.href = url; link.download = fileName; link.click(); URL.revokeObjectURL(url); }
