export type NavigationFlush = () => Promise<void>;

let activeFlush: NavigationFlush | null = null;

export function registerNavigationFlush(flush: NavigationFlush) {
  activeFlush = flush;
  return () => {
    if (activeFlush === flush) activeFlush = null;
  };
}

export async function flushBeforeNavigation() {
  await activeFlush?.();
}
