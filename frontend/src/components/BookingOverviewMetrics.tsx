import React from 'react';

export interface BookingOverviewMetricsData {
  past_count: number;
  today_count: number;
  upcoming_count: number;
  calendar_today: string;
}

export type BookingMetricKey = 'past' | 'today' | 'upcoming';

interface BookingOverviewMetricsProps {
  overview: BookingOverviewMetricsData | null;
  activeMetric: BookingMetricKey | null;
  loading?: boolean;
  onMetricClick: (metric: BookingMetricKey) => void;
}

const METRIC_CARDS: Array<{
  key: BookingMetricKey;
  title: string;
  countKey: keyof Pick<
    BookingOverviewMetricsData,
    'past_count' | 'today_count' | 'upcoming_count'
  >;
  accent: string;
  accentBg: string;
  accentBorder: string;
}> = [
  {
    key: 'past',
    title: 'Past',
    countKey: 'past_count',
    accent: 'text-slate-700',
    accentBg: 'bg-slate-50',
    accentBorder: 'border-slate-200',
  },
  {
    key: 'today',
    title: 'Today',
    countKey: 'today_count',
    accent: 'text-emerald-800',
    accentBg: 'bg-emerald-50',
    accentBorder: 'border-emerald-200',
  },
  {
    key: 'upcoming',
    title: 'Upcoming',
    countKey: 'upcoming_count',
    accent: 'text-sky-800',
    accentBg: 'bg-sky-50',
    accentBorder: 'border-sky-200',
  },
];

const BookingOverviewMetrics: React.FC<BookingOverviewMetricsProps> = ({
  overview,
  activeMetric,
  loading = false,
  onMetricClick,
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {METRIC_CARDS.map(card => {
        const count = overview?.[card.countKey] ?? 0;
        const isActive = activeMetric === card.key;

        return (
          <button
            key={card.key}
            type="button"
            disabled={loading}
            onClick={() => onMetricClick(card.key)}
            className={[
              'rounded-xl border p-4 text-left transition-all cursor-pointer',
              card.accentBg,
              isActive
                ? `${card.accentBorder} ring-2 ring-accent/40 shadow-sm`
                : `${card.accentBorder} hover:shadow-sm hover:border-accent/30`,
              loading ? 'opacity-60 cursor-wait' : '',
            ].join(' ')}
          >
            <span className="block text-xs font-semibold uppercase tracking-wide text-text-muted">
              {card.title}
            </span>
            <span className={`mt-1 block text-3xl font-bold tabular-nums ${card.accent}`}>
              {loading ? '…' : count}
            </span>
            <span className="mt-1 block text-xs text-text-muted">Bookings</span>
          </button>
        );
      })}
    </div>
  );
};

export default BookingOverviewMetrics;
