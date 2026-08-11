import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Check, Download, RefreshCw, Settings2, Sparkles } from 'lucide-react';
import {
  analyzeChapterScenes,
  confirmScenePreanalysis,
  confirmCharacterModificationAnalysis,
  getChapter,
  getChapterScenes,
  getChapters,
  getCreativeWorkflowStates,
  getProjectCharacters,
  getProject,
  getProjectMasterPrompt,
  getProjectMaterials,
  getModels,
  getSceneCreativeIntent,
  getScenePreanalysis,
  getCharacterModificationAnalysis,
  runScenePreanalysis,
  runCharacterModificationAnalysis,
  saveSceneCreativeIntent,
  saveScenePreanalysis,
  saveCharacterModificationAnalysis,
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
} from '../api/types';

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

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [states, setStates] = useState<ChapterWorkflowState[]>([]);
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
  const [sourceCharacter, setSourceCharacter] = useState('');
  const [targetCharacterId, setTargetCharacterId] = useState<number | null>(null);
  const [focusedEvidence, setFocusedEvidence] = useState('');

  const stateByChapter = useMemo(
    () => new Map(states.map((item) => [item.chapter_id, item])),
    [states],
  );
  const selectedState = selectedChapterId ? stateByChapter.get(selectedChapterId) ?? null : null;
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
    setSelectedChapterId((current) => (
      current && chapterItems.some((item) => item.id === current) ? current : chapterItems[0]?.id ?? null
    ));
  }, [projectId]);

  const loadChapter = useCallback(async (chapterId: number) => {
    const [chapterDetail, sceneItems] = await Promise.all([
      getChapter(chapterId),
      getChapterScenes(chapterId),
    ]);
    setDetail(chapterDetail);
    setScenes(sceneItems);
  }, []);

  const activeSceneId = selectedState?.active_scene_id ?? null;

  useEffect(() => {
    if (!activeSceneId) {
      setSceneContextLoading(false);
      setPreanalysis(null);
      setIntent(null);
      setCharacterAnalysis(null);
      return;
    }
    let cancelled = false;
    setSceneContextLoading(true);
    void Promise.all([getScenePreanalysis(activeSceneId), getSceneCreativeIntent(activeSceneId), getCharacterModificationAnalysis(activeSceneId)])
      .then(([analysis, creativeIntent, specialized]) => {
        if (cancelled) return;
        setPreanalysis(analysis);
        setIntent(creativeIntent);
        setCharacterAnalysis(specialized);
        setSourceCharacter(specialized?.source_character ?? analysis?.characters[0] ?? '');
        setTargetCharacterId(specialized?.target_character_card_id ?? creativeIntent?.selected_character_ids[0] ?? null);
        setAnalysisDirty(false);
        setIntentDirty(false);
        setCharacterAnalysisDirty(false);
        setFocusedEvidence('');
      })
      .catch((reason) => { if (!cancelled) setError(messageOf(reason)); })
      .finally(() => { if (!cancelled) setSceneContextLoading(false); });
    return () => { cancelled = true; };
  }, [activeSceneId]);

  useEffect(() => {
    if (!activeSceneId || !preanalysis || !analysisDirty) return;
    const timeout = window.setTimeout(() => {
      void saveScenePreanalysis(activeSceneId, analysisWrite(preanalysis))
        .then((saved) => { setPreanalysis(saved); setAnalysisDirty(false); })
        .catch((reason) => setError(messageOf(reason)));
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [activeSceneId, analysisDirty, preanalysis]);

  useEffect(() => {
    if (!activeSceneId || !intent || !intentDirty) return;
    const timeout = window.setTimeout(() => {
      void saveSceneCreativeIntent(activeSceneId, intent)
        .then((saved) => { setIntent(saved); setIntentDirty(false); })
        .catch((reason) => setError(messageOf(reason)));
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [activeSceneId, intent, intentDirty]);

  useEffect(() => {
    if (!activeSceneId || !characterAnalysis || !characterAnalysisDirty) return;
    const timeout = window.setTimeout(() => {
      void saveCharacterModificationAnalysis(activeSceneId, characterAnalysis)
        .then((saved) => { setCharacterAnalysis(saved); setCharacterAnalysisDirty(false); })
        .catch((reason) => setError(messageOf(reason)));
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [activeSceneId, characterAnalysis, characterAnalysisDirty]);

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

  const reachedIndex = workflowIndex(selectedState?.current_stage ?? 'not_started');

  async function chooseScene(sceneId: number) {
    if (!selectedChapterId || !selectedState) return;
    setBusy(true);
    setError(null);
    try {
      const currentStage = selectedState.current_stage === 'not_started' ? 'preanalysis' : selectedState.current_stage;
      const updated = await updateCreativeWorkflowState(selectedChapterId, currentStage, sceneId);
      setStates((items) => items.map((item) => item.chapter_id === updated.chapter_id ? updated : item));
      setViewStage(currentStage);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function createScenes() {
    if (!selectedChapterId) return;
    await perform(async () => {
      const items = await analyzeChapterScenes(selectedChapterId, { source: 'heuristic', confirm: false });
      setScenes(items);
      if (items[0]) await chooseScene(items[0].id);
    });
  }

  async function analyzeScene() {
    if (!activeSceneId) return;
    const replace = Boolean(preanalysis?.user_edited);
    if (replace && !window.confirm('重新分析会替换当前预分析结果。')) return;
    await perform(async () => {
      const saved = await runScenePreanalysis(activeSceneId, replace);
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
      setPreanalysis(saved);
      setViewStage('direction');
      await refreshStates();
    });
  }

  async function continueToSpecialAnalysis() {
    if (!activeSceneId || !selectedChapterId || !intent) return;
    await perform(async () => {
      const savedIntent = await saveSceneCreativeIntent(activeSceneId, intent);
      setIntent(savedIntent);
      setTargetCharacterId((current) => current ?? savedIntent.selected_character_ids[0] ?? null);
      const updated = await updateCreativeWorkflowState(selectedChapterId, 'special_analysis', activeSceneId);
      setStates((items) => items.map((item) => item.chapter_id === updated.chapter_id ? updated : item));
      setViewStage('special_analysis');
    });
  }

  async function refreshStates() {
    setStates(await getCreativeWorkflowStates(projectId));
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  function patchAnalysis(patch: Partial<BaseSceneAnalysis>) {
    setPreanalysis((current) => current ? { ...current, ...patch } : current);
    setAnalysisDirty(true);
  }

  function patchIntent(patch: Partial<CreativeIntent>) {
    setIntent((current) => current ? { ...current, ...patch } : current);
    setIntentDirty(true);
  }

  function chooseStrategy(strategy: CreativeStrategy) {
    if (!activeSceneId) return;
    if (intent) patchIntent({ strategy });
    else {
      setIntent({
        scene_id: activeSceneId,
        strategy,
        user_instruction: '',
        selected_character_ids: [],
        selected_plot_material_ids: [],
        selected_scene_material_ids: [],
        status: 'draft',
        updated_at: new Date().toISOString(),
      });
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
      setCharacterAnalysis(saved);
      setCharacterAnalysisDirty(false);
      await refreshStates();
    });
  }

  async function confirmCharacterAnalysis() {
    if (!activeSceneId) return;
    await perform(async () => {
      const saved = await confirmCharacterModificationAnalysis(activeSceneId);
      setCharacterAnalysis(saved);
      setCharacterAnalysisDirty(false);
      setViewStage('target_design');
      await refreshStates();
    });
  }

  function patchCharacterAnalysis(value: CharacterModificationAnalysis) {
    setCharacterAnalysis(value);
    setCharacterAnalysisDirty(true);
  }

  return (
    <div className="creative-workspace">
      <header className="creative-topbar">
        <button className="button ghost" onClick={() => onNavigate('/library')} type="button">
          <ArrowLeft size={17} />工程列表
        </button>
        <div className="creative-project-title"><strong>{projectName}</strong><span>/</span><span>{selectedChapter?.title ?? '暂无章节'}</span></div>
        <div className="creative-top-actions">
          <button className="button ghost" onClick={() => void openSettings()} type="button"><Settings2 size={17} />工程设置</button>
          <button className="button ghost" type="button"><Download size={17} />导出</button>
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
                  key={chapter.id}
                  onClick={() => setSelectedChapterId(chapter.id)}
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
            <div className="section-title"><h2>场景</h2><span>{scenes.length} 个工作对象</span></div>
            <div className="creative-scene-list">
              {scenes.map((scene, index) => {
                const active = scene.id === selectedState?.active_scene_id;
                return (
                  <button className={active ? 'active' : ''} disabled={busy} key={scene.id} onClick={() => void chooseScene(scene.id)} type="button">
                    <span className="scene-number">{String(index + 1).padStart(2, '0')}</span>
                    <span className="scene-name">{scene.title}</span>
                    <small>{active ? '当前' : index < scenes.findIndex((item) => item.id === selectedState?.active_scene_id) ? '已完成' : '待处理'}</small>
                  </button>
                );
              })}
              {!scenes.length ? <div className="creative-empty"><p>本章尚未生成场景工作对象。</p><button className="button secondary" disabled={busy} onClick={() => void createScenes()} type="button"><Sparkles size={15} />分析并切分</button></div> : null}
            </div>
          </section>

          {viewStage === 'preanalysis' ? (
            <PreanalysisEditor analysis={preanalysis} busy={busy || sceneContextLoading} dirty={analysisDirty} onAnalyze={() => void analyzeScene()} onChange={patchAnalysis} onConfirm={() => void confirmAnalysis()} />
          ) : null}
          {viewStage === 'direction' ? (
            <DirectionEditor intent={intent} busy={busy || sceneContextLoading} onContinue={() => void continueToSpecialAnalysis()} onInstruction={(value) => patchIntent({ user_instruction: value })} onStrategy={chooseStrategy} />
          ) : null}
          {viewStage === 'special_analysis' ? <CharacterAnalysisEditor analysis={characterAnalysis} busy={busy || sceneContextLoading} characters={characters} dirty={characterAnalysisDirty} intent={intent} onAnalyze={() => void analyzeCharacterModification()} onChange={patchCharacterAnalysis} onConfirm={() => void confirmCharacterAnalysis()} onEvidence={setFocusedEvidence} onSourceCharacter={setSourceCharacter} onTargetCharacter={setTargetCharacterId} sourceCharacter={sourceCharacter} targetCharacterId={targetCharacterId} /> : null}
          {viewStage === 'target_design' ? <section className="stage-placeholder target-design-shell"><h2>目标设计</h2><p>专项分析已确认。目标设计将在第二阶段实现；本阶段不会生成正文。</p></section> : null}
          {!['preanalysis', 'direction', 'special_analysis', 'target_design'].includes(viewStage) ? <section className="stage-placeholder"><h2>{stageLabels[viewStage]}</h2><p>该阶段将在后续阶段接入。</p></section> : null}
        </main>

        <aside className="creative-context-panel">
          <h2>当前上下文</h2>
          {viewStage === 'direction' ? <ContextResources characters={characters} intent={intent} materials={materials} onIntent={patchIntent} /> : null}
          {viewStage === 'special_analysis' ? <CharacterContext characters={characters} targetId={characterAnalysis?.target_character_card_id ?? targetCharacterId} /> : null}
          <h3>原文</h3>
          {focusedEvidence ? <div className="focused-evidence"><strong>当前证据</strong><p>{focusedEvidence}</p></div> : null}
          <div className="source-context">{scenes.find((item) => item.id === activeSceneId)?.original_text || selectedChapter?.original_text || '暂无原文'}</div>
        </aside>
      </div>
      {settingsOpen ? <div className="settings-backdrop" role="presentation"><section aria-label="工程设置" className="creative-settings-panel" role="dialog"><header><div><h2>工程设置</h2><p>AI 配置</p></div><button className="button ghost" onClick={() => setSettingsOpen(false)} type="button">关闭</button></header><label><span>默认模型</span><select value={settingsModelId ?? ''} onChange={(event) => setSettingsModelId(event.target.value ? Number(event.target.value) : null)}><option value="">使用全局默认模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label><label className="settings-master-field"><span>总提示词</span><textarea value={masterPrompt} onChange={(event) => { setMasterPrompt(event.target.value); setMasterDirty(true); }} /></label><footer><button className="button secondary" onClick={() => void exportMaster()} type="button">导出到提示词库</button><button className="button primary" disabled={busy || (!masterDirty && settingsModelId === null)} onClick={() => void saveSettings()} type="button">保存设置</button></footer></section></div> : null}
    </div>
  );
}

function PreanalysisEditor({ analysis, busy, dirty, onAnalyze, onChange, onConfirm }: { analysis: BaseSceneAnalysis | null; busy: boolean; dirty: boolean; onAnalyze: () => void; onChange: (patch: Partial<BaseSceneAnalysis>) => void; onConfirm: () => void }) {
  if (!analysis) return <section className="stage-placeholder stage-action-empty"><h2>预分析</h2><p>轻量判断这是什么场景，不在这里生成完整人物状态或改写方案。</p><button className="button primary" disabled={busy} onClick={onAnalyze} type="button"><Sparkles size={16} />运行预分析</button></section>;
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

  return <section className="character-analysis-editor"><header><div><h2>贴合原文 / 人物修改</h2><p>{analysis.source_character} → {analysis.target_character_name}</p></div><span>{dirty ? '正在自动保存…' : analysis.status === 'stale' ? '上游已修改，需要重新确认' : analysis.status === 'confirmed' ? '已确认' : '已自动保存'}</span></header>{analysisCategories.map(([category, label]) => <details key={category} open={analysis[category].length > 0}><summary><span>{label}</span><small>{analysis[category].length} 项</small></summary><div className="analysis-item-list">{analysis[category].map((item) => <article key={item.id}><div className="analysis-item-toolbar"><label><input checked={item.inferred} onChange={(event) => updateItem(category, item.id, { inferred: event.target.checked })} type="checkbox" />推断</label><button className="button ghost" onClick={() => onEvidence(item.source_text)} type="button">查看原文</button><button className="button ghost danger-quiet" onClick={() => removeItem(category, item.id)} type="button">删除</button></div><label><span>结论</span><input value={item.summary} onChange={(event) => updateItem(category, item.id, { summary: event.target.value })} /></label><label><span>对应原文</span><textarea value={item.source_text} onChange={(event) => updateItem(category, item.id, { source_text: event.target.value, start_offset: 0, end_offset: 0 })} /></label>{category === 'target_character_conflicts' ? <div className="conflict-fields"><label><span>原文状态</span><input value={item.source_state ?? ''} onChange={(event) => updateItem(category, item.id, { source_state: event.target.value })} /></label><label><span>目标人物卡</span><input value={item.target_state ?? ''} onChange={(event) => updateItem(category, item.id, { target_state: event.target.value })} /></label><label><span>差异</span><input value={item.difference ?? ''} onChange={(event) => updateItem(category, item.id, { difference: event.target.value })} /></label></div> : null}</article>)}<button className="button secondary add-analysis-item" onClick={() => addItem(category)} type="button"><PlusIcon />补充一项</button></div></details>)}<footer><button className="button secondary" disabled={busy} onClick={onAnalyze} type="button"><RefreshCw size={15} />重新分析</button><button className="button primary" disabled={busy || dirty} onClick={onConfirm} type="button"><Check size={16} />确认分析</button></footer></section>;
}

function CharacterContext({ characters, targetId }: { characters: CharacterCard[]; targetId: number | null }) {
  const target = characters.find((item) => item.id === targetId);
  if (!target) return <><h3>人物</h3><div className="creative-empty">尚未选择目标人物卡。</div></>;
  return <><h3>人物</h3><div className="character-context-card"><strong>{target.name}</strong><p>{target.setting_text || target.description || '暂无人物设定'}</p>{target.personality ? <small>性格：{target.personality}</small> : null}{target.action_constraints ? <small>行动约束：{target.action_constraints}</small> : null}</div></>;
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
