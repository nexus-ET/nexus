import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, MessageSquareText, X } from 'lucide-react';
import {
  useCounselorFollowupStatuses,
  useCreateLeadFollowup,
  useLeadFollowups,
} from '../hooks/useCounselorFollowups';
import HeadlessScrollArea from './HeadlessScrollArea';

interface CounselorFollowupDrawerProps {
  open: boolean;
  leadId: number | null;
  leadName?: string | null;
  onClose: () => void;
  onFollowupSaved?: () => void;
}

const formatTime = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const formatDateOnly = (value: string): string => {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
};

/** Local calendar date as YYYY-MM-DD (avoids UTC day-shift). */
function todayLocalIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Split status master templates into Points Discussed / Action Items. */
function splitTemplateDescription(raw: string): { points: string; actions: string } {
  const text = (raw || '').trim();
  if (!text) return { points: '', actions: '' };
  const match = text.match(/^(.*?)(?:\s*Action\s+Items\s*:\s*)([\s\S]*)$/i);
  if (!match) {
    const pointsOnly = text.replace(/^\s*Points\s+Discussed\s*:\s*/i, '').trim();
    return { points: pointsOnly || text, actions: '' };
  }
  const points = match[1].replace(/^\s*Points\s+Discussed\s*:\s*/i, '').trim();
  const actions = match[2].trim();
  return { points: points || text, actions };
}

