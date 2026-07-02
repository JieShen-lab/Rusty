import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const isDev = process.env.NODE_ENV !== 'production';
const API_HOST = process.env.RUSTY_API_HOST || '127.0.0.1';
const API_PORT = Number(process.env.RUSTY_API_PORT || '8765');
const API_BASE = `http://${API_HOST}:${API_PORT}`;
const API_TOKEN = process.env.RUSTY_API_TOKEN || crypto.randomBytes(24).toString('hex');

let backendProcess: ChildProcessWithoutNullStreams | null = null;

function projectRoot(): string {
  const appPath = app.getAppPath();
  const devRoot = path.resolve(appPath, '..');
  if (fs.existsSync(path.join(devRoot, 'backend', 'server.py'))) {
    return devRoot;
  }
  return appPath;
}

function pythonExecutable(root: string): string {
  if (process.env.RUSTY_PYTHON) {
    return process.env.RUSTY_PYTHON;
  }
  const venvPython =
    process.platform === 'win32'
      ? path.join(root, '.venv', 'Scripts', 'python.exe')
      : path.join(root, '.venv', 'bin', 'python');
  return fs.existsSync(venvPython) ? venvPython : 'python';
}

function waitForHealth(timeoutMs = 1200): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get(`${API_BASE}/api/health`, { timeout: timeoutMs }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function waitForBackendReady(timeoutMs = 12000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await waitForHealth(700)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

async function ensureBackend(): Promise<void> {
  if (await waitForHealth()) {
    return;
  }

  const root = projectRoot();
  backendProcess = spawn(pythonExecutable(root), ['-m', 'backend.server'], {
    cwd: root,
    env: {
      ...process.env,
      RUSTY_API_HOST: API_HOST,
      RUSTY_API_PORT: String(API_PORT),
      RUSTY_API_TOKEN: API_TOKEN,
      RUSTY_API_ALLOWED_ORIGINS: 'http://127.0.0.1:5173,http://localhost:5173',
    },
    windowsHide: true,
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[rusty-backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr.on('data', (data) => {
    console.error(`[rusty-backend] ${data.toString().trim()}`);
  });
  backendProcess.on('exit', (code, signal) => {
    console.log(`[rusty-backend] exited code=${code ?? 'null'} signal=${signal ?? 'null'}`);
    backendProcess = null;
  });

  const ready = await waitForBackendReady();
  if (!ready) {
    console.warn('Rusty backend did not become healthy before the Electron window opened.');
  }
}

function stopBackend(): void {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
  backendProcess = null;
}

function createWindow(): void {
  process.env.RUSTY_RENDERER_API_URL = API_BASE;
  process.env.RUSTY_RENDERER_API_TOKEN = API_TOKEN;

  const window = new BrowserWindow({
    width: 1500,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    backgroundColor: '#07111f',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#07111f',
      symbolColor: '#f8fafc',
      height: 36,
    },
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

  const query = { apiBase: API_BASE, apiToken: API_TOKEN };
  if (isDev) {
    const params = new URLSearchParams(query);
    void window.loadURL(`http://127.0.0.1:5173?${params.toString()}`);
  } else {
    void window.loadFile(path.join(__dirname, '../dist/index.html'), { query });
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

ipcMain.handle('rusty:get-backend-config', () => ({
  apiBase: API_BASE,
  apiToken: API_TOKEN,
}));

app.whenReady().then(async () => {
  await ensureBackend();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopBackend();
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void ensureBackend().then(createWindow);
  }
});

app.on('before-quit', stopBackend);
