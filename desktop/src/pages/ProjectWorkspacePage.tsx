import { useEffect, useState } from 'react';
import { getChapters, getProject } from '../api/client';
import type { Chapter, Project } from '../api/types';
import { CreativeWorkspacePage } from './CreativeWorkspacePage';

type Props = { onNavigate: (path: string, state?: unknown) => void; projectId: number };

export function ProjectWorkspacePage({ onNavigate, projectId }: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void Promise.all([getProject(projectId), getChapters(projectId)])
      .then(([projectValue, chapterValues]) => {
        if (cancelled) return;
        setProject(projectValue);
        setChapters(chapterValues);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { cancelled = true; };
  }, [projectId]);

  if (error) return <div className="workspace-message"><h2>无法打开工程</h2><p>{error}</p></div>;
  if (!project) return <div className="workspace-message"><h2>正在打开工程…</h2></div>;

  return <CreativeWorkspacePage onNavigate={onNavigate} projectId={projectId} projectName={project.name} />;
}
