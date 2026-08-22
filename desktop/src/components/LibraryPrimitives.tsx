import { useEffect, useId, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { CircleDashed, X } from 'lucide-react';

export function BodyPortal({ children }: { children: ReactNode }) {
  return createPortal(children, document.body);
}

export function LibrarySidebarItem({
  active,
  count,
  icon,
  label,
  onClick,
  onContextMenu,
}: {
  active: boolean;
  count: number;
  icon: ReactNode;
  label: string;
  onClick: () => void;
  onContextMenu?: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      aria-pressed={active}
      className={`library-sidebar-item ${active ? 'selected' : ''}`}
      onClick={onClick}
      onContextMenu={onContextMenu}
      type="button"
    >
      {icon}
      <span>{label}</span>
      <small>{count}</small>
    </button>
  );
}

export function LibrarySidebarSectionTitle({ action, children }: { action?: ReactNode; children: ReactNode }) {
  return <div className="library-sidebar-section-title"><strong>{children}</strong>{action}</div>;
}

export function LibraryDivider() {
  return <div aria-hidden="true" className="library-sidebar-divider" />;
}

export function LibraryResourceGrid({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`document-shelf-grid ${className}`}>{children}</div>;
}

export function LibraryResourceCard({
  ariaLabel,
  children,
  onClick,
  onDoubleClick,
  selected,
}: {
  ariaLabel: string;
  children: ReactNode;
  onClick: () => void;
  onDoubleClick?: () => void;
  selected: boolean;
}) {
  return <button aria-label={ariaLabel} aria-pressed={selected} className={`document-book ${selected ? 'selected' : ''}`} onClick={onClick} onDoubleClick={onDoubleClick} type="button">{children}</button>;
}

export type LibraryContextMenuAction = {
  danger?: boolean;
  icon?: ReactNode;
  label: string;
  onSelect: () => void;
};

export function LibraryContextMenu({
  actions,
  label = '分类操作',
  onClose,
  x,
  y,
}: {
  actions: LibraryContextMenuAction[];
  label?: string;
  onClose: () => void;
  x: number;
  y: number;
}) {
  const menuRef = useRef<HTMLDivElement>(null);
  const safeX = Number.isFinite(x) ? x : 8;
  const safeY = Number.isFinite(y) ? y : 8;
  const [position, setPosition] = useState({ left: safeX, top: safeY });

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const margin = 8;
    const rect = menu.getBoundingClientRect();
    setPosition({
      left: Math.max(margin, Math.min(safeX, window.innerWidth - rect.width - margin)),
      top: Math.max(margin, Math.min(safeY, window.innerHeight - rect.height - margin)),
    });
  }, [safeX, safeY]);

  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) onClose();
    };
    const closeOnKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('pointerdown', closeOutside);
    window.addEventListener('keydown', closeOnKey);
    window.addEventListener('resize', onClose);
    window.addEventListener('scroll', onClose, true);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      window.removeEventListener('keydown', closeOnKey);
      window.removeEventListener('resize', onClose);
      window.removeEventListener('scroll', onClose, true);
    };
  }, [onClose]);

  return createPortal(
    <div
      aria-label={label}
      className="library-context-menu"
      ref={menuRef}
      role="menu"
      style={{ left: position.left, top: position.top }}
    >
      {actions.map((action) => (
        <button
          className={action.danger ? 'danger' : ''}
          key={action.label}
          onClick={() => { onClose(); action.onSelect(); }}
          role="menuitem"
          type="button"
        >
          {action.icon}{action.label}
        </button>
      ))}
    </div>,
    document.body,
  );
}

export function LibraryEmptyState({
  action,
  title,
}: {
  action?: ReactNode;
  title: string;
}) {
  return (
    <div className="document-shelf-empty">
      <CircleDashed aria-hidden="true" size={28} />
      <strong>{title}</strong>
      {action ? <div className="document-shelf-empty-action">{action}</div> : null}
    </div>
  );
}

export function LibraryDialog({
  bodyClassName,
  children,
  className,
  closeOnBackdrop = true,
  footer,
  onClose,
  title,
}: {
  bodyClassName?: string;
  children: ReactNode;
  className?: string;
  closeOnBackdrop?: boolean;
  footer: ReactNode;
  onClose: () => void;
  title: string;
}) {
  const titleId = useId();
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    if (closeOnBackdrop && event.currentTarget === event.target) {
      onClose();
    }
  };

  return createPortal(
    <div className="library-dialog-backdrop" onMouseDown={handleBackdrop} role="presentation">
      <section aria-labelledby={titleId} aria-modal="true" className={`library-dialog ${className ?? ''}`} role="dialog">
        <header>
          <div>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button aria-label="关闭" className="icon-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </header>
        <div className={`library-dialog-body ${bodyClassName ?? ''}`}>{children}</div>
        <footer>{footer}</footer>
      </section>
    </div>,
    document.body,
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
