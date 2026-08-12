import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { ArrowLeft, Check, RefreshCw, Settings2, Sparkles } from 'lucide-react';
import {
  activateCreativeScene,
  adjustChapterScenes,
  analyzeChapterScenes,
  confirmChapterScenes,
  confirmScenePreanalysis,
  confirmCharacterModificationAnalysis,
  confirmSceneTarget,
  confirmStrategyAnalysis,
  editSelectedDraft,
  startSceneReview,
  getReviewDiff,
  getReviewMarks,
  createReviewMark,
  removeReviewMark,
  restoreReviewSource,
  reworkReviewRange,
  reworkAllReviewMarks,
  adoptReviewRework,
  confirmCreativeScene,
  generateCurrentDraft,
  getChapter,
  getChapterScenes,
  getChapters,
  getCreativeWorkflowStates,
  getCreativeSceneStates,
  getProjectCharacters,
  getProject,
  getProjectMasterPrompt,
  getProjectMaterials,
  getModels,
  getSceneCreativeIntent,
  getScenePreanalysis,
  getCharacterModificationAnalysis,
  getStrategyAnalysis,
  getSceneTarget,
  getWritingPlan,
  getCurrentDraft,
  runScenePreanalysis,
  runCharacterModificationAnalysis,
  runStrategyAnalysis,
  runSceneTarget,
  runWritingPlan,
  saveSceneCreativeIntent,
  saveScenePreanalysis,
  saveCharacterModificationAnalysis,
  saveStrategyAnalysis,
  saveSceneTarget,
  saveWritingPlan,
  saveCurrentDraft,
  saveProjectMasterPrompt,
  exportProjectMasterPrompt,
  updateProjectSettings,
  updateCreativeWorkflowState,
} from '../api/client';
import type {
  Chapter,
  BaseSceneAnalysis,
  ChapterDetail,
  ChapterWorkflowState,
  CreativeWorkflowStage,
  CreativeIntent,
  CreativeStrategy,
  CharacterCard,
  CharacterAnalysisItem,
  CharacterModificationAnalysis,
  Material,
  ModelConfig,
  SceneRecord,
  SceneWorkflowState,
  SceneBoundaryItem,
  SceneTarget,
  ChangeSetItem,
  WritingPlan,
  WritingBlock,
  SceneDraft,
  SceneReviewDiff,
  ReviewMark,
  StrategySceneAnalysis,
} from '../api/types';
import { registerNavigationFlush } from '../navigationFlush';

type Props = {
  projectId: number;
  projectName: string;
  onNavigate: (path: string, state?: unknown) => void;
};

const stageOrder: CreativeWorkflowStage[] = [
  'preanalysis', 'direction', 'special_analysis', 'target_design', 'writing', 'review',
];

const stageLabels: Record<CreativeWorkflowStage, string> = {
  not_started: '未开始',
  preanalysis: '预分析',
  direction: '方向选择',
  special_analysis: '专项分析',
  target_design: '目标设计',
  writing: '写作',
  review: '审查',
  confirmed: '已确认',
};

