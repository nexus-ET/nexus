import { useEffect, useId } from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, Loader2, X } from 'lucide-react';
import { useLeadBookings, type LeadBookingSummary } from '../hooks/useLeadBookings';

export type LeadBookingsModalProps = {
  open: boolean;
  leadId: number | null;
  leadName?: string | null;
  onClose: () => void;
  onSelectBooking: (booking: LeadBookingSummary) => void;
};

export default function LeadBookingsModal({
  open,
  leadId,
  leadName,
  onClose,
  onSelectBooking,
}: LeadBookingsModalProps) {
  const titleId = useId();
  const query = useLeadBookings(open ? leadId : null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open || leadId == null || typeof document === 'undefined') return null;

  const items = query.data?.items ?? [];

  return createPortal(
    <div
      className="fixed inset-0 z-[280] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[min(36rem,90vh)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl"
        onMouseDown={event => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-start gap-3 border-b border-border-subtle px-5 py-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
            <CalendarDays size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-bold text-text-main">
              Bookings
            </h2>
            <p className="mt-0.5 truncate text-sm text-text-muted">
              {leadName || `Lead #${leadId}`}
              {query.data?.total != null ? ` · ${query.data.total} total` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted hover:bg-surface-bg hover:text-text-main"
            aria-label="Close bookings"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {query.isLoading ? (
            <div className="flex items-center justify-center gap-2 px-5 py-12 text-sm text-text-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading bookings…
            </div>
          ) : query.isError ? (
            <p className="m-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
              {query.error instanceof Error ? query.error.message : 'Could not load bookings.'}
            </p>
          ) : items.length === 0 ? (
            <p className="m-4 rounded-lg border border-border-subtle bg-surface-bg/50 px-4 py-8 text-center text-sm text-text-muted">
              No counselling bookings yet for this student.
            </p>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {items.map(booking => (
                <li key={booking.id}>
                  <button
                    type="button"
                    onClick={() => onSelectBooking(booking)}
                    className="flex w-full flex-col items-start gap-1 px-5 py-3 text-left transition hover:bg-surface-bg"
                  >
                    <span className="text-sm font-semibold text-text-main">
                      {[booking.date_label, booking.time_label].filter(Boolean).join(' · ') ||
                        `Booking #${booking.id}`}
                    </span>
                    <span className="text-xs text-text-muted">
                      {[
                        booking.admin_name ? `with ${booking.admin_name}` : null,
                        booking.session_status_label || booking.status || null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
