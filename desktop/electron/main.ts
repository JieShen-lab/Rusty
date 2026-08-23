import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import path from 'node:path';

const isDev = !app.isPackaged && process.env.NODE_ENV !== 'production';
const API_HOST = process.env.RUSTY_API_HOST || '127.0.0.1';
let apiPort = Number(process.env.RUSTY_API_PORT || (isDev ? '8765' : '0'));
let apiBase = apiPort > 0 ? `http://${API_HOST}:${apiPort}` : '';
const API_TOKEN = process.env.RUSTY_API_TOKEN || crypto.randomBytes(24).toString('hex');

let backendProcess: ChildProcessWithoutNullStreams | null = null;
let mainWindow: BrowserWindow | null = null;

type BackendRequestInput = {
  path: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
};

type BackendRequestResult = {
  status: number;
  statusText: string;
  body: string;
  headers: Record<string, string>;
};

function proxyBackendRequest(input: BackendRequestInput): Promise<BackendRequestResult> {
  if (!input.path.startsWith('/api/')) {
    return Promise.reject(new Error('只允许访问 Rusty API。'));
  }
  return new Promise((resolve, reject) => {
    const request = http.request(`${apiBase}${input.path}`, {
      method: input.method || 'GET',
      headers: {
        ...input.headers,
        'X-Rusty-Token': API_TOKEN,
      },
    }, (response) => {
      const chunks: Buffer[] = [];
      response.on('data', (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
      response.on('end', () => {
        const headers = Object.fromEntries(
          Object.entries(response.headers).map(([key, value]) => [key, Array.isArray(value) ? value.join(', ') : String(value ?? '')]),
        );
        resolve({
          status: response.statusCode || 500,
          statusText: response.statusMessage || '',
          body: Buffer.concat(chunks).toString('utf8'),
          headers,
        });
      });
    });
    request.on('error', reject);
    if (input.body) request.write(input.body);
    request.end();
  });
}

function chooseAvailablePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, API_HOST, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

async function prepareBackendEndpoint(): Promise<void> {
  if (apiPort <= 0) {
    apiPort = await chooseAvailablePort();
    apiBase = `http://${API_HOST}:${apiPort}`;
  }
}

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

function backendLaunch(): { command: string; args: string[]; cwd: string } {
  if (app.isPackaged) {
    const backendRoot = path.join(process.resourcesPath, 'backend');
    const executable = path.join(backendRoot, process.platform === 'win32' ? 'rusty-backend.exe' : 'rusty-backend');
    if (!fs.existsSync(executable)) {
      throw new Error(`Rusty 后端文件不存在：${executable}`);
    }
    return { command: executable, args: [], cwd: backendRoot };
  }

  const root = projectRoot();
  return { command: pythonExecutable(root), args: ['-m', 'backend.server'], cwd: root };
}

function waitForHealth(timeoutMs = 1200): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get(`${apiBase}/api/health`, { timeout: timeoutMs }, (response) => {
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
  if (backendProcess && !backendProcess.killed && await waitForHealth()) {
    return;
  }
  if (isDev && await waitForHealth()) {
    return;
  }

  const launch = backendLaunch();
  const spawnedProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: {
      ...process.env,
      RUSTY_API_HOST: API_HOST,
      RUSTY_API_PORT: String(apiPort),
      RUSTY_API_TOKEN: API_TOKEN,
      RUSTY_API_ALLOWED_ORIGINS: 'http://127.0.0.1:5173,http://localhost:5173,null',
    },
    windowsHide: true,
  });
  backendProcess = spawnedProcess;

  spawnedProcess.stdout.on('data', (data) => {
    console.log(`[rusty-backend] ${data.toString().trim()}`);
  });
  spawnedProcess.stderr.on('data', (data) => {
    console.error(`[rusty-backend] ${data.toString().trim()}`);
  });
  spawnedProcess.on('exit', (code, signal) => {
    console.log(`[rusty-backend] exited code=${code ?? 'null'} signal=${signal ?? 'null'}`);
    if (backendProcess === spawnedProcess) {
      backendProcess = null;
    }
  });
  spawnedProcess.on('error', (error) => {
    console.error(`[rusty-backend] failed to start: ${error.message}`);
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

async function restartBackend(): Promise<boolean> {
  // A renderer request can fail during a very short startup or wake-up window.
  // Do not tear down a backend that has already recovered by the time IPC runs.
  if (await waitForHealth(1500)) {
    return true;
  }

  const currentProcess = backendProcess;
  if (currentProcess && !currentProcess.killed) {
    const exited = new Promise<void>((resolve) => currentProcess.once('exit', () => resolve()));
    currentProcess.kill();
    await Promise.race([exited, new Promise<void>((resolve) => setTimeout(resolve, 2000))]);
  }
  backendProcess = null;
  await ensureBackend();
  return waitForHealth(1500);
}

function createWindow(): void {
  process.env.RUSTY_RENDERER_API_URL = apiBase;
  process.env.RUSTY_RENDERER_API_TOKEN = API_TOKEN;

  const window = new BrowserWindow({
    width: 1500,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    backgroundColor: '#eef1f5',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#00000000',
      symbolColor: '#5f6978',
      height: 30,
    },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  mainWindow = window;
  window.on('closed', () => {
    if (mainWindow === window) mainWindow = null;
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

  const query = { apiBase, apiToken: API_TOKEN };
  if (isDev) {
    const params = new URLSearchParams(query);
    void window.loadURL(`http://127.0.0.1:5173?${params.toString()}`);
  } else {
    void window.loadFile(path.join(app.getAppPath(), 'dist', 'index.html'), { query });
  }
}

ipcMain.handle('rusty:select-book-file', async () => {
  if (process.env.NODE_ENV === 'test' && process.env.RUSTY_E2E_BOOK_FILE) {
    return process.env.RUSTY_E2E_BOOK_FILE;
  }
  const result = await dialog.showOpenDialog({
    title: '选择电子书文件',
    properties: ['openFile'],
    filters: [{ name: 'Books', extensions: ['txt', 'epub', 'docx'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('rusty:select-library-document-file', async () => {
  if (process.env.NODE_ENV === 'test' && process.env.RUSTY_E2E_BOOK_FILE) {
    return process.env.RUSTY_E2E_BOOK_FILE;
  }
  const result = await dialog.showOpenDialog({
    title: '导入文档到文档库',
    properties: ['openFile'],
    filters: [{ name: 'Documents', extensions: ['txt', 'epub', 'docx'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('rusty:select-document-library-directory', async () => {
  if (process.env.NODE_ENV === 'test' && process.env.RUSTY_E2E_WORKSPACE) {
    return process.env.RUSTY_E2E_WORKSPACE;
  }
  const result = await dialog.showOpenDialog({
    title: '选择文档保存目录',
    properties: ['openDirectory', 'createDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('rusty:select-document-export-path', async (_event, format: 'txt' | 'epub', title: string) => {
  if (process.env.NODE_ENV === 'test' && process.env.RUSTY_E2E_EXPORT_PATH) {
    return process.env.RUSTY_E2E_EXPORT_PATH;
  }
  const extension = format === 'epub' ? 'epub' : 'txt';
  const result = await dialog.showSaveDialog({
    title: `导出 ${format.toUpperCase()}`,
    defaultPath: `${title || 'document'}.${extension}`,
    filters: [{ name: format.toUpperCase(), extensions: [extension] }],
  });
  return result.canceled ? null : result.filePath;
});

ipcMain.handle('rusty:select-workspace-directory', async () => {
  if (process.env.NODE_ENV === 'test' && process.env.RUSTY_E2E_WORKSPACE) {
    return process.env.RUSTY_E2E_WORKSPACE;
  }
  const result = await dialog.showOpenDialog({
    title: '选择工作目录',
    properties: ['openDirectory', 'createDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('rusty:get-backend-config', () => ({
  apiBase,
  apiToken: API_TOKEN,
}));

ipcMain.handle('rusty:backend-request', (_event, input: BackendRequestInput) => proxyBackendRequest(input));

ipcMain.handle('rusty:restart-backend', async () => ({
  ok: await restartBackend(),
  apiBase,
  apiToken: API_TOKEN,
}));

ipcMain.handle('rusty:set-theme', (event, theme: 'light' | 'dark') => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!window || (theme !== 'light' && theme !== 'dark')) {
    return false;
  }
  const dark = theme === 'dark';
  window.setBackgroundColor(dark ? '#15181d' : '#eef1f5');
  window.setTitleBarOverlay({
    color: '#00000000',
    symbolColor: dark ? '#d8dee8' : '#5f6978',
    height: 30,
  });
  return true;
});

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const window = mainWindow ?? BrowserWindow.getAllWindows()[0];
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  });

  app.whenReady().then(async () => {
    await prepareBackendEndpoint();
    await ensureBackend();
    createWindow();
  });
}

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
