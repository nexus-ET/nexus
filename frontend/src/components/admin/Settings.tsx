import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Save, Shield } from 'lucide-react';
import { apiFetch } from '../../utils/api';

interface RetentionResponse {
  audit_log_retention_days: number;
}

const Settings: React.FC = () => {
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
      const data = (await apiFetch('admin/audit-logs/retention')) as RetentionResponse;
      setRetentionDays(data.audit_log_retention_days);
      setSavedDays(data.audit_log_retention_days);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load audit settings.');
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
      const data = (await apiFetch('admin/audit-logs/retention', {
        method: 'PUT',
        body: JSON.stringify({ audit_log_retention_days: retentionDays }),
      })) as RetentionResponse;
      setRetentionDays(data.audit_log_retention_days);
      setSavedDays(data.audit_log_retention_days);
      setMessage(`Retention updated to ${data.audit_log_retention_days} days.`);
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
          <Shield size={16} />
          Audit Log Retention
        </h2>
        <p className="text-xs text-text-muted mt-1">
          Entries older than this threshold are permanently removed by the daily cleanup job (03:15 UTC).
        </p>
      </div>
      <div className="p-4">
        {loading ? (
          <div className="flex items-center text-sm text-text-muted py-4">
            <Loader2 size={16} className="animate-spin mr-2" />
            Loading audit settings...
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-end gap-3 max-w-md">
            <div className="flex-1">
              <label htmlFor="audit-retention-days" className="block text-sm font-medium text-text-main">
                Retention (days)
              </label>
              <input
                id="audit-retention-days"
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

export default Settings;