type LoadedSceneDraft = {
  chapterId: number;
  sceneId: number;
  preanalysis: BaseSceneAnalysis | null;
  intent: CreativeIntent | null;
  characterAnalysis: CharacterModificationAnalysis | null;
  strategyAnalysis: StrategySceneAnalysis | null;
  target: SceneTarget | null;
  writingPlan: WritingPlan | null;
  currentDraft: SceneDraft | null;
  analysisDirty: boolean;
  intentDirty: boolean;
  characterAnalysisDirty: boolean;
  strategyAnalysisDirty: boolean;
  targetDirty: boolean;
  writingPlanDirty: boolean;
  currentDraftDirty: boolean;
  analysisRevision: number;
  intentRevision: number;
  characterAnalysisRevision: number;
  strategyAnalysisRevision: number;
  targetRevision: number;
  writingPlanRevision: number;
  currentDraftRevision: number;
};

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [states, setStates] = useState<ChapterWorkflowState[]>([]);
  const [sceneStates, setSceneStates] = useState<SceneWorkflowState[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);
  const [scenes, setScenes] = useState<SceneRecord[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [preanalysis, setPreanalysis] = useState<BaseSceneAnalysis | null>(null);
  const [analysisDirty, setAnalysisDirty] = useState(false);
  const [intent, setIntent] = useState<CreativeIntent | null>(null);
  const [intentDirty, setIntentDirty] = useState(false);
  const [viewStage, setViewStage] = useState<CreativeWorkflowStage>('preanalysis');
  const [busy, setBusy] = useState(false);
  const [sceneContextLoading, setSceneContextLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [settingsModelId, setSettingsModelId] = useState<number | null>(null);
  const [masterPrompt, setMasterPrompt] = useState('');
  const [masterDirty, setMasterDirty] = useState(false);
  const [characterAnalysis, setCharacterAnalysis] = useState<CharacterModificationAnalysis | null>(null);
  const [characterAnalysisDirty, setCharacterAnalysisDirty] = useState(false);
  const [strategyAnalysis, setStrategyAnalysis] = useState<StrategySceneAnalysis | null>(null);
  const [strategyAnalysisDirty, setStrategyAnalysisDirty] = useState(false);
  const [target, setTarget] = useState<SceneTarget | null>(null);
  const [targetDirty, setTargetDirty] = useState(false);
  const [writingPlan, setWritingPlan] = useState<WritingPlan | null>(null);
  const [writingPlanDirty, setWritingPlanDirty] = useState(false);
  const [currentDraft, setCurrentDraft] = useState<SceneDraft | null>(null);
  const [currentDraftDirty, setCurrentDraftDirty] = useState(false);
  const [writingView, setWritingView] = useState<'plan' | 'draft'>('plan');
  const draftEditorRef = useRef<HTMLTextAreaElement | null>(null);
  const reviewSourceRef = useRef<HTMLTextAreaElement | null>(null);
  const reviewTargetRef = useRef<HTMLTextAreaElement | null>(null);
  const [reviewDiff, setReviewDiff] = useState<SceneReviewDiff | null>(null);
  const [reviewMarks, setReviewMarks] = useState<ReviewMark[]>([]);
  const [reviewUndo, setReviewUndo] = useState<{ beforeText: string; markIds: number[] } | null>(null);
  const [sourceCharacter, setSourceCharacter] = useState('');
  const [targetCharacterId, setTargetCharacterId] = useState<number | null>(null);
  const [focusedEvidence, setFocusedEvidence] = useState('');
  const [loadedSceneId, setLoadedSceneId] = useState<number | null>(null);
  const [boundaryEditing, setBoundaryEditing] = useState(false);
  const [boundaryDrafts, setBoundaryDrafts] = useState<SceneBoundaryItem[]>([]);
  const loadedDraftRef = useRef<LoadedSceneDraft | null>(null);
  const selectedChapterIdRef = useRef<number | null>(null);
  const sceneLoadSequenceRef = useRef(0);
  const switchQueueRef = useRef<Promise<void>>(Promise.resolve());
  const flushPromiseRef = useRef<Promise<void> | null>(null);

  const stateByChapter = useMemo(
    () => new Map(states.map((item) => [item.chapter_id, item])),
    [states],
  );
  const selectedState = selectedChapterId ? stateByChapter.get(selectedChapterId) ?? null : null;
  const sceneStateById = useMemo(
    () => new Map(sceneStates.map((item) => [item.scene_id, item])),
    [sceneStates],
  );
  const selectedChapter = detail?.chapter ?? chapters.find((item) => item.id === selectedChapterId) ?? null;

  const loadProject = useCallback(async () => {
    const [chapterItems, workflowStates, characterBindings, materialItems] = await Promise.all([
      getChapters(projectId),
      getCreativeWorkflowStates(projectId),
      getProjectCharacters(projectId),
      getProjectMaterials(projectId),
    ]);
    setChapters(chapterItems);
    setStates(workflowStates);
    setCharacters(characterBindings.character_cards);
    setMaterials(materialItems);
    setSelectedChapterId((current) => {
      const next = current && chapterItems.some((item) => item.id === current) ? current : chapterItems[0]?.id ?? null;
      selectedChapterIdRef.current = next;
      return next;
    });
  }, [projectId]);

  const loadChapter = useCallback(async (chapterId: number) => {
    const [chapterDetail, sceneItems, workflowItems] = await Promise.all([
      getChapter(chapterId),
      getChapterScenes(chapterId),
      getCreativeSceneStates(chapterId),
    ]);
    if (selectedChapterIdRef.current !== chapterId) return;
    setDetail(chapterDetail);
    setScenes(sceneItems);
    setSceneStates(workflowItems);
    setBoundaryDrafts(boundariesFromScenes(sceneItems));
  }, []);

  const activeSceneId = selectedState?.active_scene_id ?? null;

  const refreshWorkflowStates = useCallback(async (chapterId?: number) => {
    const chapterStates = await getCreativeWorkflowStates(projectId);
    setStates(chapterStates);
    const targetChapterId = chapterId ?? selectedChapterIdRef.current;
    if (targetChapterId && selectedChapterIdRef.current === targetChapterId) {
      setSceneStates(await getCreativeSceneStates(targetChapterId));
    }
  }, [projectId]);

  const flushLoadedScene = useCallback(async () => {
    if (flushPromiseRef.current) return flushPromiseRef.current;
    const pending = (async () => {
      while (true) {
        const draft = loadedDraftRef.current;
        if (!draft || (!draft.analysisDirty && !draft.intentDirty && !draft.characterAnalysisDirty && !draft.strategyAnalysisDirty && !draft.targetDirty && !draft.writingPlanDirty && !draft.currentDraftDirty)) return;
        const snapshot = { ...draft };
        if (snapshot.analysisDirty && snapshot.preanalysis) {
          const saved = await saveScenePreanalysis(snapshot.sceneId, analysisWrite(snapshot.preanalysis));
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.analysisRevision === snapshot.analysisRevision) {
            current.preanalysis = saved;
            current.analysisDirty = false;
            setPreanalysis(saved);
            setAnalysisDirty(false);
          }
        }
        if (snapshot.intentDirty && snapshot.intent) {
          const saved = await saveSceneCreativeIntent(snapshot.sceneId, snapshot.intent);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.intentRevision === snapshot.intentRevision) {
            current.intent = saved;
            current.intentDirty = false;
            setIntent(saved);
            setIntentDirty(false);
          }
        }
        if (snapshot.characterAnalysisDirty && snapshot.characterAnalysis) {
          const saved = await saveCharacterModificationAnalysis(snapshot.sceneId, snapshot.characterAnalysis);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.characterAnalysisRevision === snapshot.characterAnalysisRevision) {
            current.characterAnalysis = saved;
            current.characterAnalysisDirty = false;
            setCharacterAnalysis(saved);
            setCharacterAnalysisDirty(false);
          }
        }
        if (snapshot.strategyAnalysisDirty && snapshot.strategyAnalysis) {
          const saved = await saveStrategyAnalysis(snapshot.sceneId, snapshot.strategyAnalysis);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.strategyAnalysisRevision === snapshot.strategyAnalysisRevision) {
            current.strategyAnalysis = saved; current.strategyAnalysisDirty = false; setStrategyAnalysis(saved); setStrategyAnalysisDirty(false);
          }
        }
        if (snapshot.targetDirty && snapshot.target) {
          const saved = await saveSceneTarget(snapshot.sceneId, snapshot.target);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.targetRevision === snapshot.targetRevision) {
            current.target = saved;
            current.targetDirty = false;
            setTarget(saved);
            setTargetDirty(false);
          }
        }
        if (snapshot.writingPlanDirty && snapshot.writingPlan) {
          const saved = await saveWritingPlan(snapshot.sceneId, snapshot.writingPlan);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.writingPlanRevision === snapshot.writingPlanRevision) {
            current.writingPlan = saved; current.writingPlanDirty = false; setWritingPlan(saved); setWritingPlanDirty(false);
          }
        }
        if (snapshot.currentDraftDirty && snapshot.currentDraft) {
          const saved = await saveCurrentDraft(snapshot.sceneId, snapshot.currentDraft);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && current.currentDraftRevision === snapshot.currentDraftRevision) {
            current.currentDraft = saved; current.currentDraftDirty = false; setCurrentDraft(saved); setCurrentDraftDirty(false);
          }
        }
        if (snapshot.analysisDirty || snapshot.intentDirty || snapshot.characterAnalysisDirty || snapshot.strategyAnalysisDirty || snapshot.targetDirty) {
          const [latestAnalysis, latestStrategyAnalysis, latestTarget, latestPlan] = await Promise.all([
            getCharacterModificationAnalysis(snapshot.sceneId), getStrategyAnalysis(snapshot.sceneId), getSceneTarget(snapshot.sceneId), getWritingPlan(snapshot.sceneId),
          ]);
          const current = loadedDraftRef.current;
          if (current?.sceneId === snapshot.sceneId && !current.characterAnalysisDirty) {
            current.characterAnalysis = latestAnalysis;
            setCharacterAnalysis(latestAnalysis);
          }
          if (current?.sceneId === snapshot.sceneId && !current.strategyAnalysisDirty) { current.strategyAnalysis = latestStrategyAnalysis; setStrategyAnalysis(latestStrategyAnalysis); }
          if (current?.sceneId === snapshot.sceneId && !current.targetDirty) {
            current.target = latestTarget;
            setTarget(latestTarget);
          }
          if (current?.sceneId === snapshot.sceneId && !current.writingPlanDirty) {
            current.writingPlan = latestPlan; setWritingPlan(latestPlan);
          }
        }
        await refreshWorkflowStates(snapshot.chapterId);
      }
    })().catch((reason) => {
      setError(messageOf(reason));
      throw reason;
    }).finally(() => {
      flushPromiseRef.current = null;
    });
    flushPromiseRef.current = pending;
    await pending;
  }, [refreshWorkflowStates]);

  const loadSceneContext = useCallback(async (chapterId: number, sceneId: number) => {
    const sequence = ++sceneLoadSequenceRef.current;
    setSceneContextLoading(true);
    const [analysis, creativeIntent, specialized, strategySpecific, sceneTarget, plan, draftText, marks] = await Promise.all([
      getScenePreanalysis(sceneId),
      getSceneCreativeIntent(sceneId),
      getCharacterModificationAnalysis(sceneId),
      getStrategyAnalysis(sceneId),
      getSceneTarget(sceneId),
      getWritingPlan(sceneId),
      getCurrentDraft(sceneId),
      getReviewMarks(sceneId),
    ]);
    const diff = draftText ? await getReviewDiff(sceneId) : null;
    if (sequence !== sceneLoadSequenceRef.current || selectedChapterIdRef.current !== chapterId) return;
    loadedDraftRef.current = {
      chapterId,
      sceneId,
      preanalysis: analysis,
      intent: creativeIntent,
      characterAnalysis: specialized,
      strategyAnalysis: strategySpecific,
      target: sceneTarget,
      writingPlan: plan,
      currentDraft: draftText,
      analysisDirty: false,
      intentDirty: false,
      characterAnalysisDirty: false,
      strategyAnalysisDirty: false,
      targetDirty: false,
      writingPlanDirty: false,
      currentDraftDirty: false,
      analysisRevision: 0,
      intentRevision: 0,
      characterAnalysisRevision: 0,
      strategyAnalysisRevision: 0,
      targetRevision: 0,
      writingPlanRevision: 0,
      currentDraftRevision: 0,
    };
    setLoadedSceneId(sceneId);
    setPreanalysis(analysis);
    setIntent(creativeIntent);
    setCharacterAnalysis(specialized);
    setStrategyAnalysis(strategySpecific);
    setTarget(sceneTarget);
    setWritingPlan(plan);
    setCurrentDraft(draftText);
    setReviewMarks(marks);
    setReviewDiff(diff);
    setReviewUndo(null);
    setWritingView(draftText ? 'draft' : 'plan');
    setSourceCharacter(specialized?.source_character ?? analysis?.characters[0] ?? '');
    setTargetCharacterId(specialized?.target_character_card_id ?? creativeIntent?.selected_character_ids[0] ?? null);
    setAnalysisDirty(false);
    setIntentDirty(false);
    setCharacterAnalysisDirty(false);
    setStrategyAnalysisDirty(false);
    setTargetDirty(false);
    setWritingPlanDirty(false);
    setCurrentDraftDirty(false);
    setFocusedEvidence('');
    setSceneContextLoading(false);
  }, []);

  useEffect(() => {
    const unregister = registerNavigationFlush(flushLoadedScene);
    const flushBestEffort = () => { void flushLoadedScene().catch(() => undefined); };
    window.addEventListener('pagehide', flushBestEffort);
    return () => {
      window.removeEventListener('pagehide', flushBestEffort);
      unregister();
      flushBestEffort();
    };
  }, [flushLoadedScene]);

  useEffect(() => {
    if (!activeSceneId || !selectedChapterId) {
      sceneLoadSequenceRef.current += 1;
      loadedDraftRef.current = null;
      setLoadedSceneId(null);
      setSceneContextLoading(false);
      setPreanalysis(null);
      setIntent(null);
      setCharacterAnalysis(null);
      setStrategyAnalysis(null);
      setTarget(null);
      setWritingPlan(null);
      setCurrentDraft(null);
      setReviewDiff(null);
      setReviewMarks([]);
      return;
    }
    if (loadedDraftRef.current?.sceneId === activeSceneId) return;
    void loadSceneContext(selectedChapterId, activeSceneId).catch((reason) => {
      setSceneContextLoading(false);
      setError(messageOf(reason));
    });
  }, [activeSceneId, loadSceneContext, selectedChapterId]);

  useEffect(() => {
    if (!loadedSceneId || (!analysisDirty && !intentDirty && !characterAnalysisDirty && !strategyAnalysisDirty && !targetDirty && !writingPlanDirty && !currentDraftDirty)) return;
    const timeout = window.setTimeout(() => {
      void flushLoadedScene().catch(() => undefined);
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [analysisDirty, characterAnalysisDirty, strategyAnalysisDirty, flushLoadedScene, intentDirty, loadedSceneId, preanalysis, intent, characterAnalysis, strategyAnalysis, target, targetDirty, writingPlan, writingPlanDirty, currentDraft, currentDraftDirty]);

  useEffect(() => {
    void loadProject().catch((reason) => setError(messageOf(reason)));
  }, [loadProject]);

  useEffect(() => {
    if (!selectedChapterId) return;
    void loadChapter(selectedChapterId).catch((reason) => setError(messageOf(reason)));
  }, [loadChapter, selectedChapterId]);

  useEffect(() => {
    if (!selectedState) return;
    setViewStage(selectedState.current_stage === 'not_started' ? 'preanalysis' : selectedState.current_stage);
  }, [selectedState?.chapter_id, selectedState?.current_stage]);

  useEffect(() => {
    if (!selectedChapterId || !selectedState || selectedState.active_scene_id || !scenes[0] || busy) return;
    void chooseScene(scenes[0].id);
  }, [busy, scenes, selectedChapterId, selectedState?.active_scene_id, selectedState?.chapter_id]);

  const activeSceneState = activeSceneId ? sceneStateById.get(activeSceneId) ?? null : null;
  const reachedIndex = workflowIndex(activeSceneState?.current_stage ?? 'not_started');

  async function chooseChapter(chapterId: number) {
    if (chapterId === selectedChapterIdRef.current) return;
    setBusy(true);
    setError(null);
    const operation = switchQueueRef.current.then(async () => {
      await flushLoadedScene();
      sceneLoadSequenceRef.current += 1;
      loadedDraftRef.current = null;
      setLoadedSceneId(null);
      selectedChapterIdRef.current = chapterId;
      setSelectedChapterId(chapterId);
    });
    switchQueueRef.current = operation.catch(() => undefined);
    try { await operation; }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function chooseScene(sceneId: number) {
    if (!selectedChapterId || sceneId === activeSceneId) return;
    const chapterId = selectedChapterId;
    setBusy(true);
    setError(null);
    const operation = switchQueueRef.current.then(async () => {
      await flushLoadedScene();
      if (selectedChapterIdRef.current !== chapterId) return;
      const updated = await activateCreativeScene(sceneId);
      const ownState = sceneStateById.get(sceneId) ?? (await getCreativeSceneStates(chapterId)).find((item) => item.scene_id === sceneId);
      setStates((items) => items.map((item) => item.chapter_id === updated.chapter_id ? updated : item));
      setSceneStates(await getCreativeSceneStates(chapterId));
      setViewStage(ownState?.current_stage === 'not_started' || !ownState ? 'preanalysis' : ownState.current_stage);
    });
    switchQueueRef.current = operation.catch(() => undefined);
    try { await operation; }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function createScenes() {
    if (!selectedChapterId) return;
    await perform(async () => {
      const items = await analyzeChapterScenes(selectedChapterId, { source: 'heuristic', confirm: false });
      setScenes(items);
      setBoundaryDrafts(boundariesFromScenes(items));
      await refreshWorkflowStates(selectedChapterId);
    });
  }

  async function analyzeScene() {
    if (!activeSceneId) return;
    const replace = Boolean(preanalysis?.user_edited);
    if (replace && !window.confirm('重新分析会替换当前预分析结果。')) return;
    await perform(async () => {
      const saved = await runScenePreanalysis(activeSceneId, replace);
      if (loadedDraftRef.current?.sceneId === activeSceneId) {
        loadedDraftRef.current.preanalysis = saved;
        loadedDraftRef.current.analysisDirty = false;
      }
      setPreanalysis(saved);
      setSourceCharacter((current) => current || saved.characters[0] || '');
      setAnalysisDirty(false);
      setViewStage('preanalysis');
      await refreshStates();
    });
  }

  async function confirmAnalysis() {
    if (!activeSceneId) return;
    await perform(async () => {
      const saved = await confirmScenePreanalysis(activeSceneId);
      if (loadedDraftRef.current?.sceneId === activeSceneId) loadedDraftRef.current.preanalysis = saved;
      setPreanalysis(saved);
      setViewStage('direction');
      await refreshStates();
    });
  }

  async function continueToSpecialAnalysis() {
    if (!activeSceneId || !selectedChapterId || !intent) return;
    await perform(async () => {
      await flushLoadedScene();
      const loaded = loadedDraftRef.current;
      if (!loaded || loaded.sceneId !== activeSceneId || !loaded.intent) return;
      setTargetCharacterId((current) => current ?? loaded.intent?.selected_character_ids[0] ?? null);
      const specialized = loaded.intent.strategy === 'faithful' ? loaded.characterAnalysis : loaded.strategyAnalysis;
      if (!specialized || specialized.status === 'stale') {
        await updateCreativeWorkflowState(selectedChapterId, 'special_analysis', activeSceneId);
        await refreshWorkflowStates(selectedChapterId);
      }
      setViewStage('special_analysis');
    });
  }

  async function refreshStates() {
    await refreshWorkflowStates(selectedChapterId ?? undefined);
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  function patchAnalysis(patch: Partial<BaseSceneAnalysis>) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId || !draft.preanalysis) return;
    const next = { ...draft.preanalysis, ...patch };
    draft.preanalysis = next;
    draft.analysisDirty = true;
    draft.analysisRevision += 1;
    setPreanalysis(next);
    setAnalysisDirty(true);
  }

  function patchIntent(patch: Partial<CreativeIntent>) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId || !draft.intent) return;
    const next = { ...draft.intent, ...patch };
    draft.intent = next;
    draft.intentDirty = true;
    draft.intentRevision += 1;
    setIntent(next);
    setIntentDirty(true);
  }

  function chooseStrategy(strategy: CreativeStrategy) {
    if (!activeSceneId) return;
    if (intent) patchIntent({ strategy });
    else {
      const next: CreativeIntent = {
        scene_id: activeSceneId,
        strategy,
        user_instruction: '',
        selected_character_ids: [],
        selected_plot_material_ids: [],
        selected_scene_material_ids: [],
        status: 'draft',
        updated_at: new Date().toISOString(),
      };
      const draft = loadedDraftRef.current;
      if (!draft || draft.sceneId !== activeSceneId) return;
      draft.intent = next;
      draft.intentDirty = true;
      draft.intentRevision += 1;
      setIntent(next);
      setIntentDirty(true);
    }
  }

  async function openSettings() {
    await perform(async () => {
      const [project, modelItems, master] = await Promise.all([
        getProject(projectId), getModels(), getProjectMasterPrompt(projectId),
      ]);
      setModels(modelItems);
      setSettingsModelId(typeof project.settings?.model_id === 'number' ? project.settings.model_id : null);
      setMasterPrompt(master.content);
      setMasterDirty(false);
      setSettingsOpen(true);
    });
  }

  async function saveSettings() {
    await perform(async () => {
      await Promise.all([
        updateProjectSettings(projectId, { model_id: settingsModelId }),
        saveProjectMasterPrompt(projectId, masterPrompt),
      ]);
      setMasterDirty(false);
    });
  }

  async function exportMaster() {
    const name = window.prompt('保存到提示词库的名称', `${projectName} · 总提示词`);
    if (!name?.trim()) return;
    await perform(async () => { await exportProjectMasterPrompt(projectId, name.trim()); });
  }

  async function analyzeCharacterModification() {
    if (!activeSceneId || !targetCharacterId || !sourceCharacter.trim()) return;
    const replace = Boolean(characterAnalysis?.user_edited);
    if (replace && !window.confirm('重新分析会替换当前专项分析结果。')) return;
    await perform(async () => {
      const saved = await runCharacterModificationAnalysis(activeSceneId, {
        source_character: sourceCharacter.trim(),
        target_character_card_id: targetCharacterId,
        replace_existing: replace,
      });
      if (loadedDraftRef.current?.sceneId === activeSceneId) {
        loadedDraftRef.current.characterAnalysis = saved;
        loadedDraftRef.current.characterAnalysisDirty = false;
      }
      setCharacterAnalysis(saved);
      setCharacterAnalysisDirty(false);
      await refreshStates();
    });
  }

  async function confirmCharacterAnalysis() {
    if (!activeSceneId) return;
    await perform(async () => {
      const saved = await confirmCharacterModificationAnalysis(activeSceneId);
      if (loadedDraftRef.current?.sceneId === activeSceneId) loadedDraftRef.current.characterAnalysis = saved;
      setCharacterAnalysis(saved);
      setCharacterAnalysisDirty(false);
      setViewStage('target_design');
      await refreshStates();
    });
  }

  function patchCharacterAnalysis(value: CharacterModificationAnalysis) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId) return;
    draft.characterAnalysis = value;
    draft.characterAnalysisDirty = true;
    draft.characterAnalysisRevision += 1;
    setCharacterAnalysis(value);
    setCharacterAnalysisDirty(true);
  }

  async function analyzeStrategy() {
    if (!activeSceneId) return;
    const replace = Boolean(strategyAnalysis?.user_edited);
    if (replace && !window.confirm('重新分析会替换当前专项分析结果。')) return;
    await perform(async () => { const saved = await runStrategyAnalysis(activeSceneId, replace); const draft = loadedDraftRef.current; if (draft?.sceneId === activeSceneId) { draft.strategyAnalysis = saved; draft.strategyAnalysisDirty = false; } setStrategyAnalysis(saved); setStrategyAnalysisDirty(false); await refreshStates(); });
  }

  function patchStrategyAnalysis(value: StrategySceneAnalysis) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId) return;
    draft.strategyAnalysis = value; draft.strategyAnalysisDirty = true; draft.strategyAnalysisRevision += 1;
    setStrategyAnalysis(value); setStrategyAnalysisDirty(true);
  }

  async function confirmGenericAnalysis() {
    if (!activeSceneId) return;
    await perform(async () => { const saved = await confirmStrategyAnalysis(activeSceneId); const draft = loadedDraftRef.current; if (draft?.sceneId === activeSceneId) draft.strategyAnalysis = saved; setStrategyAnalysis(saved); setStrategyAnalysisDirty(false); setViewStage('target_design'); await refreshStates(); });
  }

  async function generateTarget() {
    if (!activeSceneId) return;
    const replace = Boolean(target);
    if (replace && !window.confirm('重新生成会替换当前目标草案。')) return;
    await perform(async () => {
      await flushLoadedScene();
      const saved = await runSceneTarget(activeSceneId, replace);
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) { draft.target = saved; draft.targetDirty = false; }
      setTarget(saved);
      setTargetDirty(false);
      await refreshStates();
    });
  }

  function patchTarget(value: SceneTarget) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId) return;
    draft.target = value;
    draft.targetDirty = true;
    draft.targetRevision += 1;
    setTarget(value);
    setTargetDirty(true);
  }

  async function confirmTargetDesign() {
    if (!activeSceneId) return;
    await perform(async () => {
      await flushLoadedScene();
      const saved = await confirmSceneTarget(activeSceneId);
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) { draft.target = saved; draft.targetDirty = false; }
      setTarget(saved);
      setTargetDirty(false);
      setViewStage('writing');
      await refreshStates();
    });
  }

  async function planWriting() {
    if (!activeSceneId) return;
    const replace = Boolean(writingPlan);
    if (replace && writingPlan?.status !== 'stale' && !window.confirm('重新规划会替换当前写作规划，但不会删除当前正文。')) return;
    await perform(async () => {
      await flushLoadedScene();
      const saved = await runWritingPlan(activeSceneId, replace || writingPlan?.status === 'stale');
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) { draft.writingPlan = saved; draft.writingPlanDirty = false; }
      setWritingPlan(saved); setWritingPlanDirty(false); setWritingView('plan');
    });
  }

  function patchWritingPlan(value: WritingPlan) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId) return;
    draft.writingPlan = value; draft.writingPlanDirty = true; draft.writingPlanRevision += 1;
    setWritingPlan(value); setWritingPlanDirty(true);
  }

  async function generateDraft() {
    if (!activeSceneId) return;
    const replace = Boolean(currentDraft);
    if (replace && !window.confirm('重新生成会替换当前正文及人工修改，是否继续？')) return;
    await perform(async () => {
      await flushLoadedScene();
      const saved = await generateCurrentDraft(activeSceneId, replace);
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) { draft.currentDraft = saved; draft.currentDraftDirty = false; }
      setCurrentDraft(saved); setCurrentDraftDirty(false); setWritingView('draft');
    });
  }

  function patchCurrentDraftText(text: string) {
    const draft = loadedDraftRef.current;
    if (!draft || draft.sceneId !== loadedSceneId || !draft.currentDraft) return;
    const next = { ...draft.currentDraft, text };
    draft.currentDraft = next; draft.currentDraftDirty = true; draft.currentDraftRevision += 1;
    setCurrentDraft(next); setCurrentDraftDirty(true);
  }

  async function aiEditSelection() {
    if (!activeSceneId || !currentDraft || !draftEditorRef.current) return;
    const start = draftEditorRef.current.selectionStart;
    const end = draftEditorRef.current.selectionEnd;
    if (start === end) { setError('请先选择需要修改的正文。'); return; }
    const instruction = window.prompt('修改要求', '动作更快一些，但不要增加新的攻击。');
    if (!instruction?.trim()) return;
    await perform(async () => {
      await flushLoadedScene();
      const saved = await editSelectedDraft(activeSceneId, { start_offset: start, end_offset: end, user_instruction: instruction.trim() });
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) { draft.currentDraft = saved; draft.currentDraftDirty = false; }
      setCurrentDraft(saved); setCurrentDraftDirty(false);
    });
  }

  async function beginReview() {
    if (!activeSceneId) return;
    await perform(async () => {
      await flushLoadedScene();
      const [diff, marks] = await Promise.all([startSceneReview(activeSceneId), getReviewMarks(activeSceneId)]);
      setReviewDiff(diff); setReviewMarks(marks); setReviewUndo(null); setViewStage('review');
      await refreshStates();
    });
  }

  async function addReviewNote() {
    if (!activeSceneId || !reviewDiff || !reviewTargetRef.current || !reviewSourceRef.current) return;
    const targetStart = reviewTargetRef.current.selectionStart, targetEnd = reviewTargetRef.current.selectionEnd;
    let sourceStart = reviewSourceRef.current.selectionStart, sourceEnd = reviewSourceRef.current.selectionEnd;
    if (sourceStart === sourceEnd && targetStart !== targetEnd) {
      sourceStart = Math.min(targetStart, reviewDiff.source_text.length);
      sourceEnd = Math.min(Math.max(sourceStart + 1, targetEnd), reviewDiff.source_text.length);
    }
    if (targetStart === targetEnd && sourceStart === sourceEnd) { setError('请先在原文或当前稿中选择范围。'); return; }
    const note = window.prompt('添加备注', '这里的动作不能删除。');
    if (!note?.trim()) return;
    await perform(async () => {
      const saved = await createReviewMark(activeSceneId, { source_start_offset: sourceStart, source_end_offset: sourceEnd,
        target_start_offset: targetStart, target_end_offset: targetEnd, user_note: note.trim() });
      setReviewMarks((items) => [...items, saved]);
    });
  }

  function selectedReviewRanges() {
    if (!reviewDiff || !reviewTargetRef.current || !reviewSourceRef.current) return null;
    const targetStart = reviewTargetRef.current.selectionStart, targetEnd = reviewTargetRef.current.selectionEnd;
    let sourceStart = reviewSourceRef.current.selectionStart, sourceEnd = reviewSourceRef.current.selectionEnd;
    if (sourceStart === sourceEnd && targetStart !== targetEnd) { sourceStart = Math.min(targetStart, reviewDiff.source_text.length); sourceEnd = Math.min(targetEnd, reviewDiff.source_text.length); }
    return { targetStart, targetEnd, sourceStart, sourceEnd };
  }

  async function restoreSelectedReview() {
    if (!activeSceneId || !currentDraft || !reviewDiff) return;
    const range = selectedReviewRanges();
    if (!range || range.targetStart === range.targetEnd || range.sourceStart === range.sourceEnd) { setError('请在原文和当前稿中选择对应范围。'); return; }
    const nextText = currentDraft.text.slice(0, range.targetStart) + reviewDiff.source_text.slice(range.sourceStart, range.sourceEnd) + currentDraft.text.slice(range.targetEnd);
    await perform(async () => { const saved = await saveCurrentDraft(activeSceneId, { ...currentDraft, text: nextText }); const draft = loadedDraftRef.current; if (draft?.sceneId === activeSceneId) draft.currentDraft = saved; setCurrentDraft(saved); setReviewDiff(await getReviewDiff(activeSceneId)); });
  }

  async function aiReworkSelected() {
    if (!activeSceneId) return;
    const range = selectedReviewRanges();
    if (!range || range.targetStart === range.targetEnd) { setError('请先在当前稿中选择需要重改的范围。'); return; }
    const instruction = window.prompt('重改要求', '') ?? '';
    await perform(async () => { const result = await reworkReviewRange(activeSceneId, { target_start_offset: range.targetStart, target_end_offset: range.targetEnd, source_start_offset: range.sourceStart, source_end_offset: range.sourceEnd, user_instruction: instruction }); const draft = loadedDraftRef.current; if (draft?.sceneId === activeSceneId) draft.currentDraft = result.draft; setReviewUndo({ beforeText: result.before_text, markIds: result.mark_ids }); setCurrentDraft(result.draft); setReviewDiff(await getReviewDiff(activeSceneId)); });
  }

  async function deleteMark(markId: number) {
    if (!activeSceneId) return;
    await perform(async () => { await removeReviewMark(activeSceneId, markId); setReviewMarks((items) => items.filter((item) => item.id !== markId)); });
  }

  async function restoreMark(mark: ReviewMark) {
    if (!activeSceneId) return;
    await perform(async () => {
      const saved = await restoreReviewSource(activeSceneId, mark.id);
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) draft.currentDraft = saved;
      setCurrentDraft(saved); setReviewMarks(await getReviewMarks(activeSceneId)); setReviewDiff(await getReviewDiff(activeSceneId));
    });
  }

  async function aiReworkMark(mark: ReviewMark) {
    if (!activeSceneId) return;
    const instruction = window.prompt('重改要求（可留空使用备注）', mark.user_note) ?? '';
    await perform(async () => {
      const result = await reworkReviewRange(activeSceneId, { target_start_offset: mark.target_start_offset,
        target_end_offset: mark.target_end_offset, mark_id: mark.id, user_instruction: instruction });
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) draft.currentDraft = result.draft;
      setReviewUndo({ beforeText: result.before_text, markIds: result.mark_ids }); setCurrentDraft(result.draft); setReviewMarks(await getReviewMarks(activeSceneId)); setReviewDiff(await getReviewDiff(activeSceneId));
    });
  }

  async function reworkAllMarks() {
    if (!activeSceneId) return;
    await perform(async () => {
      const result = await reworkAllReviewMarks(activeSceneId);
      if (!result.draft) return;
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) draft.currentDraft = result.draft;
      setReviewUndo({ beforeText: result.before_text, markIds: result.mark_ids }); setCurrentDraft(result.draft); setReviewMarks(await getReviewMarks(activeSceneId)); setReviewDiff(await getReviewDiff(activeSceneId));
    });
  }

  async function undoReviewRework() {
    if (!activeSceneId || reviewUndo === null || !currentDraft) return;
    await perform(async () => {
      const saved = await saveCurrentDraft(activeSceneId, { ...currentDraft, text: reviewUndo.beforeText });
      const draft = loadedDraftRef.current;
      if (draft?.sceneId === activeSceneId) draft.currentDraft = saved;
      setCurrentDraft(saved); setReviewUndo(null); setReviewMarks(await getReviewMarks(activeSceneId)); setReviewDiff(await getReviewDiff(activeSceneId));
    });
  }

  async function acceptReviewRework() {
    if (!activeSceneId || reviewUndo === null) return;
    await perform(async () => {
      if (reviewUndo.markIds.length) setReviewMarks(await adoptReviewRework(activeSceneId, reviewUndo.markIds));
      setReviewUndo(null);
    });
  }

  async function confirmSceneFromReview() {
    if (!activeSceneId) return;
    const unresolved = reviewMarks.filter((item) => !item.resolved).length;
    if (unresolved && !window.confirm(`当前还有 ${unresolved} 条备注，仍然确认？`)) return;
    await perform(async () => { await confirmCreativeScene(activeSceneId); setViewStage('confirmed'); await refreshStates(); });
  }

  async function applyBoundaries() {
    if (!selectedChapterId || !boundaryDrafts.length) return;
    await perform(async () => {
      await flushLoadedScene();
      const items = await adjustChapterScenes(selectedChapterId, boundaryDrafts);
      sceneLoadSequenceRef.current += 1;
      loadedDraftRef.current = null;
      setLoadedSceneId(null);
      setScenes(items);
      setBoundaryDrafts(boundariesFromScenes(items));
      await refreshWorkflowStates(selectedChapterId);
      setBoundaryEditing(false);
    });
  }

  async function confirmBoundaries() {
    if (!selectedChapterId) return;
    await perform(async () => {
      await flushLoadedScene();
      const items = await confirmChapterScenes(selectedChapterId);
      setScenes(items);
      setBoundaryDrafts(boundariesFromScenes(items));
      await refreshWorkflowStates(selectedChapterId);
    });
  }

  return (
    <div className="creative-workspace">
      <header className="creative-topbar">
        <div className="creative-project-title">
          <button className="button ghost" onClick={() => onNavigate('/library')} type="button"><ArrowLeft size={17} />工程列表</button>
          <div><h1>{projectName}</h1><span>{selectedChapter?.title ?? '暂无章节'}</span></div>
        </div>
        <div className="creative-top-actions">
          <button className="button ghost" onClick={() => void openSettings()} type="button"><Settings2 size={17} />工程设置</button>
        </div>
      </header>

      {error ? <div className="inline-alert error creative-alert" role="alert">{error}</div> : null}

      <div className="creative-columns">
        <aside className="chapter-rail" aria-label="章节导航">
          <h2>章节</h2>
          <div className="chapter-only-list">
            {chapters.map((chapter) => {
              const state = stateByChapter.get(chapter.id);
              return (
                <button
                  aria-current={chapter.id === selectedChapterId ? 'page' : undefined}
                  className={chapter.id === selectedChapterId ? 'active' : ''}
                  disabled={busy}
                  key={chapter.id}
                  onClick={() => void chooseChapter(chapter.id)}
                  type="button"
                >
                  <span>{chapter.title}</span>
                  <small>{stageLabels[state?.current_stage ?? 'not_started']}</small>
                </button>
              );
            })}
          </div>
          <div className="rail-save-state">自动保存 · {selectedState ? formatTime(selectedState.updated_at) : '—'}</div>
        </aside>

        <main className="chapter-workspace">
          <header className="chapter-workspace-head">
            <h1>{selectedChapter ? `${chapterNumber(selectedChapter.index)} · ${selectedChapter.title}` : '暂无章节'}</h1>
            <nav className="creative-stage-rail" aria-label="章节创作阶段">
              {stageOrder.map((stage, index) => {
                const disabled = index > Math.max(0, reachedIndex);
                return (
                  <button
                    aria-current={viewStage === stage ? 'step' : undefined}
                    className={`${index < reachedIndex ? 'complete' : ''} ${viewStage === stage ? 'active' : ''}`}
                    disabled={disabled}
                    key={stage}
                    onClick={() => setViewStage(stage)}
                    type="button"
                  >
                    <span />{stageLabels[stage]}
                  </button>
                );
              })}
            </nav>
          </header>

          <section className="scene-list-section">
            <div className="section-title"><h2>场景</h2><span>{scenes.length} 个工作对象</span><button className="button ghost" disabled={!scenes.length || busy} onClick={() => setBoundaryEditing((value) => !value)} type="button">调整场景边界</button></div>
            <div className="creative-scene-list">
              {scenes.map((scene, index) => {
                const active = scene.id === selectedState?.active_scene_id;
                const sceneState = sceneStateById.get(scene.id);
                return (
                  <button className={active ? 'active' : ''} disabled={busy} key={scene.id} onClick={() => void chooseScene(scene.id)} type="button">
                    <span className="scene-number">{String(index + 1).padStart(2, '0')}</span>
                    <span className="scene-name">{scene.title}</span>
                    <small>{sceneProgressLabel(sceneState?.current_stage ?? 'not_started')}{active ? ' · 当前' : ''}</small>
                  </button>
                );
              })}
              {!scenes.length ? <div className="creative-empty"><p>本章尚未生成场景工作对象。</p><button className="button secondary" disabled={busy} onClick={() => void createScenes()} type="button"><Sparkles size={15} />分析并切分</button></div> : null}
            </div>
            {boundaryEditing ? <SceneBoundaryEditor boundaries={boundaryDrafts} busy={busy} onApply={() => void applyBoundaries()} onChange={setBoundaryDrafts} onConfirm={() => void confirmBoundaries()} scenes={scenes} /> : null}
          </section>

          {viewStage === 'preanalysis' ? (
            <PreanalysisEditor analysis={preanalysis} boundariesConfirmed={scenes.find((item) => item.id === activeSceneId)?.user_confirmed ?? false} busy={busy || sceneContextLoading} dirty={analysisDirty} onAnalyze={() => void analyzeScene()} onChange={patchAnalysis} onConfirm={() => void confirmAnalysis()} />
          ) : null}
          {viewStage === 'direction' ? (
            <DirectionEditor intent={intent} busy={busy || sceneContextLoading} onContinue={() => void continueToSpecialAnalysis()} onInstruction={(value) => patchIntent({ user_instruction: value })} onStrategy={chooseStrategy} />
          ) : null}
          {viewStage === 'special_analysis' ? (intent?.strategy === 'faithful' ? <CharacterAnalysisEditor analysis={characterAnalysis} busy={busy || sceneContextLoading} characters={characters} dirty={characterAnalysisDirty} intent={intent} onAnalyze={() => void analyzeCharacterModification()} onChange={patchCharacterAnalysis} onConfirm={() => void confirmCharacterAnalysis()} onEvidence={setFocusedEvidence} onSourceCharacter={setSourceCharacter} onTargetCharacter={setTargetCharacterId} sourceCharacter={sourceCharacter} targetCharacterId={targetCharacterId} /> : <StrategyAnalysisEditor analysis={strategyAnalysis} busy={busy || sceneContextLoading} dirty={strategyAnalysisDirty} intent={intent} onAnalyze={() => void analyzeStrategy()} onChange={patchStrategyAnalysis} onConfirm={() => void confirmGenericAnalysis()} />) : null}
          {viewStage === 'target_design' ? (intent?.strategy === 'faithful' ? <TargetDesignEditor busy={busy || sceneContextLoading} dirty={targetDirty} intent={intent} onChange={patchTarget} onConfirm={() => void confirmTargetDesign()} onGenerate={() => void generateTarget()} target={target} /> : <StrategyTargetEditor busy={busy || sceneContextLoading} dirty={targetDirty} intent={intent} materials={materials} onChange={patchTarget} onConfirm={() => void confirmTargetDesign()} onGenerate={() => void generateTarget()} target={target} />) : null}
          {viewStage === 'writing' ? <WritingStage busy={busy || sceneContextLoading} currentDraft={currentDraft} draftDirty={currentDraftDirty} draftEditorRef={draftEditorRef} onDraftText={patchCurrentDraftText} onGenerate={() => void generateDraft()} onPlan={patchWritingPlan} onPlanWriting={() => void planWriting()} onReview={() => void beginReview()} onSelectedEdit={() => void aiEditSelection()} onView={setWritingView} plan={writingPlan} planDirty={writingPlanDirty} target={target} view={writingView} /> : null}
          {viewStage === 'review' ? <ReviewStage busy={busy || sceneContextLoading} currentDraft={currentDraft} diff={reviewDiff} onAccept={() => void acceptReviewRework()} onAddNote={() => void addReviewNote()} onConfirm={() => void confirmSceneFromReview()} onRestore={() => void restoreSelectedReview()} onRework={() => void aiReworkSelected()} onReworkAll={() => void reworkAllMarks()} onUndo={() => void undoReviewRework()} sourceRef={reviewSourceRef} targetRef={reviewTargetRef} undoAvailable={reviewUndo !== null} /> : null}
          {!['preanalysis', 'direction', 'special_analysis', 'target_design', 'writing', 'review'].includes(viewStage) ? <section className="stage-placeholder"><h2>{stageLabels[viewStage]}</h2><p>场景已确认。</p></section> : null}
        </main>

        <aside className="creative-context-panel">
          <h2>{viewStage === 'review' ? '备注' : '当前上下文'}</h2>
          {viewStage === 'direction' ? <ContextResources characters={characters} intent={intent} materials={materials} onIntent={patchIntent} /> : null}
          {viewStage === 'special_analysis' ? (intent?.strategy === 'faithful' ? <CharacterContext characters={characters} targetId={characterAnalysis?.target_character_card_id ?? targetCharacterId} /> : <SelectedMaterials intent={intent} materials={materials} />) : null}
          {viewStage === 'target_design' ? <><CharacterContext characters={characters} targetId={characterAnalysis?.target_character_card_id ?? targetCharacterId} /><SelectedMaterials intent={intent} materials={materials} /></> : null}
          {viewStage === 'writing' ? <><CharacterContext characters={characters} targetId={characterAnalysis?.target_character_card_id ?? targetCharacterId} /><SelectedMaterials intent={intent} materials={materials} /><TargetContext target={target} /></> : null}
          {viewStage === 'review' ? <ReviewMarksPanel marks={reviewMarks} onDelete={(mark) => void deleteMark(mark.id)} onRestore={(mark) => void restoreMark(mark)} onRework={(mark) => void aiReworkMark(mark)} /> : null}
          {viewStage !== 'review' ? <><h3>原文</h3>{focusedEvidence ? <div className="focused-evidence"><strong>当前证据</strong><p>{focusedEvidence}</p></div> : null}<div className="source-context">{scenes.find((item) => item.id === activeSceneId)?.original_text || selectedChapter?.original_text || '暂无原文'}</div></> : null}
        </aside>
      </div>
      {settingsOpen ? <div className="settings-backdrop" role="presentation"><section aria-label="工程设置" className="creative-settings-panel" role="dialog"><header><div><h2>工程设置</h2><p>AI 配置</p></div><button className="button ghost" onClick={() => setSettingsOpen(false)} type="button">关闭</button></header><label><span>默认模型</span><select value={settingsModelId ?? ''} onChange={(event) => setSettingsModelId(event.target.value ? Number(event.target.value) : null)}><option value="">使用全局默认模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label><label className="settings-master-field"><span>总提示词</span><textarea value={masterPrompt} onChange={(event) => { setMasterPrompt(event.target.value); setMasterDirty(true); }} /></label><footer><button className="button secondary" onClick={() => void exportMaster()} type="button">导出到提示词库</button><button className="button primary" disabled={busy || (!masterDirty && settingsModelId === null)} onClick={() => void saveSettings()} type="button">保存设置</button></footer></section></div> : null}
    </div>
  );
}

