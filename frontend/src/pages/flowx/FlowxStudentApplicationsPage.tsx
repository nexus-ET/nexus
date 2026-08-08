import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import FlowxJourneyTestDataControls from '../../components/flowx/FlowxJourneyTestDataControls';
import { useFlowxEnrollments } from '../../hooks/useFlowx';
import { FLOWX_JOURNEY_STAGES } from '../../config/flowxNav';
import { CountryFlag } from '../../utils/countryFlag';
import { slaChipClass, slaLabel } from '../../types/flowx';

/**
 * Student applications hub — all country/college journeys for one lead.
 */
const FlowxStudentApplicationsPage: React.FC = () => {
  const { leadId: leadIdParam } = useParams<{ leadId: string }>();
  const leadId = Number(leadIdParam);

  const enrollmentsQuery = useFlowxEnrollments({
    lead_id: Number.isFinite(leadId) && leadId > 0 ? leadId : undefined,
  });

  const items = enrollmentsQuery.data?.items ?? [];
  const studentName = items[0]?.lead_name || `Lead #${leadId}`;

  const byCountry = useMemo(() => {
    const map = new Map<string, typeof items>();
    for (const item of items) {
      const key = item.country_iso2;
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  const stageLabel = (key: string) =>
    (
      FLOWX_JOURNEY_STAGES.find(s => s.key === key)?.label || key.replace(/_/g, ' ')
    ).toUpperCase();

  if (!Number.isFinite(leadId) || leadId <= 0) {
    return <p className="text-sm text-red-700">Invalid student lead id.</p>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="rounded-2xl border border-border-subtle bg-card px-4 py-3">
        <Link
          to="/flowx/journeys"
          className="mb-1 inline-flex items-center gap-1 text-sm font-semibold text-text-muted hover:text-text-main"
        >
          <ArrowLeft size={14} /> All journeys
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold text-text-main">{studentName}</h2>
            <p className="text-sm text-text-muted">
              Lead #{leadId} · {items.length} application{items.length === 1 ? '' : 's'} across{' '}
              {byCountry.length} countr{byCountry.length === 1 ? 'y' : 'ies'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FlowxJourneyTestDataControls leadId={leadId} lockLeadId />
            <Link
              to={`/flowx/journeys/new?leadId=${leadId}`}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white"
            >
              <Plus size={15} />
              Add application
            </Link>
          </div>
        </div>
      </div>

      {enrollmentsQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading applications…</p>
      ) : items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border-subtle bg-card p-8 text-center text-sm text-text-muted">
          No applications for this student yet.{' '}
          <Link
            to={`/flowx/journeys/new?leadId=${leadId}`}
            className="font-semibold text-accent hover:underline"
          >
            Add one
          </Link>
          .
        </p>
      ) : (
        <div className="space-y-4">
          {byCountry.map(([iso2, apps]) => (
            <section key={iso2} className="rounded-2xl border border-border-subtle bg-card">
              <header className="flex items-center gap-2 border-b border-border-subtle px-4 py-3">
                <CountryFlag iso2={iso2} size="md" />
                <div>
                  <h3 className="text-lg font-bold text-text-main">
                    {iso2} · {apps[0]?.country_name}
                  </h3>
                  <p className="text-xs text-text-muted">
                    {apps.length} college/application track{apps.length === 1 ? '' : 's'}
                  </p>
                </div>
              </header>
              <ul className="divide-y divide-border-subtle">
                {apps.map(app => (
                  <li key={app.id}>
                    <Link
                      to={`/flowx/journeys/${app.id}`}
                      className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition hover:bg-accent/5"
                    >
                      <div className="min-w-0">
                        <p className="font-semibold text-text-main">
                          {app.program_name ||
                            app.college_name ||
                            app.university_name ||
                            app.institution_name ||
                            'Country-level application'}
                        </p>
                        <p className="text-xs text-text-muted">
                          {[
                            app.university_name || app.institution_name,
                            app.campus_name,
                            app.intake_name,
                            app.pathway_name,
                            stageLabel(app.current_stage_key),
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${slaChipClass(app.sla_health)}`}
                        >
                          {slaLabel(app.sla_health)}
                        </span>
                        <span className="rounded-md bg-surface-bg px-2 py-0.5 text-xs capitalize text-text-muted">
                          {(app.application_status || app.status || '').replace(/_/g, ' ')}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
};

export default FlowxStudentApplicationsPage;
