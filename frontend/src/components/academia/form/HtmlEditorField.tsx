import { useCallback, useId, useRef } from 'react';
import {
  Bold,
  Heading2,
  Italic,
  Link2,
  List,
  Pilcrow,
  Underline,
} from 'lucide-react';

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-mono outline-none focus:border-accent';

interface HtmlEditorFieldProps {
  label: string;
  maxLength: number;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  rows?: number;
}

const toolbarButtonClass =
  'inline-flex items-center justify-center rounded-lg border border-border-subtle bg-card px-2 py-1.5 text-text-muted transition-colors hover:border-accent/40 hover:text-accent';

const HtmlEditorField: React.FC<HtmlEditorFieldProps> = ({
  label,
  maxLength,
  value,
  onChange,
  placeholder,
  hint,
  rows = 10,
}) => {
  const fieldId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const count = value.length;

  const applyWrap = useCallback(
    (openTag: string, closeTag: string) => {
      const el = textareaRef.current;
      if (!el) return;

      const start = el.selectionStart;
      const end = el.selectionEnd;
      const selected = value.slice(start, end) || 'text';
      const next = value.slice(0, start) + openTag + selected + closeTag + value.slice(end);
      if (next.length > maxLength) return;

      onChange(next);
      requestAnimationFrame(() => {
        el.focus();
        const cursorStart = start + openTag.length;
        const cursorEnd = cursorStart + selected.length;
        el.setSelectionRange(cursorStart, cursorEnd);
      });
    },
    [maxLength, onChange, value]
  );

  const insertSnippet = useCallback(
    (snippet: string) => {
      const el = textareaRef.current;
      if (!el) return;

      const start = el.selectionStart;
      const end = el.selectionEnd;
      const next = value.slice(0, start) + snippet + value.slice(end);
      if (next.length > maxLength) return;

      onChange(next);
      requestAnimationFrame(() => {
        el.focus();
        const cursor = start + snippet.length;
        el.setSelectionRange(cursor, cursor);
      });
    },
    [maxLength, onChange, value]
  );

  const tools = [
    { icon: Bold, label: 'Bold', action: () => applyWrap('<strong>', '</strong>') },
    { icon: Italic, label: 'Italic', action: () => applyWrap('<em>', '</em>') },
    { icon: Underline, label: 'Underline', action: () => applyWrap('<u>', '</u>') },
    { icon: Heading2, label: 'Heading', action: () => applyWrap('<h2>', '</h2>') },
    { icon: Pilcrow, label: 'Paragraph', action: () => applyWrap('<p>', '</p>') },
    { icon: List, label: 'List item', action: () => insertSnippet('<ul>\n  <li>Item</li>\n</ul>') },
    {
      icon: Link2,
      label: 'Link',
      action: () =>
        applyWrap('<a href="https://www.example.edu" target="_blank" rel="noopener">', '</a>'),
    },
  ] as const;

  return (
    <div className="space-y-1.5 text-sm">
      <label htmlFor={fieldId} className="block text-base font-bold text-text-main">
        {label}
        <span className="ml-1 font-normal text-text-muted">(max {maxLength} characters, HTML)</span>
      </label>

      <div className="flex flex-wrap gap-1 rounded-t-xl border border-b-0 border-border-subtle bg-surface-bg/60 p-2">
        {tools.map(tool => {
          const Icon = tool.icon;
          return (
            <button
              key={tool.label}
              type="button"
              title={tool.label}
              aria-label={tool.label}
              onClick={tool.action}
              className={toolbarButtonClass}
            >
              <Icon size={14} />
            </button>
          );
        })}
        <button
          type="button"
          title="Line break"
          aria-label="Line break"
          onClick={() => insertSnippet('<br />')}
          className={`${toolbarButtonClass} px-2.5 text-xs font-semibold`}
        >
          BR
        </button>
      </div>

      <textarea
        id={fieldId}
        ref={textareaRef}
        maxLength={maxLength}
        rows={rows}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${fieldClass} rounded-t-none text-xs`}
      />

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        {hint ? <span>{hint}</span> : <span>Use the toolbar to insert HTML tags.</span>}
        <span className={count > maxLength ? 'text-alert' : undefined}>
          {count} / {maxLength} characters
        </span>
      </div>
    </div>
  );
};

export default HtmlEditorField;
