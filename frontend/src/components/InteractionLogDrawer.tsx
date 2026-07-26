import React, { useEffect, useState } from 'react';
import { ExternalLink, FileText, Loader2, MessageSquare, Mic, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import HeadlessScrollArea from './HeadlessScrollArea';

type TimelineKind = 'whatsapp' | 'session_note' | 'audio' | 'system';

interface TimelineItem {
  id: string;
  kind: TimelineKind;
  participant: string;
  participant_label: string;
  text: string;
  created_at: string;
  media_url?: string | null;
  file_name?: string | null;
}

interface InteractionLogData {
  booking: {
    id: number;
    candidate_name: string;
    time_label: string;
    date_label: string;
  };
  timeline: TimelineItem[];
}

interface InteractionLogDrawerProps {
  open: boolean;
  bookingId: number | null;
  onClose: () => void;
  /** `schedule` = Manage Appointments (works before assignment). Default: My Bookings. */
  scope?: 'mine' | 'schedule';
}

const timelineIcon = (kind: TimelineKind) => {
  switch (kind) {
    case 'audio':
      return <Mic size={12} />;
    case 'session_note':
      return <FileText size={12} />;
    default:
      return <MessageSquare size={12} />;
  }
};

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

const InteractionLogDrawer: React.FC<InteractionLogDrawerProps> = ({
  open,
  bookingId,
  onClose,
  scope = 'mine',
}) => {
  const [interaction, setInteraction] = useState<InteractionLogData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !bookingId) {
      setInteraction(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const path =
      scope === 'schedule'
        ? `bookings/${bookingId}/interactions`
        : `bookings/mine/${bookingId}/interactions`;

    apiFetch(path)
      .then(data => {
        if (!cancelled) setInteraction(data as InteractionLogData);
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load interaction log.');
          setInteraction(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, bookingId, scope]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open || !bookingId) return null;

  const booking = interaction?.booking;

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-[60]" onClick={onClose} role="presentation" />
      <aside className="fixed top-0 right-0 h-full w-full max-w-2xl bg-card border-l border-border-subtle shadow-2xl z-[70] flex flex-col min-h-0 overflow-hidden">
        <div className="shrink-0 flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Interaction Log</p>
            <h2 className="text-lg font-bold text-text-main truncate">
              {booking?.candidate_name ?? 'Loading…'}
            </h2>
            {booking && (
              <p className="text-xs text-text-muted mt-1">
                {booking.date_label} · {booking.time_label}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-surface-bg shrink-0">
            <X size={18} />
          </button>
        </div>

        <HeadlessScrollArea className="flex-1 min-h-0 h-0" viewportClassName="px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-text-muted">
              <Loader2 size={22} className="animate-spin mr-2" />
              Loading…
            </div>
          ) : error && !interaction ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          ) : interaction ? (
            <section className="space-y-3 pb-24">
              <h3 className="text-sm font-semibold text-text-main">Communication History</h3>
              <p className="text-xs text-text-muted">
                All interactions between Nexus and the student for this booking.
              </p>
              {interaction.timeline.length === 0 ? (
                <p className="text-sm text-text-muted italic">No communication history yet.</p>
              ) : (
                <div className="space-y-2">
                  {interaction.timeline.map(item => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-border-subtle bg-surface-bg/40 p-3"
                    >
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-card px-2 py-0.5 text-[11px] font-semibold text-text-main">
                          {timelineIcon(item.kind)}
                          {item.participant_label}
                        </span>
                        <span className="text-[11px] text-text-muted">{formatTime(item.created_at)}</span>
                      </div>
                      {item.text && (
                        <p className="text-sm text-text-main whitespace-pre-wrap break-words">{item.text}</p>
                      )}
                      {item.media_url && (
                        <a
                          href={item.media_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 mt-2 text-xs text-accent hover:underline"
                        >
                          <ExternalLink size={12} />
                          {item.file_name || 'Open attachment'}
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          ) : null}

          {error && interaction && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 mt-4 mb-24">
              {error}
            </div>
          )}
        </HeadlessScrollArea>
      </aside>
    </>
  );
};

export default InteractionLogDrawer;
