import { useEffect } from 'react';

export function useAutoDismiss(
  value: string | null,
  clear: (value: null) => void,
  delay = 3600,
) {
  useEffect(() => {
    if (!value) return undefined;
    const timer = window.setTimeout(() => clear(null), delay);
    return () => window.clearTimeout(timer);
  }, [clear, delay, value]);
}
