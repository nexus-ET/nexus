import React, { useEffect, useState } from 'react';
import { Loader2, UserPlus, UserRound } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';

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
  previous_stage_id?: number | null;
  appointment_date?: string | null;
  calendar_today?: string | null;
  forward_status_changes_blocked?: boolean;
  backward_status_ids?: number[];
  shared_by_student: DataExchangeItem[];
  shared_by_admin: DataExchangeItem[];
  can_update_status: boolean;
}

interface SessionOutcomeSectionProps {
  bookingId: number;
  /** @deprecated Status updates are saved from the Session form. Kept for call-site compatibility. */
  onStatusUpdated?: () => void | Promise<void>;
}


export const getSelectableStatusOptions = (
  definitions: StatusDefinition[],
  currentStatusId: number | null | undefined
): StatusDefinition[] => {
  if (!currentStatusId) return definitions;
  return definitions.filter(item => item.id !== currentStatusId);
};

export const resolveSuggestedNextStatusId = (
  definitions: StatusDefinition[],
  currentStatusId: number | null | undefined,
  suggestedNextStatusDefinitionId?: number | null
): number | '' => {
  if (suggestedNextStatusDefinitionId) {
    return suggestedNextStatusDefinitionId;
  }

  const current = definitions.find(item => item.id === currentStatusId);
  if (current?.next_stage_id) {
    return current.next_stage_id;
  }

  return '';
};

export const isUpcomingAppointment = (
  appointmentDate?: string | null,
  calendarToday?: string | null
): boolean => {
  if (!appointmentDate || !calendarToday) return false;
  return appointmentDate > calendarToday;
};

export const COUNSELLING_FOLLOW_UP_STATUS_ID = 15;

export const isForwardStageSelection = (
  currentStatusId: number | null | undefined,
  targetStatusId: number | '',
  backwardStatusIds: number[] = []
): boolean => {
  if (!currentStatusId || !targetStatusId) return false;

  const current = Number(currentStatusId);
  const target = Number(targetStatusId);
  if (target === current) return false;
  if (backwardStatusIds.includes(target)) return false;
  if (target < current) return false;
  return true;
};

/** Stages that must not be selected before the appointment date (forward + follow-up). */
export const isStageBlockedBeforeAppointment = (
  currentStatusId: number | null | undefined,
  targetStatusId: number | '',
  backwardStatusIds: number[] = []
): boolean => {
  if (!targetStatusId) return false;
  if (Number(targetStatusId) === COUNSELLING_FOLLOW_UP_STATUS_ID) return true;
  return isForwardStageSelection(currentStatusId, targetStatusId, backwardStatusIds);
};

export const resolvePreselectedStageId = (
  data: Pick<
    SessionOutcomeData,
    | 'status_definitions'
    | 'current_status_definition_id'
    | 'suggested_next_status_definition_id'
    | 'previous_stage_id'
    | 'appointment_date'
    | 'calendar_today'
    | 'backward_status_ids'
  >,
  selectable: StatusDefinition[]
): number | '' => {
  const upcoming = isUpcomingAppointment(data.appointment_date, data.calendar_today);
  if (!upcoming) {
    const suggested = resolveSuggestedNextStatusId(
      data.status_definitions,
      data.current_status_definition_id,
      data.suggested_next_status_definition_id
    );
    if (suggested && selectable.some(item => item.id === suggested)) {
      return suggested;
    }
    return selectable[0]?.id ?? '';
  }

  const backwardCandidates = [
    data.previous_stage_id,
    ...(data.backward_status_ids ?? []),
    ...selectable.filter(stage => stage.id < Number(data.current_status_definition_id)).map(stage => stage.id),
  ]
    .filter((value): value is number => typeof value === 'number')
    .filter(id => id !== COUNSELLING_FOLLOW_UP_STATUS_ID);

  const allowed = backwardCandidates.find(id => selectable.some(item => item.id === id));
  return allowed ?? '';
};

export const FORWARD_STATUS_BLOCKED_MESSAGE =
  'Forward stage and follow-up changes are not allowed before the appointment date. You may move the candidate to an earlier stage.';

const SessionOutcomeSection: React.FC<SessionOutcomeSectionProps> = ({
  bookingId,
}) => {
  const { formatDateTime } = useBusinessTimezone();
  const [activity, setActivity] = useState<SessionOutcomeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadActivity = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = (await apiFetch(`bookings/mine/${bookingId}/activity`)) as SessionOutcomeData;
        if (!cancelled) setActivity(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load session outcome data.');
          setActivity(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void loadActivity();
    return () => {
      cancelled = true;
    };
  }, [bookingId]);

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
                  <p className="text-text-muted mt-0.5">{formatDateTime(item.created_at, { second: undefined })}</p>
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
                  <p className="text-text-muted mt-0.5">{formatDateTime(item.created_at, { second: undefined })}</p>
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
