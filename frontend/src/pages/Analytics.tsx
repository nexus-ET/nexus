import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  ScatterChart,
  Scatter,
  ZAxis,
} from 'recharts';
import {
  BarChart3,
  BrainCircuit,
  CalendarRange,
  Filter,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { apiFetch } from '../utils/api';

type ChartType = 'funnel' | 'channel' | 'ai_efficacy' | 'velocity';
type ChannelFilter = 'All' | 'WhatsApp' | 'Instagram' | 'Web';

interface TrendsPayload {
  generated_at: string;
  filters: {
    channel: string;
    funnel_weeks: number;
    channel_days: number;
    ai_weeks: number;
  };
  conversion_funnel: {
    weeks: Array<{
      week_label: string;
      inquiry: number;
      enrolled: number;
      conversion_rate: number;
    }>;
  };
  channel_performance: {
    period_days: number;
    channels: Array<{
      channel: string;
      leads: number;
      enrolled: number;
      conversion_rate: number;
    }>;
  };
  ai_efficacy: {
    weeks: Array<{
      week_label: string;
      resolution_rate: number;
      closed_leads: number;
      ai_resolved: number;
    }>;
  };
  lead_velocity: {
    current_month: { label: string; average_days: number; closed_leads: number };
    previous_month: { label: string; average_days: number; closed_leads: number };
    delta_days: number;
    change_percent: number;
  };
}

const CHANNEL_OPTIONS: ChannelFilter[] = ['All', 'WhatsApp', 'Instagram', 'Web'];

const Analytics: React.FC = () => {
  const [channel, setChannel] = useState<ChannelFilter>('All');
  const [funnelWeeks, setFunnelWeeks] = useState(8);
  const [channelDays, setChannelDays] = useState(90);
  const [aiWeeks, setAiWeeks] = useState(12);
  const [trends, setTrends] = useState<TrendsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explaining, setExplaining] = useState<ChartType | null>(null);
  const [insights, setInsights] = useState<Partial<Record<ChartType, { summary: string; source: string }>>>({});

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      channel,
      funnel_weeks: String(funnelWeeks),
      channel_days: String(channelDays),
      ai_weeks: String(aiWeeks),
    });
    return params.toString();
  }, [channel, funnelWeeks, channelDays, aiWeeks]);

  const loadTrends = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiFetch(`analytics/trends?${queryString}`);
      setTrends(data as TrendsPayload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics trends.');
    } finally {
      setLoading(false);
    }
  }, [queryString]);

  useEffect(() => {
    loadTrends();
  }, [loadTrends]);

  const velocityScatter = useMemo(() => {
    if (!trends) return [];
    return [
      {
        label: trends.lead_velocity.previous_month.label,
        average_days: trends.lead_velocity.previous_month.average_days,
        closed_leads: trends.lead_velocity.previous_month.closed_leads,
      },
      {
        label: trends.lead_velocity.current_month.label,
        average_days: trends.lead_velocity.current_month.average_days,
        closed_leads: trends.lead_velocity.current_month.closed_leads,
      },
    ];
  }, [trends]);

  const handleExplain = async (chartType: ChartType, data: Record<string, unknown>) => {
    try {
      setExplaining(chartType);
      const response = await apiFetch('analytics/explain', {
        method: 'POST',
        body: JSON.stringify({ chart_type: chartType, data }),
      });
      setInsights(prev => ({
        ...prev,
        [chartType]: response as { summary: string; source: string },
      }));
    } catch (err: unknown) {
      setInsights(prev => ({
        ...prev,
        [chartType]: {
          summary: err instanceof Error ? err.message : 'Unable to generate insight.',
          source: 'error',
        },
      }));
    } finally {
      setExplaining(null);
    }
  };

  const ChartInsight = ({ chartType }: { chartType: ChartType }) => {
    const insight = insights[chartType];
    if (!insight) return null;
    return (
      <div className="mt-3 p-3 rounded-xl bg-accent/5 border border-accent/15 text-xs text-text-main leading-relaxed">
        <div className="flex items-center gap-1.5 mb-1 text-[10px] font-bold uppercase tracking-wider text-accent">
          <Sparkles size={12} />
          Insight {insight.source === 'llm' ? '(AI)' : insight.source === 'heuristic' ? '(Smart Summary)' : ''}
        </div>
        {insight.summary}
      </div>
    );
  };

  const ExplainButton = ({
    chartType,
    data,
  }: {
    chartType: ChartType;
    data: Record<string, unknown>;
  }) => (
    <button
      type="button"
      onClick={() => handleExplain(chartType, data)}
      disabled={explaining === chartType}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-border-subtle text-[11px] font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors disabled:opacity-50"
    >
      {explaining === chartType ? <Loader2 size={12} className="animate-spin" /> : <BrainCircuit size={12} />}
      Explain
    </button>
  );

  return (
    <div className="relative z-10 mx-auto w-full max-w-none space-y-5 pb-10">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 size={18} className="text-accent" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-text-muted">
              Strategic Intelligence
            </span>
          </div>
          <h2 className="text-2xl font-extrabold text-text-main tracking-tight">Analytical Dashboard</h2>
          <p className="text-text-muted text-sm max-w-2xl">
            Historical trends, channel performance, and AI efficacy — separate from the real-time operational dashboard.
          </p>
        </div>

        <button
          type="button"
          onClick={loadTrends}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all disabled:opacity-50 self-start"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh Trends
        </button>
      </div>

      <div className="bg-card border border-border-subtle rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-3 text-xs font-bold uppercase tracking-wider text-text-muted">
          <Filter size={14} />
          Exploratory Filters
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <label className="text-xs text-text-muted">
            Source
            <select
              value={channel}
              onChange={e => setChannel(e.target.value as ChannelFilter)}
              className="mt-1 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main"
            >
              {CHANNEL_OPTIONS.map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Funnel Window (weeks)
            <select
              value={funnelWeeks}
              onChange={e => setFunnelWeeks(Number(e.target.value))}
              className="mt-1 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main"
            >
              {[4, 8, 12, 16].map(value => (
                <option key={value} value={value}>{value} weeks</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Channel Lookback
            <select
              value={channelDays}
              onChange={e => setChannelDays(Number(e.target.value))}
              className="mt-1 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main"
            >
              {[30, 60, 90, 180].map(value => (
                <option key={value} value={value}>{value} days</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text-muted">
            AI Trend Window
            <select
              value={aiWeeks}
              onChange={e => setAiWeeks(Number(e.target.value))}
              className="mt-1 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main"
            >
              {[8, 12, 16, 24].map(value => (
                <option key={value} value={value}>{value} weeks</option>
              ))}
            </select>
          </label>
        </div>
        {trends && (
          <p className="mt-3 text-[11px] text-text-muted flex items-center gap-1.5">
            <CalendarRange size={12} />
            Generated {new Date(trends.generated_at).toLocaleString()}
          </p>
        )}
      </div>

      {error && (
        <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
          {error}
        </div>
      )}

      {loading && !trends ? (
        <div className="flex items-center justify-center gap-2 py-20 text-sm text-text-muted">
          <Loader2 size={18} className="animate-spin" />
          Loading historical analytics...
        </div>
      ) : trends ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <section className="bg-card border border-border-subtle rounded-2xl p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="text-sm font-bold text-text-main">Conversion Funnel Trends</h3>
                <p className="text-[11px] text-text-muted">Week-over-week inquiry to enrolled movement</p>
              </div>
              <ExplainButton chartType="funnel" data={trends.conversion_funnel as unknown as Record<string, unknown>} />
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={trends.conversion_funnel.weeks}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="week_label" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="left" dataKey="inquiry" name="Inquiry" fill="#93c5fd" radius={[4, 4, 0, 0]} />
                  <Bar yAxisId="left" dataKey="enrolled" name="Enrolled" fill="#059669" radius={[4, 4, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="conversion_rate" name="Conversion %" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <ChartInsight chartType="funnel" />
          </section>

          <section className="bg-card border border-border-subtle rounded-2xl p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="text-sm font-bold text-text-main">Channel Performance</h3>
                <p className="text-[11px] text-text-muted">Conversion rates over the last {trends.channel_performance.period_days} days</p>
              </div>
              <ExplainButton chartType="channel" data={trends.channel_performance as unknown as Record<string, unknown>} />
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trends.channel_performance.channels}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="channel" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="conversion_rate" name="Conversion Rate" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <ChartInsight chartType="channel" />
          </section>

          <section className="bg-card border border-border-subtle rounded-2xl p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="text-sm font-bold text-text-main">AI Efficacy</h3>
                <p className="text-[11px] text-text-muted">Resolution rate trend for AI-closed leads</p>
              </div>
              <ExplainButton chartType="ai_efficacy" data={trends.ai_efficacy as unknown as Record<string, unknown>} />
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trends.ai_efficacy.weeks}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="week_label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="resolution_rate" name="Resolution Rate" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <ChartInsight chartType="ai_efficacy" />
          </section>

          <section className="bg-card border border-border-subtle rounded-2xl p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="text-sm font-bold text-text-main">Lead Velocity</h3>
                <p className="text-[11px] text-text-muted">Average days from inquiry to enrolled</p>
              </div>
              <ExplainButton chartType="velocity" data={trends.lead_velocity as unknown as Record<string, unknown>} />
            </div>

            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="rounded-xl border border-border-subtle bg-surface-bg/60 p-3">
                <p className="text-[10px] uppercase tracking-wider text-text-muted font-bold">Current Month</p>
                <p className="text-2xl font-black text-text-main mt-1">{trends.lead_velocity.current_month.average_days}d</p>
                <p className="text-[11px] text-text-muted">{trends.lead_velocity.current_month.closed_leads} closes</p>
              </div>
              <div className="rounded-xl border border-border-subtle bg-surface-bg/60 p-3">
                <p className="text-[10px] uppercase tracking-wider text-text-muted font-bold">Previous Month</p>
                <p className="text-2xl font-black text-text-main mt-1">{trends.lead_velocity.previous_month.average_days}d</p>
                <p className="text-[11px] text-text-muted">{trends.lead_velocity.previous_month.closed_leads} closes</p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs font-semibold mb-2">
              <TrendingUp size={14} className={trends.lead_velocity.delta_days <= 0 ? 'text-success' : 'text-alert'} />
              <span className={trends.lead_velocity.delta_days <= 0 ? 'text-success' : 'text-alert'}>
                {trends.lead_velocity.delta_days <= 0 ? 'Faster' : 'Slower'} by {Math.abs(trends.lead_velocity.delta_days)} days ({trends.lead_velocity.change_percent}%)
              </span>
            </div>

            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" dataKey="average_days" name="Avg Days" tick={{ fontSize: 11 }} />
                  <YAxis type="number" dataKey="closed_leads" name="Closed Leads" tick={{ fontSize: 11 }} />
                  <ZAxis type="category" dataKey="label" name="Month" />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                  <Scatter data={velocityScatter} fill="#0ea5e9" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <ChartInsight chartType="velocity" />
          </section>
        </div>
      ) : null}
    </div>
  );
};

export default Analytics;
