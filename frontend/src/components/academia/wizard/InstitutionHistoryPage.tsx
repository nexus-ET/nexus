import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock3, Loader2, Wrench } from 'lucide-react';
import { apiFetch } from '../../../utils/api';
import {
  INSTITUTIONS_SECTION_PATH,
  getAcademiaSectionLabel,
} from '../../../config/academiaHubNav';
import type {
  AcademiaAuditEntry,
  InstitutionPublishReport,
  PublishReportStep,
} from '../../../schemas/wizard';
import { normalizePublishReportSteps, WIZARD_UI_STEP_COUNT } from '../../../schemas/wizard';
import type { CampusRecord, CollegeRecord, InstitutionRecord } from '../../../types/institutions';
import AcademiaBreadcrumbs from '../AcademiaBreadcrumbs';

const formatResultLabel = (key: string) =>
  key.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase());

const getPublishReport = (entry: AcademiaAuditEntry): InstitutionPublishReport | null => {
  const report = entry.new_data?.publish_report;
  if (!report || typeof report !== 'object' || !Array.isArray((report as { steps?: unknown }).steps)) {
    return null;
  }
  const typed = report as InstitutionPublishReport;
  const steps = normalizePublishReportSteps(typed.steps || []) as PublishReportStep[];
  return {
    ...typed,
    steps,
    summary: {
      ...typed.summary,
      steps_total: steps.length || WIZARD_UI_STEP_COUNT,
      steps_passed: Math.min(typed.summary?.steps_passed ?? steps.length, steps.length),
    },
  };
};

