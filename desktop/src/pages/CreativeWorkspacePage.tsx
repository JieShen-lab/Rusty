import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Download, Settings2 } from 'lucide-react';
import {
  getChapter,
  getChapterScenes,
  getChapters,
  getCreativeWorkflowStates,
  updateCreativeWorkflowState,
} from '../api/client';
import type {
  Chapter,
  ChapterDetail,
  ChapterWorkflowState,
  CreativeWorkflowStage,
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
    const [chapterItems, workflowStates] = await Promise.all([
      getChapters(projectId),
      getCreativeWorkflowStates(projectId),
    ]);
    setChapters(chapterItems);
    setStates(workflowStates);
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
              {!scenes.length ? <div className="creative-empty">本章尚未生成场景工作对象，请从预分析开始。</div> : null}
            </div>
          </section>

          <section className="stage-placeholder">
            <h2>{stageLabels[viewStage]}</h2>
            <p>{viewStage === 'preanalysis' ? '选择一个场景后，在这里完成轻量预分析。' : '该阶段将在对应批次中接入。'}</p>
          </section>
        </main>

        <aside className="creative-context-panel">
          <h2>当前上下文</h2>
          <h3>原文</h3>
          <div className="source-context">{selectedChapter?.original_text || '暂无原文'}</div>
        </aside>
      </div>
    </div>
  );
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
