import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Building2, Filter } from 'lucide-react';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import { FLOWX_JOURNEY_STAGES } from '../../config/flowxNav';
import { useFlowxCountries, useFlowxEnrollments } from '../../hooks/useFlowx';
import { slaChipClass, slaLabel, type FlowxSlaStatus } from '../../types/flowx';
import { CountryFlag } from '../../utils/countryFlag';

type SlaFilter = 'all' | FlowxSlaStatus;

const FlowxCountryHubPage: React.FC = () => {
  const { countryCode } = useParams<{ countryCode: string }>();
  const iso2 = (countryCode || '').toUpperCase();
  const countriesQuery = useFlowxCountries();
  const enrollmentsQuery = useFlowxEnrollments({
    country: iso2 || undefined,
    status: 'active',
  });
  const [collegeKey, setCollegeKey] = useState<string>('all');
  const [slaFilter, setSlaFilter] = useState<SlaFilter>('all');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [q, setQ] = useState('');

  const countryMeta = useMemo(
    () => (countriesQuery.data ?? []).find(c => c.country_iso2.toUpperCase() === iso2),
    [countriesQuery.data, iso2]
  );

  const items = enrollmentsQuery.data?.items ?? [];

  const colleges = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of items) {
      const key = row.college_name?.trim() || row.institution_name?.trim() || 'Unassigned';
      map.set(key, key);
    }
    return [...map.keys()].sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items.filter(row => {
      const college = row.college_name?.trim() || row.institution_name?.trim() || 'Unassigned';
      if (collegeKey !== 'all' && college !== collegeKey) return false;
      if (slaFilter !== 'all' && row.sla_health !== slaFilter) return false;
      if (stageFilter !== 'all' && row.current_stage_key !== stageFilter) return false;
      if (!needle) return true;
      const hay = [
        row.lead_name,
        row.college_name,
        row.institution_name,
        row.program_name,
        row.pathway_name,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [items, collegeKey, slaFilter, stageFilter, q]);

  const stageLabel = (key: string) =>
    FLOWX_JOURNEY_STAGES.find(s => s.key === key)?.label || key.replace(/_/g, ' ');

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="shrink-0 rounded-xl border border-border-subtle bg-card px-4 py-3">
        <Link
          to="/flowx/ops"
          className="mb-1 inline-flex items-center gap-1 text-xs font-semibold text-text-muted hover:text-text-main"
        >
          <ArrowLeft size={12} /> Ops Dashboard
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="inline-flex min-w-0 items-center gap-3">
            <CountryFlag iso2={iso2} size="lg" className="rounded-lg" />
            <div>
              <h2 className="text-xl font-bold text-text-main">
                {iso2} · {countryMeta?.country_name || iso2}
              </h2>
              <p className="text-sm text-text-muted">
                Country command center — filter by college, process, and SLA, then open a candidate
                workspace.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to={`/flowx/countries/${iso2}`}
              className="rounded-xl border border-border-subtle px-3 py-1.5 text-xs font-semibold text-text-muted hover:text-text-main"
            >
              Configure workflow
            </Link>
            <Link
              to={`/flowx/board?country=${iso2}`}
              className="rounded-xl border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-text-main"
            >
              Stage board
            </Link>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-xs tabular-nums text-text-muted">
          <span>{countryMeta?.institution_count ?? 0} institutions</span>
          <span>{countryMeta?.college_count ?? 0} colleges</span>
          <span>{items.length} active applications</span>
          <span>{countryMeta?.students_in_process ?? 0} in process (catalog)</span>
        </div>
      </div>

      <div className="shrink-0 flex flex-wrap items-center gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2">
        <Filter size={14} className="text-text-muted" />
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search student, college, program…"
          className="min-w-[12rem] flex-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-sm"
        />
        <select
          value={collegeKey}
          onChange={e => setCollegeKey(e.target.value)}
          className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm"
        >
          <option value="all">All colleges</option>
          {colleges.map(c => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={stageFilter}
          onChange={e => setStageFilter(e.target.value)}
          className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm"
        >
          <option value="all">All processes</option>
          {FLOWX_JOURNEY_STAGES.map(s => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          value={slaFilter}
          onChange={e => setSlaFilter(e.target.value as SlaFilter)}
          className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm"
        >
          <option value="all">All SLA</option>
          <option value="on_track">On track</option>
          <option value="amber">At risk</option>
          <option value="breached">Delayed</option>
        </select>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-border-subtle bg-card">
        <HeadlessScrollArea className="h-full" viewportClassName="p-0">
          {enrollmentsQuery.isLoading ? (
            <p className="p-4 text-sm text-text-muted">Loading applications…</p>
          ) : filtered.length === 0 ? (
            <p className="p-6 text-center text-sm text-text-muted">
              No applications match these filters.
            </p>
          ) : (
            <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
              <thead className="sticky top-0 z-10 bg-surface-bg/95 text-xs uppercase tracking-wide text-text-muted backdrop-blur">
                <tr className="border-b border-border-subtle">
                  <th className="px-3 py-2.5 font-semibold">Candidate</th>
                  <th className="px-3 py-2.5 font-semibold">College</th>
                  <th className="px-3 py-2.5 font-semibold">Process</th>
                  <th className="px-3 py-2.5 font-semibold">SLA</th>
                  <th className="px-3 py-2.5 font-semibold">Updated</th>
                  <th className="px-3 py-2.5 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {filtered.map(row => (
                  <tr
                    key={row.id}
                    className="border-b border-border-subtle/70 transition hover:bg-accent/5"
                  >
                    <td className="px-3 py-2.5">
                      <p className="font-semibold text-text-main">{row.lead_name}</p>
                      <p className="text-xs text-text-muted">
                        Lead #{row.lead_id}
                        {row.program_name ? ` · ${row.program_name}` : ''}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="inline-flex items-center gap-1.5 text-text-main">
                        <Building2 size={13} className="text-text-muted" />
                        {row.college_name || row.institution_name || 'Unassigned'}
                      </p>
                      {row.pathway_name ? (
                        <p className="text-xs text-text-muted">{row.pathway_name}</p>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="font-medium text-text-main">
                        {stageLabel(row.current_stage_key)}
                      </p>
                      <p className="text-xs capitalize text-text-muted">
                        {(row.application_status || row.status || '').replace(/_/g, ' ')}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-semibold ${slaChipClass(
                          row.sla_health
                        )}`}
                      >
                        {row.sla_health === 'breached' ? 'Delayed' : slaLabel(row.sla_health)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-text-muted">
                      {row.updated_at ? new Date(row.updated_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <Link
                        to={`/flowx/journeys/${row.id}?fromCountry=${iso2}`}
                        className="rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-text-main hover:bg-accent/20"
                      >
                        Open workspace
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </HeadlessScrollArea>
      </div>
    </div>
  );
};

export default FlowxCountryHubPage;
