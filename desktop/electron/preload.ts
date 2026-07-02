import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('rustyDesktop', {
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
  selectBookFile: () => ipcRenderer.invoke('rusty:select-book-file') as Promise<string | null>,
});