function PreanalysisEditor({ analysis, boundariesConfirmed, busy, dirty, onAnalyze, onChange, onConfirm }: { analysis: BaseSceneAnalysis | null; boundariesConfirmed: boolean; busy: boolean; dirty: boolean; onAnalyze: () => void; onChange: (patch: Partial<BaseSceneAnalysis>) => void; onConfirm: () => void }) {
  if (!analysis) return <section className="stage-placeholder stage-action-empty"><h2>预分析</h2><p>轻量判断这是什么场景，不在这里生成完整人物状态或改写方案。</p>{!boundariesConfirmed ? <p className="inline-hint">请先确认场景切分，再运行预分析。</p> : null}<button className="button primary" disabled={busy || !boundariesConfirmed} onClick={onAnalyze} type="button"><Sparkles size={16} />运行预分析</button></section>;
  return <section className="analysis-editor"><div className="analysis-editor-head"><div><h2>预分析</h2><span>{dirty ? '正在自动保存…' : analysis.status === 'confirmed' ? '已确认' : '已自动保存'}</span></div><button className="button secondary" disabled={busy} onClick={onAnalyze} type="button"><RefreshCw size={15} />重新分析</button></div><label><span>摘要</span><textarea value={analysis.summary} onChange={(event) => onChange({ summary: event.target.value })} /></label><div className="analysis-fields"><label><span>人物（每行一个）</span><textarea value={analysis.characters.join('\n')} onChange={(event) => onChange({ characters: lines(event.target.value) })} /></label><label><span>基础事件（每行一个）</span><textarea value={analysis.basic_events.join('\n')} onChange={(event) => onChange({ basic_events: lines(event.target.value) })} /></label></div><div className="analysis-meta-fields"><label><span>地点</span><input value={analysis.location} onChange={(event) => onChange({ location: event.target.value })} /></label><label><span>时间</span><input value={analysis.time} onChange={(event) => onChange({ time: event.target.value })} /></label><label><span>场景类型</span><input value={analysis.scene_type} onChange={(event) => onChange({ scene_type: event.target.value })} /></label></div><div className="analysis-actions"><button className="button primary" disabled={busy || dirty} onClick={onConfirm} type="button"><Check size={16} />确认预分析</button></div></section>;
}

