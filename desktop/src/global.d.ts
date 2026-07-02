export {};

declare global {
  interface Window {
    rustyDesktop?: {
      platform?: string;
      versions?: Record<string, string>;
      backend?: {
        apiBase?: string;
        apiToken?: string;
      };
      getBackendConfig?: () => Promise<{ apiBase: string; apiToken: string }>;
      selectBookFile?: () => Promise<string | null>;
    };
  }
}
