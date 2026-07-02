import { useEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import type { RouteKey } from './components/Sidebar';
import { HomePage } from './pages/HomePage';
import { ModelManagePage } from './pages/ModelManagePage';
import { NewProjectPage } from './pages/NewProjectPage';
import { ProjectWorkspacePage } from './pages/ProjectWorkspacePage';
import { PromptManagePage } from './pages/PromptManagePage';
import { WorkbenchPage } from './pages/WorkbenchPage';

type Route = {
  key: RouteKey;
  path: string;
  projectId?: number;
};

function parseRoute(pathname: string): Route {
  const parts = pathname.split('/').filter(Boolean);
  if (parts[0] === 'library') return { key: 'library', path: '/library' };
  if (parts[0] === 'workspace') {
    const projectId = parts[1] ? Number(parts[1]) : undefined;
    return { key: 'workspace', path: pathname, projectId: Number.isFinite(projectId) ? projectId : undefined };
  }
  if (parts[0] === 'new-project') return { key: 'new-project', path: '/new-project' };
  if (parts[0] === 'models') return { key: 'models', path: '/models' };
  if (parts[0] === 'prompts') return { key: 'prompts', path: '/prompts' };
  return { key: 'home', path: '/home' };
}

export default function App() {
  const [route, setRoute] = useState(() => parseRoute(window.location.pathname));

  useEffect(() => {
    if (window.location.pathname === '/') {
      window.history.replaceState(null, '', '/home');
      setRoute(parseRoute('/home'));
    }
    const onPop = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  function navigate(path: string) {
    window.history.pushState(null, '', path);
    setRoute(parseRoute(path));
  }

  let page = <HomePage onNavigate={navigate} />;
  if (route.key === 'library') page = <WorkbenchPage onNavigate={navigate} />;
  if (route.key === 'workspace') page = <ProjectWorkspacePage projectId={route.projectId} onNavigate={navigate} />;
  if (route.key === 'new-project') page = <NewProjectPage onNavigate={navigate} />;
  if (route.key === 'models') page = <ModelManagePage />;
  if (route.key === 'prompts') page = <PromptManagePage />;

  return (
    <AppShell active={route.key} onNavigate={navigate}>
      {page}
    </AppShell>
  );
}
