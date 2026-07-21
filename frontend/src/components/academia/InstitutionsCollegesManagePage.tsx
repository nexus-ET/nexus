import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, CalendarDays, Eye, GraduationCap, Landmark, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';

import { apiFetch } from '../../utils/api';
import { institutionEditPath } from '../../config/academiaHubNav';
import type { InstitutionalHierarchySummary } from '../../types/institutions';
import type { IntakeEntityType } from '../../types/hierarchicalIntake';
import CollegeDetailsInlinePanel from './colleges/CollegeDetailsInlinePanel';
import InlineExpandPanel from './form/InlineExpandPanel';
import IntakeConfigureContent from './intakes/IntakeConfigureContent';
import EmptyListMessage from '../ui/EmptyListMessage';

type EntityKind = 'institution' | 'campus' | 'college';

type ExpandedPanel =
  | {
      key: string;
      mode: 'details';
      kind: 'institution';
      institutionId: number;
      entityName: string;
    }
  | {
      key: string;
      mode: 'details';
      kind: 'college';
      institutionId: number;
      collegeId: number;
      entityName: string;
    }
  | {
      key: string;
      mode: 'calendar';
      institutionId: number;
      entityType: IntakeEntityType;
      entityId: number;
      entityName: string;
    };

interface HierarchyRow {
  key: string;
  kind: EntityKind;
  name: string;
  institutionId: number;
  campusName?: string;
  deanName?: string;
  entityId: number;
  collegeId?: number;
}

interface InstitutionDetailsRecord {
  id: number;
  name: string;
  code?: string | null;
  institution_type?: string | null;
  country_name?: string | null;
  state_name?: string | null;
  city_name?: string | null;
  accreditation_details?: string | null;
}

