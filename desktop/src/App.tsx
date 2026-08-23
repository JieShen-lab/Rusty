import { useEffect, useLayoutEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import { AITaskNotice } from './components/FloatingNotice';
import type { RouteKey } from './components/Sidebar';
import { DocumentLibraryPage } from './pages/DocumentLibraryPage';
import { ModelManagePage } from './pages/ModelManagePage';
import { AuthorLibraryPage } from './pages/MaterialLibraryPage';
import { NewProjectPage } from './pages/NewProjectPage';
import { ProjectWorkspacePage } from './pages/ProjectWorkspacePage';
import { PromptManagePage } from './pages/PromptManagePage';
import { WorkbenchPage } from './pages/WorkbenchPage';
import { applyTheme, getInitialTheme, type UiTheme } from './theme';
import { flushBeforeNavigation } from './navigationFlush';

type Route = {
  key: RouteKey;
  projectId?: number;
};

const usesFileRouting = window.location.protocol === 'file:';

function currentRoutePath(): string {
  if (!usesFileRouting) return window.location.pathname;
  const hashPath = window.location.hash.slice(1);
  return hashPath.startsWith('/') ? hashPath : '/library';
}

function historyUrl(path: string): string {
  return usesFileRouting ? `#${path}` : path;
}

function parseRoute(pathname: string): Route {
  const parts = pathname.split('/').filter(Boolean);
  if (parts[0] === 'library') return { key: 'library' };
  if (parts[0] === 'workspace') {
    const projectId = parts[1] ? Number(parts[1]) : undefined;
    return { key: 'workspace', projectId: Number.isFinite(projectId) ? projectId : undefined };
  }
  if (parts[0] === 'new-project') return { key: 'new-project' };
  if (parts[0] === 'models') return { key: 'models' };
  if (parts[0] === 'prompts') return { key: 'prompts' };
  if (parts[0] === 'authors') return { key: 'authors' };
  if (parts[0] === 'documents') return { key: 'documents' };
  return { key: 'library' };
}

export default function App() {
  const [route, setRoute] = useState(() => parseRoute(currentRoutePath()));
  const [theme, setTheme] = useState<UiTheme>(getInitialTheme);

  useLayoutEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if ((!usesFileRouting && window.location.pathname === '/') || (usesFileRouting && !window.location.hash)) {
      window.history.replaceState(window.history.state, '', historyUrl('/library'));
      setRoute(parseRoute('/library'));
    }
    const onPop = async () => {
      try {
        await flushBeforeNavigation();
      } catch {
        return;
      }
      setRoute(parseRoute(currentRoutePath()));
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  async function navigate(path: string, state?: unknown) {
    try {
      await flushBeforeNavigation();
    } catch {
      return;
    }
    window.history.pushState(state ?? null, '', historyUrl(path));
    setRoute(parseRoute(path));
  }

  let page = <WorkbenchPage onNavigate={navigate} />;
  if (route.key === 'workspace' && route.projectId !== undefined) page = <ProjectWorkspacePage projectId={route.projectId} onNavigate={navigate} />;
  if (route.key === 'new-project') page = <NewProjectPage onNavigate={navigate} />;
  if (route.key === 'models') page = <ModelManagePage />;
  if (route.key === 'prompts') page = <PromptManagePage />;
  if (route.key === 'authors') page = <AuthorLibraryPage />;
  if (route.key === 'documents') page = <DocumentLibraryPage />;
  const showAITasks = ['library', 'models', 'prompts', 'authors', 'documents'].includes(route.key);

  return (
    <AppShell active={route.key} onNavigate={navigate} onToggleTheme={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} theme={theme}>
      {showAITasks ? <AITaskNotice /> : null}
      {page}
    </AppShell>
  );
}
