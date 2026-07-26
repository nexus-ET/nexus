import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Save, ShieldAlert } from 'lucide-react';
import { apiFetch } from '../../utils/api';

interface RetentionResponse {
  exception_log_retention_days: number;
  deleted_count?: number | null;
}

interface ExceptionRetentionSettingsProps {
  onPurged?: () => void;
}

const ExceptionRetentionSettings: React.FC<ExceptionRetentionSettingsProps> = ({ onPurged }) => {
  const [retentionDays, setRetentionDays] = useState(90);
  const [savedDays, setSavedDays] = useState(90);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRetention = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = (await apiFetch('reports/exception-logs/retention')) as RetentionResponse;
      setRetentionDays(data.exception_log_retention_days);
      setSavedDays(data.exception_log_retention_days);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load retention setting.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRetention();
  }, [loadRetention]);

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const data = (await apiFetch('reports/exception-logs/retention', {
        method: 'PUT',
        body: JSON.stringify({ exception_log_retention_days: retentionDays }),
      })) as RetentionResponse;
      setRetentionDays(data.exception_log_retention_days);
      setSavedDays(data.exception_log_retention_days);
      const purged = data.deleted_count ?? 0;
      setMessage(
        purged > 0
          ? `Retention updated to ${data.exception_log_retention_days} days. Permanently deleted ${purged.toLocaleString()} older entr${purged === 1 ? 'y' : 'ies'}.`
          : `Retention updated to ${data.exception_log_retention_days} days. No older entries to delete.`
      );
      onPurged?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save retention setting.');
    } finally {
      setSaving(false);
    }
  };

  const isDirty = retentionDays !== savedDays;

  return (
    <div className="rounded-xl border border-border-subtle bg-card overflow-hidden">
      <div className="border-b border-border-subtle bg-surface-bg px-4 py-3">
        <h2 className="text-sm font-semibold text-text-main flex items-center gap-2">
          <ShieldAlert size={16} />
          Exception Log Retention
        </h2>
        <p className="text-xs text-text-muted mt-1">
          Entries older than this threshold are permanently deleted when you save, and again by the
          daily cleanup job (03:20 UTC).
        </p>
      </div>
      <div className="p-4">
        {loading ? (
          <div className="flex items-center text-sm text-text-muted py-4">
            <Loader2 size={16} className="animate-spin mr-2" />
            Loading retention setting...
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-end gap-3 max-w-md">
            <div className="flex-1">
              <label htmlFor="exception-retention-days" className="block text-sm font-medium text-text-main">
                Retention (days)
              </label>
              <input
                id="exception-retention-days"
                type="number"
                min={1}
                max={3650}
                value={retentionDays}
                onChange={event =>
                  setRetentionDays(Math.max(1, Math.min(3650, Number(event.target.value) || 1)))
                }
                className="mt-1.5 w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving || !isDirty}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save
            </button>
          </div>
        )}
        {message ? <p className="mt-3 text-xs text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-3 text-xs text-red-700">{error}</p> : null}
      </div>
    </div>
  );
};

export default ExceptionRetentionSettings;
