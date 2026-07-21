import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, HelpCircle, Trash2, X } from 'lucide-react';

export interface ConfirmationModalOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'primary';
}

interface ConfirmationModalProps extends ConfirmationModalOptions {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const variantStyles = {
  danger: {
    icon: <Trash2 size={22} />,
    iconClass: 'bg-red-100 text-red-700',
    buttonClass: 'bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500',
  },
  warning: {
    icon: <AlertTriangle size={22} />,
    iconClass: 'bg-amber-100 text-amber-700',
    buttonClass: 'bg-amber-500 text-white hover:bg-amber-600 focus-visible:ring-amber-500',
  },
  primary: {
    icon: <HelpCircle size={22} />,
    iconClass: 'bg-accent/15 text-accent',
    buttonClass: 'bg-accent text-text-dark-bg hover:brightness-95 focus-visible:ring-accent',
  },
} as const;

const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.requestAnimationFrame(() => cancelButtonRef.current?.focus());

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open, onCancel]);

  if (!open) return null;

  const styles = variantStyles[variant];
  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-border-subtle bg-card shadow-2xl"
      >
        <div className="flex items-start gap-4 p-6">
          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${styles.iconClass}`}>
            {styles.icon}
          </div>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-bold text-text-main">
              {title}
            </h2>
            <p id={descriptionId} className="mt-2 whitespace-pre-line text-sm leading-6 text-text-muted">
              {message}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-bg hover:text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            aria-label="Close confirmation"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex justify-end gap-3 border-t border-border-subtle bg-surface-bg/40 px-6 py-4">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm font-semibold text-text-main transition hover:bg-surface-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-xl px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${styles.buttonClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default ConfirmationModal;
