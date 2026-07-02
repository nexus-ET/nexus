import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, UserPlus, UserRound } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { categoryBadgeClass } from '../utils/statusBadges';

interface StatusDefinition {
  id: number;
  stage_name: string;
  category: string;
  description?: string | null;
  next_stage_id?: number | null;
  is_terminal?: boolean;
}

interface DataExchangeItem {
  id: string;
  title: string;
  url: string;
  shared_by: 'student' | 'admin';
  created_at: string;
  file_name?: string | null;
}

interface SessionOutcomeData {
  status_definitions: StatusDefinition[];
  current_status_definition_id?: number | null;
  suggested_next_status_definition_id?: number | null;
  shared_by_student: DataExchangeItem[];
  shared_by_admin: DataExchangeItem[];
  can_update_status: boolean;
}

interface SessionOutcomeSectionProps {
  bookingId: number;
  onStatusUpdated?: () => void | Promise<void>;
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

export const getSelectableStatusOptions = (
  definitions: StatusDefinition[],
  currentStatusId: number | null | undefined
): StatusDefinition[] => {
  if (!currentStatusId) return definitions;

  const current = definitions.find(item => item.id === currentStatusId);
  if (!current) return definitions;

  if (current.stage_name === 'Counselling: Scheduled' && current.next_stage_id) {
    const next = definitions.find(item => item.id === current.next_stage_id);
    return next ? [next] : [];
  }

  if (current.next_stage_id) {
    const next = definitions.find(item => item.id === current.next_stage_id);
    return next ? [next] : definitions;
  }

  return definitions;
};

const SessionOutcomeSection: React.FC<SessionOutcomeSectionProps> = ({
  bookingId,
  onStatusUpdated,
}) => {
  const [activity, setActivity] = useState<SessionOutcomeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextStatusId, setNextStatusId] = useState<number | ''>('');
  const [statusNotes, setStatusNotes] = useState('');
  const [submittingStatus, setSubmittingStatus] = useState(false);

  const loadActivity = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = (await apiFetch(`bookings/mine/${bookingId}/activity`)) as SessionOutcomeData;
      setActivity(data);

      const selectable = getSelectableStatusOptions(
        data.status_definitions,
        data.current_status_definition_id
      );
      const suggested =
        data.suggested_next_status_definition_id ??
        selectable[0]?.id ??
        data.status_definitions.find(item => item.id === data.current_status_definition_id)
          ?.next_stage_id ??
        '';
      setNextStatusId(suggested || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session outcome data.');
      setActivity(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadActivity();
  }, [bookingId]);

  const selectableOptions = useMemo(
    () =>
      activity
        ? getSelectableStatusOptions(activity.status_definitions, activity.current_status_definition_id)
        : [],
    [activity]
  );

  const currentStatus = useMemo(
    () =>
      activity?.status_definitions.find(item => item.id === activity.current_status_definition_id) ??
      null,
    [activity]
  );

  const selectedStatus = useMemo(
    () => selectableOptions.find(item => item.id === nextStatusId) ?? null,
    [selectableOptions, nextStatusId]
  );

  const handleUpdateStatus = async () => {
    if (!nextStatusId) return;
    try {
      setSubmittingStatus(true);
      setError(null);
      await apiFetch(`bookings/mine/${bookingId}/status`, {
        method: 'POST',
        body: JSON.stringify({
          status_definition_id: Number(nextStatusId),
          notes: statusNotes.trim() || null,
        }),
      });
      await onStatusUpdated?.();
      await loadActivity();
      setStatusNotes('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status.');
    } finally {
      setSubmittingStatus(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10 text-text-muted">
        <Loader2 size={20} className="animate-spin mr-2" />
        Loading session outcome…
      </div>
    );
  }

  if (!activity) {
    return error ? (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
    ) : null;
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {activity.can_update_status && (
        <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-4 space-y-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">
              Update Session Outcome
            </p>
            <p className="text-xs text-violet-900/80 mt-0.5">
              Move the candidate to the next pipeline status after completing the session.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-start gap-3">
            <div className="flex-1 min-w-0 space-y-1">
              <label className="block">
                <span className="text-xs font-medium text-text-muted">Next stage</span>
                <select
                  value={nextStatusId}
                  onChange={event =>
                    setNextStatusId(event.target.value ? Number(event.target.value) : '')
                  }
                  className="mt-1 w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm"
                >
                  {selectableOptions.length === 0 ? (
                    <option value="">No next stages available</option>
                  ) : (
                    selectableOptions.map(stage => (
                      <option key={stage.id} value={stage.id}>
                        {stage.stage_name}
                      </option>
                    ))
                  )}
                </select>
              </label>
              {selectedStatus?.description ? (
                <p className="text-[11px] text-text-muted leading-snug">{selectedStatus.description}</p>
              ) : null}
            </div>

            {currentStatus ? (
              <div className="shrink-0 sm:pt-5">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-1">
                  Current status
                </p>
                <span
                  className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${categoryBadgeClass(
                    currentStatus.category
                  )}`}
                >
                  {currentStatus.stage_name}
                </span>
              </div>
            ) : null}
          </div>

          <label className="block space-y-1">
            <span className="text-xs font-medium text-text-muted">Notes (optional)</span>
            <textarea
              value={statusNotes}
              onChange={event => setStatusNotes(event.target.value)}
              rows={2}
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm resize-y"
              placeholder="Notes for this status change…"
            />
          </label>

          <button
            type="button"
            onClick={handleUpdateStatus}
            disabled={submittingStatus || !nextStatusId}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-700 px-3 py-2 text-sm font-semibold text-white hover:bg-violet-800 disabled:opacity-60"
          >
            {submittingStatus ? <Loader2 size={16} className="animate-spin" /> : null}
            Apply Status
          </button>
        </div>
      )}

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text-main">Data Exchange</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl border border-border-subtle p-3 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted flex items-center gap-1">
              <UserRound size={12} />
              Shared by Student
            </p>
            {activity.shared_by_student.length === 0 ? (
              <p className="text-xs text-text-muted italic">No student files yet.</p>
            ) : (
              activity.shared_by_student.map(item => (
                <a
                  key={item.id}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-border-subtle bg-card px-3 py-2 text-xs hover:bg-surface-bg"
                >
                  <p className="font-medium text-text-main">{item.title}</p>
                  <p className="text-text-muted mt-0.5">{formatTime(item.created_at)}</p>
                </a>
              ))
            )}
          </div>
          <div className="rounded-xl border border-border-subtle p-3 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted flex items-center gap-1">
              <UserPlus size={12} />
              Shared by Admin
            </p>
            {activity.shared_by_admin.length === 0 ? (
              <p className="text-xs text-text-muted italic">No admin files yet.</p>
            ) : (
              activity.shared_by_admin.map(item => (
                <a
                  key={item.id}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-border-subtle bg-card px-3 py-2 text-xs hover:bg-surface-bg"
                >
                  <p className="font-medium text-text-main">{item.title}</p>
                  <p className="text-text-muted mt-0.5">{formatTime(item.created_at)}</p>
                </a>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
};

export default SessionOutcomeSection;
