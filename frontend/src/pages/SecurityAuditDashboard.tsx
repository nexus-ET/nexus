import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  RefreshCw,
  Shield,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';

interface SecurityCheckResult {
  name: string;
  category: string;
  passed: boolean;
  message: string;
}

interface SecurityAuditRun {
  id: number;
  status: string;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  red_flags: boolean;
  triggered_by: string;
  triggered_by_user_id?: number | null;
  checks: SecurityCheckResult[];
  started_at: string;
  completed_at?: string | null;
}

interface SecurityAuditRunsResponse {
  runs: SecurityAuditRun[];
  latest_status?: string | null;
}

interface SecurityAuditStatusResponse {
  latest_run: SecurityAuditRun | null;
  fortress_healthy: boolean;
}

interface SecurityAuditTriggerResponse {
  run: SecurityAuditRun;
  alert_sent: boolean;
}

const categoryLabels: Record<string, string> = {
  rate_limiting: 'Rate Limiting',
  idor: 'IDOR',
  prompt_injection: 'Prompt Injection / AI',
  headers: 'Security Headers',
};

const SecurityAuditDashboard: React.FC = () => {
  const { formatDateTime } = useBusinessTimezone();
  const [runs, setRuns] = useState<SecurityAuditRun[]>([]);
  const [latestStatus, setLatestStatus] = useState<SecurityAuditStatusResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setAccessDenied(false);
      const [statusData, runsData] = await Promise.all([
        apiFetch('security-audit/status') as Promise<SecurityAuditStatusResponse>,
        apiFetch('security-audit/runs') as Promise<SecurityAuditRunsResponse>,
      ]);
      setLatestStatus(statusData);
      const items = Array.isArray(runsData.runs) ? runsData.runs : [];
      setRuns(items);
      setSelectedRunId(prev => prev ?? items[0]?.id ?? null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load security audit data.';
      if (message.toLowerCase().includes('super admin')) {
        setAccessDenied(true);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const selectedRun = useMemo(
    () => runs.find(run => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId]
  );

  const handleRunAudit = async () => {
    try {
      setRunning(true);
      setError(null);
      setSuccessMessage(null);
      const data = (await apiFetch('security-audit/run', { method: 'POST' })) as SecurityAuditTriggerResponse;
      setSuccessMessage(
        data.alert_sent
          ? `Audit run #${data.run.id} completed with red flags. Urgent alert dispatched.`
          : `Audit run #${data.run.id} completed successfully.`
      );
      await loadDashboard();
      setSelectedRunId(data.run.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to run security audit.');
    } finally {
      setRunning(false);
    }
  };

  if (accessDenied) {
    return (
      <div className="p-8">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <p className="font-semibold">Super Admin access required</p>
          <p className="text-sm mt-1">The Security Audit dashboard is restricted to Super Admins.</p>
        </div>
      </div>
    );
  }

  const fortressHealthy = latestStatus?.fortress_healthy ?? true;
  const latestRun = latestStatus?.latest_run ?? selectedRun;

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield className="text-accent" size={22} />
            <h1 className="text-2xl font-bold text-text-main">Security Audit Fortress</h1>
          </div>
          <p className="text-sm text-text-muted">
            Automated validation for rate limits, IDOR controls, prompt injection guardrails, and security headers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadDashboard}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle text-sm hover:bg-surface-bg"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleRunAudit}
            disabled={running}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-60"
          >
            {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Run Audit Now
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}
      {successMessage && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {successMessage}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          className={`rounded-xl border p-5 ${
            fortressHealthy
              ? 'border-emerald-200 bg-emerald-50'
              : 'border-red-200 bg-red-50'
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            {fortressHealthy ? (
              <CheckCircle2 className="text-emerald-600" size={20} />
            ) : (
              <ShieldAlert className="text-red-600" size={20} />
            )}
            <p className="font-semibold text-text-main">Fortress Status</p>
          </div>
          <p className={`text-2xl font-bold ${fortressHealthy ? 'text-emerald-700' : 'text-red-700'}`}>
            {fortressHealthy ? 'Healthy' : 'Red Flags Detected'}
          </p>
        </div>

        <div className="rounded-xl border border-border-subtle bg-card p-5">
          <p className="text-sm text-text-muted mb-1">Latest Run</p>
          <p className="text-2xl font-bold text-text-main">
            {latestRun ? `#${latestRun.id}` : '—'}
          </p>
          <p className="text-xs text-text-muted mt-1 capitalize">
            {latestRun?.triggered_by ?? 'none'} · {latestRun?.status ?? 'pending'}
          </p>
        </div>

        <div className="rounded-xl border border-border-subtle bg-card p-5">
          <p className="text-sm text-text-muted mb-1">Checks Passed</p>
          <p className="text-2xl font-bold text-text-main">
            {latestRun ? `${latestRun.passed_checks}/${latestRun.total_checks}` : '—'}
          </p>
          {latestRun?.red_flags && (
            <p className="text-xs text-red-600 mt-1 inline-flex items-center gap-1">
              <AlertTriangle size={12} />
              Emergency alert channel may have been triggered
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 rounded-xl border border-border-subtle bg-card overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle bg-surface-bg">
            <p className="font-semibold text-sm text-text-main">Past Audit Runs</p>
          </div>
          <div className="max-h-[520px] overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="p-6 text-sm text-text-muted flex items-center gap-2">
                <Loader2 size={16} className="animate-spin" />
                Loading runs...
              </div>
            ) : runs.length === 0 ? (
              <p className="p-6 text-sm text-text-muted italic">No audit runs yet. Trigger one manually.</p>
            ) : (
              runs.map(run => (
                <button
                  key={run.id}
                  type="button"
                  onClick={() => setSelectedRunId(run.id)}
                  className={`w-full text-left px-4 py-3 border-b border-border-subtle/60 hover:bg-surface-bg transition-colors ${
                    selectedRunId === run.id ? 'bg-surface-bg' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-sm text-text-main">Run #{run.id}</span>
                    {run.status === 'pass' ? (
                      <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                    ) : (
                      <XCircle size={16} className="text-red-600 shrink-0" />
                    )}
                  </div>
                  <p className="text-xs text-text-muted mt-1">
                    {formatDateTime(run.started_at)} · {run.triggered_by}
                  </p>
                  <p className="text-xs text-text-muted">
                    {run.passed_checks}/{run.total_checks} passed
                  </p>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="lg:col-span-2 rounded-xl border border-border-subtle bg-card overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle bg-surface-bg flex items-center justify-between">
            <p className="font-semibold text-sm text-text-main">
              {selectedRun ? `Run #${selectedRun.id} Checks` : 'Audit Checks'}
            </p>
            {selectedRun && (
              <span
                className={`text-xs font-bold uppercase px-2 py-1 rounded-full ${
                  selectedRun.status === 'pass'
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-red-100 text-red-700'
                }`}
              >
                {selectedRun.status}
              </span>
            )}
          </div>
          <div className="p-4 space-y-3 max-h-[520px] overflow-y-auto custom-scrollbar">
            {!selectedRun ? (
              <p className="text-sm text-text-muted italic">Select an audit run to inspect individual checks.</p>
            ) : (
              selectedRun.checks.map(check => (
                <div
                  key={`${check.category}-${check.name}`}
                  className={`rounded-lg border px-4 py-3 ${
                    check.passed
                      ? 'border-emerald-200 bg-emerald-50/40'
                      : 'border-red-200 bg-red-50/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-text-main">
                        {categoryLabels[check.category] ?? check.category}: {check.name}
                      </p>
                      <p className="text-xs text-text-muted mt-1">{check.message}</p>
                    </div>
                    {check.passed ? (
                      <CheckCircle2 size={18} className="text-emerald-600 shrink-0 mt-0.5" />
                    ) : (
                      <XCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SecurityAuditDashboard;
