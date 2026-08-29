import { useEffect } from 'react';
import { Loader2, Map, X } from 'lucide-react';
import { categoryBadgeClass } from '../utils/statusBadges';
import { useStudentJourney } from '../hooks/useStudentStatus';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import HeadlessScrollArea from './HeadlessScrollArea';

export type StudentJourneyPanelProps = {
  open: boolean;
  studentId: number | null;
  studentName?: string | null;
  onClose: () => void;
};


export default function StudentJourneyPanel({
  open,
  studentId,
  studentName,
  onClose,
}: StudentJourneyPanelProps) {
  const { formatDateTime } = useBusinessTimezone();
  const { data, isLoading, error, refetch } = useStudentJourney(open ? studentId : null);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open && studentId != null) refetch();
  }, [open, studentId, refetch]);

  if (!open || studentId == null) return null;

  const items = data?.items ?? [];

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-[60]" onClick={onClose} role="presentation" />
      <aside
        className="fixed top-0 right-0 h-full w-full max-w-[65.625rem] bg-card border-l border-border-subtle shadow-2xl z-[70] flex flex-col min-h-0 overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="student-journey-title"
      >
        <div className="shrink-0 flex items-center gap-3 px-5 py-4 border-b border-border-subtle bg-surface-bg/40">
          <Map size={16} className="text-accent shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold uppercase tracking-wide text-text-muted">Student Journey</p>
            <h2 id="student-journey-title" className="text-lg font-bold text-text-main truncate">
              {studentName || `Student #${studentId}`}
            </h2>
            <p className="text-sm text-text-muted">
              {items.length} status {items.length === 1 ? 'entry' : 'entries'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-surface-bg shrink-0"
            aria-label="Close journey panel"
          >
            <X size={18} />
          </button>
        </div>

        <div className="shrink-0 hidden sm:grid grid-cols-[minmax(0,1.4fr)_minmax(110px,0.7fr)_minmax(90px,0.5fr)_minmax(0,1fr)] gap-2 px-5 py-2 border-b border-border-subtle bg-surface-bg/30 text-sm font-semibold uppercase tracking-wide text-text-muted">
          <span>Status</span>
          <span>When</span>
          <span>By</span>
          <span>Notes</span>
        </div>

        <HeadlessScrollArea className="flex-1 min-h-0 h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-text-muted text-sm">
              <Loader2 size={18} className="animate-spin mr-2" />
              Loading journey…
            </div>
          ) : error ? (
            <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error instanceof Error ? error.message : 'Failed to load journey.'}
            </div>
          ) : items.length === 0 ? (
            <div className="m-4 rounded-lg border border-border-subtle bg-surface-bg/40 p-6 text-center text-sm text-text-muted italic">
              No status changes recorded yet.
            </div>
          ) : (
            <ul className="divide-y divide-border-subtle pb-24">
              {items.map((item, index) => (
                <li
                  key={`${item.id}-${item.created_at}`}
                  className={`grid grid-cols-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(110px,0.7fr)_minmax(90px,0.5fr)_minmax(0,1fr)] gap-1 sm:gap-2 px-5 py-2 text-sm hover:bg-surface-bg/50 ${
                    index === items.length - 1 ? 'bg-accent/5' : ''
                  }`}
                >
                  <div className="min-w-0 flex items-start gap-2">
                    <span className="text-sm font-mono text-text-muted w-5 shrink-0 pt-0.5">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <span
                        className={`inline-flex items-center rounded border px-1.5 py-0.5 text-sm font-semibold leading-tight ${categoryBadgeClass(
                          item.category
                        )}`}
                      >
                        {item.stage_name}
                      </span>
                      {item.description ? (
                        <p className="text-sm text-text-muted mt-0.5 line-clamp-1">{item.description}</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="sm:pt-0.5 pl-7 sm:pl-0 text-sm text-text-muted whitespace-nowrap">
                    {formatDateTime(item.created_at)}
                  </div>
                  <div className="sm:pt-0.5 pl-7 sm:pl-0 text-sm text-text-main truncate">
                    {item.changed_by_label}
                    <span className="text-text-muted">
                      {item.changed_by_type === 'system' ? ' · auto' : ' · admin'}
                    </span>
                  </div>
                  <div className="sm:pt-0.5 pl-7 sm:pl-0 text-sm text-text-muted line-clamp-2">
                    {item.comments || '—'}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </HeadlessScrollArea>
      </aside>
    </>
  );
}