const InstitutionHistoryPage: React.FC = () => {
  const { institutionId = '' } = useParams();
  const location = useLocation();
  const [institution, setInstitution] = useState<InstitutionRecord | null>(null);
  const [campuses, setCampuses] = useState<CampusRecord[]>([]);
  const [colleges, setColleges] = useState<CollegeRecord[]>([]);
  const [entries, setEntries] = useState<AcademiaAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const publishReports = useMemo(
    () =>
      entries
        .map(entry => ({ entry, report: getPublishReport(entry) }))
        .filter(
          (item): item is { entry: AcademiaAuditEntry; report: InstitutionPublishReport } =>
            item.report !== null
        ),
    [entries]
  );
  const latestPublishReport = publishReports[0] ?? null;

  const loadHistory = useCallback(async () => {
    if (!institutionId) {
      setLoading(false);
      setError('Institution id is missing from the URL.');
      setInstitution(null);
      setCampuses([]);
      setColleges([]);
      setEntries([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [institutionData, campusData, collegeData, auditData] = await Promise.all([
        apiFetch<InstitutionRecord>(`academia/institutions/${institutionId}`),
        apiFetch<CampusRecord[]>(`academia/campuses?institution_id=${institutionId}`),
        apiFetch<CollegeRecord[]>(`academia/colleges?institution_id=${institutionId}`),
        apiFetch<AcademiaAuditEntry[]>(`academia/institutions/${institutionId}/history`),
      ]);
      setInstitution(institutionData);
      setCampuses(Array.isArray(campusData) ? campusData : []);
      setColleges(Array.isArray(collegeData) ? collegeData : []);
      setEntries(Array.isArray(auditData) ? auditData : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institution history');
      setInstitution(null);
      setCampuses([]);
      setColleges([]);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [institutionId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  return (
    <div className="space-y-4">
      <AcademiaBreadcrumbs
        items={[
          { label: 'Academia Hub', path: '/academia' },
          { label: getAcademiaSectionLabel('institutions'), path: INSTITUTIONS_SECTION_PATH },
          { label: institution?.name || `Institution ${institutionId}` },
          { label: 'History' },
        ]}
      />

      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="border-b border-border-subtle px-6 py-4">
          <h2 className="text-xl font-bold text-text-main">Institution History</h2>
          <p className="text-sm text-text-muted">
            Current campuses and schools/colleges, plus the latest publish activity report.
          </p>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" /> Loading...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : (
          <>
            <section className="border-b border-border-subtle px-6 py-5">
              <h3 className="text-sm font-bold uppercase tracking-wide text-text-muted">
                Current structure
              </h3>
              <p className="mt-1 text-lg font-semibold text-text-main">
                {institution?.name || `Institution #${institutionId}`}
              </p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                  <p className="text-xs font-semibold uppercase text-text-muted">Campuses</p>
                  <p className="mt-1 text-2xl font-bold text-text-main">{campuses.length}</p>
                  {campuses.length === 0 ? (
                    <p className="mt-2 text-sm text-text-muted">No campuses saved yet.</p>
                  ) : (
                    <ul className="mt-3 space-y-1 text-sm text-text-main">
                      {campuses.map(campus => (
                        <li key={campus.id}>
                          {campus.name}
                          {campus.location_label ? (
                            <span className="text-text-muted"> — {campus.location_label}</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                  <p className="text-xs font-semibold uppercase text-text-muted">Schools &amp; Colleges</p>
                  <p className="mt-1 text-2xl font-bold text-text-main">{colleges.length}</p>
                  {colleges.length === 0 ? (
                    <p className="mt-2 text-sm text-text-muted">No schools or colleges saved yet.</p>
                  ) : (
                    <ul className="mt-3 space-y-1 text-sm text-text-main">
                      {colleges.map(college => (
                        <li key={college.id}>
                          {college.name}
                          {college.campus_name ? (
                            <span className="text-text-muted"> — {college.campus_name}</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </section>

            <section className="border-b border-border-subtle px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-text-muted">
                    Latest publish activity
                  </h3>
                  <p className="mt-1 text-sm text-text-muted">
                    Checks, synchronization work, discrepancies, and fixes recorded during publishing.
                  </p>
                </div>
                {latestPublishReport ? (
                  <div className="flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-700">
                    <CheckCircle2 size={14} /> Published successfully
                  </div>
                ) : null}
              </div>

              {!latestPublishReport ? (
                <p className="mt-4 rounded-xl border border-border-subtle bg-surface-bg/40 p-4 text-sm text-text-muted">
                  No detailed publish report is available yet. Reports are created by the next publish.
                </p>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-main">
                          Publish attempt {latestPublishReport.report.attempt_id.slice(0, 8)}
                        </p>
                        <p className="mt-1 flex items-center gap-1 text-xs text-text-muted">
                          <Clock3 size={13} />
                          {new Date(latestPublishReport.report.started_at).toLocaleString()} ·{' '}
                          {latestPublishReport.report.duration_ms.toLocaleString()} ms · Draft #
                          {latestPublishReport.report.draft_id} · User #
                          {latestPublishReport.report.actor_user_id ?? 'system'}
                        </p>
                      </div>
                      {publishReports.length > 1 ? (
                        <p className="text-xs text-text-muted">
                          {publishReports.length} detailed publish reports recorded
                        </p>
                      ) : null}
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-4">
                      {[
                        ['Steps passed', `${latestPublishReport.report.summary.steps_passed}/${latestPublishReport.report.summary.steps_total}`],
                        ['Checks passed', latestPublishReport.report.summary.checks_passed],
                        ['Discrepancies', latestPublishReport.report.summary.discrepancies_found],
                        ['Fixed', latestPublishReport.report.summary.discrepancies_fixed],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-lg border border-border-subtle bg-card px-3 py-2">
                          <p className="text-xs text-text-muted">{label}</p>
                          <p className="mt-1 text-lg font-bold text-text-main">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-3">
                    {latestPublishReport.report.steps.map(step => (
                      <article
                        key={`${latestPublishReport.report.attempt_id}-${step.step}`}
                        className="rounded-xl border border-border-subtle bg-card p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-sm font-bold text-emerald-700">
                              {step.step}
                            </div>
                            <div>
                              <h4 className="font-semibold text-text-main">{step.label}</h4>
                              <p className="text-xs text-text-muted">
                                {new Date(step.started_at).toLocaleString()} –{' '}
                                {new Date(step.completed_at).toLocaleTimeString()}
                              </p>
                            </div>
                          </div>
                          <span className="inline-flex items-center gap-1 text-xs font-bold capitalize text-emerald-700">
                            <CheckCircle2 size={14} /> {step.status}
                          </span>
                        </div>

                        <div className="mt-4 space-y-2">
                          {step.checks.map(check => (
                            <div
                              key={`${step.step}-${check.name}`}
                              className="flex items-start gap-2 text-sm"
                            >
                              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" />
                              <p>
                                <span className="font-semibold text-text-main">{check.name}:</span>{' '}
                                <span className="text-text-muted">{check.details}</span>
                              </p>
                            </div>
                          ))}
                        </div>

                        {step.discrepancies.length ? (
                          <div className="mt-4 space-y-2">
                            {step.discrepancies.map((discrepancy, index) => (
                              <div
                                key={`${step.step}-discrepancy-${index}`}
                                className="rounded-lg border border-amber-300/60 bg-amber-500/5 p-3 text-sm"
                              >
                                <p className="flex items-start gap-2 font-semibold text-amber-800">
                                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                                  {discrepancy.description}
                                </p>
                                <p className="mt-2 flex items-start gap-2 text-text-muted">
                                  <Wrench size={15} className="mt-0.5 shrink-0 text-emerald-600" />
                                  <span>
                                    <span className="font-semibold text-emerald-700">Fixed:</span>{' '}
                                    {discrepancy.resolution}
                                  </span>
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-4 text-xs text-text-muted">No discrepancies found.</p>
                        )}

                        {Object.keys(step.result).length ? (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {Object.entries(step.result).map(([key, value]) => (
                              <span
                                key={key}
                                className="rounded-full bg-surface-bg px-2.5 py-1 text-xs text-text-muted"
                              >
                                {formatResultLabel(key)}: <strong className="text-text-main">{String(value)}</strong>
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </article>
                    ))}
                  </div>
                </div>
              )}
            </section>
          </>
        )}

        <div className="border-t border-border-subtle px-6 py-4">
          <Link
            to={{ pathname: INSTITUTIONS_SECTION_PATH, search: location.search }}
            className="text-sm font-semibold text-accent hover:underline"
          >
            Back to institutions
          </Link>
        </div>
      </div>
    </div>
  );
};

export default InstitutionHistoryPage;
