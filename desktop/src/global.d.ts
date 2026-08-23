export {};

declare global {
  interface Window {
    rustyDesktop?: {
      backend?: {
        apiBase?: string;
        apiToken?: string;
      };
      getBackendConfig?: () => Promise<{ apiBase: string; apiToken: string }>;
      requestBackend?: (input: { path: string; method?: string; headers?: Record<string, string>; body?: string | null }) => Promise<{ status: number; statusText: string; body: string; headers: Record<string, string> }>;
      restartBackend?: () => Promise<{ ok: boolean; apiBase: string; apiToken: string }>;
      setTheme?: (theme: 'light' | 'dark') => Promise<boolean>;
      selectBookFile?: () => Promise<string | null>;
      selectLibraryDocumentFile?: () => Promise<string | null>;
      selectDocumentLibraryDirectory?: () => Promise<string | null>;
      selectDocumentExportPath?: (format: 'txt' | 'epub', title: string) => Promise<string | null>;
      selectWorkspaceDirectory?: () => Promise<string | null>;
    };
  }
}
