import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Loader2, RefreshCw, School } from 'lucide-react';
import { apiFetch } from '../utils/api';
import {
  FIT_BAND_META,
  formatCatalogRef,
  formatPathwayLine,
  formatScore,
  scoreNumber,
  type FitBand,
  type MatchedAcademicPathway,
  type MatchingWeightProfile,
  type UniversityShortlistItem,
  type UniversityShortlistResponse,
  type UniversityShortlistRun,
} from '../types/universityShortlist';
import EmptyListMessage from './ui/EmptyListMessage';
import {
  studentInfoAlertErrorClass,
  studentInfoAlertSuccessClass,
  studentInfoGhostBtnClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
  studentInfoMutedClass,
  studentInfoPrimaryBtnClass,
  studentInfoSectionClass as sectionClass,
  studentInfoSectionTitleClass,
} from './studentInfoFormStyles';

interface UniversityShortlistTabProps {
  bookingId: number;
  compact?: boolean;
}

type BandFilter = 'all' | FitBand;

function ScoreBar({ label, value, barClass }: { label: string; value: number; barClass: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-text-muted">{label}</span>
        <span className="font-bold text-text-main">{value.toFixed(1)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-bg overflow-hidden">
        <div className={`h-full rounded-full ${barClass}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function AcademicPathwayBlock({
  item,
  pathways,
}: {
  item: UniversityShortlistItem;
  pathways: MatchedAcademicPathway[];
}) {
  const primary = pathways[0];
  const alternates = pathways.slice(1);

  return (
    <div className="rounded-md border border-sky-100 bg-sky-50/50 px-3 py-2 space-y-2">
      <p className="text-xs font-bold uppercase tracking-wide text-sky-900">Derived academic path</p>
      <div className="grid gap-1.5 sm:grid-cols-3 text-sm">
        <div>
          <p className="text-xs font-semibold text-text-muted">Program</p>
          <p className="font-semibold text-text-main">
            {item.program_name || item.program_code || primary?.program_name || primary?.program_code || '—'}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold text-text-muted">Major</p>
          <p className="font-semibold text-text-main">
            {item.major_name || item.major_code || primary?.major_name || primary?.major_code || '—'}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold text-text-muted">Course</p>
          <p className="font-semibold text-text-main">
            {item.course_label || item.course_code || primary?.course_label || primary?.course_code || '—'}
            {item.course_level || primary?.course_level
              ? ` · ${item.course_level || primary?.course_level}`
              : ''}
          </p>
        </div>
      </div>
      {primary?.match_reason ? (
        <p className={`text-xs ${studentInfoMutedClass}`}>{primary.match_reason}</p>
      ) : null}
      {alternates.length > 0 ? (
        <div className="pt-1 border-t border-sky-100 space-y-1">
          <p className="text-xs font-semibold text-text-muted">Other matched offerings</p>
          {alternates.map(pathway => (
            <p
              key={`${pathway.offering_id}-${pathway.course_code}-${pathway.major_code}`}
              className="text-sm text-text-main"
            >
              {formatPathwayLine(pathway) || 'Catalog offering'}
              {pathway.match_score != null ? (
                <span className="text-text-muted"> · match {Number(pathway.match_score).toFixed(0)}</span>
              ) : null}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ShortlistItemCard({ item }: { item: UniversityShortlistItem }) {
  const [open, setOpen] = useState(false);
  const band = FIT_BAND_META[item.fit_band];
  const pathways =
    item.matched_pathways && item.matched_pathways.length > 0
      ? item.matched_pathways
      : item.explanation?.matched_pathways || [];
  const reasons = [
    ...(item.explanation?.academic?.reasons ?? []),
    ...(item.explanation?.aspirations?.reasons ?? []),
    ...(item.explanation?.profile?.reasons ?? []),
    ...(item.explanation?.safety?.reasons ?? []),
  ].slice(0, 8);

  return (
    <article className="rounded-lg border border-border-subtle bg-card p-3 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-text-muted">#{item.rank}</span>
            <h4 className="text-sm font-bold text-text-main truncate">
              {item.institution_name || `Institution #${item.institution_id}`}
            </h4>
            <span
              className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${band.badgeClass}`}
            >
              {band.label}
            </span>
          </div>
          <p className={`mt-1 ${studentInfoMutedClass}`}>
            {[
              item.institution_country_iso2,
              item.ranking_tier_global,
              item.institution_type,
            ]
              .filter(Boolean)
              .join(' · ') || 'Catalog metadata limited'}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Fit score</p>
          <p className="text-xl font-bold text-sky-900">{formatScore(item.consolidated_score)}</p>
        </div>
      </div>

      <AcademicPathwayBlock item={item} pathways={pathways} />

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <ScoreBar label="Academic" value={scoreNumber(item.s_academic)} barClass="bg-violet-500" />
        <ScoreBar label="Profile" value={scoreNumber(item.s_profile)} barClass="bg-teal-500" />
        <ScoreBar label="Aspirations" value={scoreNumber(item.s_aspirations)} barClass="bg-sky-500" />
        <ScoreBar label="Safety*" value={scoreNumber(item.s_safety)} barClass={band.barClass} />
      </div>

      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="inline-flex items-center gap-1 text-sm font-semibold text-sky-700 hover:text-sky-900"
      >
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {open ? 'Hide explanation' : 'Why this match'}
      </button>

      {open ? (
        <div className="rounded-md border border-border-subtle bg-surface-bg/40 px-3 py-2 space-y-1.5">
          {reasons.length > 0 ? (
            reasons.map(reason => (
              <p key={reason} className="text-sm text-text-main">
                • {reason}
              </p>
            ))
          ) : (
            <p className={studentInfoMutedClass}>No explanation details stored for this item.</p>
          )}
        </div>
      ) : null}
    </article>
  );
}

const UniversityShortlistTab: React.FC<UniversityShortlistTabProps> = ({
  bookingId,
  compact = false,
}) => {
  const [profiles, setProfiles] = useState<MatchingWeightProfile[]>([]);
  const [weightCode, setWeightCode] = useState<string>('default');
  const [run, setRun] = useState<UniversityShortlistRun | null>(null);
  const [bandFilter, setBandFilter] = useState<BandFilter>('all');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const apiPath = `bookings/mine/${bookingId}/university-shortlist`;

  const loadLatest = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as UniversityShortlistResponse;
    setRun(response.run);
  }, [apiPath]);

  const loadProfiles = useCallback(async () => {
    const list = (await apiFetch('bookings/matching/weight-profiles')) as MatchingWeightProfile[];
    setProfiles(list);
    const preferred = list.find(p => p.is_default) || list[0];
    if (preferred) setWeightCode(preferred.code);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    (async () => {
      try {
        await loadLatest();
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load university shortlist.');
      }
      try {
        await loadProfiles();
      } catch {
        // Profiles are optional for viewing an existing run; generation still works with "default".
        if (!cancelled) setProfiles([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadLatest, loadProfiles]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    setSuccess(null);
    try {
      const response = (await apiFetch(apiPath, {
        method: 'POST',
        body: JSON.stringify({
          weight_profile_code: weightCode || null,
          limit: 40,
        }),
      })) as UniversityShortlistResponse;
      setRun(response.run);
      const count = response.run?.item_count ?? 0;
      setSuccess(
        count > 0
          ? `Generated ${count} institution${count === 1 ? '' : 's'} (Phase 1 heuristic fit).`
          : 'Shortlist run finished with no matching institutions.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate shortlist.');
    } finally {
      setGenerating(false);
    }
  };

  const items = useMemo(() => {
    const list = run?.items ?? [];
    if (bandFilter === 'all') return list;
    return list.filter(item => item.fit_band === bandFilter);
  }, [run, bandFilter]);

  const bandCounts = useMemo(() => {
    const counts: Record<FitBand, number> = { safe: 0, target: 0, reach: 0 };
    for (const item of run?.items ?? []) {
      counts[item.fit_band] += 1;
    }
    return counts;
  }, [run]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted py-16">
        <Loader2 size={20} className="animate-spin mr-2" />
        <span className="text-sm">Loading university shortlist…</span>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-1 min-h-0 flex-col overflow-y-auto custom-scrollbar space-y-4 ${
        compact ? '' : 'px-1'
      }`}
    >
      <section className={sectionClass}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className={studentInfoSectionTitleClass}>University Shortlist</h3>
            <p className={`mt-1 ${studentInfoMutedClass}`}>
              Soft match from aspirations, catalog, GPA bands, tests, and profile signals.
            </p>
          </div>
          <School size={18} className="text-sky-700 shrink-0 mt-0.5" />
        </div>

        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          {run?.disclaimer ||
            'Phase 1 fit confidence only. Safe/Target/Reach are heuristics — not admission probability.'}
        </div>

        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div>
            <label htmlFor="weight-profile" className={labelClass}>
              Weight profile
            </label>
            <select
              id="weight-profile"
              className={inputClass}
              value={weightCode}
              onChange={e => setWeightCode(e.target.value)}
              disabled={generating}
            >
              {profiles.length === 0 ? <option value="default">Default</option> : null}
              {profiles.map(profile => (
                <option key={profile.id} value={profile.code}>
                  {profile.name}
                  {profile.is_default ? ' (default)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={studentInfoGhostBtnClass}
              onClick={() => {
                setError(null);
                setSuccess(null);
                setLoading(true);
                loadLatest()
                  .catch(err =>
                    setError(err instanceof Error ? err.message : 'Failed to refresh shortlist.')
                  )
                  .finally(() => setLoading(false));
              }}
              disabled={generating || loading}
            >
              <RefreshCw size={14} />
              Refresh
            </button>
            <button
              type="button"
              className={studentInfoPrimaryBtnClass}
              onClick={() => void handleGenerate()}
              disabled={generating}
            >
              {generating ? <Loader2 size={14} className="animate-spin" /> : null}
              {generating ? 'Generating…' : run ? 'Regenerate shortlist' : 'Generate shortlist'}
            </button>
          </div>
        </div>

        {error ? <div className={studentInfoAlertErrorClass}>{error}</div> : null}
        {success ? <div className={studentInfoAlertSuccessClass}>{success}</div> : null}
        {run?.notes ? (
          <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
            {run.notes}
          </div>
        ) : null}
      </section>

      {!run ? (
        <EmptyListMessage message="No shortlist yet. Generate one to score institutions against this student’s profile." />
      ) : (
        <>
          <section className={sectionClass}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className={studentInfoSectionTitleClass}>Results</h3>
                <p className={`mt-1 ${studentInfoMutedClass}`}>
                  Run #{run.id} · {run.algorithm_version} · {run.item_count} institutions ·{' '}
                  {new Date(run.created_at).toLocaleString()}
                  {run.weight_profile ? ` · ${run.weight_profile.name}` : ''}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    ['all', `All (${run.item_count})`],
                    ['safe', `Safe (${bandCounts.safe})`],
                    ['target', `Target (${bandCounts.target})`],
                    ['reach', `Reach (${bandCounts.reach})`],
                  ] as Array<[BandFilter, string]>
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setBandFilter(key)}
                    className={`rounded-md border px-2.5 py-1 text-xs font-semibold transition-colors ${
                      bandFilter === key
                        ? 'border-sky-300 bg-sky-100 text-sky-900'
                        : 'border-border-subtle bg-card text-text-muted hover:text-text-main'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <p className={`text-xs ${studentInfoMutedClass}`}>
              *Safety is a heuristic vs ranking selectivity, not historical admit odds.
            </p>
          </section>

          {run.derived_academic ? (
            <section className={sectionClass}>
              <h3 className={studentInfoSectionTitleClass}>Derived Programs · Majors · Courses</h3>
              <p className={`mt-1 ${studentInfoMutedClass}`}>
                {run.derived_academic.source === 'aspiration_catalog'
                  ? 'No institution offerings published yet — derived from aspirations against the academic catalog.'
                  : 'Aggregated from institution offerings matched in this shortlist run.'}
              </p>
              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-md border border-border-subtle bg-surface-bg/30 px-3 py-2 space-y-1">
                  <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                    Student preferences
                  </p>
                  <p className="text-sm text-text-main">
                    Programs:{' '}
                    {(run.derived_academic.student_preferences?.programs || []).join(', ') || '—'}
                    {run.derived_academic.student_preferences?.programs_other
                      ? ` / ${run.derived_academic.student_preferences.programs_other}`
                      : ''}
                  </p>
                  <p className="text-sm text-text-main">
                    Disciplines:{' '}
                    {(
                      run.derived_academic.student_preferences?.discipline_university_college || []
                    ).join(', ') || '—'}
                  </p>
                </div>
                <div className="rounded-md border border-border-subtle bg-surface-bg/30 px-3 py-2 space-y-2">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                      Matched programs
                    </p>
                    <p className="text-sm text-text-main">
                      {(run.derived_academic.matched_programs || [])
                        .map(formatCatalogRef)
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                      Matched majors
                    </p>
                    <p className="text-sm text-text-main">
                      {(run.derived_academic.matched_majors || [])
                        .map(formatCatalogRef)
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                      Matched courses
                    </p>
                    <p className="text-sm text-text-main">
                      {(run.derived_academic.matched_courses || [])
                        .map(formatCatalogRef)
                        .filter(Boolean)
                        .slice(0, 12)
                        .join(' · ') || '—'}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          ) : null}

          {items.length === 0 ? (
            <EmptyListMessage message="No institutions in this filter. Try All, or regenerate after updating aspirations/countries." />
          ) : (
            <div className="space-y-3 pb-2">
              {items.map(item => (
                <ShortlistItemCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UniversityShortlistTab;
