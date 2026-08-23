export type AITask = {
  id: number;
  label: string;
};

let nextTaskId = 1;
let tasks: AITask[] = [];
const listeners = new Set<() => void>();

export function getAITasks(): AITask[] {
  return tasks;
}

export function subscribeAITasks(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function trackAITask<T>(label: string, action: () => Promise<T>): Promise<T> {
  const id = nextTaskId++;
  tasks = [...tasks, { id, label }];
  emitChange();
  try {
    return await action();
  } finally {
    tasks = tasks.filter((task) => task.id !== id);
    emitChange();
  }
}

function emitChange(): void {
  listeners.forEach((listener) => listener());
}
