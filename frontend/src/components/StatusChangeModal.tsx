import React, { useEffect, useState } from 'react';
import { Loader2, UserCheck, UserX, X } from 'lucide-react';
import { apiFetch } from '../utils/api';

export interface StatusChangeReason {
  id: number;
  reason_type: string;
  reason: string;
  description: string;
}

type StatusChangeMode = 'activate' | 'deactivate';

interface StatusChangeModalProps {
  open: boolean;
  mode: StatusChangeMode;
  userName: string;
  saving?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: (statusChangeReasonId: number) => void;
}

const MODE_COPY: Record<
  StatusChangeMode,
  { title: string; reasonType: string; submitLabel: string; icon: typeof UserX }
> = {
  deactivate: {
    title: 'Deactivate User',
    reasonType: 'Deactivate',
    submitLabel: 'Deactivate',
    icon: UserX,
  },
  activate: {
    title: 'Activate User',
    reasonType: 'Activate',
    submitLabel: 'Activate',
    icon: UserCheck,
  },
};

const StatusChangeModal: React.FC<StatusChangeModalProps> = ({
  open,
  mode,
  userName,
  saving = false,
  error = null,
  onClose,
  onConfirm,
}) => {
  const [reasons, setReasons] = useState<StatusChangeReason[]>([]);
  const [loadingReasons, setLoadingReasons] = useState(true);
  const [selectedReasonId, setSelectedReasonId] = useState<number | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const copy = MODE_COPY[mode];
  const SubmitIcon = copy.icon;

  useEffect(() => {
    if (!open) return;

    setSelectedReasonId(null);
    setLocalError(null);

    const loadReasons = async () => {
      try {
        setLoadingReasons(true);
        const data = await apiFetch(
          `users/status-change-reasons?reason_type=${encodeURIComponent(copy.reasonType)}`
        );
        const list = Array.isArray(data) ? (data as StatusChangeReason[]) : [];
        setReasons(list);
        if (list.length > 0) {
          setSelectedReasonId(list[0].id);
        }
      } catch (err: unknown) {
        setLocalError(err instanceof Error ? err.message : 'Failed to load status change reasons.');
      } finally {
        setLoadingReasons(false);
      }
    };

    loadReasons();
  }, [open, copy.reasonType]);

  if (!open) return null;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedReasonId) {
      setLocalError('Please select a reason.');
      return;
    }
    setLocalError(null);
    onConfirm(selectedReasonId);
  };

  const displayError = error || localError;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md bg-card border border-border-subtle rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
          <div>
            <h3 className="text-sm font-bold text-text-main">{copy.title}</h3>
            <p className="text-[11px] text-text-muted mt-1">{userName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {displayError && (
            <div className="p-3 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
              {displayError}
            </div>
          )}

          <fieldset>
            <legend className="block text-xs font-semibold text-text-muted mb-2">
              Select Reason
            </legend>
            {loadingReasons ? (
              <div className="flex items-center gap-2 text-sm text-text-muted py-2">
                <Loader2 size={14} className="animate-spin" />
                Loading reasons...
              </div>
            ) : reasons.length === 0 ? (
              <p className="text-sm text-text-muted">No reasons configured.</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {reasons.map(item => (
                  <label
                    key={item.id}
                    className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                      selectedReasonId === item.id
                        ? 'border-accent bg-accent/5'
                        : 'border-border-subtle hover:bg-surface-bg/50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="status-change-reason"
                      value={item.id}
                      checked={selectedReasonId === item.id}
                      onChange={() => setSelectedReasonId(item.id)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-semibold text-text-main">
                        {item.reason}
                      </span>
                      <span className="block text-[11px] text-text-muted mt-0.5">
                        {item.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-border-subtle text-sm font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || loadingReasons || reasons.length === 0}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold hover:opacity-90 transition-all disabled:opacity-50 ${
                mode === 'deactivate'
                  ? 'bg-alert text-white'
                  : 'bg-accent text-text-dark-bg'
              }`}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <SubmitIcon size={14} />}
              {copy.submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default StatusChangeModal;
