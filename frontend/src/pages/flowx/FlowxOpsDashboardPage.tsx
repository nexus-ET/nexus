import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Plane,
  Stamp,
  Users,
} from 'lucide-react';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import { flowxCountryHubPath } from '../../config/flowxNav';
import { useFlowxOpsOverview } from '../../hooks/useFlowx';
import { CountryFlag } from '../../utils/countryFlag';

function KpiCard({
  label,
  value,
  hint,
  icon,
  tone = 'default',
}: {
  label: string;
  value: number;
  hint: string;
  icon: ReactNode;
  tone?: 'default' | 'danger' | 'warn' | 'ok';
}) {
  const toneClass =
    tone === 'danger'
      ? 'border-red-200 bg-red-50/60'
      : tone === 'warn'
        ? 'border-amber-200 bg-amber-50/60'
        : tone === 'ok'
          ? 'border-emerald-200 bg-emerald-50/50'
          : 'border-border-subtle bg-card';
  return (
    <div className={`rounded-2xl border px-4 py-3 ${toneClass}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</p>
        <span className="text-text-muted">{icon}</span>
      </div>
      <p className="mt-1 text-3xl font-extrabold tabular-nums text-text-main">{value}</p>
      <p className="mt-0.5 text-xs text-text-muted">{hint}</p>
    </div>
  );
}

const FlowxOpsDashboardPage: React.FC = () => {
  const overviewQuery = useFlowxOpsOverview();
  const data = overviewQuery.data;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="shrink-0 rounded-xl border border-border-subtle bg-card px-4 py-3">
        <h2 className="text-lg font-bold text-text-main">Ops Dashboard</h2>
        <p className="text-sm text-text-muted">
          Destinations with open student journeys only. Template-only countries stay under Configure
          → Country Workflows.
        </p>
      </div>

      {overviewQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading ops overview…</p>
      ) : overviewQuery.isError ? (
        <p className="text-sm text-red-700">Failed to load ops overview.</p>
      ) : data ? (
        <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="pb-4 pr-1 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
            <KpiCard
              label="Active applications"
              value={data.total_active}
              hint="Active + paused journeys"
              icon={<Users size={16} />}
            />
            <KpiCard
              label="On track"
              value={data.total_on_track}
              hint="SLA healthy"
              icon={<CheckCircle2 size={16} />}
              tone="ok"
            />
            <KpiCard
              label="At risk"
              value={data.total_at_risk}
              hint="Due within 24 hours"
              icon={<Clock3 size={16} />}
              tone="warn"
            />
            <KpiCard
              label="Delayed"
              value={data.total_delayed}
              hint="SLA breached"
              icon={<AlertTriangle size={16} />}
              tone="danger"
            />
            <KpiCard
              label="Visa in process"
              value={data.visas_in_process}
              hint="Current stage = visa"
              icon={<Stamp size={16} />}
            />
            <KpiCard
              label="Landing stage"
              value={data.landed_candidates}
              hint="Pre-arrival / landing"
              icon={<Plane size={16} />}
            />
          </div>

          <section className="rounded-2xl border border-border-subtle bg-card">
            <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
              <div>
                <h3 className="text-sm font-bold text-text-main">Bottlenecks</h3>
                <p className="text-xs text-text-muted">
                  Countries × processes with delayed or at-risk applications
                </p>
              </div>
            </div>
            {data.bottlenecks.length === 0 ? (
              <p className="px-4 py-6 text-sm text-text-muted">No SLA bottlenecks right now.</p>
            ) : (
              <ul className="divide-y divide-border-subtle">
                {data.bottlenecks.map(b => (
                  <li key={`${b.country_iso2}-${b.stage_key}`}>
                    <Link
                      to={flowxCountryHubPath(b.country_iso2)}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 transition hover:bg-accent/5"
                    >
                      <div className="inline-flex min-w-0 items-center gap-2.5">
                        <CountryFlag iso2={b.country_iso2} size="md" className="rounded-md" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-text-main">
                            {b.country_name}
                            <span className="ml-1.5 text-xs font-medium text-text-muted">
                              {b.country_iso2}
                            </span>
                          </p>
                          <p className="text-xs text-text-muted">{b.stage_label}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-xs font-semibold">
                        {b.delayed_count > 0 ? (
                          <span className="rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-red-800">
                            {b.delayed_count} delayed
                          </span>
                        ) : null}
                        {(b.at_risk_count ?? 0) > 0 ? (
                          <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-900">
                            {b.at_risk_count} at risk
                          </span>
                        ) : null}
                        <ArrowRight size={14} className="text-text-muted" />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-end justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-text-main">Countries in process</h3>
                <p className="text-xs text-text-muted">
                  Only destinations with active/paused applications
                </p>
              </div>
              <Link
                to="/flowx/countries"
                className="text-xs font-semibold text-accent hover:underline"
              >
                Configure workflows
              </Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {data.countries.map(c => (
                <Link
                  key={c.country_iso2}
                  to={flowxCountryHubPath(c.country_iso2)}
                  className="rounded-2xl border border-border-subtle bg-card p-4 transition hover:border-accent/40 hover:bg-accent/5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="inline-flex min-w-0 items-center gap-2.5">
                      <CountryFlag iso2={c.country_iso2} size="md" className="rounded-md" />
                      <div className="min-w-0">
                        <p className="truncate text-base font-bold text-text-main">
                          <span className="mr-1.5 text-xs font-semibold text-text-muted">
                            {c.country_iso2}
                          </span>
                          {c.country_name}
                        </p>
                        <p className="text-xs text-text-muted">
                          {c.institution_count} institutions · {c.college_count} colleges
                        </p>
                      </div>
                    </div>
                    <ArrowRight size={15} className="mt-1 shrink-0 text-text-muted" />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-lg bg-surface-bg/80 px-2 py-1.5">
                      <p className="text-lg font-bold tabular-nums text-text-main">
                        {c.active_applications}
                      </p>
                      <p className="text-[10px] font-semibold uppercase text-text-muted">Active</p>
                    </div>
                    <div className="rounded-lg bg-amber-50 px-2 py-1.5">
                      <p className="text-lg font-bold tabular-nums text-amber-900">{c.at_risk_count}</p>
                      <p className="text-[10px] font-semibold uppercase text-amber-800/80">At risk</p>
                    </div>
                    <div className="rounded-lg bg-red-50 px-2 py-1.5">
                      <p className="text-lg font-bold tabular-nums text-red-800">{c.delayed_count}</p>
                      <p className="text-[10px] font-semibold uppercase text-red-700/80">Delayed</p>
                    </div>
                  </div>
                  {c.top_stage_label ? (
                    <p className="mt-2 text-xs text-text-muted">
                      Busiest process:{' '}
                      <span className="font-semibold text-text-main">{c.top_stage_label}</span>
                    </p>
                  ) : (
                    <p className="mt-2 text-xs text-text-muted">No open applications</p>
                  )}
                </Link>
              ))}
            </div>
          </section>
        </HeadlessScrollArea>
      ) : null}
    </div>
  );
};

export default FlowxOpsDashboardPage;
