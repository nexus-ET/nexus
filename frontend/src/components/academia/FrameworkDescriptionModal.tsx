import { useEffect, useId, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

interface FrameworkDescriptionModalProps {
  open: boolean;
  title: string;
  description: string;
  onClose: () => void;
  /**
   * When true, treat description as rich HTML from TipTap (sanitize + render).
   * When false, show as plain text (with literal \\n → newline normalization).
   */
  stripHtml?: boolean;
}

const ALLOWED_TAGS = new Set([
  'A',
  'B',
  'BR',
  'DIV',
  'EM',
  'H1',
  'H2',
  'H3',
  'H4',
  'I',
  'LI',
  'OL',
  'P',
  'SPAN',
  'STRONG',
  'TABLE',
  'TBODY',
  'TD',
  'TH',
  'THEAD',
  'TR',
  'U',
  'UL',
]);

const ALLOWED_ATTRS: Record<string, ReadonlySet<string>> = {
  A: new Set(['href', 'target', 'rel', 'title']),
  TD: new Set(['colspan', 'rowspan']),
  TH: new Set(['colspan', 'rowspan']),
  TABLE: new Set(['class']),
  DIV: new Set(['class']),
  SPAN: new Set(['class']),
};

/** Convert stored description to plain text while preserving paragraph / line breaks. */
function toPlainText(value: string): string {
  let text = value.replace(/\\n/g, '\n');

  text = text
    .replace(/[^\S\n]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return text;
}

function isSafeHref(href: string): boolean {
  const trimmed = href.trim();
  if (!trimmed) return false;
  const lower = trimmed.toLowerCase();
  return (
    lower.startsWith('http://') ||
    lower.startsWith('https://') ||
    lower.startsWith('mailto:') ||
    lower.startsWith('/') ||
    lower.startsWith('#')
  );
}

/**
 * Allowlist sanitizer for framework rich-text descriptions.
 * Keeps tables and common TipTap tags; strips scripts/events/unknown nodes.
 */
export function sanitizeFrameworkDescriptionHtml(html: string): string {
  if (typeof DOMParser === 'undefined') {
    return html
      .replace(/<\s*script[\s\S]*?>[\s\S]*?<\s*\/\s*script\s*>/gi, '')
      .replace(/\son\w+\s*=\s*(['"]).*?\1/gi, '');
  }

  const doc = new DOMParser().parseFromString(html, 'text/html');
  const walk = (node: Node) => {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as HTMLElement;
        const tag = el.tagName.toUpperCase();
        if (!ALLOWED_TAGS.has(tag)) {
          // Keep text content of disallowed wrappers (e.g. <font>), drop the element.
          while (el.firstChild) {
            node.insertBefore(el.firstChild, el);
          }
          node.removeChild(el);
          continue;
        }

        const allowed = ALLOWED_ATTRS[tag];
        for (const attr of Array.from(el.attributes)) {
          const name = attr.name.toLowerCase();
          if (name.startsWith('on') || name === 'style') {
            el.removeAttribute(attr.name);
            continue;
          }
          if (!allowed || !allowed.has(name)) {
            el.removeAttribute(attr.name);
            continue;
          }
          if (name === 'href' && !isSafeHref(attr.value)) {
            el.removeAttribute(attr.name);
          }
          if (name === 'target' && attr.value !== '_blank') {
            el.removeAttribute(attr.name);
          }
        }
        if (tag === 'A') {
          el.setAttribute('rel', 'noopener noreferrer');
        }
        walk(el);
      } else if (child.nodeType === Node.COMMENT_NODE) {
        node.removeChild(child);
      }
    }
  };

  walk(doc.body);
  return doc.body.innerHTML;
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

  const plain = useMemo(
    () => (stripHtml ? '' : toPlainText(description)),
    [description, stripHtml]
  );
  const safeHtml = useMemo(
    () => (stripHtml ? sanitizeFrameworkDescriptionHtml(description) : ''),
    [description, stripHtml]
  );

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

  const bodyClassName =
    'min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm leading-6 text-text-main ' +
    (stripHtml
      ? [
          '[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-6',
          '[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-6',
          '[&_li]:my-0.5',
          '[&_p]:my-2',
          '[&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-base [&_h2]:font-semibold',
          '[&_a]:text-accent [&_a]:underline',
          '[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:overflow-hidden [&_table]:rounded-md [&_table]:border [&_table]:border-border-subtle',
          '[&_th]:border [&_th]:border-border-subtle [&_th]:bg-surface-bg/80 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold',
          '[&_td]:border [&_td]:border-border-subtle [&_td]:px-2 [&_td]:py-1.5',
        ].join(' ')
      : '');

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
        <div id={bodyId} className={bodyClassName}>
          {stripHtml ? (
            safeHtml.trim() ? (
              <div dangerouslySetInnerHTML={{ __html: safeHtml }} />
            ) : (
              <p>—</p>
            )
          ) : (
            <p className="whitespace-pre-wrap break-words">{plain || '—'}</p>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};

export default FrameworkDescriptionModal;
