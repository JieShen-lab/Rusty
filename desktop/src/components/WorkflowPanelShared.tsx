import type { ReactNode } from 'react';

import type {
  ChapterRewriteVersion,
  ChapterSourceSelection,
  PlotGenerationRun,
} from '../api/types';

export function RewriteVersionHistory({
  onSelectSource,
  onRestore,
  onUseCurrent,
  onUseOriginal,
  onView,
  selectedSource,
  versions,
  viewedVersion,
}: {
  onSelectSource: (version: ChapterRewriteVersion) => void;
  onRestore: (version: ChapterRewriteVersion) => void;
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
      <p>{selectedSource.kind === 'rewrite_version' ? '本次将基于所选历史稿继续' : selectedSource.kind === 'original' ? '本次将基于原文继续' : '本次将基于当前稿继续'}</p>
      <button onClick={onUseCurrent} type="button">当前稿</button>
      <button onClick={onUseOriginal} type="button">原文</button>
      {versions.length === 0 ? <p>No rewrite versions.</p> : (
        <ul>
          {versions.map((version) => (
            <li key={version.id}>
              <button onClick={() => onView(version)} type="button">
                {version.is_current ? '当前稿' : `版本 ${version.version}`}
              </button>
              <button onClick={() => onSelectSource(version)} type="button">
                基于此版本继续
              </button>
              {!version.is_current ? <button onClick={() => onRestore(version)} type="button">恢复为新版本</button> : null}
              <time>{version.created_at}</time>
            </li>
          ))}
        </ul>
      )}
      {viewedVersion ? <pre>{viewedVersion.rewritten_text}</pre> : null}
    </section>
  );
}

export function RunStatus({ run }: { run: { id: number; status: string; stage?: string } }) {
  const labels: Record<string, string> = {
    awaiting_skeleton: '等待确认剧情规划',
    ready: '规划已确认，可以开始生成',
    generating: '正在分场景生成',
    completed: '本次创作已完成',
    failed: '生成遇到错误',
    cancelled: '本次创作已取消',
    planned: '重写计划已生成',
  };
  return <p className="wide" role="status">{labels[run.status] ?? '正在处理'}</p>;
}

export function plannedSceneCount(run: PlotGenerationRun): number {
  const chapters = Array.isArray(run.scene_plan.chapters) ? run.scene_plan.chapters : [];
  return chapters.reduce((count, chapter) => {
    if (!chapter || typeof chapter !== 'object') return count;
    const scenes = (chapter as { scenes?: unknown }).scenes;
    return count + (Array.isArray(scenes) ? scenes.length : 0);
  }, 0);
}

export function OperationButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-pressed={active} className={active ? 'active' : ''} onClick={onClick} type="button">{icon}<strong>{label}</strong></button>;
}
