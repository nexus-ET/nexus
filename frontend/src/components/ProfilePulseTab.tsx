import React from 'react';
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2 } from 'lucide-react';
import { useProfilePulse } from '../hooks/useProfilePulse';
import type { ProfilePanelTab } from '../types/profilePanel';
import type { ProfileSectionStatus } from '../utils/profilePulse';

interface ProfilePulseTabProps {
  bookingId: number;
  statusCategory?: string | null;
  onNavigateTab?: (tab: ProfilePanelTab) => void;
}

const STATUS_META: Record<
  ProfileSectionStatus,
  { label: string; badgeClass: string; icon: React.ReactNode }
> = {
  completed: {
    label: 'Completed',
    badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    icon: <CheckCircle2 size={14} className="text-emerald-600" />,
  },
  in_progress: {
    label: 'In Progress',
    badgeClass: 'bg-sky-50 text-sky-800 border-sky-200',
    icon: <CircleDashed size={14} className="text-sky-600" />,
  },
  action_required: {
    label: 'Action Required',
    badgeClass: 'bg-amber-50 text-amber-900 border-amber-300',
    icon: <AlertTriangle size={14} className="text-amber-600" />,
  },
};

const ProfilePulseTab: React.FC<ProfilePulseTabProps> = ({
  bookingId,
  statusCategory,
  onNavigateTab,
}) => {
  const { data, isLoading, error, refetch, isFetching } = useProfilePulse(
    bookingId,
    statusCategory,
    true
  );

  if (isLoading && !data) {
    return (
      <div className="flex flex-1 items-center justify-center py-16 text-text-muted">
        <Loader2 size={20} className="animate-spin mr-2" />
        <span className="text-sm">Loading profile pulse…</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error instanceof Error ? error.message : 'Failed to load profile pulse.'}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const actionSections = data.sections.filter(section => section.status === 'action_required');

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-y-auto custom-scrollbar px-3 py-4 sm:px-4">
      <div className="mx-auto w-full max-w-none space-y-4">
        <section className="rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50 to-card p-4 sm:p-5 shadow-sm">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-800">
            Personal Vision Statement
          </p>
          <p className="mt-2 text-base sm:text-lg font-semibold leading-relaxed text-text-main">
            {data.visionStatement}
          </p>
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <section className="rounded-xl border border-border-subtle bg-card p-4 sm:p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-bold text-text-main">Profile Completeness</h3>
                <p className="text-sm text-text-muted mt-1">
                  Based on mandatory fields across all profile sections.
                </p>
              </div>
              <span className="text-2xl font-bold text-sky-800">{data.overallCompletionPercent}%</span>
            </div>
            <div className="mt-4 h-3 rounded-full bg-surface-bg overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-sky-500 to-emerald-500 transition-all duration-500"
                style={{ width: `${data.overallCompletionPercent}%` }}
              />
            </div>
            {actionSections.length > 0 ? (
              <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5">
                <p className="text-sm font-bold text-amber-900">
                  {actionSections.length} section{actionSections.length === 1 ? '' : 's'} need attention
                </p>
                <p className="text-xs text-amber-800 mt-1">
                  Complete highlighted items below to improve admission readiness.
                </p>
              </div>
            ) : null}
          </section>

          <section className="rounded-xl border border-border-subtle bg-card p-4 sm:p-5 shadow-sm">
            <h3 className="text-base font-bold text-text-main">Application Timeline</h3>
            <p className="text-sm text-text-muted mt-1 mb-4">Where you are in the admissions journey.</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {data.timeline.map(milestone => {
                const canOpenShortlist =
                  milestone.id === 'university_shortlisting' && Boolean(onNavigateTab);
                const className = `rounded-lg border px-2 py-2 text-center ${
                  milestone.state === 'current'
                    ? 'border-sky-400 bg-sky-50'
                    : milestone.state === 'complete'
                      ? 'border-emerald-200 bg-emerald-50/70'
                      : 'border-border-subtle bg-surface-bg/50'
                }${canOpenShortlist ? ' cursor-pointer hover:border-sky-400 hover:bg-sky-50/80' : ''}`;
                const label = (
                  <p
                    className={`text-xs font-bold leading-tight ${
                      milestone.state === 'current'
                        ? 'text-sky-900'
                        : milestone.state === 'complete'
                          ? 'text-emerald-800'
                          : 'text-text-muted'
                    }`}
                  >
                    {milestone.label}
                  </p>
                );
                if (canOpenShortlist) {
                  return (
                    <button
                      key={milestone.id}
                      type="button"
                      className={className}
                      onClick={() => onNavigateTab?.('university_shortlist')}
                    >
                      {label}
                    </button>
                  );
                }
                return (
                  <div key={milestone.id} className={className}>
                    {label}
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        <section className="rounded-xl border border-border-subtle bg-card p-4 sm:p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h3 className="text-base font-bold text-text-main">Status Tracker</h3>
              <p className="text-sm text-text-muted mt-1">Quick gist from each profile section.</p>
            </div>
            <button
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="text-xs font-semibold text-sky-700 hover:text-sky-900 disabled:opacity-60"
            >
              {isFetching ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {data.sections.map(section => {
              const meta = STATUS_META[section.status];
              return (
                <button
                  key={section.key}
                  type="button"
                  onClick={() => onNavigateTab?.(section.key)}
                  className={`rounded-xl border p-3 text-left transition-colors hover:bg-surface-bg/60 ${
                    section.status === 'action_required'
                      ? 'border-amber-300 bg-amber-50/40'
                      : 'border-border-subtle bg-surface-bg/20'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-text-main">{section.label}</p>
                      <p className="text-sm text-text-muted mt-1 line-clamp-2">{section.gist}</p>
                    </div>
                    <span
                      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${meta.badgeClass}`}
                    >
                      {meta.icon}
                      {meta.label}
                    </span>
                  </div>
                  {section.actionHint ? (
                    <p
                      className={`mt-2 text-xs leading-snug ${
                        section.status === 'action_required' ? 'text-amber-900 font-medium' : 'text-text-muted'
                      }`}
                    >
                      {section.actionHint}
                    </p>
                  ) : null}
                  <div className="mt-3 h-1.5 rounded-full bg-card overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        section.status === 'completed'
                          ? 'bg-emerald-500'
                          : section.status === 'in_progress'
                            ? 'bg-sky-500'
                            : 'bg-amber-400'
                      }`}
                      style={{ width: `${section.completionPercent}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
};

export default ProfilePulseTab;
