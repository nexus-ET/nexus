import { useEffect } from 'react';
import { CharacterCount } from '@tiptap/extension-character-count';
import Link from '@tiptap/extension-link';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import {
  Bold,
  Heading2,
  Italic,
  Link2,
  List,
  Pilcrow,
} from 'lucide-react';

import { stripHtml } from '../../schemas/wizard/shared';

const toolbarButtonClass =
  'inline-flex items-center justify-center rounded-lg border border-border-subtle bg-card px-2 py-1.5 text-text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40';

export interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  maxLength?: number;
  placeholder?: string;
  label?: string;
  error?: string;
  hint?: string;
}

const RichTextEditor: React.FC<RichTextEditorProps> = ({
  content,
  onChange,
  maxLength = 5000,
  placeholder,
  label,
  error,
  hint,
}) => {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ link: false }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          rel: 'noopener noreferrer',
          target: '_blank',
        },
      }),
      CharacterCount.configure({ limit: maxLength }),
    ],
    content: content || '',
    editorProps: {
      attributes: {
        class:
          'min-h-[160px] w-full rounded-b-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent prose prose-sm max-w-none [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-0.5',
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      onChange(currentEditor.getHTML());
    },
  });

  useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    if (content !== current) {
      editor.commands.setContent(content || '', { emitUpdate: false });
    }
  }, [content, editor]);

  if (!editor) return null;

  const textCount = stripHtml(content || '').length;
  const overLimit = textCount > maxLength;

  const tools = [
    {
      icon: Bold,
      label: 'Bold',
      active: editor.isActive('bold'),
      action: () => editor.chain().focus().toggleBold().run(),
    },
    {
      icon: Italic,
      label: 'Italic',
      active: editor.isActive('italic'),
      action: () => editor.chain().focus().toggleItalic().run(),
    },
    {
      icon: Heading2,
      label: 'Heading',
      active: editor.isActive('heading', { level: 2 }),
      action: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
    },
    {
      icon: Pilcrow,
      label: 'Paragraph',
      active: editor.isActive('paragraph'),
      action: () => editor.chain().focus().setParagraph().run(),
    },
    {
      icon: List,
      label: 'Bullet list',
      active: editor.isActive('bulletList'),
      action: () => editor.chain().focus().toggleBulletList().run(),
    },
    {
      icon: Link2,
      label: 'Link',
      active: editor.isActive('link'),
      action: () => {
        const previous = editor.getAttributes('link').href as string | undefined;
        const url = window.prompt('Enter URL', previous || 'https://');
        if (url === null) return;
        if (!url) {
          editor.chain().focus().extendMarkRange('link').unsetLink().run();
          return;
        }
        editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
      },
    },
  ] as const;

  return (
    <div className="space-y-1.5 text-sm">
      {label ? (
        <div className="block text-sm font-bold text-text-main">
          {label}
          <span className="ml-1 font-normal text-text-muted">(max {maxLength} characters)</span>
        </div>
      ) : null}

      <div
        className={`relative rounded-xl border ${error || overLimit ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'}`}
      >
        <div className="flex flex-wrap gap-1 rounded-t-xl border-b border-border-subtle bg-surface-bg/60 p-2">
          {tools.map(tool => {
            const Icon = tool.icon;
            return (
              <button
                key={tool.label}
                type="button"
                title={tool.label}
                aria-label={tool.label}
                aria-pressed={tool.active}
                onClick={tool.action}
                className={`${toolbarButtonClass} ${
                  tool.active ? 'border-accent/50 bg-accent/10 text-accent' : ''
                }`}
              >
                <Icon size={14} />
              </button>
            );
          })}
        </div>
        <EditorContent editor={editor} />
        {!content && placeholder ? (
          <p className="pointer-events-none absolute left-3 right-3 top-[58px] text-sm text-text-muted">
            {placeholder}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        {hint ? <span className="text-text-muted">{hint}</span> : <span />}
        <span className={overLimit ? 'text-alert' : 'text-text-muted'}>
          {textCount} / {maxLength} characters
        </span>
      </div>
      {error ? <p className="text-xs text-alert">{error}</p> : null}
    </div>
  );
};

export default RichTextEditor;
