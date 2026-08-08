import React, { useEffect } from 'react';
import { Sparkles, X } from 'lucide-react';
import IntakeSessionWorkspace from './IntakeSessionWorkspace';
import SessionOutcomeSection from './SessionOutcomeSection';

interface CounsellingSessionModalProps {
  open: boolean;
  bookingId: number | null;
  candidateName: string;
  dateLabel?: string | null;
  timeLabel?: string | null;
  onClose: () => void;
  onStatusUpdated?: () => void;
}

const CounsellingSessionModal: React.FC<CounsellingSessionModalProps> = ({
  open,
  bookingId,
  candidateName,
  dateLabel,
  timeLabel,
  onClose,
  onStatusUpdated,
}) => {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open || !bookingId) return null;

  const scheduleLabel = [dateLabel, timeLabel].filter(Boolean).join(' · ');

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="counselling-session-title"
    >
      <div className="w-full max-w-[min(120rem,98vw)] max-h-[92vh] rounded-2xl border border-border-subtle bg-card shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle bg-surface-bg shrink-0">
          <div>
            <h3
              id="counselling-session-title"
              className="text-lg font-semibold text-text-main flex items-center gap-2"
            >
              <Sparkles size={18} className="text-violet-700" />
              Counselling Session
            </h3>
            <p className="text-sm text-text-muted mt-0.5">
              {candidateName}
              {scheduleLabel ? ` · ${scheduleLabel}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"
            aria-label="Close counselling session dialog"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-5 py-5 space-y-8">
          <IntakeSessionWorkspace
            bookingId={bookingId}
            candidateName={candidateName}
            onStatusUpdated={onStatusUpdated}
          />
          <div className="border-t border-border-subtle pt-6">
            <SessionOutcomeSection bookingId={bookingId} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default CounsellingSessionModal;
