import { useEffect, useState } from 'react';


export function usePersistedWorkflowRun<T>(
  key: string,
  load: (id: number) => Promise<T>,
): [T | null, (value: T | null, id?: number) => void, () => void] {
  const [run, setRunState] = useState<T | null>(null);

  useEffect(() => {
    const id = Number(localStorage.getItem(key));
    if (id) {
      void load(id)
        .then(setRunState)
        .catch(() => localStorage.removeItem(key));
    }
  }, [key, load]);

  function setRun(value: T | null, id?: number) {
    setRunState(value);
    if (value && id) localStorage.setItem(key, String(id));
    if (!value) localStorage.removeItem(key);
  }

  return [run, setRun, () => setRun(null)];
}
