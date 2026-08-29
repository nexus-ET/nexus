import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import type { InquiryFaqPayload } from './types';

interface Props {
  path: string;
  initial?: Pick<InquiryFaqPayload, 'question' | 'answer'>;
  submitLabel?: string;
  busy?: boolean;
  onSubmit: (payload: InquiryFaqPayload) => Promise<void>;
  onCancel?: () => void;
}

export default function FaqEditor({
  path,
  initial,
  submitLabel = 'Save inquiry',
  busy,
  onSubmit,
  onCancel,
}: Props) {
  const [question, setQuestion] = useState(initial?.question || '');
  const [answer, setAnswer] = useState(initial?.answer || '');
  const [error, setError] = useState('');

  useEffect(() => {
    setQuestion(initial?.question || '');
    setAnswer(initial?.answer || '');
    setError('');
  }, [initial?.question, initial?.answer, path]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 5 || !answer.trim()) {
      setError('Enter a complete question and answer.');
      return;
    }
    setError('');
    try {
      await onSubmit({ path, question: question.trim(), answer: answer.trim() });
      if (!initial) {
        setQuestion('');
        setAnswer('');
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this inquiry.');
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <label className="block text-xs font-semibold uppercase tracking-wide text-text-muted">
        Question
        <textarea
          value={question}
          onChange={event => setQuestion(event.target.value)}
          rows={2}
          maxLength={5000}
          placeholder="What do students or counselors frequently ask?"
          className="mt-1.5 w-full resize-y rounded-xl border border-border-subtle bg-surface-bg px-3 py-2.5 text-sm normal-case tracking-normal text-text-main outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
        />
      </label>
      <label className="block text-xs font-semibold uppercase tracking-wide text-text-muted">
        Answer
        <textarea
          value={answer}
          onChange={event => setAnswer(event.target.value)}
          rows={5}
          maxLength={30000}
          placeholder="Provide clear, reusable guidance…"
          className="mt-1.5 w-full resize-y rounded-xl border border-border-subtle bg-surface-bg px-3 py-2.5 text-sm normal-case tracking-normal text-text-main outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
        />
      </label>
      {error ? <p role="alert" className="text-sm text-alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        {onCancel ? (
          <button type="button" onClick={onCancel} disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-sm font-semibold text-text-muted hover:text-text-main">
            <X size={15} /> Cancel
          </button>
        ) : null}
        <button type="submit" disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-sm font-semibold text-text-dark-bg hover:brightness-95 disabled:opacity-60">
          <Check size={15} /> {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  );
}
