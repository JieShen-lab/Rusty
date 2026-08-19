import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { getChapter, getChapters } from '../api/client';
import type { Chapter, ChapterDetail } from '../api/types';

type Props = {
  projectId: number;
  projectName: string;
  onNavigate: (path: string, state?: unknown) => void;
};

export function CreativeWorkspacePage({ onNavigate, projectId, projectName }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);
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
    if (!selectedId) { setDetail(null); return; }
    let cancelled = false;
    void getChapter(selectedId)
      .then((value) => { if (!cancelled) setDetail(value); })
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
          <p>本阶段已移除角色卡与剧情骨架素材依赖。新的章节级 Workflow 将在下一阶段接入。</p>
          <textarea readOnly value={detail?.chapter.original_text ?? ''} />
        </main>
      </div>
    </div>
  );
}

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}
