import { useEffect, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { LoaderCircle } from 'lucide-react';
import { getAITasks, subscribeAITasks } from '../api/aiTaskStatus';

type FloatingNoticeProps = {
  error?: ReactNode;
  message?: ReactNode;
};

export function FloatingNotice({ error, message }: FloatingNoticeProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!error && !message) {
      setVisible(false);
      return;
    }
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 3000);
    return () => window.clearTimeout(timer);
  }, [error, message]);

  if (!visible || (!error && !message)) return null;

  return createPortal(
    <div className="floating-notice-stack">
      {error ? <div className="inline-alert error floating-notice" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success floating-notice" role="status">{message}</div> : null}
    </div>,
    document.body,
  );
}

export function AITaskNotice() {
  const tasks = useSyncExternalStore(subscribeAITasks, getAITasks);
  if (!tasks.length) return null;

  const text = tasks.length === 1
    ? `AI 正在处理：${tasks[0].label}`
    : `AI 正在处理 ${tasks.length} 项任务`;

  return createPortal(
    <div className="floating-notice-stack">
      <div className="inline-alert pending floating-notice ai-task-notice" role="status">
        <LoaderCircle aria-hidden="true" size={15} />
        {text}
      </div>
    </div>,
    document.body,
  );
}
