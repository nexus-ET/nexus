import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import FlowxJourneyTestDataControls from './FlowxJourneyTestDataControls';
import { useFlowxEnrollments } from '../../hooks/useFlowx';
import { FLOWX_JOURNEY_STAGES } from '../../config/flowxNav';
import { CountryFlag } from '../../utils/countryFlag';
import { slaChipClass, slaLabel } from '../../types/flowx';

type Props = {
  leadId: number | null | undefined;
  /** Show seed/reset demo controls (admin testing). */
  showTestControls?: boolean;
  /** Compact layout for session workspace tab. */
  embedded?: boolean;
  candidateName?: string | null;
};

/**
 * Lead-scoped FlowX applications list (formerly the global Student Journeys page).
 */
const StudentApplicationsPanel: React.FC<Props> = ({
  leadId,
  showTestControls = false,
  embedded = false,
  candidateName,
}) => {
  const resolvedLead =
    leadId != null && Number.isFinite(leadId) && leadId > 0 ? Number(leadId) : null;

  const enrollmentsQuery = useFlowxEnrollments({
    lead_id: resolvedLead ?? undefined,
    enabled: resolvedLead != null,
  });

  const items = enrollmentsQuery.data?.items ?? [];
  const studentName = candidateName || items[0]?.lead_name || (resolvedLead ? `Lead #${resolvedLead}` : 'Student');

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

  if (resolvedLead == null) {
    return (
      <p className="rounded-xl border border-dashed border-border-subtle bg-surface-bg/40 p-6 text-sm text-text-muted">
        Link this booking to a student lead to view and manage FlowX applications.
      </p>
    );
  }

  return (
    <div className={`flex min-h-0 flex-col gap-4 ${embedded ? '' : 'h-full'}`}>
      <div
        className={
          embedded
            ? 'flex flex-wrap items-start justify-between gap-3'
            : 'rounded-2xl border border-border-subtle bg-card px-4 py-3'
        }
      >
        <div>
          {!embedded ? (
            <h2 className="text-2xl font-bold text-text-main">{studentName}</h2>
          ) : (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-violet-700">
                FlowX applications
              </p>
              <h3 className="mt-0.5 text-sm font-semibold text-text-main">{studentName}</h3>
            </div>
          )}
          <p className="text-sm text-text-muted">
            Lead #{resolvedLead} · {items.length} application{items.length === 1 ? '' : 's'}
            {byCountry.length > 0
              ? ` across ${byCountry.length} countr${byCountry.length === 1 ? 'y' : 'ies'}`
              : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {showTestControls ? (
            <FlowxJourneyTestDataControls leadId={resolvedLead} lockLeadId />
          ) : null}
          <Link
            to={`/flowx/journeys/new?leadId=${resolvedLead}`}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white"
          >
            <Plus size={15} />
            Add application
          </Link>
        </div>
      </div>

      {enrollmentsQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading applications…</p>
      ) : items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border-subtle bg-card p-8 text-center text-sm text-text-muted">
          No applications for this student yet.{' '}
          <Link
            to={`/flowx/journeys/new?leadId=${resolvedLead}`}
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

export default StudentApplicationsPanel;
