import { useEffect, useLayoutEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import type { RouteKey } from './components/Sidebar';
import { CharacterLibraryPage } from './pages/CharacterLibraryPage';
import { DocumentLibraryPage } from './pages/DocumentLibraryPage';
import { ModelManagePage } from './pages/ModelManagePage';
import { MaterialLibraryPage } from './pages/MaterialLibraryPage';
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
  if (parts[0] === 'materials' || parts[0] === 'outlines' || parts[0] === 'anchors') return { key: 'outlines' };
  if (parts[0] === 'characters') return { key: 'characters' };
  if (parts[0] === 'documents') return { key: 'documents' };
  if (parts[0] === 'styles') return { key: 'prompts' };
  return { key: 'library' };
}

export default function App() {
  const [route, setRoute] = useState(() => parseRoute(window.location.pathname));
  const [theme, setTheme] = useState<UiTheme>(getInitialTheme);

  useLayoutEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (window.location.pathname === '/') {
      window.history.replaceState(null, '', '/library');
      setRoute(parseRoute('/library'));
    }
    const onPop = async () => {
      try {
        await flushBeforeNavigation();
      } catch {
        return;
      }
      setRoute(parseRoute(window.location.pathname));
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
    window.history.pushState(state ?? null, '', path);
    setRoute(parseRoute(path));
  }

  let page = <WorkbenchPage onNavigate={navigate} />;
  if (route.key === 'workspace' && route.projectId !== undefined) page = <ProjectWorkspacePage projectId={route.projectId} onNavigate={navigate} />;
  if (route.key === 'new-project') page = <NewProjectPage onNavigate={navigate} />;
  if (route.key === 'models') page = <ModelManagePage />;
  if (route.key === 'prompts') page = <PromptManagePage />;
  if (route.key === 'outlines') page = <MaterialLibraryPage />;
  if (route.key === 'characters') page = <CharacterLibraryPage />;
  if (route.key === 'documents') page = <DocumentLibraryPage onNavigate={navigate} />;

  return (
    <AppShell active={route.key} onNavigate={navigate} onToggleTheme={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} theme={theme}>
      {page}
    </AppShell>
  );
}
