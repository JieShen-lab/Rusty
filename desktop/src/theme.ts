export type UiTheme = 'light' | 'dark';

const THEME_STORAGE_KEY = 'rusty.ui.theme.v1';

export function getInitialTheme(): UiTheme {
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (savedTheme === 'light' || savedTheme === 'dark') {
    return savedTheme;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(theme: UiTheme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  void window.rustyDesktop?.setTheme?.(theme);
}
