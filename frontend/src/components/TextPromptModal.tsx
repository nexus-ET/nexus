import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle, X } from 'lucide-react';

export interface TextPromptModalProps {
  open: boolean;
  title: string;
  message: string;
  label?: string;
  placeholder?: string;
  defaultValue?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Return an error message to block confirm, or null when valid. */
  validate?: (value: string) => string | null;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

const TextPromptModal: React.FC<TextPromptModalProps> = ({
  open,
  title,
  message,
  label = 'Name',
  placeholder,
  defaultValue = '',
  confirmLabel = 'Add',
  cancelLabel = 'Cancel',
  validate,
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const inputId = useId();
  const errorId = useId();
  const [value, setValue] = useState(defaultValue);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setValue(defaultValue);
    setError(null);

    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });

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
  }, [open, defaultValue, onCancel]);

  if (!open) return null;

  const submit = () => {
    const trimmed = value.trim();
    const validationError = validate?.(trimmed) ?? (!trimmed ? 'Enter a valid name.' : null);
    if (validationError) {
      setError(validationError);
      inputRef.current?.focus();
      return;
    }
    setError(null);
    onConfirm(trimmed);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-border-subtle bg-card shadow-2xl"
      >
        <div className="flex items-start gap-4 p-6">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
            <HelpCircle size={22} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-bold text-text-main">
              {title}
            </h2>
            <p
              id={descriptionId}
              className="mt-2 whitespace-pre-line text-sm leading-6 text-text-muted"
            >
              {message}
            </p>
            <div className="mt-4">
              <label htmlFor={inputId} className="mb-1.5 block text-sm font-semibold text-text-main">
                {label}
              </label>
              <input
                ref={inputRef}
                id={inputId}
                type="text"
                value={value}
                placeholder={placeholder}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={event => {
                  setValue(event.target.value);
                  if (error) setError(null);
                }}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    submit();
                  }
                }}
                className={`w-full rounded-xl border bg-surface-bg px-3 py-2.5 text-sm text-text-main outline-none transition focus:border-accent ${
                  error ? 'border-alert' : 'border-border-subtle'
                }`}
              />
              {error ? (
                <p id={errorId} className="mt-1.5 text-sm text-alert" role="alert">
                  {error}
                </p>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-bg hover:text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex justify-end gap-3 border-t border-border-subtle bg-surface-bg/40 px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm font-semibold text-text-main transition hover:bg-surface-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={submit}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg transition hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default TextPromptModal;
