import { useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import FaqEditor from './FaqEditor';
import type { InquiryFaq, InquiryFaqPayload } from './types';

interface Props {
  faq: InquiryFaq;
  busy?: boolean;
  onUpdate: (payload: InquiryFaqPayload) => Promise<void>;
  onDelete: () => void;
}

export default function FaqCard({ faq, busy, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <article className="rounded-2xl border border-accent/35 bg-card p-5 shadow-sm">
        <FaqEditor
          path={faq.nested_process_code || faq.subprocess_code || faq.process_code}
          initial={{ question: faq.question, answer: faq.answer }}
          submitLabel="Update answer"
          busy={busy}
          onCancel={() => setEditing(false)}
          onSubmit={async payload => {
            await onUpdate(payload);
            setEditing(false);
          }}
        />
      </article>
    );
  }

  return (
    <article className="group rounded-2xl border border-border-subtle bg-card p-5 shadow-sm transition hover:border-accent/35">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-xs font-extrabold text-accent">Q</span>
        <div className="min-w-0 flex-1">
          <h3 className="font-bold leading-6 text-text-main">{faq.question}</h3>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-text-muted">
            {faq.answer.replaceAll('**', '').replaceAll('`', '')}
          </p>
        </div>
        <div className="flex shrink-0 gap-1 opacity-60 transition group-hover:opacity-100">
          <button type="button" onClick={() => setEditing(true)} className="rounded-lg p-2 text-text-muted hover:bg-accent/10 hover:text-accent" aria-label="Edit inquiry">
            <Pencil size={16} />
          </button>
          <button type="button" onClick={onDelete} className="rounded-lg p-2 text-text-muted hover:bg-red-50 hover:text-red-600" aria-label="Delete inquiry">
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}
