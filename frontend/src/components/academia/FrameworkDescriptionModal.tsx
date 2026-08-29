import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

interface FrameworkDescriptionModalProps {
  open: boolean;
  title: string;
  description: string;
  onClose: () => void;
  /** Strip HTML tags (e.g. rich-text major descriptions) before display. */
  stripHtml?: boolean;
}

/** Convert stored description to plain text while preserving paragraph / line breaks. */
function toPlainText(value: string, stripHtml: boolean): string {
  let text = value;

  if (stripHtml) {
    text = text
      .replace(/<\s*br\s*\/?\s*>/gi, '\n')
      .replace(/<\s*\/\s*p\s*>/gi, '\n')
      .replace(/<\s*\/\s*div\s*>/gi, '\n')
      .replace(/<\s*\/\s*h[1-6]\s*>/gi, '\n')
      .replace(/<\s*li[^>]*>/gi, '\n• ')
      .replace(/<\s*\/\s*(ul|ol)\s*>/gi, '\n')
      .replace(/<[^>]*>/g, '')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/&quot;/gi, '"')
      .replace(/&#39;|&apos;/gi, "'");
  }

  // Seeded plain-text majors often store a literal "\n" sequence instead of a newline.
  text = text.replace(/\\n/g, '\n');

  // Collapse horizontal whitespace only; keep newlines for whitespace-pre-wrap.
  text = text
    .replace(/[^\S\n]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return text;
}

const FrameworkDescriptionModal: React.FC<FrameworkDescriptionModalProps> = ({
  open,
  title,
  description,
  onClose,
  stripHtml = false,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const bodyId = useId();
  const plain = toPlainText(description, stripHtml);

  useEffect(() => {
    if (!open) return;

    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.requestAnimationFrame(() => closeButtonRef.current?.focus());

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        tabIndex={-1}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border-subtle px-5 py-4">
          <h3 id={titleId} className="pr-4 text-lg font-bold text-text-main">
            {title}
          </h3>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-text-muted hover:bg-surface-bg"
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>
        <div
          id={bodyId}
          className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm leading-6 text-text-main"
        >
          <p className="whitespace-pre-wrap break-words">{plain || '—'}</p>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default FrameworkDescriptionModal;
