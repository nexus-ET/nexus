import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Briefcase,
  Building2,
  Compass,
  ExternalLink,
  Home,
  Loader2,
  Plane,
  Shield,
  TrendingUp,
} from 'lucide-react';
import { findCountryByIso2, useCountries } from '../hooks/useCountries';
import { useFutureInsights } from '../hooks/useNexusIntel';
import { useConsultationStore } from '../stores/consultationStore';
import { POST_STUDY_GOAL_OPTIONS } from '../config/aspirations.config';
import {
  BUDGET_OPTIONS,
  aspirationsToForm,
  emptyAspirationsForm,
  type StudentAspirationsResponse,
} from '../types/studentAspirations';
import type { UniversityShortlistResponse } from '../types/universityShortlist';
import type {
  FutureInsightsDestinationPack,
  FutureInsightsEmployer,
  FutureInsightsHabitat,
  FutureInsightsInstitutionContext,
  FutureInsightsJob,
} from '../types/nexusIntel';
import { CountryFlag } from '../utils/countryFlag';
import { apiFetch } from '../utils/api';

interface FutureInsightsTabProps {
  bookingId: number;
}

const HABITAT_ICONS: Record<string, React.ReactNode> = {
  city_campus_snapshot: <Compass size={16} />,
  livability_scores: <Activity size={16} />,
  housing_neighborhood: <Home size={16} />,
  transit_mobility: <Plane size={16} />,
  safety_health: <Shield size={16} />,
  lifestyle_amenities: <Building2 size={16} />,
  income_careers: <Briefcase size={16} />,
  digital_academic: <TrendingUp size={16} />,
  ecosystem_culture: <Compass size={16} />,
  funding_support: <TrendingUp size={16} />,
};

const CORE_TAB_ROI = 'core_roi';
const CORE_TAB_IMMIGRATION = 'core_immigration';
const CORE_TAB_JOBS = 'core_jobs';

type InsightTab = {
  key: string;
  title: string;
  icon: React.ReactNode;
  kind: 'roi' | 'immigration' | 'jobs' | 'habitat';
  habitatKey?: string;
};

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className="text-sm text-text-main leading-snug">{value}</p>
    </div>
  );
}

