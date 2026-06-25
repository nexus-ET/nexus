import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, CloudDownload, Loader2, Save } from 'lucide-react';
import { apiFetch, API_SYNC_TIMEOUT_MS } from '../../utils/api';

type LeadSyncMode = 'automated' | 'manual';
type LeadSyncIntervalUnit = 'minutes' | 'hours' | 'days' | 'weeks';

interface LeadSyncLastRunSummary {
  forms_processed?: number;
  leads_seen?: number;
  leads_created?: number;
  leads_skipped?: number;
  errors?: string[];
}

interface LeadSyncConfig {
  mode: LeadSyncMode;
  interval_value: number;
  interval_unit: LeadSyncIntervalUnit;
  interval_unit_label: string;
  last_run_at: string | null;
  last_run_summary: LeadSyncLastRunSummary | null;
  scheduler_enabled?: boolean;
  scheduler_active?: boolean;
  scheduler_is_leader?: boolean;
  configured_interval?: string | null;
  configured_schedule?: string | null;
  active_job_interval?: string | null;
  next_scheduled_run_at?: string | null;
}

const LEAD_SYNC_INTERVAL_OPTIONS: Array<{ value: LeadSyncIntervalUnit; label: string }> = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
];

const MetaLeadSyncPanel: React.FC = () => {
  const [leadSyncConfig, setLeadSyncConfig] = useState<LeadSyncConfig | null>(null);
  const [leadSyncDraft, setLeadSyncDraft] = useState<{
    mode: LeadSyncMode;
    interval_value: number;
    interval_unit: LeadSyncIntervalUnit;
  }>({ mode: 'automated', interval_value: 1, interval_unit: 'hours' });
  const [leadSyncLoading, setLeadSyncLoading] = useState(true);
  const [leadSyncSaving, setLeadSyncSaving] = useState(false);
  const [leadSyncRunning, setLeadSyncRunning] = useState(false);
  const [leadSyncMessage, setLeadSyncMessage] = useState<string | null>(null);
  const [leadSyncError, setLeadSyncError] = useState<string | null>(null);
  const [leadSyncUnavailable, setLeadSyncUnavailable] = useState<string | null>(null);

  const loadLeadSyncSettings = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLeadSyncLoading(true);
    }
    setLeadSyncUnavailable(null);

    try {
      const leadSyncData = (await apiFetch('settings/lead-sync')) as LeadSyncConfig;
      setLeadSyncConfig(leadSyncData);
      setLeadSyncDraft({
        mode: leadSyncData.mode,
        interval_value: leadSyncData.interval_value,
        interval_unit: leadSyncData.interval_unit,
      });
      setLeadSyncError(null);
    } catch (err: unknown) {
      setLeadSyncConfig(null);
      const message = err instanceof Error ? err.message : 'Failed to load lead sync settings.';
      if (/not found/i.test(message)) {
        setLeadSyncUnavailable(
          'Meta lead sync is not available on this server. Restart the NEXUS backend to load the latest routes.'
        );
      } else {
        setLeadSyncUnavailable(message);
      }
    } finally {
      if (!options?.silent) {
        setLeadSyncLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadLeadSyncSettings();
  }, [loadLeadSyncSettings]);

  useEffect(() => {
    if (leadSyncDraft.mode !== 'automated' || leadSyncUnavailable) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadLeadSyncSettings({ silent: true });
    }, 30_000);

    return () => window.clearInterval(timer);
  }, [leadSyncDraft.mode, leadSyncUnavailable, loadLeadSyncSettings]);

  const leadSyncScheduleHint = useMemo(() => {
    if (leadSyncDraft.mode !== 'automated' || !leadSyncConfig) {
      return null;
    }

    if (leadSyncConfig.scheduler_enabled === false) {
      return 'Automatic scheduling is disabled on the server (META_LEAD_SYNC_ENABLED=false).';
    }

    if (leadSyncConfig.scheduler_is_leader === false) {
      return 'This backend is not the scheduler leader — another NEXUS process is running automated sync. Stop duplicate backends and keep only one server on port 8002.';
    }

    if (leadSyncConfig.scheduler_active === false) {
      return 'Scheduler is not running. Keep the NEXUS backend process running and save the schedule again.';
    }

    const intervalNote = leadSyncConfig.configured_interval
      ? ` Saved: every ${leadSyncConfig.configured_interval}.`
      : leadSyncConfig.active_job_interval
        ? ` Active job: every ${leadSyncConfig.active_job_interval}.`
        : '';

    if (leadSyncConfig.next_scheduled_run_at) {
      return `Next automatic sync: ${new Date(leadSyncConfig.next_scheduled_run_at).toLocaleString()}.${intervalNote} Activity appears in Reports.`;
    }

    return `Automatic sync is armed.${intervalNote} Keep one backend running — activity appears in Reports.`;
  }, [leadSyncConfig, leadSyncDraft.mode]);

  const isLeadSyncDirty = useMemo(() => {
    if (!leadSyncConfig) return false;
    return (
      leadSyncDraft.mode !== leadSyncConfig.mode ||
      leadSyncDraft.interval_value !== leadSyncConfig.interval_value ||
      leadSyncDraft.interval_unit !== leadSyncConfig.interval_unit
    );
  }, [leadSyncConfig, leadSyncDraft]);

  const handleSaveLeadSyncSettings = async () => {
    setLeadSyncSaving(true);
    setLeadSyncError(null);
    setLeadSyncMessage(null);
    try {
      const updated = (await apiFetch('settings/lead-sync', {
        method: 'PUT',
        body: JSON.stringify(leadSyncDraft),
      })) as LeadSyncConfig;
      setLeadSyncConfig(updated);
      setLeadSyncDraft({
        mode: updated.mode,
        interval_value: updated.interval_value,
        interval_unit: updated.interval_unit,
      });
      setLeadSyncMessage(
        updated.mode === 'automated'
          ? `Automated sync enabled every ${updated.interval_value} ${updated.interval_unit}.`
          : 'Manual sync mode enabled. Use Sync Now to fetch leads.'
      );
    } catch (err: unknown) {
      setLeadSyncError(err instanceof Error ? err.message : 'Failed to save lead sync settings.');
    } finally {
      setLeadSyncSaving(false);
    }
  };

  const handleRunLeadSync = async () => {
    setLeadSyncRunning(true);
    setLeadSyncError(null);
    setLeadSyncMessage(null);
    try {
      const result = (await apiFetch('settings/lead-sync/run', {
        method: 'POST',
        timeoutMs: API_SYNC_TIMEOUT_MS,
      })) as LeadSyncLastRunSummary & {
        run_at: string;
        delta_since_label?: string | null;
        delta_is_initial_backfill?: boolean;
      };
      setLeadSyncConfig(prev =>
        prev
          ? {
              ...prev,
              last_run_at: result.run_at,
              last_run_summary: {
                forms_processed: result.forms_processed,
                leads_seen: result.leads_seen,
                leads_created: result.leads_created,
                leads_skipped: result.leads_skipped,
                errors: result.errors,
              },
            }
          : prev
      );
      const deltaHint =
        result.delta_since_label && result.delta_is_initial_backfill
          ? ` (initial window from ${result.delta_since_label})`
          : result.delta_since_label
            ? ` (delta since ${result.delta_since_label})`
            : '';
      setLeadSyncMessage(
        `Sync complete${deltaHint}: ${result.leads_created ?? 0} new, ${result.leads_skipped ?? 0} already in Nexus.`
      );
    } catch (err: unknown) {
      setLeadSyncError(err instanceof Error ? err.message : 'Lead sync failed.');
    } finally {
      setLeadSyncRunning(false);
    }
  };

  return (
    <div className="rounded-xl border border-border-subtle bg-card overflow-hidden shadow-sm">
      <div className="px-4 py-2.5 md:px-4 border-b border-border-subtle bg-surface-bg/80">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <div className="flex items-center gap-2 min-w-0">
            <CloudDownload size={16} className="text-accent shrink-0" />
            <h2 className="text-sm font-semibold text-text-main whitespace-nowrap">Meta Lead Sync</h2>
            <span className="hidden sm:inline text-[11px] text-text-muted truncate">
              Pull Facebook &amp; Instagram Lead Ads into Nexus
            </span>
          </div>
          {leadSyncConfig?.last_run_at ? (
            <p className="text-[10px] text-text-muted whitespace-nowrap shrink-0">
              Last sync: {new Date(leadSyncConfig.last_run_at).toLocaleString()}
            </p>
          ) : null}
        </div>
        {leadSyncScheduleHint ? (
          <p className="mt-1 text-[10px] text-text-muted leading-snug">{leadSyncScheduleHint}</p>
        ) : null}
      </div>

      <div className="px-4 py-3">
        {leadSyncLoading ? (
          <div className="flex items-center py-2 text-text-muted text-xs">
            <Loader2 size={14} className="animate-spin mr-2" />
            Loading lead sync settings...
          </div>
        ) : leadSyncUnavailable ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {leadSyncUnavailable}
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <div className="inline-flex rounded-md border border-border-subtle bg-surface-bg p-0.5 shrink-0">
                {(['automated', 'manual'] as LeadSyncMode[]).map(mode => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => {
                      setLeadSyncDraft(prev => ({ ...prev, mode }));
                      setLeadSyncMessage(null);
                    }}
                    className={`px-2.5 py-1 text-xs font-semibold rounded transition-colors ${
                      leadSyncDraft.mode === mode
                        ? 'bg-accent text-text-dark-bg shadow-sm'
                        : 'text-text-muted hover:text-text-main'
                    }`}
                  >
                    {mode === 'automated' ? 'Automated' : 'Manual'}
                  </button>
                ))}
              </div>

              {leadSyncDraft.mode === 'automated' ? (
                <>
                  <div className="flex items-center gap-2">
                    <label htmlFor="lead-sync-interval" className="text-xs text-text-muted whitespace-nowrap">
                      Every
                    </label>
                    <input
                      id="lead-sync-interval"
                      type="number"
                      min={1}
                      value={leadSyncDraft.interval_value}
                      onChange={event =>
                        setLeadSyncDraft(prev => ({
                          ...prev,
                          interval_value: Math.max(1, Number(event.target.value) || 1),
                        }))
                      }
                      className="w-14 rounded-md border border-border-subtle bg-surface-bg px-2 py-1 text-xs text-text-main focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/10"
                    />
                    <select
                      id="lead-sync-unit"
                      value={leadSyncDraft.interval_unit}
                      onChange={event =>
                        setLeadSyncDraft(prev => ({
                          ...prev,
                          interval_unit: event.target.value as LeadSyncIntervalUnit,
                        }))
                      }
                      className="w-24 rounded-md border border-border-subtle bg-surface-bg px-2 py-1 text-xs text-text-main focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/10"
                    >
                      {LEAD_SYNC_INTERVAL_OPTIONS.map(option => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveLeadSyncSettings}
                    disabled={leadSyncSaving || !isLeadSyncDirty}
                    title="Save sync schedule"
                    className="inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md bg-accent text-text-dark-bg text-xs font-semibold hover:opacity-90 disabled:opacity-50 shrink-0"
                  >
                    {leadSyncSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                    Save
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={handleRunLeadSync}
                    disabled={leadSyncRunning}
                    className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1 rounded-md bg-accent text-text-dark-bg text-xs font-semibold hover:opacity-90 disabled:opacity-50 shrink-0"
                  >
                    {leadSyncRunning ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <CloudDownload size={12} />
                    )}
                    Sync Now
                  </button>
                  <p className="text-[10px] text-text-muted leading-snug min-w-0 flex-1">
                    Delta sync — new leads only since last import.
                  </p>
                  {isLeadSyncDirty ? (
                    <button
                      type="button"
                      onClick={handleSaveLeadSyncSettings}
                      disabled={leadSyncSaving}
                      className="inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md border border-border-subtle bg-card text-xs font-semibold hover:bg-surface-bg disabled:opacity-50 shrink-0"
                    >
                      {leadSyncSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                      Save
                    </button>
                  ) : null}
                </>
              )}

              {leadSyncConfig?.last_run_summary ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-text-muted md:ml-auto">
                  <span>
                    Forms <strong className="text-text-main">{leadSyncConfig.last_run_summary.forms_processed ?? 0}</strong>
                  </span>
                  <span>
                    Seen <strong className="text-text-main">{leadSyncConfig.last_run_summary.leads_seen ?? 0}</strong>
                  </span>
                  <span>
                    New <strong className="text-text-main">{leadSyncConfig.last_run_summary.leads_created ?? 0}</strong>
                  </span>
                  <span>
                    Skipped <strong className="text-text-main">{leadSyncConfig.last_run_summary.leads_skipped ?? 0}</strong>
                  </span>
                  {(leadSyncConfig.last_run_summary.errors?.length ?? 0) > 0 ? (
                    <span className="text-amber-700">
                      {leadSyncConfig.last_run_summary.errors?.length} warning(s)
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>

            {leadSyncMessage ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-800 flex items-center gap-1.5">
                <CheckCircle2 size={12} className="shrink-0" />
                {leadSyncMessage}
              </div>
            ) : null}

            {leadSyncError ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700">
                {leadSyncError}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
};

export default MetaLeadSyncPanel;
