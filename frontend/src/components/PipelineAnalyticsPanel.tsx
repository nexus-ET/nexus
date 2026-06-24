import React from 'react';
import { AlertTriangle, BarChart3, Loader2 } from 'lucide-react';

interface CounsellorConversion {
  counsellor_id: number;
  counsellor_name: string;
  counselling_sessions: number;
  moved_to_applied: number;
  conversion_rate: number;
}

interface StalledCandidate {
  lead_id: number;
  full_name: string;
  days_in_stage: number | null;
  admission_stage: string | null;
}

interface OutcomeFrequency {
  outcome_key: string;
  label: string;
  count: number;
}

export interface PipelineAnalyticsData {
  conversion_by_counsellor: CounsellorConversion[];
  overall_counselling_moves: number;
  average_days_in_stage: Record<string, number>;
  stalled_candidates: StalledCandidate[];
  outcome_frequency: OutcomeFrequency[];
  awaiting_docs_reminder_pending: number;
}

interface PipelineAnalyticsPanelProps {
  analytics: PipelineAnalyticsData | null;
  loading: boolean;
}

const stageLabels: Record<string, string> = {
  COUNSELLING: 'Counselling',
  AWAITING_DOCS: 'Awaiting Docs',
  APPLIED: 'Applied',
};

const PipelineAnalyticsPanel: React.FC<PipelineAnalyticsPanelProps> = ({ analytics, loading }) => {
  const maxOutcomeCount = Math.max(...(analytics?.outcome_frequency.map(item => item.count) ?? [1]), 1);

  return (
    <div className="rounded-2xl border border-border-subtle bg-card p-5 space-y-5">
      <div className="flex items-center gap-2">
        <BarChart3 size={18} className="text-accent" />
        <div>
          <h2 className="text-lg font-semibold text-text-main">Pipeline Analytics</h2>
          <p className="text-xs text-text-muted">Counsellor effectiveness and funnel health</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-text-muted py-6">
          <Loader2 size={16} className="animate-spin" />
          Loading analytics...
        </div>
      ) : !analytics ? (
        <p className="text-sm text-text-muted italic">Analytics unavailable.</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
              <p className="text-xs text-text-muted mb-1">Counselling → Applied Moves</p>
              <p className="text-2xl font-bold text-text-main">{analytics.overall_counselling_moves}</p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
              <p className="text-xs text-text-muted mb-1">Stalled in Counselling (&gt;14 days)</p>
              <p className="text-2xl font-bold text-amber-700">{analytics.stalled_candidates.length}</p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
              <p className="text-xs text-text-muted mb-1">Doc Reminders Pending</p>
              <p className="text-2xl font-bold text-text-main">{analytics.awaiting_docs_reminder_pending}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-border-subtle p-4">
              <p className="text-sm font-semibold text-text-main mb-3">Conversion Rate per Counsellor</p>
              {analytics.conversion_by_counsellor.length === 0 ? (
                <p className="text-xs text-text-muted italic">No completed wrap-ups yet.</p>
              ) : (
                <div className="space-y-2">
                  {analytics.conversion_by_counsellor.map(row => (
                    <div key={row.counsellor_id} className="flex items-center justify-between gap-3 text-sm">
                      <span className="truncate">{row.counsellor_name}</span>
                      <span className="font-semibold text-accent shrink-0">{row.conversion_rate}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-border-subtle p-4">
              <p className="text-sm font-semibold text-text-main mb-3">Average Time in Stage (days)</p>
              <div className="space-y-2 text-sm">
                {Object.entries(analytics.average_days_in_stage).map(([stage, days]) => (
                  <div key={stage} className="flex items-center justify-between gap-3">
                    <span>{stageLabels[stage] ?? stage}</span>
                    <span className="font-semibold">{days}d</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border-subtle p-4">
            <p className="text-sm font-semibold text-text-main mb-3">Outcome Frequency</p>
            {analytics.outcome_frequency.length === 0 ? (
              <p className="text-xs text-text-muted italic">Complete sessions to populate outcome trends.</p>
            ) : (
              <div className="space-y-3">
                {analytics.outcome_frequency.map(item => (
                  <div key={item.outcome_key}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span>{item.label}</span>
                      <span className="font-semibold">{item.count}</span>
                    </div>
                    <div className="h-2 rounded-full bg-surface-bg overflow-hidden">
                      <div
                        className="h-full bg-accent rounded-full"
                        style={{ width: `${Math.max(8, (item.count / maxOutcomeCount) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {analytics.stalled_candidates.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
              <p className="text-sm font-semibold text-amber-900 flex items-center gap-2 mb-2">
                <AlertTriangle size={16} />
                Stalled Candidates
              </p>
              <div className="space-y-1">
                {analytics.stalled_candidates.slice(0, 5).map(candidate => (
                  <p key={candidate.lead_id} className="text-xs text-amber-900">
                    {candidate.full_name} — {candidate.days_in_stage ?? '?'} days in{' '}
                    {stageLabels[candidate.admission_stage ?? ''] ?? candidate.admission_stage}
                  </p>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default PipelineAnalyticsPanel;