function ScorePill({ score }: { score: number }) {
  const tone =
    score >= 80
      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
      : score >= 70
        ? 'bg-sky-50 text-sky-900 border-sky-200'
        : score >= 60
          ? 'bg-amber-50 text-amber-900 border-amber-200'
          : 'bg-rose-50 text-rose-900 border-rose-200';
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold ${tone}`}>
      {Math.round(score)}/100
    </span>
  );
}

function EmployerCard({
  name,
  websiteUrl,
  logoUrl,
  city,
  sectors,
}: {
  name: string;
  websiteUrl: string;
  logoUrl?: string | null;
  city?: string | null;
  sectors: string[];
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const initial = name.trim().charAt(0).toUpperCase() || '?';

  return (
    <a
      href={websiteUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2.5 transition hover:border-primary/40 hover:bg-primary/5"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border-subtle bg-card">
        {logoUrl && !imgFailed ? (
          <img
            src={logoUrl}
            alt=""
            className="h-7 w-7 object-contain"
            loading="lazy"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <span className="text-sm font-bold text-primary">{initial}</span>
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-text-main group-hover:text-primary">
          {name}
        </span>
        <span className="block truncate text-xs text-text-muted">
          {[city, sectors.slice(0, 2).join(' · ')].filter(Boolean).join(' · ') || 'Official site'}
        </span>
      </span>
      <ExternalLink size={14} className="shrink-0 text-text-muted opacity-60 group-hover:opacity-100" />
    </a>
  );
}

function JobsEmployersPanel({
  employers,
  jobs,
  locationLabel,
  metroMatched,
  institutionName,
  incomeMetrics,
}: {
  employers: FutureInsightsEmployer[];
  jobs: FutureInsightsJob[];
  locationLabel: string;
  metroMatched: boolean;
  institutionName?: string | null;
  incomeMetrics?: FutureInsightsHabitat['categories'][number]['metrics'];
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-muted">
        {institutionName
          ? metroMatched
            ? `Employers & openings near ${institutionName} (${locationLabel}).`
            : `Best-available market data for ${institutionName} (${locationLabel}).`
          : `Country-level market snapshot for ${locationLabel}. Select a shortlisted college for campus-local employers.`}
      </p>

      {incomeMetrics && incomeMetrics.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {incomeMetrics.map(metric => (
            <div
              key={metric.key}
              className="rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2.5 space-y-1"
            >
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                {metric.label}
              </p>
              <p className="text-sm text-text-main leading-snug">{metric.value}</p>
            </div>
          ))}
        </div>
      ) : null}

      {employers.length === 0 ? (
        <p className="text-sm text-text-muted">Employer pack not available for this location yet.</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {employers.map(employer => (
            <EmployerCard
              key={`${employer.name}-${employer.website_url}`}
              name={employer.name}
              websiteUrl={employer.website_url}
              logoUrl={employer.logo_url}
              city={employer.city_or_region}
              sectors={employer.sectors}
            />
          ))}
        </div>
      )}

      <div className="space-y-2 border-t border-border-subtle pt-3">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
          <Briefcase size={12} />
          Targeted openings · {locationLabel}
        </p>
        {jobs.length === 0 ? (
          <p className="text-sm text-text-muted">
            No curated openings for this campus/program mix yet — check employer career pages above.
          </p>
        ) : (
          <ul className="space-y-2">
            {jobs.map(job => (
              <li key={`${job.title}-${job.apply_url}`}>
                <a
                  href={job.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start justify-between gap-3 rounded-lg border border-border-subtle px-3 py-2 transition hover:border-primary/40 hover:bg-primary/5"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-text-main">{job.title}</span>
                    <span className="block text-xs text-text-muted">
                      {job.employer_name} · {job.location}
                    </span>
                  </span>
                  <ExternalLink size={14} className="mt-1 shrink-0 text-text-muted" />
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function DestinationBody({
  pack,
  institutions,
  activeInstitutionId,
  onSelectInstitution,
  budgetLabel,
  postStudyLabels,
}: {
  pack: FutureInsightsDestinationPack;
  institutions: FutureInsightsInstitutionContext[];
  activeInstitutionId: number | null;
  onSelectInstitution: (id: number | null) => void;
  budgetLabel: string | null;
  postStudyLabels: string[];
}) {
  const activeInstitution =
    institutions.find(item => item.institution_id === activeInstitutionId) || null;

  const employers = activeInstitution?.employers?.length
    ? activeInstitution.employers
    : pack.employers;
  const jobs = activeInstitution?.jobs?.length ? activeInstitution.jobs : pack.jobs;
  const locationLabel = activeInstitution?.location_label || pack.country_iso2;
  const metroMatched = Boolean(activeInstitution?.metro_matched);
  const habitat = activeInstitution?.habitat || pack.habitat || null;

  const tabs: InsightTab[] = useMemo(() => {
    const core: InsightTab[] = [
      { key: CORE_TAB_ROI, title: 'ROI & Economics', icon: <TrendingUp size={14} />, kind: 'roi' },
      {
        key: CORE_TAB_IMMIGRATION,
        title: 'Immigration & Visas',
        icon: <Plane size={14} />,
        kind: 'immigration',
      },
      {
        key: CORE_TAB_JOBS,
        title: 'Jobs & Employers',
        icon: <Briefcase size={14} />,
        kind: 'jobs',
      },
    ];
    // Habitat categories except income_careers (merged into Jobs & Employers to avoid duplicate career copy).
    const habitatTabs: InsightTab[] = (habitat?.categories || [])
      .filter(category => category.key !== 'income_careers')
      .map(category => ({
        key: `habitat_${category.key}`,
        title: category.title,
        icon: HABITAT_ICONS[category.key] || <Compass size={14} />,
        kind: 'habitat' as const,
        habitatKey: category.key,
      }));
    return [...core, ...habitatTabs];
  }, [habitat]);

  const [activeTabKey, setActiveTabKey] = useState(CORE_TAB_ROI);
  useEffect(() => {
    if (!tabs.some(tab => tab.key === activeTabKey)) {
      setActiveTabKey(tabs[0]?.key || CORE_TAB_ROI);
    }
  }, [tabs, activeTabKey]);

  const activeTab = tabs.find(tab => tab.key === activeTabKey) || tabs[0];
  const activeHabitatCategory =
    activeTab?.kind === 'habitat' && activeTab.habitatKey
      ? habitat?.categories.find(category => category.key === activeTab.habitatKey)
      : null;
  const incomeMetrics = habitat?.categories.find(c => c.key === 'income_careers')?.metrics;

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      {institutions.length > 0 && (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Shortlisted college / campus location
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onSelectInstitution(null)}
              className={`rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                activeInstitutionId == null
                  ? 'border-primary bg-primary text-white'
                  : 'border-border-subtle bg-card text-text-muted hover:border-primary/40'
              }`}
            >
              Country overview
            </button>
            {institutions.map(inst => (
              <button
                key={inst.institution_id}
                type="button"
                onClick={() => onSelectInstitution(inst.institution_id)}
                className={`max-w-[16rem] rounded-xl border px-3 py-2 text-left text-xs font-semibold transition ${
                  activeInstitutionId === inst.institution_id
                    ? 'border-primary bg-primary text-white'
                    : 'border-border-subtle bg-card text-text-main hover:border-primary/40'
                }`}
              >
                <span className="block truncate">{inst.institution_name}</span>
                <span
                  className={`block truncate font-medium ${
                    activeInstitutionId === inst.institution_id
                      ? 'text-white/80'
                      : 'text-text-muted'
                  }`}
                >
                  {inst.location_label}
                  {inst.metro_matched ? ' · local market' : ''}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {(budgetLabel || postStudyLabels.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {budgetLabel ? (
            <span className="rounded-full border border-border-subtle bg-card px-2.5 py-1 text-xs font-medium text-text-muted">
              Budget: {budgetLabel}
            </span>
          ) : null}
          {postStudyLabels.map(label => (
            <span
              key={label}
              className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary"
            >
              {label}
            </span>
          ))}
        </div>
      )}

      <section className="rounded-xl border border-border-subtle bg-card overflow-hidden">
        <div className="border-b border-border-subtle bg-surface-bg/60 px-4 py-3">
          <p className="text-[10px] font-bold uppercase tracking-wide text-primary">Insights</p>
          <h4 className="text-sm font-bold text-text-main">
            One category at a time · {locationLabel}
          </h4>
        </div>

        <div className="flex gap-1 overflow-x-auto border-b border-border-subtle px-2 pt-2 custom-scrollbar">
          {tabs.map(tab => {
            const on = tab.key === activeTab?.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTabKey(tab.key)}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-xs font-semibold transition ${
                  on
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-transparent text-text-muted hover:text-text-main'
                }`}
              >
                {tab.icon}
                {tab.title}
              </button>
            );
          })}
        </div>

        <div className="p-4 space-y-3">
          {activeTab?.kind === 'roi' && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <MetricRow label="Tuition baseline" value={pack.roi.tuition_baseline} />
                <MetricRow label="Health / fees" value={pack.roi.health_fees_note} />
                <MetricRow label="Median starting salary" value={pack.roi.median_starting_salary} />
                <MetricRow label="Break-even horizon" value={pack.roi.break_even_horizon} />
              </div>
              <p className="text-sm text-text-muted leading-snug border-t border-border-subtle pt-3">
                <span className="font-semibold text-text-main">10-year yield: </span>
                {pack.roi.ten_year_yield_note}
              </p>
            </>
          )}

          {activeTab?.kind === 'immigration' && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <MetricRow label="Post-study work" value={pack.immigration.psw_rights} />
                <MetricRow label="Work while studying" value={pack.immigration.work_limits} />
                <MetricRow label="Dependents" value={pack.immigration.dependent_rules} />
                <MetricRow
                  label="Proof of funds"
                  value={pack.immigration.proof_of_funds_summary || '—'}
                />
              </div>
              {pack.immigration.pathway_notes.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-text-muted border-t border-border-subtle pt-3">
                  {pack.immigration.pathway_notes.map(note => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )}
              {pack.immigration.language_requirements ? (
                <p className="text-xs text-text-muted">
                  Language: {pack.immigration.language_requirements}
                </p>
              ) : null}
            </>
          )}

          {activeTab?.kind === 'jobs' && (
            <JobsEmployersPanel
              employers={employers}
              jobs={jobs}
              locationLabel={locationLabel}
              metroMatched={metroMatched}
              institutionName={activeInstitution?.institution_name}
              incomeMetrics={incomeMetrics}
            />
          )}

          {activeTab?.kind === 'habitat' && activeHabitatCategory && (
            <>
              <p className="text-sm text-text-muted leading-snug">{activeHabitatCategory.summary}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {activeHabitatCategory.metrics.map(metric => (
                  <div
                    key={metric.key}
                    className="rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2.5 space-y-1"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                        {metric.label}
                      </p>
                      {metric.score != null && Number.isFinite(metric.score) ? (
                        <ScorePill score={Number(metric.score)} />
                      ) : null}
                    </div>
                    <p className="text-sm text-text-main leading-snug">{metric.value}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      <p className="text-[11px] leading-relaxed text-text-muted">
        As of {pack.as_of}. {pack.disclaimer}{' '}
        <Link to="/nexus-intel/workflows" className="font-semibold text-primary hover:underline">
          Open Intel Workflows
        </Link>{' '}
        for proof-of-funds and side-by-side compare.
      </p>
    </div>
  );
}

const FutureInsightsTab: React.FC<FutureInsightsTabProps> = ({ bookingId }) => {
  const { countries } = useCountries();
  const form = useConsultationStore(state => state.form);
  const hydrated = useConsultationStore(state => state.hydrated);
  const loadingAspirations = useConsultationStore(state => state.loading);
  const loadSeq = useRef(0);
  const [activeIso2, setActiveIso2] = useState<string | null>(null);
  const [activeInstitutionId, setActiveInstitutionId] = useState<number | null>(null);

  useEffect(() => {
    const seq = ++loadSeq.current;
    const hydrate = useConsultationStore.getState().hydrate;
    const setLoading = useConsultationStore.getState().setLoading;
    const setError = useConsultationStore.getState().setError;
    useConsultationStore.setState({ bookingId });

    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = (await apiFetch(
          `bookings/mine/${bookingId}/aspirations`
        )) as StudentAspirationsResponse;
        if (cancelled || seq !== loadSeq.current) return;
        hydrate({
          form: aspirationsToForm(response.aspirations),
          bookingId,
          savedAt: response.saved_at || null,
        });
      } catch (err) {
        if (cancelled || seq !== loadSeq.current) return;
        setError(err instanceof Error ? err.message : 'Failed to load aspirations.');
        hydrate({ form: emptyAspirationsForm(), bookingId, savedAt: null });
      } finally {
        if (!cancelled && seq === loadSeq.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [bookingId]);

  const destinationIso2s = useMemo(() => {
    const fromTargets = form.target_countries.map(item => item.iso2.toUpperCase());
    const fromLegacy = (form.study_countries_iso2 || []).map(code => code.toUpperCase());
    const merged = [...fromTargets, ...fromLegacy].filter(
      code => code && code !== 'OTHER' && /^[A-Z]{2}$/.test(code)
    );
    return Array.from(new Set(merged));
  }, [form.target_countries, form.study_countries_iso2]);

  const priorityByIso = useMemo(() => {
    const map = new Map<string, string>();
    form.target_countries.forEach(item => {
      map.set(item.iso2.toUpperCase(), item.priority);
    });
    return map;
  }, [form.target_countries]);

  const sortedDestinations = useMemo(() => {
    return [...destinationIso2s].sort((a, b) => {
      const aTop = priorityByIso.get(a) === 'TOP_CHOICE' ? 0 : 1;
      const bTop = priorityByIso.get(b) === 'TOP_CHOICE' ? 0 : 1;
      if (aTop !== bTop) return aTop - bTop;
      return a.localeCompare(b);
    });
  }, [destinationIso2s, priorityByIso]);

  useEffect(() => {
    if (!sortedDestinations.length) {
      setActiveIso2(null);
      return;
    }
    setActiveIso2(prev =>
      prev && sortedDestinations.includes(prev) ? prev : sortedDestinations[0]
    );
  }, [sortedDestinations]);

  const programs = useMemo(
    () => [...(form.programs || []), form.current_program_code || ''].filter(Boolean),
    [form.programs, form.current_program_code]
  );

  const shortlistQuery = useQuery({
    queryKey: ['university-shortlist', bookingId, 'future-insights'],
    queryFn: () =>
      apiFetch<UniversityShortlistResponse>(`bookings/mine/${bookingId}/university-shortlist`),
    staleTime: 60_000,
  });

  const shortlistInstitutionIds = useMemo(() => {
    const items = shortlistQuery.data?.run?.items || [];
    return Array.from(new Set(items.map(item => item.institution_id).filter(Boolean)));
  }, [shortlistQuery.data]);

  const insightsQuery = useFutureInsights(sortedDestinations, programs, shortlistInstitutionIds);

  const packByIso = useMemo(() => {
    const map = new Map<string, FutureInsightsDestinationPack>();
    (insightsQuery.data?.destinations || []).forEach(pack => {
      map.set(pack.country_iso2.toUpperCase(), pack);
      map.set(pack.country_code.toUpperCase(), pack);
    });
    return map;
  }, [insightsQuery.data]);

  const activePack =
    (activeIso2 &&
      (packByIso.get(activeIso2) || packByIso.get(activeIso2 === 'GB' ? 'UK' : activeIso2))) ||
    null;

  const institutionsForCountry = useMemo(() => {
    if (!activePack) return [];
    return activePack.institutions || [];
  }, [activePack]);

  useEffect(() => {
    if (!institutionsForCountry.length) {
      setActiveInstitutionId(null);
      return;
    }
    setActiveInstitutionId(prev => {
      if (prev != null && institutionsForCountry.some(item => item.institution_id === prev)) {
        return prev;
      }
      // Prefer first metro-matched college (e.g. UCLA → LA), else first shortlisted.
      const preferred =
        institutionsForCountry.find(item => item.metro_matched) || institutionsForCountry[0];
      return preferred.institution_id;
    });
  }, [institutionsForCountry, activeIso2]);

  const budgetLabel =
    BUDGET_OPTIONS.find(option => form.budget?.[0] === option.value)?.label.replace(/ — .*$/, '') ||
    null;

  const postStudyLabels = (form.post_study_goals || [])
    .map(code => POST_STUDY_GOAL_OPTIONS.find(option => option.value === code)?.label)
    .filter((label): label is string => Boolean(label));

  const unsupported = insightsQuery.data?.unsupported_countries || [];

  if (loadingAspirations && !hydrated) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-text-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading Future Insights…
      </div>
    );
  }

  if (!sortedDestinations.length) {
    return (
      <div className="mx-auto max-w-xl space-y-3 px-4 py-12 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Compass size={22} />
        </div>
        <h3 className="text-base font-bold text-text-main">No destinations selected yet</h3>
        <p className="text-sm text-text-muted leading-relaxed">
          Add target countries in Aspirations (Core Vision & Destination). Future Insights will then
          load ROI, employers, immigration pathways, and city living for each selection.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-primary">Future Insights</p>
          <h3 className="text-base font-bold text-text-main">Destination & career intelligence</h3>
          <p className="mt-0.5 text-xs text-text-muted">
            Comparative talk-track for selected destinations, programs, and shortlisted colleges.
          </p>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
        {sortedDestinations.map(iso2 => {
          const country = findCountryByIso2(countries, iso2);
          const active = activeIso2 === iso2;
          const top = priorityByIso.get(iso2) === 'TOP_CHOICE';
          return (
            <button
              key={iso2}
              type="button"
              onClick={() => setActiveIso2(iso2)}
              className={`inline-flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                active
                  ? 'border-primary bg-primary text-white shadow-sm'
                  : 'border-border-subtle bg-card text-text-main hover:border-primary/40 hover:bg-primary/5'
              }`}
            >
              <CountryFlag iso2={iso2} size="sm" />
              <span>{country?.name || iso2}</span>
              {top ? (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                    active ? 'bg-white/20 text-white' : 'bg-primary/10 text-primary'
                  }`}
                >
                  Top
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {unsupported.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Limited pack for: {unsupported.join(', ')}. Immigration/ROI detail may be incomplete —
          verify official sources.
        </p>
      )}

      {!shortlistInstitutionIds.length && (
        <p className="rounded-lg border border-border-subtle bg-surface-bg/70 px-3 py-2 text-xs text-text-muted">
          Tip: generate a Shortlist to unlock campus-local employers and job openings (e.g. UCLA →
          Los Angeles market).
        </p>
      )}

      {insightsQuery.isLoading || shortlistQuery.isLoading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-text-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Fetching destination intelligence…
        </div>
      ) : insightsQuery.isError ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {insightsQuery.error instanceof Error
            ? insightsQuery.error.message
            : 'Failed to load Future Insights.'}
        </p>
      ) : activePack ? (
        <DestinationBody
          pack={activePack}
          institutions={institutionsForCountry}
          activeInstitutionId={activeInstitutionId}
          onSelectInstitution={setActiveInstitutionId}
          budgetLabel={budgetLabel}
          postStudyLabels={postStudyLabels}
        />
      ) : (
        <p className="text-sm text-text-muted py-8 text-center">
          No intelligence pack available for this destination yet.
        </p>
      )}
    </div>
  );
};

export default FutureInsightsTab;
