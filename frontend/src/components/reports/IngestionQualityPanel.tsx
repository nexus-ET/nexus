import React from 'react';
import { Loader2, ShieldCheck, ShieldAlert } from 'lucide-react';
import { useIngestionQuality } from '../../hooks/useIngestionQuality';

interface IngestionQualityPanelProps {
  startDate?: string;
  endDate?: string;
}

const IngestionQualityPanel: React.FC<IngestionQualityPanelProps> = ({ startDate, endDate }) => {
  const { data, isLoading, error } = useIngestionQuality({ startDate, endDate });

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border-subtle bg-card px-4 py-3 text-sm text-text-muted flex items-center gap-2">
        <Loader2 size={16} className="animate-spin" />
        Loading ingestion quality metrics…
      </div>
    );
  }

  if (error || !data) return null;

  return (
    <div className="rounded-xl border border-border-subtle bg-card p-4 space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text-main">Ingestion quality</h2>
          <p className="text-xs text-text-muted mt-1">
            Clean vs quarantined ratio from staged Meta payloads (automated and manual sync).
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <div className="inline-flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-emerald-800">
            <ShieldCheck size={16} />
            Clean {data.clean_ratio_percent}%
          </div>
          <div className="inline-flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-amber-900">
            <ShieldAlert size={16} />
            Quarantined {data.quarantine_ratio_percent}%
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Metric label="Received" value={data.total_received} />
        <Metric label="Promoted" value={data.total_promoted} />
        <Metric label="Quarantined" value={data.total_quarantined} />
        <Metric label="Pending processing" value={data.total_pending} />
      </div>

      {data.quarantine_reasons.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">
            Quarantine reasons
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.quarantine_reasons.map(reason => (
              <span
                key={reason.reason}
                className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-bg px-3 py-1 text-xs text-text-main"
              >
                {reason.label}
                <span className="font-semibold tabular-nums">{reason.count}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
    <div className="text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
    <div className="text-lg font-semibold tabular-nums text-text-main">{value.toLocaleString()}</div>
  </div>
);

export default IngestionQualityPanel;
