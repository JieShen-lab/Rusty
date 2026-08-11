import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Check, Download, RefreshCw, Settings2, Sparkles } from 'lucide-react';
import {
  analyzeChapterScenes,
  confirmScenePreanalysis,
  getChapter,
  getChapterScenes,
  getChapters,
  getCreativeWorkflowStates,
  getProjectCharacters,
  getProjectMaterials,
  getSceneCreativeIntent,
  getScenePreanalysis,
  runScenePreanalysis,
  saveSceneCreativeIntent,
  saveScenePreanalysis,
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
  Material,
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
  const [error, setError] = useState<string | null>(null);

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
      setPreanalysis(null);
      setIntent(null);
      return;
    }
    void Promise.all([getScenePreanalysis(activeSceneId), getSceneCreativeIntent(activeSceneId)])
      .then(([analysis, creativeIntent]) => {
        setPreanalysis(analysis);
        setIntent(creativeIntent);
        setAnalysisDirty(false);
        setIntentDirty(false);
      })
      .catch((reason) => setError(messageOf(reason)));
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

  return (
    <div className="creative-workspace">
      <header className="creative-topbar">
        <button className="button ghost" onClick={() => onNavigate('/library')} type="button">
          <ArrowLeft size={17} />工程列表
        </button>
        <div className="creative-project-title"><strong>{projectName}</strong><span>/</span><span>{selectedChapter?.title ?? '暂无章节'}</span></div>
        <div className="creative-top-actions">
          <button className="button ghost" type="button"><Settings2 size={17} />工程设置</button>
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
                const disabled = index > reachedIndex + 1;
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
            <PreanalysisEditor analysis={preanalysis} busy={busy} dirty={analysisDirty} onAnalyze={() => void analyzeScene()} onChange={patchAnalysis} onConfirm={() => void confirmAnalysis()} />
          ) : null}
          {viewStage === 'direction' ? (
            <DirectionEditor intent={intent} busy={busy} onContinue={() => void continueToSpecialAnalysis()} onInstruction={(value) => patchIntent({ user_instruction: value })} onStrategy={chooseStrategy} />
          ) : null}
          {!['preanalysis', 'direction'].includes(viewStage) ? <section className="stage-placeholder"><h2>{stageLabels[viewStage]}</h2><p>该阶段将在对应批次中接入。</p></section> : null}
        </main>

        <aside className="creative-context-panel">
          <h2>当前上下文</h2>
          {viewStage === 'direction' ? <ContextResources characters={characters} intent={intent} materials={materials} onIntent={patchIntent} /> : null}
          <h3>原文</h3>
          <div className="source-context">{scenes.find((item) => item.id === activeSceneId)?.original_text || selectedChapter?.original_text || '暂无原文'}</div>
        </aside>
      </div>
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