const strategies: Array<{ key: CreativeStrategy; label: string; description: string }> = [
  { key: 'faithful', label: '贴合原文', description: '保留主要事件与作用，只调整指定对象。' },
  { key: 'plot_adjust', label: '调整剧情', description: '修改现有剧情走向或关键事件。' },
  { key: 'expansion', label: '增加剧情', description: '在原有场景中加入新的事件材料。' },
  { key: 'reimagine', label: '重新构思', description: '以当前 Source 为参照重新设计场景。' },
];

function DirectionEditor({ busy, intent, onContinue, onInstruction, onStrategy }: { busy: boolean; intent: CreativeIntent | null; onContinue: () => void; onInstruction: (value: string) => void; onStrategy: (strategy: CreativeStrategy) => void }) {
  return <section className="direction-editor"><h2>怎样处理这个场景？</h2><div className="strategy-grid">{strategies.map((item) => <button aria-pressed={intent?.strategy === item.key} className={intent?.strategy === item.key ? 'active' : ''} key={item.key} onClick={() => onStrategy(item.key)} type="button"><strong>{item.label}</strong><span>{item.description}</span></button>)}</div><label className="instruction-field"><span>具体要求</span><textarea disabled={!intent} placeholder="例如：把张三替换成李四，战斗过程尽量保留。" value={intent?.user_instruction ?? ''} onChange={(event) => onInstruction(event.target.value)} /></label><div className="analysis-actions"><button className="button primary" disabled={busy || !intent || !intent.user_instruction.trim()} onClick={onContinue} type="button">进入专项分析</button></div></section>;
}

