import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import FlowxJourneyTestDataControls from '../../components/flowx/FlowxJourneyTestDataControls';
import { useFlowxCountries, useFlowxEnrollments } from '../../hooks/useFlowx';
import { FLOWX_JOURNEY_STAGES } from '../../config/flowxNav';
import { CountryFlag } from '../../utils/countryFlag';
import { slaChipClass, slaLabel } from '../../types/flowx';

const FlowxJourneysPage: React.FC = () => {
  const [country, setCountry] = useState('');
  const [q, setQ] = useState('');

  const countriesQuery = useFlowxCountries();
  const enrollmentsQuery = useFlowxEnrollments({
    country: country || undefined,
    q: q || undefined,
  });

  const stageLabel = (key: string) =>
    (
      FLOWX_JOURNEY_STAGES.find(s => s.key === key)?.label || key.replace(/_/g, ' ')
    ).toUpperCase();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-text-main">Student Journeys</h2>
          <p className="text-sm text-text-muted">
            One student can hold multiple applications — across countries, and across colleges in the
            same country.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FlowxJourneyTestDataControls leadId={27} />
          <Link
            to="/flowx/journeys/new"
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white"
          >
            <Plus size={16} />
            Add application
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search student…"
          className="rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm"
        />
        <select
          value={country}
          onChange={e => setCountry(e.target.value)}
          className="rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm"
        >
          <option value="">All countries</option>
          {(countriesQuery.data ?? []).map(c => (
            <option key={c.country_iso2} value={c.country_iso2}>
              {c.country_name}
            </option>
          ))}
        </select>
      </div>

      {enrollmentsQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading applications…</p>
      ) : (enrollmentsQuery.data?.items.length ?? 0) === 0 ? (
        <p className="rounded-2xl border border-dashed border-border-subtle bg-card p-8 text-center text-sm text-text-muted">
          No applications yet.{' '}
          <Link to="/flowx/journeys/new" className="font-semibold text-accent hover:underline">
            Add an application
          </Link>
          .
        </p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border-subtle bg-card">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border-subtle bg-surface-bg/60 text-[11px] uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-4 py-2 font-semibold">Student</th>
                <th className="px-4 py-2 font-semibold">Country</th>
                <th className="px-4 py-2 font-semibold">Institution</th>
                <th className="px-4 py-2 font-semibold">Program</th>
                <th className="px-4 py-2 font-semibold">Pathway</th>
                <th className="px-4 py-2 font-semibold">Stage</th>
                <th className="px-4 py-2 font-semibold">SLA</th>
                <th className="px-4 py-2 font-semibold">App status</th>
              </tr>
            </thead>
            <tbody>
              {enrollmentsQuery.data?.items.map(item => {
                const isDelayed =
                  item.sla_health === 'breached' || Boolean(item.intake_overdue);
                return (
                <tr
                  key={item.id}
                  className={`border-b border-border-subtle last:border-0 hover:bg-surface-bg/40 ${
                    isDelayed ? 'bg-red-50/70' : ''
                  }`}
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/flowx/journeys/${item.id}`}
                      className="font-semibold text-text-main hover:underline"
                    >
                      {item.lead_name}
                    </Link>
                    <p className="text-[11px] text-text-muted">
                      Lead #{item.lead_id} ·{' '}
                      <Link
                        to={`/flowx/journeys/student/${item.lead_id}`}
                        className="font-semibold text-accent hover:underline"
                      >
                        All applications
                      </Link>
                    </p>
                    {item.intake_overdue ? (
                      <p className="mt-1 text-[11px] font-extrabold text-red-700">
                        1.1 Intake Session delayed
                        {item.intake_delay_label ? ` · ${item.intake_delay_label}` : ''}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-2 text-text-muted">
                      <CountryFlag iso2={item.country_iso2} size="sm" />
                      {item.country_iso2} · {item.country_name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text-muted">
                    <div>{item.university_name || item.institution_name || '—'}</div>
                    {item.college_name || item.campus_name ? (
                      <div className="text-[11px]">
                        {[item.college_name, item.campus_name].filter(Boolean).join(' · ')}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-text-muted">
                    <div>{item.program_name || '—'}</div>
                    {item.intake_name ? (
                      <div className="text-[11px]">{item.intake_name}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-text-muted">{item.pathway_name || '—'}</td>
                  <td className="px-4 py-3 text-text-muted">{stageLabel(item.current_stage_key)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${
                        isDelayed
                          ? 'border-red-600 bg-red-600 text-white'
                          : slaChipClass(item.sla_health)
                      }`}
                    >
                      {isDelayed ? 'Delayed' : slaLabel(item.sla_health)}
                    </span>
                  </td>
                  <td className="px-4 py-3 capitalize text-text-muted">
                    {(item.application_status || item.status || '').replace(/_/g, ' ')}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default FlowxJourneysPage;
