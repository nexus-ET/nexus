import React from 'react';
import { CalendarRange } from 'lucide-react';

export type PeriodDaySummary = {
  date: string;
  label: string;
  count: number;
  pendingCount?: number;
  bookedCount?: number;
};

type PeriodAgendaShellProps = {
  periodLabel: string;
  totalCount: number;
  days: PeriodDaySummary[];
  activeDate: string | null;
  onSelectDate: (date: string | null) => void;
  stats?: Array<{ label: string; value: number | string; tone?: 'default' | 'amber' | 'emerald' | 'sky' }>;
  children: React.ReactNode;
  emptyMessage?: string;
};

const toneClass = {
  default: 'border-border-subtle bg-surface-bg text-text-main',
  amber: 'border-amber-200 bg-amber-50 text-amber-950',
  emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950',
  sky: 'border-sky-200 bg-sky-50 text-sky-950',
} as const;

/** Multi-date period shell: summary strip, day jump rail, and agenda body. */
const PeriodAgendaShell: React.FC<PeriodAgendaShellProps> = ({
  periodLabel,
  totalCount,
  days,
  activeDate,
  onSelectDate,
  stats = [],
  children,
  emptyMessage = 'No appointments in this period.',
}) => {
  const hasAny = days.some(day => day.count > 0);

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border-subtle bg-surface-bg/70 px-4 py-3">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-text-main">
              <CalendarRange size={16} className="text-accent shrink-0" />
              <h3 className="text-sm font-semibold">Period agenda</h3>
            </div>
            <p className="text-xs text-text-muted mt-1">
              {periodLabel}
              {totalCount > 0
                ? ` · ${totalCount} appointment${totalCount === 1 ? '' : 's'} across ${days.length} day${
                    days.length === 1 ? '' : 's'
                  }`
                : null}
            </p>
          </div>
          {stats.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {stats.map(stat => (
                <div
                  key={stat.label}
                  className={`rounded-lg border px-2.5 py-1.5 min-w-[72px] ${toneClass[stat.tone || 'default']}`}
                >
                  <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{stat.label}</p>
                  <p className="text-lg font-bold leading-none mt-0.5">{stat.value}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {days.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
          <button
            type="button"
            onClick={() => onSelectDate(null)}
            className={`shrink-0 rounded-lg border px-3 py-2 text-left transition-colors ${
              activeDate === null
                ? 'border-accent bg-accent/10 text-accent'
                : 'border-border-subtle bg-card text-text-main hover:bg-surface-bg'
            }`}
          >
            <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">All days</p>
            <p className="text-sm font-bold leading-none mt-1">{totalCount}</p>
          </button>
          {days.map(day => (
            <button
              type="button"
              key={day.date}
              onClick={() => onSelectDate(day.date === activeDate ? null : day.date)}
              className={`shrink-0 rounded-lg border px-3 py-2 text-left transition-colors min-w-[108px] ${
                activeDate === day.date
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border-subtle bg-card text-text-main hover:bg-surface-bg'
              }`}
            >
              <p className="text-[11px] font-semibold truncate">{day.label}</p>
              <p className="text-sm font-bold leading-none mt-1">
                {day.count}
                <span className="text-[10px] font-medium opacity-70 ml-1">
                  {day.count === 1 ? 'session' : 'sessions'}
                </span>
              </p>
              {(day.pendingCount != null || day.bookedCount != null) && (
                <p className="text-[10px] text-text-muted mt-1 whitespace-nowrap">
                  {day.bookedCount != null ? `${day.bookedCount} assigned` : null}
                  {day.bookedCount != null && day.pendingCount != null ? ' · ' : null}
                  {day.pendingCount != null ? `${day.pendingCount} queue` : null}
                </p>
              )}
            </button>
          ))}
        </div>
      ) : null}

      {!hasAny ? (
        <div className="rounded-xl border border-dashed border-border-subtle px-4 py-10 text-center">
          <p className="text-sm text-text-muted">{emptyMessage}</p>
        </div>
      ) : (
        children
      )}
    </div>
  );
};

export default PeriodAgendaShell;