const analysisCategories = [
  ['explicit_mentions', '显式关联'], ['implicit_references', '隐式指代'],
  ['actions', '人物行为'], ['dialogue', '人物对白'], ['states', '人物状态'],
  ['objects', '持有物 / 武器'], ['spatial_relations', '空间关系'],
  ['related_events', '关联剧情事件'], ['target_character_conflicts', '与目标人物卡的差异'],
] as const;
type AnalysisCategory = typeof analysisCategories[number][0];

function CharacterAnalysisEditor({ analysis, busy, characters, dirty, intent, onAnalyze, onChange, onConfirm, onEvidence, onSourceCharacter, onTargetCharacter, sourceCharacter, targetCharacterId }: { analysis: CharacterModificationAnalysis | null; busy: boolean; characters: CharacterCard[]; dirty: boolean; intent: CreativeIntent | null; onAnalyze: () => void; onChange: (value: CharacterModificationAnalysis) => void; onConfirm: () => void; onEvidence: (text: string) => void; onSourceCharacter: (value: string) => void; onTargetCharacter: (value: number | null) => void; sourceCharacter: string; targetCharacterId: number | null }) {
  if (intent?.strategy !== 'faithful') return <section className="stage-placeholder"><h2>专项分析</h2><p>第一阶段只完整接通“贴合原文 → 人物修改”。其他创作方向将在下一阶段实现。</p></section>;
  const availableTargets = intent.selected_character_ids.length ? characters.filter((item) => intent.selected_character_ids.includes(item.id)) : characters;
  if (!analysis) return <section className="analysis-editor character-analysis-setup"><div><h2>贴合原文 / 人物修改</h2><p>识别 Source 中与原人物有关的显式、隐式和行为关联，再对照目标人物卡列出差异。</p></div><div className="analysis-meta-fields"><label><span>Source 人物</span><input value={sourceCharacter} onChange={(event) => onSourceCharacter(event.target.value)} /></label><label><span>目标人物卡</span><select value={targetCharacterId ?? ''} onChange={(event) => onTargetCharacter(event.target.value ? Number(event.target.value) : null)}><option value="">请选择</option>{availableTargets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><div className="analysis-actions"><button className="button primary" disabled={busy || !sourceCharacter.trim() || !targetCharacterId} onClick={onAnalyze} type="button"><Sparkles size={16} />运行人物专项分析</button></div></section>;

  function updateItem(category: AnalysisCategory, id: string, patch: Partial<CharacterAnalysisItem>) {
    if (!analysis) return;
    onChange({ ...analysis, [category]: analysis[category].map((item) => item.id === id ? { ...item, ...patch } : item) });
  }
  function removeItem(category: AnalysisCategory, id: string) {
    if (!analysis) return;
    onChange({ ...analysis, [category]: analysis[category].filter((item) => item.id !== id) });
  }
  function addItem(category: AnalysisCategory) {
    if (!analysis) return;
    onChange({ ...analysis, [category]: [...analysis[category], { id: `${category}-${Date.now()}`, summary: '', source_text: '', start_offset: 0, end_offset: 0, inferred: category === 'implicit_references' }] });
  }

  return <section className="character-analysis-editor"><header><div><h2>贴合原文 / 人物修改</h2><p>{analysis.source_character} → {analysis.target_character_name}</p></div><span>{dirty ? '正在自动保存…' : analysis.status === 'stale' ? '上游已修改，需要重新分析' : analysis.status === 'confirmed' ? '已确认' : '已自动保存'}</span></header>{analysisCategories.map(([category, label]) => <details key={category} open={analysis[category].length > 0}><summary><span>{label}</span><small>{analysis[category].length} 项</small></summary><div className="analysis-item-list">{analysis[category].map((item) => <article key={item.id}><div className="analysis-item-toolbar"><label><input checked={item.inferred} onChange={(event) => updateItem(category, item.id, { inferred: event.target.checked })} type="checkbox" />推断</label><button className="button ghost" onClick={() => onEvidence(item.source_text)} type="button">查看原文</button><button className="button ghost danger-quiet" onClick={() => removeItem(category, item.id)} type="button">删除</button></div><label><span>结论</span><input value={item.summary} onChange={(event) => updateItem(category, item.id, { summary: event.target.value })} /></label><label><span>对应原文</span><textarea value={item.source_text} onChange={(event) => updateItem(category, item.id, { source_text: event.target.value, start_offset: 0, end_offset: 0 })} /></label>{category === 'target_character_conflicts' ? <div className="conflict-fields"><label><span>原文状态</span><input value={item.source_state ?? ''} onChange={(event) => updateItem(category, item.id, { source_state: event.target.value })} /></label><label><span>目标人物卡</span><input value={item.target_state ?? ''} onChange={(event) => updateItem(category, item.id, { target_state: event.target.value })} /></label><label><span>差异</span><input value={item.difference ?? ''} onChange={(event) => updateItem(category, item.id, { difference: event.target.value })} /></label></div> : null}</article>)}<button className="button secondary add-analysis-item" onClick={() => addItem(category)} type="button"><PlusIcon />补充一项</button></div></details>)}<footer><button className="button secondary" disabled={busy} onClick={onAnalyze} type="button"><RefreshCw size={15} />重新分析</button><button className="button primary" disabled={busy || dirty || analysis.status === 'stale'} onClick={onConfirm} type="button"><Check size={16} />确认分析</button></footer></section>;
}

function CharacterContext({ characters, targetId }: { characters: CharacterCard[]; targetId: number | null }) {
  const target = characters.find((item) => item.id === targetId);
  if (!target) return <><h3>人物</h3><div className="creative-empty">尚未选择目标人物卡。</div></>;
  return <><h3>人物</h3><div className="character-context-card"><strong>{target.name}</strong><p>{target.setting_text || target.description || '暂无人物设定'}</p>{target.personality ? <small>性格：{target.personality}</small> : null}{target.action_constraints ? <small>行动约束：{target.action_constraints}</small> : null}</div></>;
}

function TargetDesignEditor({ busy, dirty, intent, onChange, onConfirm, onGenerate, target }: { busy: boolean; dirty: boolean; intent: CreativeIntent | null; onChange: (value: SceneTarget) => void; onConfirm: () => void; onGenerate: () => void; target: SceneTarget | null }) {
  if (intent?.strategy !== 'faithful') return <section className="stage-placeholder"><h2>目标设计</h2><p>当前方向的目标结构将在对应 strategy 批次接入。</p></section>;
  if (!target) return <section className="stage-placeholder stage-action-empty"><h2>目标设计</h2><p>根据 Source、已确认专项分析、人物卡和用户资源生成可编辑 ChangeSet。AI 只生成草案，不会自动确认。</p><button className="button primary" disabled={busy} onClick={onGenerate} type="button"><Sparkles size={16} />生成目标草案</button></section>;
  const currentTarget = target;
  const items = currentTarget.design.items ?? [];
  function replaceItem(id: string, patch: Partial<ChangeSetItem>) {
    onChange({ ...currentTarget, design: { ...currentTarget.design, items: items.map((item) => item.id === id ? { ...item, ...patch } : item) } });
  }
  function addItem() {
    onChange({ ...currentTarget, design: { ...currentTarget.design, items: [...items, { id: `change-${Date.now()}`, label: '', operation: 'preserve', source_value: '', target_value: '', source_start_offset: 0, source_end_offset: 0 }] } });
  }
  return <section className="target-editor"><header><div><h2>贴合原文 / ChangeSet</h2><p>{target.status === 'stale' ? '专项分析已修改，需要重新生成目标草案' : dirty ? '正在自动保存…' : target.status === 'confirmed' ? '已确认' : '草案已自动保存'}</p></div><button className="button secondary" disabled={busy} onClick={onGenerate} type="button"><RefreshCw size={15} />重新生成目标草案</button></header><div className="target-item-list">{items.map((item) => <article key={item.id}><input aria-label="目标项名称" placeholder="目标项" value={item.label} onChange={(event) => replaceItem(item.id, { label: event.target.value })} /><select aria-label={`${item.label || '目标项'}操作`} value={item.operation} onChange={(event) => replaceItem(item.id, { operation: event.target.value as ChangeSetItem['operation'] })}><option value="preserve">保持</option><option value="adapt">适配</option><option value="modify">修改</option></select><input aria-label={`${item.label || '目标项'}原值`} placeholder="Source" value={item.source_value} onChange={(event) => replaceItem(item.id, { source_value: event.target.value })} /><span>→</span><input aria-label={`${item.label || '目标项'}目标值`} disabled={item.operation === 'preserve'} placeholder={item.operation === 'adapt' ? '适配要求' : '目标值'} value={item.target_value} onChange={(event) => replaceItem(item.id, { target_value: event.target.value })} /><button className="button ghost danger-quiet" onClick={() => onChange({ ...target, design: { ...target.design, items: items.filter((entry) => entry.id !== item.id) } })} type="button">删除</button></article>)}</div><button className="button secondary add-target-item" onClick={addItem} type="button">＋ 添加目标项</button><div className="target-summary"><h3>本次目标</h3><textarea value={(target.design.summary ?? []).join('\n')} onChange={(event) => onChange({ ...target, design: { ...target.design, summary: lines(event.target.value) } })} /></div><footer><button className="button primary" disabled={busy || dirty || target.status === 'stale' || items.length === 0} onClick={onConfirm} type="button"><Check size={16} />确认目标</button></footer></section>;
}

const plotAnalysisFields = [
  ['source_events','Source 事件'], ['causal_links','因果关系'], ['participants','参与人物'],
  ['preconditions','前置条件'], ['downstream_dependencies','下游依赖'], ['affected_events','受影响事件'],
] as const;
const expansionAnalysisFields = [
  ['entry_state','进入状态'], ['exit_constraints','退出约束'], ['character_relations','人物关系'],
  ['active_events','当前事件'], ['unresolved_goals','未解决目标'], ['available_hooks','可用钩子'],
] as const;
const reimagineAnalysisFields = [
  ['initial_state','开始状态'], ['required_characters','必须人物'], ['location','地点'], ['time','时间'],
  ['inherited_facts','继承事实'], ['required_end_state','必须结束状态'], ['downstream_constraints','下游约束'],
] as const;

function StrategyAnalysisEditor({ analysis, busy, dirty, intent, onAnalyze, onChange, onConfirm }: { analysis: StrategySceneAnalysis | null; busy: boolean; dirty: boolean; intent: CreativeIntent | null; onAnalyze: () => void; onChange: (value: StrategySceneAnalysis) => void; onConfirm: () => void }) {
  if (!intent) return <section className="stage-placeholder"><h2>专项分析</h2><p>请先选择创作方向。</p></section>;
  if (!analysis) return <section className="stage-placeholder stage-action-empty"><h2>{strategies.find((item) => item.key === intent.strategy)?.label} / 专项分析</h2><p>{intent.strategy === 'plot_adjust' ? '分析 Source 当前剧情结构与受用户要求影响的事件，不在这里提出改法。' : '分析当前 Source 的策略边界。'}</p><button className="button primary" disabled={busy} onClick={onAnalyze} type="button"><Sparkles size={16} />运行专项分析</button></section>;
  const currentAnalysis = analysis;
  const fields = intent.strategy === 'plot_adjust' ? plotAnalysisFields : intent.strategy === 'expansion' ? expansionAnalysisFields : reimagineAnalysisFields;
  function fieldLines(key: string) { const value = currentAnalysis.analysis[key]; if (typeof value === 'string') return [value]; return Array.isArray(value) ? value.map((item) => typeof item === 'string' ? item : String((item as Record<string, unknown>).summary ?? (item as Record<string, unknown>).id ?? '')).filter(Boolean) : []; }
  return <section className="strategy-analysis-editor"><header><div><h2>{strategies.find((item) => item.key === analysis.strategy)?.label} / 专项分析</h2><p>{analysis.status === 'stale' ? '上游已修改，需要重新分析' : dirty ? '正在自动保存…' : analysis.status === 'confirmed' ? '已确认' : '分析草案已保存'}</p></div><button className="button secondary" disabled={busy} onClick={onAnalyze} type="button"><RefreshCw size={15} />重新分析</button></header><div className="strategy-analysis-fields">{fields.map(([key,label]) => <label key={key}><span>{label}</span><textarea value={fieldLines(key).join('\n')} onChange={(event) => onChange({ ...analysis, analysis: { ...analysis.analysis, [key]: key === 'location' || key === 'time' ? event.target.value : lines(event.target.value) } })} /></label>)}</div><footer><button className="button primary" disabled={busy || dirty || analysis.status === 'stale'} onClick={onConfirm} type="button"><Check size={16} />确认分析</button></footer></section>;
}

type SkeletonNode = { id: string; order: number; summary: string; participants: string[]; outcome: string; source_relation: 'inherited' | 'modified' | 'inserted' };
type SourceMapping = { source_event_id: string; target_node_id: string | null };
function StrategyTargetEditor({ busy, dirty, intent, materials, onChange, onConfirm, onGenerate, target }: { busy: boolean; dirty: boolean; intent: CreativeIntent | null; materials: Material[]; onChange: (value: SceneTarget) => void; onConfirm: () => void; onGenerate: () => void; target: SceneTarget | null }) {
  if (intent?.strategy === 'expansion') return <ExpansionTargetEditor busy={busy} dirty={dirty} intent={intent} materials={materials} onChange={onChange} onConfirm={onConfirm} onGenerate={onGenerate} target={target} />;
  if (intent?.strategy === 'reimagine') return <ReimagineTargetEditor busy={busy} dirty={dirty} onChange={onChange} onConfirm={onConfirm} onGenerate={onGenerate} target={target} />;
  if (intent?.strategy !== 'plot_adjust') return <section className="stage-placeholder"><h2>目标设计</h2><p>该 strategy 的目标结构将在对应批次接入。</p></section>;
  if (!target) return <section className="stage-placeholder stage-action-empty"><h2>调整剧情 / TargetSkeleton</h2><p>以结构化列表设计目标剧情；支持 AI 草案、手工编辑与剧情素材插入。</p><button className="button primary" disabled={busy} onClick={onGenerate} type="button"><Sparkles size={16} />AI 生成草案</button></section>;
  const currentTarget = target;
  const currentIntent = intent;
  const nodes = (Array.isArray(currentTarget.design.nodes) ? currentTarget.design.nodes : []) as SkeletonNode[];
  const sourceMapping = (Array.isArray(currentTarget.design.source_mapping) ? currentTarget.design.source_mapping : []) as SourceMapping[];
  function setNodes(next: SkeletonNode[]) {
    const ids = new Set(next.map((node) => node.id));
    onChange({
      ...currentTarget,
      design: {
        ...currentTarget.design,
        nodes: next.map((node,index) => ({ ...node, order: index + 1 })),
        source_mapping: sourceMapping.map((item) => item.target_node_id && !ids.has(item.target_node_id) ? { ...item, target_node_id: null } : item),
      },
    });
  }
  function setSourceMapping(next: SourceMapping[]) { onChange({ ...currentTarget, design: { ...currentTarget.design, source_mapping: next } }); }
  function patchNode(id: string, patch: Partial<SkeletonNode>) { setNodes(nodes.map((node) => node.id === id ? { ...node, ...patch } : node)); }
  function move(index: number, offset: number) { const next = [...nodes]; const destination = index + offset; if (destination < 0 || destination >= next.length) return; [next[index], next[destination]] = [next[destination], next[index]]; setNodes(next); }
  function insertMaterial() { const material = materials.find((item) => currentIntent.selected_plot_material_ids.includes(item.id)); const stages = material?.content.stages; const first = Array.isArray(stages) ? stages[0] as Record<string, unknown> : null; setNodes([...nodes, { id: `material-${Date.now()}`, order: nodes.length + 1, summary: String(first?.summary ?? material?.description ?? material?.name ?? '素材节点'), participants: [], outcome: '', source_relation: 'inserted' }]); }
  return <section className="strategy-target-editor"><header><div><h2>调整剧情 / TargetSkeleton</h2><p>{target.status === 'stale' ? '专项分析已修改，需要重新生成' : dirty ? '正在自动保存…' : '结构化目标草案'}</p></div><button className="button secondary" disabled={busy} onClick={onGenerate} type="button"><RefreshCw size={15} />AI 生成草案</button></header><div className="skeleton-node-list">{nodes.map((node,index) => <article key={node.id}><span>{String(index+1).padStart(2,'0')}</span><input aria-label={`节点 ${index+1} 摘要`} value={node.summary} onChange={(event) => patchNode(node.id,{summary:event.target.value})} /><input aria-label={`节点 ${index+1} 参与人物`} placeholder="参与人物，用 / 分隔" value={node.participants.join(' / ')} onChange={(event) => patchNode(node.id,{participants:event.target.value.split('/').map((item)=>item.trim()).filter(Boolean)})} /><input aria-label={`节点 ${index+1} 结果`} placeholder="结果" value={node.outcome} onChange={(event) => patchNode(node.id,{outcome:event.target.value})} /><select value={node.source_relation} onChange={(event) => patchNode(node.id,{source_relation:event.target.value as SkeletonNode['source_relation']})}><option value="inherited">继承</option><option value="modified">修改</option><option value="inserted">新增</option></select><div><button className="button ghost" onClick={() => move(index,-1)} type="button">上移</button><button className="button ghost" onClick={() => move(index,1)} type="button">下移</button><button className="button ghost danger-quiet" onClick={() => setNodes(nodes.filter((item)=>item.id!==node.id))} type="button">删除</button></div></article>)}</div><div className="source-mapping-list"><h3>Source → Target 映射</h3>{sourceMapping.map((mapping) => <label key={mapping.source_event_id}><span>{mapping.source_event_id}</span><select aria-label={`${mapping.source_event_id} 映射`} value={mapping.target_node_id ?? ''} onChange={(event) => setSourceMapping(sourceMapping.map((item) => item.source_event_id === mapping.source_event_id ? { ...item, target_node_id: event.target.value || null } : item))}><option value="">删除此 Source 事件</option>{nodes.filter((node) => node.source_relation !== 'inserted').map((node) => <option key={node.id} value={node.id}>{node.summary || node.id}</option>)}</select></label>)}</div><div className="strategy-target-actions"><button className="button secondary" onClick={() => setNodes([...nodes,{id:`node-${Date.now()}`,order:nodes.length+1,summary:'',participants:[],outcome:'',source_relation:'inserted'}])} type="button">＋ 新增节点</button><button className="button secondary" disabled={!intent.selected_plot_material_ids.length} onClick={insertMaterial} type="button">从剧情素材插入</button><button className="button primary" disabled={busy || dirty || target.status === 'stale' || !nodes.length || !sourceMapping.length} onClick={onConfirm} type="button">确认目标</button></div></section>;
}

type InsertionEvent = { id: string; order: number; summary: string };
function ExpansionTargetEditor({ busy, dirty, intent, materials, onChange, onConfirm, onGenerate, target }: { busy: boolean; dirty: boolean; intent: CreativeIntent; materials: Material[]; onChange: (value: SceneTarget) => void; onConfirm: () => void; onGenerate: () => void; target: SceneTarget | null }) {
  if (!target) return <section className="stage-placeholder stage-action-empty"><h2>增加剧情 / InsertionBlock</h2><p>只设计插入点、新事件与退出约束，不复制整个场景骨架。</p><button className="button primary" disabled={busy} onClick={onGenerate} type="button"><Sparkles size={16} />AI 生成草案</button></section>;
  const current = target;
  const events = (Array.isArray(current.design.new_events) ? current.design.new_events : []) as InsertionEvent[];
  const exitConstraints = Array.isArray(current.design.exit_constraints) ? current.design.exit_constraints.map(String) : [];
  function patchDesign(patch: Record<string, unknown>) { onChange({ ...current, design: { ...current.design, ...patch } }); }
  function setEvents(next: InsertionEvent[]) { patchDesign({ new_events: next.map((item,index)=>({...item,order:index+1})) }); }
  function insertMaterial() { const material=materials.find((item)=>intent.selected_plot_material_ids.includes(item.id)); const stages=material?.content.stages; const stage=Array.isArray(stages)?stages[0] as Record<string,unknown>:null; setEvents([...events,{id:`material-${Date.now()}`,order:events.length+1,summary:String(stage?.summary??material?.description??material?.name??'素材事件')}]); }
  return <section className="strategy-target-editor expansion-target-editor"><header><div><h2>增加剧情 / InsertionBlock</h2><p>{target.status==='stale'?'专项分析已修改，需要重新生成':dirty?'正在自动保存…':'局部插入目标'}</p></div><button className="button secondary" disabled={busy} onClick={onGenerate} type="button"><RefreshCw size={15}/>AI 生成草案</button></header><div className="insertion-boundaries"><label><span>插在之后</span><input value={String(current.design.insert_after??'')} onChange={(event)=>patchDesign({insert_after:event.target.value})}/></label><label><span>插在之前</span><input value={String(current.design.insert_before??'')} onChange={(event)=>patchDesign({insert_before:event.target.value})}/></label><label><span>进入状态</span><textarea value={(Array.isArray(current.design.entry_state)?current.design.entry_state.map(String):[]).join('\n')} onChange={(event)=>patchDesign({entry_state:lines(event.target.value)})}/></label></div><div className="insertion-event-list">{events.map((item,index)=><article key={item.id}><span>N{index+1}</span><input value={item.summary} onChange={(event)=>setEvents(events.map((entry)=>entry.id===item.id?{...entry,summary:event.target.value}:entry))}/><button className="button ghost danger-quiet" onClick={()=>setEvents(events.filter((entry)=>entry.id!==item.id))} type="button">删除</button></article>)}</div><div className="insertion-exit"><label><span>退出约束（必须可见、可编辑）</span><textarea value={exitConstraints.join('\n')} onChange={(event)=>patchDesign({exit_constraints:lines(event.target.value)})}/></label></div><div className="strategy-target-actions"><button className="button secondary" onClick={()=>setEvents([...events,{id:`event-${Date.now()}`,order:events.length+1,summary:''}])} type="button">＋ 新增事件</button><button className="button secondary" disabled={!intent.selected_plot_material_ids.length} onClick={insertMaterial} type="button">从剧情骨架素材生成</button><button className="button primary" disabled={busy||dirty||target.status==='stale'||!events.length||!exitConstraints.length} onClick={onConfirm} type="button">确认目标</button></div></section>;
}

const boundaryFields = [['required_characters','人物'],['location','地点'],['time','时间'],['initial_state','开始状态'],['inherited_facts','继承事实'],['required_end_state','必须结束'],['downstream_constraints','下游约束']] as const;
function ReimagineTargetEditor({ busy, dirty, onChange, onConfirm, onGenerate, target }: { busy: boolean; dirty: boolean; onChange: (value: SceneTarget) => void; onConfirm: () => void; onGenerate: () => void; target: SceneTarget | null }) {
  if (!target) return <section className="stage-placeholder stage-action-empty"><h2>重新构思 / BoundaryConditions + TargetSkeleton</h2><p>先锁定必须继承和必须结束的边界，再设计新目标骨架。</p><button className="button primary" disabled={busy} onClick={onGenerate} type="button"><Sparkles size={16}/>AI 生成草案</button></section>;
  const current=target; const boundary=(current.design.boundary_conditions??{}) as Record<string,unknown>; const nodes=(Array.isArray(current.design.nodes)?current.design.nodes:[]) as SkeletonNode[];
  function patchBoundary(key:string,value:unknown){onChange({...current,design:{...current.design,boundary_conditions:{...boundary,[key]:value}}});}
  function setNodes(next:SkeletonNode[]){onChange({...current,design:{...current.design,nodes:next.map((node,index)=>({...node,order:index+1}))}});}
  function move(index:number,offset:number){const next=[...nodes],destination=index+offset;if(destination<0||destination>=next.length)return;[next[index],next[destination]]=[next[destination],next[index]];setNodes(next);}
  return <section className="strategy-target-editor reimagine-target-editor"><header><div><h2>重新构思 / BoundaryConditions + TargetSkeleton</h2><p>{target.status==='stale'?'专项分析已修改，需要重新生成':dirty?'正在自动保存…':'边界与目标骨架'}</p></div><button className="button secondary" disabled={busy} onClick={onGenerate} type="button"><RefreshCw size={15}/>AI 生成草案</button></header><div className="boundary-condition-grid">{boundaryFields.map(([key,label])=>{const raw=boundary[key];const value=Array.isArray(raw)?raw.map(String).join('\n'):String(raw??'');return <label key={key}><span>{label}</span><textarea value={value} onChange={(event)=>patchBoundary(key,key==='location'||key==='time'?event.target.value:lines(event.target.value))}/></label>;})}</div><div className="skeleton-node-list">{nodes.map((node,index)=><article key={node.id}><span>{String(index+1).padStart(2,'0')}</span><input value={node.summary} onChange={(event)=>setNodes(nodes.map((item)=>item.id===node.id?{...item,summary:event.target.value}:item))}/><input value={node.participants.join(' / ')} onChange={(event)=>setNodes(nodes.map((item)=>item.id===node.id?{...item,participants:event.target.value.split('/').map((x)=>x.trim()).filter(Boolean)}:item))}/><input value={node.outcome} onChange={(event)=>setNodes(nodes.map((item)=>item.id===node.id?{...item,outcome:event.target.value}:item))}/><select value={node.source_relation} onChange={(event)=>setNodes(nodes.map((item)=>item.id===node.id?{...item,source_relation:event.target.value as SkeletonNode['source_relation']}:item))}><option value="inherited">继承</option><option value="modified">修改</option><option value="inserted">新增</option></select><div><button className="button ghost" onClick={()=>move(index,-1)} type="button">上移</button><button className="button ghost" onClick={()=>move(index,1)} type="button">下移</button><button className="button ghost danger-quiet" onClick={()=>setNodes(nodes.filter((item)=>item.id!==node.id))} type="button">删除</button></div></article>)}</div><div className="strategy-target-actions"><button className="button secondary" onClick={()=>setNodes([...nodes,{id:`node-${Date.now()}`,order:nodes.length+1,summary:'',participants:[],outcome:'',source_relation:'inserted'}])} type="button">＋ 新增节点</button><button className="button primary" disabled={busy||dirty||target.status==='stale'||!nodes.length||!String(boundary.location??'').trim()} onClick={onConfirm} type="button">确认目标</button></div></section>;
}

const writingOperationLabels = { preserve: '保留', transform: '局部修改', rewrite: '重写', insert: '新增', delete: '删除' } as const;

function WritingStage({ busy, currentDraft, draftDirty, draftEditorRef, onDraftText, onGenerate, onPlan, onPlanWriting, onReview, onSelectedEdit, onView, plan, planDirty, target, view }: { busy: boolean; currentDraft: SceneDraft | null; draftDirty: boolean; draftEditorRef: RefObject<HTMLTextAreaElement>; onDraftText: (text: string) => void; onGenerate: () => void; onPlan: (value: WritingPlan) => void; onPlanWriting: () => void; onReview: () => void; onSelectedEdit: () => void; onView: (view: 'plan' | 'draft') => void; plan: WritingPlan | null; planDirty: boolean; target: SceneTarget | null; view: 'plan' | 'draft' }) {
  const staleDraft = Boolean(currentDraft && (
    currentDraft.status === 'stale'
    || target?.status === 'stale'
    || plan?.status === 'stale'
    || currentDraft.based_on_plan_id !== plan?.id
    || currentDraft.based_on_target_id !== target?.id
  ));
  return <section className="writing-stage"><nav><button aria-pressed={view === 'plan'} onClick={() => onView('plan')} type="button">写作规划</button><button aria-pressed={view === 'draft'} disabled={!currentDraft} onClick={() => onView('draft')} type="button">当前正文</button></nav>{view === 'plan' ? <WritingPlanEditor busy={busy} dirty={planDirty} onChange={onPlan} onGenerate={onGenerate} onPlan={onPlanWriting} plan={plan} /> : <div className="current-draft-editor"><header><div><h2>当前正文</h2><p>{draftDirty ? '正在自动保存…' : '已自动保存'}{staleDraft ? ' · 当前正文基于旧目标/旧规划生成' : ''}</p></div><div><button className="button secondary" disabled={busy || !currentDraft} onClick={onSelectedEdit} type="button"><Sparkles size={15} />AI 修改选中内容</button><button className="button secondary" disabled={busy || !plan || plan.status === 'stale'} onClick={onGenerate} type="button">重新生成</button><button className="button primary" disabled={busy || !currentDraft || draftDirty} onClick={onReview} type="button">进入审查</button></div></header>{currentDraft ? <textarea aria-label="当前正文" ref={draftEditorRef} value={currentDraft.text} onChange={(event) => onDraftText(event.target.value)} /> : <div className="stage-action-empty"><p>尚未生成当前正文。</p></div>}</div>}</section>;
}

function WritingPlanEditor({ busy, dirty, onChange, onGenerate, onPlan, plan }: { busy: boolean; dirty: boolean; onChange: (value: WritingPlan) => void; onGenerate: () => void; onPlan: () => void; plan: WritingPlan | null }) {
  if (!plan) return <div className="stage-placeholder stage-action-empty"><h2>写作规划</h2><p>规划 Source 正文的语义区块操作；Target 已回答“改成什么”，此处只决定具体位置怎么操作。</p><button className="button primary" disabled={busy} onClick={onPlan} type="button"><Sparkles size={16} />生成写作规划</button></div>;
  const currentPlan = plan;
  function patchBlock(id: number, patch: Partial<WritingBlock>) { onChange({ ...currentPlan, blocks: currentPlan.blocks.map((block) => block.id === id ? { ...block, ...patch } : block) }); }
  return <div className="writing-plan-editor"><header><div><h2>写作规划</h2><p>{plan.status === 'stale' ? 'Target 已修改，需要重新规划' : dirty ? '正在自动保存…' : '规划已就绪'}</p></div><button className="button secondary" disabled={busy} onClick={onPlan} type="button"><RefreshCw size={15} />重新规划</button></header><div className="coverage-row">{(['preserve','transform','rewrite','insert'] as const).map((operation) => <span key={operation}><strong>{writingOperationLabels[operation]}</strong>{plan.coverage[operation] ?? 0}%</span>)}</div><div className="writing-block-list">{plan.blocks.map((block) => { const allowedOperations = block.operation === 'insert' ? (['insert'] as const) : (['preserve','transform','rewrite','delete'] as const); return <article key={block.id}><span className="block-number">{String(block.order).padStart(2, '0')}</span><div><input aria-label={`区块 ${block.order} 标题`} value={block.title} onChange={(event) => patchBlock(block.id, { title: event.target.value })} /><small>{block.source_text_snapshot.slice(0, 80) || '插入点'}</small></div><select aria-label={`区块 ${block.order} 操作`} value={block.operation} onChange={(event) => patchBlock(block.id, { operation: event.target.value as WritingBlock['operation'] })}>{allowedOperations.map((key) => <option key={key} value={key}>{writingOperationLabels[key]}</option>)}</select><div className="block-instructions"><textarea aria-label={`区块 ${block.order} 指令`} placeholder="操作指令" value={block.instruction} onChange={(event) => patchBlock(block.id, { instruction: event.target.value })} /><textarea aria-label={`区块 ${block.order} 保留约束`} placeholder="保持（每行一项）" value={block.preserve_constraints.join('\n')} onChange={(event) => patchBlock(block.id, { preserve_constraints: lines(event.target.value) })} /><textarea aria-label={`区块 ${block.order} 目标要求`} placeholder="目标要求（每行一项）" value={block.target_requirements.join('\n')} onChange={(event) => patchBlock(block.id, { target_requirements: lines(event.target.value) })} /></div></article>; })}</div><footer><button className="button primary" disabled={busy || dirty || plan.status === 'stale' || !plan.blocks.length} onClick={onGenerate} type="button">开始生成</button></footer></div>;
}

function TargetContext({ target }: { target: SceneTarget | null }) {
  return <><h3>目标</h3>{target ? <div className="target-context-summary">{(target.design.summary ?? []).map((item) => <p key={item}>{item}</p>)}</div> : <div className="creative-empty">暂无目标</div>}</>;
}

function ReviewStage({ busy, currentDraft, diff, onAccept, onAddNote, onConfirm, onRestore, onRework, onReworkAll, onUndo, sourceRef, targetRef, undoAvailable }: { busy: boolean; currentDraft: SceneDraft | null; diff: SceneReviewDiff | null; onAccept: () => void; onAddNote: () => void; onConfirm: () => void; onRestore: () => void; onRework: () => void; onReworkAll: () => void; onUndo: () => void; sourceRef: RefObject<HTMLTextAreaElement>; targetRef: RefObject<HTMLTextAreaElement>; undoAvailable: boolean }) {
  if (!diff || !currentDraft) return <section className="stage-placeholder"><h2>审查</h2><p>正在读取 Source 与 Current Draft…</p></section>;
  return <section className="review-stage"><header><div><h2>Source ↔ Current Draft</h2><p>传统文本 Diff；进入本页不会调用 AI。</p></div><div><button className="button secondary" disabled={busy} onClick={onAddNote} type="button">添加备注</button><button className="button secondary" disabled={busy} onClick={onRestore} type="button">恢复原文</button><button className="button secondary" disabled={busy} onClick={onRework} type="button">AI 重改此处</button><button className="button secondary" disabled={busy} onClick={onReworkAll} type="button"><Sparkles size={15} />AI 根据全部备注修改</button>{undoAvailable ? <><button className="button secondary" disabled={busy} onClick={onAccept} type="button">采用新版</button><button className="button secondary" disabled={busy} onClick={onUndo} type="button">撤销</button></> : null}<button className="button primary" disabled={busy} onClick={onConfirm} type="button">确认场景</button></div></header><div className="diff-head"><strong>原文</strong><strong>当前稿</strong></div><div className="traditional-diff">{diff.chunks.map((chunk, index) => <div className={`diff-row ${chunk.tag}`} key={`${chunk.tag}-${index}`}><pre>{chunk.source_text || ' '}</pre><pre>{chunk.target_text || ' '}</pre></div>)}</div><details className="review-range-picker"><summary>选择原文与当前稿范围</summary><div><label><span>原文范围</span><textarea ref={sourceRef} value={diff.source_text} readOnly /></label><label><span>当前稿范围</span><textarea ref={targetRef} value={diff.target_text} readOnly /></label></div></details></section>;
}

function ReviewMarksPanel({ marks, onDelete, onRestore, onRework }: { marks: ReviewMark[]; onDelete: (mark: ReviewMark) => void; onRestore: (mark: ReviewMark) => void; onRework: (mark: ReviewMark) => void }) {
  return <><h3>审查备注</h3>{marks.length ? <div className="review-mark-list">{marks.map((mark, index) => <article className={mark.resolved ? 'resolved' : ''} key={mark.id}><strong>{index + 1}{mark.resolved ? ' · 已处理' : ''}</strong><small>原文：“{mark.source_text.slice(0, 70)}”</small><p>{mark.user_note}</p><div><button className="button ghost" onClick={() => onRestore(mark)} type="button">恢复原文</button><button className="button ghost" onClick={() => onRework(mark)} type="button">AI 重改此处</button><button className="button ghost danger-quiet" onClick={() => onDelete(mark)} type="button">删除</button></div></article>)}</div> : <div className="creative-empty">暂无备注</div>}</>;
}

function SelectedMaterials({ intent, materials }: { intent: CreativeIntent | null; materials: Material[] }) {
  const selected = materials.filter((item) => intent?.selected_plot_material_ids.includes(item.id) || intent?.selected_scene_material_ids.includes(item.id));
  return <><h3>素材</h3>{selected.length ? <div className="context-choice-list">{selected.map((item) => <div key={item.id}><span>{item.name}</span><small>{item.material_type === 'plot_skeleton' ? '剧情' : '场景'}</small></div>)}</div> : <div className="creative-empty">未选择素材</div>}</>;
}

function PlusIcon() { return <span aria-hidden="true">＋</span>; }

function ContextResources({ characters, intent, materials, onIntent }: { characters: CharacterCard[]; intent: CreativeIntent | null; materials: Material[]; onIntent: (patch: Partial<CreativeIntent>) => void }) {
  function toggle(key: 'selected_character_ids' | 'selected_plot_material_ids' | 'selected_scene_material_ids', id: number) {
    if (!intent) return;
    const ids = intent[key];
    onIntent({ [key]: ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id] });
  }
  return <><h3>人物</h3><div className="context-choice-list">{characters.map((item) => <label key={item.id}><input checked={intent?.selected_character_ids.includes(item.id) ?? false} disabled={!intent} onChange={() => toggle('selected_character_ids', item.id)} type="checkbox" /><span>{item.name}</span></label>)}</div><h3>素材</h3><div className="context-choice-list">{materials.map((item) => { const key = item.material_type === 'plot_skeleton' ? 'selected_plot_material_ids' : 'selected_scene_material_ids'; return <label key={item.id}><input checked={intent?.[key].includes(item.id) ?? false} disabled={!intent} onChange={() => toggle(key, item.id)} type="checkbox" /><span>{item.name}</span><small>{item.material_type === 'plot_skeleton' ? '剧情' : '场景'}</small></label>; })}</div></>;
}

