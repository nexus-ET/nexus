import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, Loader2, Sparkles, X } from 'lucide-react';
import IntakeSessionWorkspace from './IntakeSessionWorkspace';
import SessionOutcomeSection from './SessionOutcomeSection';
import { useLeadBookings } from '../hooks/useLeadBookings';
import { useLeadProfileBooking } from '../hooks/useProspects';
import { apiFetch, hasValidSession } from '../utils/api';

export type CounsellingSessionDrawerProps = {
  open: boolean;
  bookingId?: number | null;
  candidateId?: number | null;
  candidateName?: string | null;
  dateLabel?: string | null;
  timeLabel?: string | null;
  onClose: () => void;
  onStatusUpdated?: () => void | Promise<void>;
};

type BookingHeader = {
  id: number;
  candidate_name: string;
  date_label?: string | null;
  time_label?: string | null;
  lead_id?: number | null;
};

const CounsellingSessionDrawer: React.FC<CounsellingSessionDrawerProps> = ({
  open,
  bookingId: bookingIdProp,
  candidateId,
  candidateName: candidateNameProp,
  dateLabel,
  timeLabel,
  onClose,
  onStatusUpdated,
}) => {
  const paramBookingId =
    bookingIdProp != null && Number.isFinite(bookingIdProp) && bookingIdProp > 0
      ? bookingIdProp
      : null;

  const [activeBookingId, setActiveBookingId] = useState<number | null>(paramBookingId);

  useEffect(() => {
    if (!open) {
      setActiveBookingId(null);
      return;
    }
    setActiveBookingId(paramBookingId);
  }, [open, paramBookingId]);

  const profileBookingQuery = useLeadProfileBooking(
    open && activeBookingId == null ? candidateId ?? null : null,
    open && activeBookingId == null && candidateId != null
  );

  const resolvedBookingId =
    activeBookingId ??
    (profileBookingQuery.data?.id != null ? Number(profileBookingQuery.data.id) : null);

  const [header, setHeader] = useState<BookingHeader | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const chronologyLeadId =
    candidateId ??
    header?.lead_id ??
    (profileBookingQuery.data?.lead_id != null
      ? Number(profileBookingQuery.data.lead_id)
      : null);

  const meetingsQuery = useLeadBookings(open ? chronologyLeadId : null);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !hasValidSession() || resolvedBookingId == null) return;
    let cancelled = false;

    const load = async () => {
      setLoadError(null);
      try {
        const data = (await apiFetch(`bookings/mine/${resolvedBookingId}/activity`)) as {
          booking?: BookingHeader & { lead_id?: number | null };
          candidate_name?: string;
        };
        if (cancelled) return;
        const booking = data.booking;
        setHeader({
          id: resolvedBookingId,
          candidate_name:
            booking?.candidate_name ||
            data.candidate_name ||
            candidateNameProp ||
            profileBookingQuery.data?.candidate_name ||
            'Candidate',
          date_label: booking?.date_label ?? dateLabel ?? null,
          time_label: booking?.time_label ?? timeLabel ?? null,
          lead_id: booking?.lead_id ?? chronologyLeadId ?? null,
        });
      } catch (err) {
        if (cancelled) return;
        setHeader({
          id: resolvedBookingId,
          candidate_name:
            candidateNameProp ||
            profileBookingQuery.data?.candidate_name ||
            'Candidate',
          date_label: dateLabel ?? null,
          time_label: timeLabel ?? null,
          lead_id: chronologyLeadId ?? null,
        });
        setLoadError(err instanceof Error ? err.message : 'Could not load session details.');
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [
    open,
    resolvedBookingId,
    candidateNameProp,
    dateLabel,
    timeLabel,
    profileBookingQuery.data?.candidate_name,
    chronologyLeadId,
  ]);

  const resolving =
    open &&
    activeBookingId == null &&
    paramBookingId == null &&
    candidateId != null &&
    profileBookingQuery.isLoading;

  const resolveFailed =
    open &&
    resolvedBookingId == null &&
    !profileBookingQuery.isLoading &&
    (paramBookingId != null || candidateId != null) &&
    (profileBookingQuery.isError ||
      (paramBookingId == null && candidateId != null && resolvedBookingId == null));

  const candidateName = useMemo(
    () =>
      header?.candidate_name ||
      candidateNameProp ||
      profileBookingQuery.data?.candidate_name ||
      'Candidate',
    [header?.candidate_name, candidateNameProp, profileBookingQuery.data?.candidate_name]
  );

  const scheduleLabel = [
    header?.date_label || dateLabel,
    header?.time_label || timeLabel,
  ]
    .filter(Boolean)
    .join(' · ');

  const meetings = meetingsQuery.data?.items ?? [];

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex justify-end bg-black/40"
      onMouseDown={onClose}
      role="presentation"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="counselling-session-drawer-title"
        className="flex h-dvh max-h-dvh w-full max-w-[min(120rem,98vw)] flex-col overflow-hidden border-l border-border-subtle bg-card shadow-2xl"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
              View Session
            </p>
            <h2
              id="counselling-session-drawer-title"
              className="mt-0.5 flex items-center gap-2 text-lg font-semibold text-text-main"
            >
              <Sparkles size={18} className="shrink-0 text-violet-700" />
              Counselling Session
            </h2>
            <p className="mt-0.5 truncate text-sm text-text-muted">
              {candidateName}
              {scheduleLabel ? ` · ${scheduleLabel}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"
            aria-label="Close counselling session"
          >
            <X size={16} />
          </button>
        </div>

        {chronologyLeadId != null && (meetingsQuery.isLoading || meetings.length > 0) ? (
          <div className="shrink-0 border-b border-border-subtle bg-card px-5 py-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wide text-text-muted">
              <CalendarDays size={12} />
              Meeting chronology
            </div>
            {meetingsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <Loader2 size={14} className="animate-spin" />
                Loading meetings…
              </div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
                {meetings.map(meeting => {
                  const active = meeting.id === resolvedBookingId;
                  return (
                    <button
                      key={meeting.id}
                      type="button"
                      onClick={() => setActiveBookingId(meeting.id)}
                      className={`min-w-[9.5rem] shrink-0 rounded-xl border px-3 py-2 text-left transition ${
                        active
                          ? 'border-accent bg-accent/10 shadow-sm'
                          : 'border-border-subtle bg-surface-bg hover:border-accent/40'
                      }`}
                    >
                      <p
                        className={`text-xs font-semibold ${
                          active ? 'text-accent' : 'text-text-main'
                        }`}
                      >
                        {meeting.date_label || `Booking #${meeting.id}`}
                      </p>
                      <p className="mt-0.5 text-[11px] text-text-muted">
                        {[meeting.time_label, meeting.admin_name, meeting.session_status_label]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pt-5 pb-28 custom-scrollbar">
          {resolving ? (
            <div className="flex min-h-[40vh] items-center justify-center gap-2 text-text-muted">
              <Loader2 className="h-5 w-5 animate-spin" />
              Opening counselling session…
            </div>
          ) : resolveFailed ? (
            <p className="text-sm text-rose-700">
              No counselling booking is available for this candidate on your account.
            </p>
          ) : resolvedBookingId == null ? (
            <p className="text-sm text-text-muted">No session selected.</p>
          ) : (
            <div className="space-y-8" key={resolvedBookingId}>
              {loadError ? (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  {loadError}
                </p>
              ) : null}
              <IntakeSessionWorkspace
                bookingId={resolvedBookingId}
                candidateName={candidateName}
                onStatusUpdated={onStatusUpdated}
              />
              <div className="border-t border-border-subtle pt-6">
                <SessionOutcomeSection bookingId={resolvedBookingId} />
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>,
    document.body
  );
};

export default CounsellingSessionDrawer;
