import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import path from 'node:path';

const isDev = process.env.NODE_ENV !== 'production';

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1500,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    backgroundColor: '#07111f',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  window.webContents.on('will-navigate', (event, url) => {
    const allowed = isDev ? url.startsWith('http://127.0.0.1:5173') : url.startsWith('file://');
    if (!allowed) {
      event.preventDefault();
    }
  });

  if (isDev) {
    void window.loadURL('http://127.0.0.1:5173');
  } else {
    void window.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

ipcMain.handle('rusty:select-book-file', async () => {
  const result = await dialog.showOpenDialog({
    title: '选择电子书文件',
    properties: ['openFile'],
    filters: [{ name: 'Books', extensions: ['txt', 'epub', 'docx'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
