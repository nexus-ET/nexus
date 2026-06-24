import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, X } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface PipelineStage {
  key: string;
  label: string;
}

interface PipelineOutcome {
  key: string;
  label: string;
  default_next_stage: string;
  action_items: string[];
}

interface PipelineConfig {
  stages: PipelineStage[];
  outcomes: PipelineOutcome[];
}

interface SessionWrapUpDrawerProps {
  open: boolean;
  bookingId: number | null;
  candidateName: string;
  onClose: () => void;
  onSubmitted: () => Promise<void> | void;
}

const SessionWrapUpDrawer: React.FC<SessionWrapUpDrawerProps> = ({
  open,
  bookingId,
  candidateName,
  onClose,
  onSubmitted,
}) => {
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcomeKey, setOutcomeKey] = useState('');
  const [nextStage, setNextStage] = useState('');
  const [notes, setNotes] = useState('');
  const [selectedActions, setSelectedActions] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setLoadingConfig(true);
    setError(null);
    apiFetch('pipeline/config')
      .then(data => {
        const payload = data as PipelineConfig;
        setConfig(payload);
        const firstOutcome = payload.outcomes[0];
        if (firstOutcome) {
          setOutcomeKey(firstOutcome.key);
          setNextStage(firstOutcome.default_next_stage);
          setSelectedActions(firstOutcome.action_items);
        }
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to load pipeline config.');
      })
      .finally(() => setLoadingConfig(false));
  }, [open]);

  const selectedOutcome = useMemo(
    () => config?.outcomes.find(item => item.key === outcomeKey) ?? null,
    [config, outcomeKey]
  );

  useEffect(() => {
    if (!selectedOutcome) return;
    setNextStage(selectedOutcome.default_next_stage);
    setSelectedActions(selectedOutcome.action_items);
  }, [selectedOutcome?.key]);

  const toggleActionItem = (item: string) => {
    setSelectedActions(prev =>
      prev.includes(item) ? prev.filter(value => value !== item) : [...prev, item]
    );
  };

  const handleSubmit = async () => {
    if (!bookingId || !outcomeKey || !nextStage) return;
    try {
      setSubmitting(true);
      setError(null);
      await apiFetch(`sessions/${bookingId}/complete`, {
        method: 'POST',
        body: JSON.stringify({
          outcome_key: outcomeKey,
          next_stage: nextStage,
          notes: notes.trim() || null,
          action_items: selectedActions,
        }),
      });
      await onSubmitted();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete session.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open || !bookingId) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <aside className="fixed top-0 right-0 h-full w-full max-w-md bg-card border-l border-border-subtle shadow-2xl z-50 flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Session Wrap-up</p>
            <h2 className="text-lg font-bold text-text-main">{candidateName}</h2>
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 custom-scrollbar">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
          )}

          {loadingConfig ? (
            <div className="flex items-center gap-2 text-sm text-text-muted py-8">
              <Loader2 size={16} className="animate-spin" />
              Loading wrap-up options...
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">Session Outcome</label>
                <select
                  value={outcomeKey}
                  onChange={event => setOutcomeKey(event.target.value)}
                  className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
                >
                  {(config?.outcomes ?? []).map(outcome => (
                    <option key={outcome.key} value={outcome.key}>
                      {outcome.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">Next Pipeline Stage</label>
                <select
                  value={nextStage}
                  onChange={event => setNextStage(event.target.value)}
                  className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
                >
                  {(config?.stages ?? []).map(stage => (
                    <option key={stage.key} value={stage.key}>
                      {stage.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">Action Items</label>
                <div className="space-y-2 rounded-lg border border-border-subtle p-3 bg-surface-bg/40">
                  {(selectedOutcome?.action_items ?? []).map(item => (
                    <label key={item} className="flex items-start gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedActions.includes(item)}
                        onChange={() => toggleActionItem(item)}
                        className="mt-0.5"
                      />
                      <span>{item}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">Counsellor Notes</label>
                <textarea
                  value={notes}
                  onChange={event => setNotes(event.target.value)}
                  rows={4}
                  placeholder="Summary of the session, blockers, and next steps..."
                  className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm resize-y"
                />
              </div>
            </>
          )}
        </div>

        <div className="px-5 py-4 border-t border-border-subtle bg-surface-bg/50">
          <button
            type="button"
            disabled={submitting || loadingConfig || !outcomeKey || !nextStage}
            onClick={handleSubmit}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-text-dark-bg disabled:opacity-60"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
            Submit Wrap-up
          </button>
        </div>
      </aside>
    </>
  );
};

export default SessionWrapUpDrawer;
