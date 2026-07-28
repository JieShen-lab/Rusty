import type { ReactNode } from 'react';
import { CircleDashed, X } from 'lucide-react';

export function LibrarySidebarItem({
  active,
  count,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  count: number;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className={`document-tag-item ${active ? 'selected' : ''}`}
      onClick={onClick}
      type="button"
    >
      {icon}
      <span>{label}</span>
      <small>{count}</small>
    </button>
  );
}

export function LibraryEmptyState({
  action,
  description,
  title,
}: {
  action?: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <div className="document-shelf-empty">
      <CircleDashed aria-hidden="true" size={28} />
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
      {action ? <div className="document-shelf-empty-action">{action}</div> : null}
    </div>
  );
}

export function LibraryDialog({
  children,
  footer,
  onClose,
  subtitle,
  title,
}: {
  children: ReactNode;
  footer: ReactNode;
  onClose: () => void;
  subtitle?: string;
  title: string;
}) {
  return (
    <div className="library-dialog-backdrop" role="presentation">
      <section aria-modal="true" className="library-dialog" role="dialog">
        <header>
          <div>
            {subtitle ? <span>{subtitle}</span> : null}
            <h2>{title}</h2>
          </div>
          <button aria-label="关闭" className="icon-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </header>
        <div className="library-dialog-body">{children}</div>
        <footer>{footer}</footer>
      </section>
    </div>
  );
}

export function LibraryDefinition({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="document-definition">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