const InstitutionsCollegesManagePage: React.FC = () => {
  const [hierarchy, setHierarchy] = useState<InstitutionalHierarchySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPanel, setExpandedPanel] = useState<ExpandedPanel | null>(null);
  const [institutionDetails, setInstitutionDetails] = useState<InstitutionDetailsRecord | null>(
    null
  );
  const [institutionDetailsLoading, setInstitutionDetailsLoading] = useState(false);
  const [institutionDetailsError, setInstitutionDetailsError] = useState<string | null>(null);

  const loadHierarchy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<InstitutionalHierarchySummary>('academia/institutions/hierarchy');
      setHierarchy(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institutions and colleges.');
      setHierarchy(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHierarchy();
  }, [loadHierarchy]);

  const rows = useMemo(() => {
    const next: HierarchyRow[] = [];
    for (const institution of hierarchy?.institutions || []) {
      next.push({
        key: `institution-${institution.id}`,
        kind: 'institution',
        name: institution.name,
        institutionId: institution.id,
        entityId: institution.id,
      });
      for (const campus of institution.campuses) {
        next.push({
          key: `campus-${campus.id}`,
          kind: 'campus',
          name: campus.name,
          institutionId: institution.id,
          campusName: campus.location_label || undefined,
          entityId: campus.id,
        });
        for (const college of campus.colleges) {
          // Same college can only appear once in the flat list even if nested under a campus.
          const collegeKey = `college-${college.id}`;
          if (next.some(row => row.key === collegeKey)) continue;
          next.push({
            key: collegeKey,
            kind: 'college',
            name: college.name,
            institutionId: institution.id,
            campusName: campus.name,
            deanName: college.dean_name || undefined,
            entityId: college.id,
            collegeId: college.id,
          });
        }
      }
    }
    return next;
  }, [hierarchy]);

  const togglePanel = (next: ExpandedPanel) => {
    setExpandedPanel(current => (current?.key === next.key ? null : next));
  };

  const loadInstitutionDetails = useCallback(async (institutionId: number) => {
    setInstitutionDetailsLoading(true);
    setInstitutionDetailsError(null);
    try {
      const record = await apiFetch<InstitutionDetailsRecord>(
        `academia/institutions/${institutionId}`
      );
      setInstitutionDetails(record);
    } catch (err) {
      setInstitutionDetailsError(
        err instanceof Error ? err.message : 'Failed to load institution details.'
      );
      setInstitutionDetails(null);
    } finally {
      setInstitutionDetailsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (expandedPanel?.mode !== 'details' || expandedPanel.kind !== 'institution') {
      setInstitutionDetails(null);
      setInstitutionDetailsError(null);
      return;
    }
    void loadInstitutionDetails(expandedPanel.institutionId);
  }, [expandedPanel, loadInstitutionDetails]);

  const entityIcon = (kind: EntityKind) => {
    if (kind === 'institution') return Landmark;
    if (kind === 'campus') return Building2;
    return GraduationCap;
  };

  const entityLabel = (kind: EntityKind) => {
    if (kind === 'institution') return 'Institution';
    if (kind === 'campus') return 'Campus';
    return 'College';
  };

  const renderExpandedPanel = (panel: ExpandedPanel) => {
    if (panel.mode === 'details' && panel.kind === 'college') {
      return (
        <CollegeDetailsInlinePanel
          collegeId={panel.collegeId}
          onClose={() => setExpandedPanel(null)}
          onSaved={() => void loadHierarchy()}
        />
      );
    }

    if (panel.mode === 'details' && panel.kind === 'institution') {
      const location = [institutionDetails?.city_name, institutionDetails?.state_name, institutionDetails?.country_name]
        .filter(Boolean)
        .join(', ');
      return (
        <InlineExpandPanel
          title={panel.entityName}
          subtitle="View Details"
          onClose={() => setExpandedPanel(null)}
          loading={institutionDetailsLoading}
          loadingLabel="Loading institution profile..."
          error={institutionDetailsError}
        >
          {institutionDetails ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <p className="text-xs font-semibold uppercase text-text-muted">Institution type</p>
                <p className="mt-1 text-sm text-text-main">
                  {institutionDetails.institution_type || '—'}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-text-muted">Short code</p>
                <p className="mt-1 text-sm text-text-main">{institutionDetails.code || '—'}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-xs font-semibold uppercase text-text-muted">Location</p>
                <p className="mt-1 text-sm text-text-main">{location || '—'}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-xs font-semibold uppercase text-text-muted">Accreditation</p>
                <p className="mt-1 text-sm text-text-main">
                  {institutionDetails.accreditation_details?.replace(/<[^>]+>/g, '').trim() || '—'}
                </p>
              </div>
              <div className="md:col-span-2">
                <Link
                  to={institutionEditPath(panel.institutionId)}
                  className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-3 py-2 text-sm font-semibold text-text-main hover:bg-card"
                >
                  Open full editor
                </Link>
              </div>
            </div>
          ) : null}
        </InlineExpandPanel>
      );
    }

    return (
      <InlineExpandPanel
        title={panel.entityName}
        subtitle="Configure Calendar"
        onClose={() => setExpandedPanel(null)}
      >
        <IntakeConfigureContent
          institutionId={panel.institutionId}
          entityType={panel.entityType}
          entityId={panel.entityId}
          onUpdated={() => void loadHierarchy()}
        />
      </InlineExpandPanel>
    );
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-muted">
        Browse institutions, campuses, and colleges in one list. Expand a row to view details or
        configure academic calendars without leaving the page.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading hierarchy...
        </div>
      ) : error ? (
        <div className="py-10 text-sm text-alert">{error}</div>
      ) : rows.length === 0 ? (
        <EmptyListMessage message="No institutions found." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-6 py-3 font-semibold">Entity</th>
                <th className="px-6 py-3 font-semibold">Type</th>
                <th className="px-6 py-3 font-semibold">Campus</th>
                <th className="px-6 py-3 font-semibold">Dean</th>
                <th className="px-6 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const Icon = entityIcon(row.kind);
                const isExpanded = expandedPanel?.key.startsWith(`${row.key}-`);
                const indentClass =
                  row.kind === 'campus' ? 'pl-8' : row.kind === 'college' ? 'pl-14' : '';

                return (
                  <Fragment key={row.key}>
                    <tr
                      className={`border-t border-border-subtle/70 ${
                        isExpanded ? 'bg-accent/5' : ''
                      }`}
                    >
                      <td className={`px-6 py-3 ${indentClass}`}>
                        <div className="flex items-center gap-2">
                          <Icon size={16} className="shrink-0 text-accent" />
                          <span className="font-semibold text-text-main">{row.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-text-muted">{entityLabel(row.kind)}</td>
                      <td className="px-6 py-3 text-text-muted">{row.campusName || '—'}</td>
                      <td className="px-6 py-3 text-text-muted">{row.deanName || '—'}</td>
                      <td className="px-6 py-3">
                        <div className="flex flex-wrap gap-2">
                          {(row.kind === 'institution' || row.kind === 'college') && (
                            <button
                              type="button"
                              onClick={() => {
                                if (row.kind === 'institution') {
                                  togglePanel({
                                    key: `${row.key}-details`,
                                    mode: 'details',
                                    kind: 'institution',
                                    institutionId: row.institutionId,
                                    entityName: row.name,
                                  });
                                } else {
                                  togglePanel({
                                    key: `${row.key}-details`,
                                    mode: 'details',
                                    kind: 'college',
                                    institutionId: row.institutionId,
                                    collegeId: row.collegeId!,
                                    entityName: row.name,
                                  });
                                }
                              }}
                              className={`inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                                expandedPanel?.key === `${row.key}-details`
                                  ? 'border-accent bg-accent/10 text-accent'
                                  : 'border-border-subtle text-text-main'
                              }`}
                            >
                              <Eye size={14} />
                              View Details
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              togglePanel({
                                key: `${row.key}-calendar`,
                                mode: 'calendar',
                                institutionId: row.institutionId,
                                entityType: row.kind,
                                entityId: row.entityId,
                                entityName: row.name,
                              })
                            }
                            className={`inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                              expandedPanel?.key === `${row.key}-calendar`
                                ? 'border-accent bg-accent/10 text-accent'
                                : 'border-border-subtle text-text-main'
                            }`}
                          >
                            <CalendarDays size={14} />
                            Configure Calendar
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedPanel && expandedPanel.key.startsWith(`${row.key}-`) ? (
                      <tr className="border-t border-border-subtle/70 bg-surface-bg/40">
                        <td colSpan={5} className="px-6 py-4">
                          {renderExpandedPanel(expandedPanel)}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default InstitutionsCollegesManagePage;
