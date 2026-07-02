import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('rustyDesktop', {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
  selectBookFile: () => ipcRenderer.invoke('rusty:select-book-file') as Promise<string | null>,
});
