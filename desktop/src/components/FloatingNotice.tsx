import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

type FloatingNoticeProps = {
  error?: ReactNode;
  message?: ReactNode;
};

export function FloatingNotice({ error, message }: FloatingNoticeProps) {
  if (!error && !message) return null;

  return createPortal(
    <div className="floating-notice-stack">
      {error ? <div className="inline-alert error floating-notice" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success floating-notice" role="status">{message}</div> : null}
    </div>,
    document.body,
  );
}