function SceneBoundaryEditor({ boundaries, busy, onApply, onChange, onConfirm, scenes }: { boundaries: SceneBoundaryItem[]; busy: boolean; onApply: () => void; onChange: (items: SceneBoundaryItem[]) => void; onConfirm: () => void; scenes: SceneRecord[] }) {
  const allConfirmed = scenes.length > 0 && scenes.every((scene) => scene.user_confirmed);
  function patch(index: number, value: Partial<SceneBoundaryItem>) {
    onChange(boundaries.map((item, itemIndex) => itemIndex === index ? { ...item, ...value } : item));
  }
  return <div className="scene-boundary-editor"><div className="scene-boundary-editor-head"><div><strong>场景切分</strong><span>调整 Source 范围后会创建新的场景工作对象。</span></div><div><button className="button secondary" disabled={busy || !boundaries.length} onClick={onApply} type="button">应用边界</button><button className="button primary" disabled={busy || !scenes.length || allConfirmed} onClick={onConfirm} type="button">{allConfirmed ? '切分已确认' : '确认场景切分'}</button></div></div>{boundaries.map((item, index) => <div className="scene-boundary-edit-row" key={`${index}-${item.start_offset}`}><span>{String(index + 1).padStart(2, '0')}</span><input aria-label={`场景 ${index + 1} 标题`} value={item.title} onChange={(event) => patch(index, { title: event.target.value })} /><label>起始<input aria-label={`场景 ${index + 1} 起始位置`} min={0} type="number" value={item.start_offset} onChange={(event) => patch(index, { start_offset: Number(event.target.value) })} /></label><label>结束<input aria-label={`场景 ${index + 1} 结束位置`} min={0} type="number" value={item.end_offset} onChange={(event) => patch(index, { end_offset: Number(event.target.value) })} /></label><small>{item.start_offset}–{item.end_offset}</small></div>)}</div>;
}

function boundariesFromScenes(scenes: SceneRecord[]): SceneBoundaryItem[] {
  return scenes.map((scene) => ({
    start_offset: scene.original_start_offset,
    end_offset: scene.original_end_offset,
    title: scene.title,
    reasons: scene.boundary_reasons,
  }));
}

function sceneProgressLabel(stage: CreativeWorkflowStage) {
  if (stage === 'not_started') return '未开始';
  if (stage === 'confirmed') return '已完成';
  if (stage === 'target_design' || stage === 'writing' || stage === 'review') return '待确认';
  return '进行中';
}

function workflowIndex(stage: CreativeWorkflowStage) {
  if (stage === 'not_started') return -1;
  if (stage === 'confirmed') return stageOrder.length;
  return stageOrder.indexOf(stage);
}

function chapterNumber(index: number) {
  return `第${index}章`;
}

function formatTime(value: string) {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function messageOf(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}

function lines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function analysisWrite(value: BaseSceneAnalysis) {
  return {
    summary: value.summary,
    characters: value.characters,
    location: value.location,
    time: value.time,
    scene_type: value.scene_type,
    basic_events: value.basic_events,
  };
}
