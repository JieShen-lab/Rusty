import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { getChapter, getChapters, getChapterWorkflow } from '../api/client';
import type { Chapter, ChapterDetail, ChapterWorkflowState } from '../api/types';

type Props = {
  projectId: number;
  projectName: string;
  onNavigate: (path: string, state?: unknown) => void;
};

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);
  const [workflow, setWorkflow] = useState<ChapterWorkflowState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getChapters(projectId)
      .then((items) => {
        if (cancelled) return;
        setChapters(items);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); setWorkflow(null); return; }
    let cancelled = false;
    void Promise.all([getChapter(selectedId), getChapterWorkflow(selectedId)])
      .then(([value, state]) => { if (!cancelled) { setDetail(value); setWorkflow(state); } })
      .catch((reason) => { if (!cancelled) setError(messageOf(reason)); });
    return () => { cancelled = true; };
  }, [selectedId]);

  return (
    <div className="creative-workspace">
      <header className="creative-toolbar">
        <button className="button ghost" onClick={() => onNavigate('/library')} type="button">
          <ArrowLeft size={16} />工程列表
        </button>
        <div><strong>{projectName}</strong><span>章节创作工作台正在切换为 chapter workflow</span></div>
      </header>
      {error ? <div className="inline-alert error" role="alert">{error}</div> : null}
      <div className="creative-layout">
        <aside className="creative-chapter-list">
          {chapters.map((chapter) => (
            <button className={chapter.id === selectedId ? 'active' : ''} key={chapter.id} onClick={() => setSelectedId(chapter.id)} type="button">
              <span>{chapter.index}</span><strong>{chapter.title}</strong>
            </button>
          ))}
        </aside>
        <main className="creative-stage-content">
          <h1>{detail?.chapter.title ?? '请选择章节'}</h1>
          <p>章节 Workflow：{stageLabel(workflow?.current_stage ?? 'not_started')}</p>
          {workflow?.source_changed ? <div className="inline-alert error">当前章节已变化，需要重新分析。</div> : null}
          <textarea readOnly value={detail?.chapter.original_text ?? ''} />
        </main>
      </div>
    </div>
  );
}

function stageLabel(stage: ChapterWorkflowState['current_stage']): string {
  return ({ not_started: '未开始', summary: '内容总结', direction: '方向选择', special_analysis: '专项分析',
    style: '风格', writing: '写作', review: '审查', confirmed: '已确认' })[stage];
}

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}