const CounselorFollowupDrawer: React.FC<CounselorFollowupDrawerProps> = ({
  open,
  leadId,
  leadName,
  onClose,
  onFollowupSaved,
}) => {
  const statusesQuery = useCounselorFollowupStatuses(open);
  const followupsQuery = useLeadFollowups(leadId, open);
  const createMutation = useCreateLeadFollowup();

  const [statusId, setStatusId] = useState<number | ''>('');
  const [pointsDiscussed, setPointsDiscussed] = useState('');
  const [actionItems, setActionItems] = useState('');
  const [nextFollowupDate, setNextFollowupDate] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const statuses = statusesQuery.data?.items ?? [];
  const minFollowupDate = useMemo(() => todayLocalIso(), [open]);

  const resetForm = () => {
    setStatusId('');
    setPointsDiscussed('');
    setActionItems('');
    setNextFollowupDate('');
    setFormError(null);
  };

  useEffect(() => {
    if (!open) resetForm();
  }, [open, leadId]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const selectedStatus = useMemo(
    () => statuses.find(item => item.id === statusId) ?? null,
    [statuses, statusId]
  );

  const handleStatusChange = (nextId: string) => {
    if (!nextId) {
      setStatusId('');
      setPointsDiscussed('');
      setActionItems('');
      return;
    }
    const id = Number(nextId);
    setStatusId(id);
    const match = statuses.find(item => item.id === id);
    if (match) {
      const split = splitTemplateDescription(match.default_description);
      setPointsDiscussed(split.points);
      setActionItems(split.actions);
    }
    setFormError(null);
  };

  const handleSave = async () => {
    if (!leadId) return;
    if (!statusId) {
      setFormError('Select a follow-up status.');
      return;
    }
    const points = pointsDiscussed.trim();
    if (!points) {
      setFormError('Points Discussed cannot be empty.');
      return;
    }
    const actions = actionItems.trim();
    const followupDate = nextFollowupDate.trim();
    const today = todayLocalIso();

    if (followupDate && followupDate < today) {
      setFormError('Next Follow-up Date cannot be in the past.');
      return;
    }
    if (actions && !followupDate) {
      setFormError('Select a Next Follow-up Date (today or a future date) when Action Items are set.');
      return;
    }
    if (actions && followupDate < today) {
      setFormError('Next Follow-up Date must be today or a future date.');
      return;
    }

    setFormError(null);
    try {
      await createMutation.mutateAsync({
        leadId,
        payload: {
          status_id: Number(statusId),
          points_discussed: points,
          action_items: actions || null,
          target_completion_date: followupDate || null,
        },
      });
      resetForm();
      onFollowupSaved?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save notes.');
    }
  };

  if (!open || !leadId) return null;

  const timeline = followupsQuery.data?.items ?? [];

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-[60]" onClick={onClose} role="presentation" />
      <aside className="fixed top-0 right-0 h-full w-full max-w-6xl bg-card border-l border-border-subtle shadow-2xl z-[70] flex flex-col min-h-0 overflow-hidden">
        <div className="shrink-0 flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Counselor Notes
            </p>
            <h2 className="text-lg font-bold text-text-main truncate">
              {leadName?.trim() || `Lead #${leadId}`}
            </h2>
            <p className="text-xs text-text-muted mt-1">
              {followupsQuery.data?.total ?? 0} interaction
              {(followupsQuery.data?.total ?? 0) === 1 ? '' : 's'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-surface-bg shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="shrink-0 border-b border-border-subtle px-5 py-4 space-y-3 bg-surface-bg/30">
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1" htmlFor="followup-status">
              Follow-up Status
            </label>
            <select
              id="followup-status"
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              value={statusId === '' ? '' : String(statusId)}
              onChange={e => handleStatusChange(e.target.value)}
              disabled={statusesQuery.isLoading || createMutation.isPending}
            >
              <option value="">Select status…</option>
              {statuses.map(status => (
                <option key={status.id} value={status.id}>
                  {status.status_heading}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              className="block text-xs font-semibold text-text-muted mb-1"
              htmlFor="followup-points"
            >
              Points Discussed
            </label>
            <textarea
              id="followup-points"
              className="w-full min-h-[96px] rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main resize-y"
              value={pointsDiscussed}
              onChange={e => setPointsDiscussed(e.target.value)}
              placeholder={
                selectedStatus
                  ? 'Edit points discussed as needed…'
                  : 'Select a status to inject a template…'
              }
              disabled={createMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3">
            <div>
              <label
                className="block text-xs font-semibold text-text-muted mb-1"
                htmlFor="followup-actions"
              >
                Action Items
              </label>
              <textarea
                id="followup-actions"
                className="w-full min-h-[96px] rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main resize-y"
                value={actionItems}
                onChange={e => setActionItems(e.target.value)}
                placeholder={
                  selectedStatus
                    ? 'Edit action items as needed…'
                    : 'Select a status to inject a template…'
                }
                disabled={createMutation.isPending}
              />
            </div>
            <div>
              <label
                className="block text-xs font-semibold text-text-muted mb-1"
                htmlFor="followup-next-date"
              >
                Next Follow-up Date
                {actionItems.trim() ? <span className="text-red-600"> *</span> : null}
              </label>
              <input
                id="followup-next-date"
                type="date"
                min={minFollowupDate}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
                value={nextFollowupDate}
                onChange={e => {
                  const next = e.target.value;
                  if (next && next < todayLocalIso()) {
                    setFormError('Next Follow-up Date cannot be in the past.');
                    return;
                  }
                  setNextFollowupDate(next);
                  setFormError(null);
                }}
                required={Boolean(actionItems.trim())}
                disabled={createMutation.isPending}
              />
            </div>
          </div>

          {formError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {formError}
            </div>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
              onClick={() => void handleSave()}
              disabled={createMutation.isPending || !statusId}
            >
              {createMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              Save Notes
            </button>
          </div>
        </div>

        <HeadlessScrollArea className="flex-1 min-h-0 h-0" viewportClassName="px-5 py-4">
          {followupsQuery.isLoading ? (
            <div className="flex items-center justify-center py-16 text-text-muted">
              <Loader2 size={22} className="animate-spin mr-2" />
              Loading history…
            </div>
          ) : followupsQuery.isError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {followupsQuery.error instanceof Error
                ? followupsQuery.error.message
                : 'Failed to load follow-up history.'}
            </div>
          ) : timeline.length === 0 ? (
            <p className="text-sm text-text-muted italic py-8 text-center">
              No counselor notes yet. Add the first follow-up above.
            </p>
          ) : (
            <section className="space-y-3 pb-8">
              <h3 className="text-sm font-semibold text-text-main">Interaction History</h3>
              <p className="text-xs text-text-muted">Newest first</p>
              <div className="space-y-2">
                {timeline.map(item => (
                  <article
                    key={item.id}
                    className="rounded-xl border border-border-subtle bg-surface-bg/40 p-3"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-card px-2.5 py-0.5 text-[11px] font-semibold text-text-main">
                        <MessageSquareText size={12} />
                        {item.status_heading}
                      </span>
                      <span className="text-[11px] text-text-muted whitespace-nowrap">
                        {formatTime(item.created_at)}
                      </span>
                    </div>
                    <div className="text-sm text-text-main whitespace-pre-wrap break-words space-y-2">
                      <p>
                        <span className="font-semibold">Points Discussed: </span>
                        {item.points_discussed}
                      </p>
                      {item.action_items ? (
                        <p>
                          <span className="font-semibold">Action Items: </span>
                          {item.action_items}
                        </p>
                      ) : null}
                      {item.target_completion_date ? (
                        <p>
                          <span className="font-semibold">Next Follow-up: </span>
                          {formatDateOnly(item.target_completion_date)}
                        </p>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
        </HeadlessScrollArea>
      </aside>
    </>
  );
};

export default CounselorFollowupDrawer;
