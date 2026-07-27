import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('rustyDesktop', {
  bridgeVersion: 2,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
  backend: {
    apiBase: process.env.RUSTY_RENDERER_API_URL || 'http://127.0.0.1:8765',
    apiToken: process.env.RUSTY_RENDERER_API_TOKEN || '',
  },
  getBackendConfig: () =>
    ipcRenderer.invoke('rusty:get-backend-config') as Promise<{ apiBase: string; apiToken: string }>,
  requestBackend: (input: { path: string; method?: string; headers?: Record<string, string>; body?: string | null }) =>
    ipcRenderer.invoke('rusty:backend-request', input) as Promise<{ status: number; statusText: string; body: string; headers: Record<string, string> }>,
  restartBackend: () =>
    ipcRenderer.invoke('rusty:restart-backend') as Promise<{ ok: boolean; apiBase: string; apiToken: string }>,
  setTheme: (theme: 'light' | 'dark') =>
    ipcRenderer.invoke('rusty:set-theme', theme) as Promise<boolean>,
  selectBookFile: () => ipcRenderer.invoke('rusty:select-book-file') as Promise<string | null>,
  selectLibraryDocumentFile: () => ipcRenderer.invoke('rusty:select-library-document-file') as Promise<string | null>,
  selectDocumentLibraryDirectory: () => ipcRenderer.invoke('rusty:select-document-library-directory') as Promise<string | null>,
  selectDocumentExportPath: (format: 'txt' | 'epub', title: string) =>
    ipcRenderer.invoke('rusty:select-document-export-path', format, title) as Promise<string | null>,
  selectWorkspaceDirectory: () => ipcRenderer.invoke('rusty:select-workspace-directory') as Promise<string | null>,
});
