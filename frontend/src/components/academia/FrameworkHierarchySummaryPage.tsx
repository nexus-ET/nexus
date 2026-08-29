import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, RefreshCw } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { apiFetch } from '../../utils/api';
import {
  COURSES_PATH,
  FRAMEWORK_SECTION_PATH,
  LEVELS_PATH,
  MAJORS_PATH,
  PROGRAMS_PATH,
  SUB_MAJORS_PATH,
  type AcademicHierarchySummary,
  type FrameworkCountryCoverage,
  type FrameworkCoverageMetrics,
  type FrameworkCoveragePair,
  type FrameworkInstitutionCoverage,
  type HierarchyLevelNode,
} from '../../types/academicFramework';
import { INSTITUTIONS_MANAGE_PATH } from '../../types/institutions';
import { INSTITUTIONS_COLLEGES_PATH } from '../../config/academiaHubNav';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import { FrameworkHierarchyId } from './FrameworkIdDisplay';

const courseFilterPath = (levelId: number, programId: number, majorId: number) =>
  `${COURSES_PATH}?levelId=${levelId}&programId=${programId}&majorId=${majorId}`;

function formatCount(value: number | undefined): string {
  return Number(value || 0).toLocaleString();
}

function formatPct(value: number | undefined): string {
  return `${Number(value || 0).toFixed(1)}%`;
}

function sharePct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 1000) / 10;
}

function GapValue({
  count,
  pct,
}: {
  count: number;
  pct: number;
}) {
  const incomplete = count > 0;
  return (
    <span className={`tabular-nums ${incomplete ? 'font-semibold text-alert' : 'text-text-main'}`}>
      {formatCount(count)}{' '}
      <span className={incomplete ? 'text-alert' : 'text-text-muted'}>({formatPct(pct)})</span>
    </span>
  );
}

function CoverageRow({
  href,
  withLabel,
  withoutLabel,
  pair,
}: {
  href: string;
  withLabel: string;
  withoutLabel: string;
  pair: FrameworkCoveragePair;
}) {
  const incomplete = pair.unmapped > 0;
  const withPct = pair.mapped_pct ?? sharePct(pair.mapped, pair.total);
  const withoutPct = pair.unmapped_pct ?? sharePct(pair.unmapped, pair.total);
  const pctClass = incomplete ? 'font-semibold text-alert' : 'text-text-main';
  return (
    <tr className="border-t border-border-subtle/70">
      <td className="px-4 py-3">
        <Link to={href} className="font-semibold text-accent hover:underline">
          {withLabel}
        </Link>
      </td>
      <td className="px-4 py-3 tabular-nums text-text-main">{formatCount(pair.mapped)}</td>
      <td className={`px-4 py-3 tabular-nums ${pctClass}`}>{formatPct(withPct)}</td>
      <td className="px-4 py-3">
        <Link to={href} className="font-semibold text-accent hover:underline">
          {withoutLabel}
        </Link>
      </td>
      <td className={`px-4 py-3 tabular-nums font-semibold ${incomplete ? 'text-alert' : 'text-text-main'}`}>
        {formatCount(pair.unmapped)}
      </td>
      <td className={`px-4 py-3 tabular-nums ${pctClass}`}>{formatPct(withoutPct)}</td>
      <td className="px-4 py-3 tabular-nums text-text-muted">{formatCount(pair.total)}</td>
    </tr>
  );
}

function CatalogMetric({
  label,
  value,
  href,
  hint,
  emphasizeGap = false,
}: {
  label: string;
  value: number;
  href: string;
  hint?: string;
  emphasizeGap?: boolean;
}) {
  const incomplete = emphasizeGap && value > 0;
  return (
    <Link
      to={href}
      className="block min-w-[7.25rem] shrink-0 rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2.5 hover:border-accent/40"
    >
      <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-text-muted">
        {label}
      </p>
      <p
        className={`mt-1 text-xl font-bold tabular-nums ${
          incomplete ? 'text-alert' : 'text-text-main'
        }`}
      >
        {formatCount(value)}
      </p>
      {hint ? (
        <p className={`mt-0.5 truncate text-[10px] ${incomplete ? 'text-alert' : 'text-text-muted'}`}>
          {hint}
        </p>
      ) : null}
    </Link>
  );
}

function mappingHint(pair: FrameworkCoveragePair): string {
  return `${formatCount(pair.mapped)} / ${formatCount(pair.total)} · ${formatPct(pair.mapped_pct)}`;
}

function gapHint(pair: FrameworkCoveragePair): string {
  return `${formatCount(pair.unmapped)} / ${formatCount(pair.total)} · ${formatPct(pair.unmapped_pct)}`;
}

function CoveragePairTable({
  major,
  subMajor,
  course,
  level,
  programUrl,
}: {
  major: FrameworkCoveragePair;
  subMajor: FrameworkCoveragePair;
  course: FrameworkCoveragePair;
  level: FrameworkCoveragePair;
  programUrl: FrameworkCoveragePair;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border-subtle">
      <table className="min-w-full text-sm">
        <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
          <tr>
            <th className="px-4 py-3 font-semibold">With</th>
            <th className="px-4 py-3 font-semibold">Count</th>
            <th className="px-4 py-3 font-semibold">%</th>
            <th className="px-4 py-3 font-semibold">Without</th>
            <th className="px-4 py-3 font-semibold">Count</th>
            <th className="px-4 py-3 font-semibold">%</th>
            <th className="px-4 py-3 font-semibold">Programs</th>
          </tr>
        </thead>
        <tbody>
          <CoverageRow
            href={PROGRAMS_PATH}
            withLabel="With major"
            withoutLabel="No major"
            pair={major}
          />
          <CoverageRow
            href={SUB_MAJORS_PATH}
            withLabel="With sub-major"
            withoutLabel="No sub-major"
            pair={subMajor}
          />
          <CoverageRow
            href={COURSES_PATH}
            withLabel="With course"
            withoutLabel="No course"
            pair={course}
          />
          <CoverageRow
            href={LEVELS_PATH}
            withLabel="With level"
            withoutLabel="No level"
            pair={level}
          />
          <CoverageRow
            href={PROGRAMS_PATH}
            withLabel="With program URL"
            withoutLabel="No program URL"
            pair={programUrl}
          />
        </tbody>
      </table>
    </div>
  );
}

function InstitutionCoverageTable({
  rows,
  showCountry,
  emptyLabel,
}: {
  rows: FrameworkInstitutionCoverage[];
  showCountry: boolean;
  emptyLabel: string;
}) {
  const colSpan = showCountry ? 8 : 7;
  return (
    <table className="min-w-full text-sm">
      <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
        <tr>
          <th className="px-4 py-3 font-semibold">Institution</th>
          {showCountry ? <th className="px-4 py-3 font-semibold">Country</th> : null}
          <th className="px-4 py-3 font-semibold">Programs</th>
          <th className="px-4 py-3 font-semibold">No major</th>
          <th className="px-4 py-3 font-semibold">No sub-major</th>
          <th className="px-4 py-3 font-semibold">No course</th>
          <th className="px-4 py-3 font-semibold">No level</th>
          <th className="px-4 py-3 font-semibold">No program URL</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={colSpan} className="px-4 py-6 text-sm text-text-muted">
              {emptyLabel}
            </td>
          </tr>
        ) : (
          rows.map(row => (
            <tr key={row.institution_id} className="border-t border-border-subtle/70">
              <td className="px-4 py-3 font-medium text-text-main">{row.institution_name}</td>
              {showCountry ? (
                <td className="px-4 py-3 text-text-main">{row.country_name || '—'}</td>
              ) : null}
              <td className="px-4 py-3 tabular-nums text-text-muted">
                {formatCount(row.program_count)}
              </td>
              <td className="px-4 py-3">
                <GapValue
                  count={row.without_major}
                  pct={row.without_major_pct ?? sharePct(row.without_major, row.program_count)}
                />
              </td>
              <td className="px-4 py-3">
                <GapValue
                  count={row.without_sub_major}
                  pct={
                    row.without_sub_major_pct ?? sharePct(row.without_sub_major, row.program_count)
                  }
                />
              </td>
              <td className="px-4 py-3">
                <GapValue
                  count={row.without_course}
                  pct={row.without_course_pct ?? sharePct(row.without_course, row.program_count)}
                />
              </td>
              <td className="px-4 py-3">
                <GapValue
                  count={row.without_level}
                  pct={row.without_level_pct ?? sharePct(row.without_level, row.program_count)}
                />
              </td>
              <td className="px-4 py-3">
                <GapValue
                  count={row.without_url ?? 0}
                  pct={row.without_url_pct ?? sharePct(row.without_url ?? 0, row.program_count)}
                />
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

function countryTabKey(row: FrameworkCountryCoverage): string {
  return row.country_id != null ? `id:${row.country_id}` : 'none';
}

function countryTabLabel(row: FrameworkCountryCoverage): string {
  return row.country_name || 'No country';
}

function filterLevelsForCountry(
  levels: HierarchyLevelNode[],
  programIds: Set<number> | null
): HierarchyLevelNode[] {
  if (!programIds) return levels;
  const filtered: HierarchyLevelNode[] = [];
  for (const level of levels) {
    const programs = level.programs.filter(program => programIds.has(program.id));
    if (programs.length === 0) continue;
    const majorIds = new Set<number>();
    const subMajorIds = new Set<number>();
    for (const program of programs) {
      for (const major of program.majors) majorIds.add(major.id);
      for (const subId of program.sub_major_ids ?? []) subMajorIds.add(subId);
    }
    filtered.push({
      ...level,
      programs,
      major_count: majorIds.size,
      sub_major_count: subMajorIds.size,
    });
  }
  return filtered;
}

function CoveragePanel({
  coverage,
  selectedTab,
  onSelectTab,
}: {
  coverage: FrameworkCoverageMetrics;
  selectedTab: string;
  onSelectTab: (tab: string) => void;
}) {
  const countries = coverage.by_country ?? [];
  const selectedCountry = useMemo(
    () => countries.find(row => countryTabKey(row) === selectedTab) ?? null,
    [countries, selectedTab]
  );
  const isAll = selectedTab === 'all' || !selectedCountry;

  const programCount = isAll ? coverage.program_count : selectedCountry.program_count;
  const institutionCount = isAll
    ? (coverage.institution_count ?? 0)
    : (selectedCountry?.institution_count ?? 0);
  const campusCount = isAll
    ? (coverage.campus_count ?? 0)
    : (selectedCountry?.campus_count ?? 0);
  const collegeCount = isAll
    ? (coverage.college_count ?? 0)
    : (selectedCountry?.college_count ?? 0);
  const majorCount = isAll ? coverage.major_count : selectedCountry.major_count;
  const subMajorCount = isAll ? coverage.sub_major_count : selectedCountry.sub_major_count;
  const levelCount = isAll ? coverage.level_count : selectedCountry.level_count;
  const noMajorCount = isAll
    ? (coverage.programs_with_no_major ?? coverage.major_mapping.unmapped)
    : (selectedCountry?.programs_with_no_major ?? selectedCountry.major_mapping.unmapped);
  const noSubMajorCount = isAll
    ? (coverage.programs_with_no_sub_major ?? coverage.sub_major_mapping.unmapped)
    : (selectedCountry?.programs_with_no_sub_major ?? selectedCountry.sub_major_mapping.unmapped);
  const pairs = isAll
    ? {
        major: coverage.major_mapping,
        subMajor: coverage.sub_major_mapping,
        course: coverage.course_link,
        level: coverage.level_assignment,
        programUrl: coverage.program_url ?? {
          mapped: 0,
          unmapped: 0,
          total: 0,
          mapped_pct: 0,
          unmapped_pct: 0,
        },
      }
    : {
        major: selectedCountry.major_mapping,
        subMajor: selectedCountry.sub_major_mapping,
        course: selectedCountry.course_link,
        level: selectedCountry.level_assignment,
        programUrl: selectedCountry.program_url ?? {
          mapped: 0,
          unmapped: 0,
          total: 0,
          mapped_pct: 0,
          unmapped_pct: 0,
        },
      };
  const institutionRows = isAll
    ? coverage.by_institution
    : selectedCountry.by_institution;

  return (
    <div className="space-y-4">
      {countries.length > 0 ? (
        <div
          className="flex flex-wrap gap-1.5"
          role="tablist"
          aria-label="Country"
        >
          <button
            type="button"
            role="tab"
            aria-selected={isAll}
            onClick={() => onSelectTab('all')}
            className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
              isAll
                ? 'bg-accent/15 font-semibold text-accent ring-1 ring-accent/30'
                : 'bg-surface-bg text-text-main hover:bg-accent/5'
            }`}
          >
            <span className="block">All</span>
            <span className="mt-0.5 block text-[11px] font-normal text-text-muted">
              {formatCount(coverage.program_count)} programs
            </span>
            <span className="mt-0.5 block text-[11px] font-normal text-text-muted">
              Major {formatPct(coverage.major_mapping.mapped_pct)} · Sub{' '}
              {formatPct(coverage.sub_major_mapping.mapped_pct)}
            </span>
          </button>
          {countries.map(row => {
            const key = countryTabKey(row);
            const active = selectedTab === key;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onSelectTab(key)}
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  active
                    ? 'bg-accent/15 font-semibold text-accent ring-1 ring-accent/30'
                    : 'bg-surface-bg text-text-main hover:bg-accent/5'
                }`}
              >
                <span className="block">{countryTabLabel(row)}</span>
                <span className="mt-0.5 block text-[11px] font-normal text-text-muted">
                  {formatCount(row.institution_count)} institution
                  {row.institution_count === 1 ? '' : 's'} · {formatCount(row.program_count)}{' '}
                  program{row.program_count === 1 ? '' : 's'}
                </span>
                <span className="mt-0.5 block text-[11px] font-normal text-text-muted">
                  Major {formatPct(row.major_mapping.mapped_pct)} · Sub{' '}
                  {formatPct(row.sub_major_mapping.mapped_pct)}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}

      <div className="flex flex-nowrap gap-3 overflow-x-auto pb-1">
        <CatalogMetric
          label="Institutions"
          value={institutionCount}
          href={INSTITUTIONS_MANAGE_PATH}
        />
        <CatalogMetric label="Campus" value={campusCount} href={INSTITUTIONS_COLLEGES_PATH} />
        <CatalogMetric label="Colleges" value={collegeCount} href={INSTITUTIONS_COLLEGES_PATH} />
        <CatalogMetric label="Programs" value={programCount} href={PROGRAMS_PATH} />
        <CatalogMetric
          label="With major"
          value={pairs.major.mapped}
          href={PROGRAMS_PATH}
          hint={mappingHint(pairs.major)}
        />
        <CatalogMetric
          label="With sub-major"
          value={pairs.subMajor.mapped}
          href={SUB_MAJORS_PATH}
          hint={mappingHint(pairs.subMajor)}
        />
        <CatalogMetric
          label="No major"
          value={noMajorCount}
          href={PROGRAMS_PATH}
          hint={gapHint(pairs.major)}
          emphasizeGap
        />
        <CatalogMetric
          label="No sub-major"
          value={noSubMajorCount}
          href={SUB_MAJORS_PATH}
          hint={gapHint(pairs.subMajor)}
          emphasizeGap
        />
        <CatalogMetric
          label="Distinct majors"
          value={majorCount}
          href={MAJORS_PATH}
          hint="Catalog majors used by these programs"
        />
        <CatalogMetric
          label="Distinct sub-majors"
          value={subMajorCount}
          href={SUB_MAJORS_PATH}
          hint="Catalog sub-majors used by these programs"
        />
        <CatalogMetric label="Levels" value={levelCount} href={LEVELS_PATH} />
        {isAll ? (
          <CatalogMetric label="Courses" value={coverage.course_count} href={COURSES_PATH} />
        ) : null}
      </div>

      <p className="text-xs text-text-muted">
        {isAll
          ? 'All / country rows count distinct programs that have an active offering in that scope (not every programs-table row). “With major / With sub-major” come from program_education_major_mappings for those offered programs — the same table NZ Mapping Review writes.'
          : `Figures below are distinct programs with an active offering at institutions in ${countryTabLabel(selectedCountry)}. Mapping coverage uses live PEM rows for those programs.`}
      </p>

      <CoveragePairTable
        major={pairs.major}
        subMajor={pairs.subMajor}
        course={pairs.course}
        level={pairs.level}
        programUrl={pairs.programUrl}
      />

      {institutionRows.length > 0 || !isAll ? (
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <div className="border-b border-border-subtle bg-surface-bg px-4 py-3">
            <p className="text-sm font-semibold text-text-main">
              {isAll
                ? 'Institutions missing a major, sub-major, course, level, or program URL'
                : `Institutions in ${countryTabLabel(selectedCountry)}`}
            </p>
            <p className="text-xs text-text-muted">
              Percentages use that institution&apos;s distinct programs with an active offering
              (same set as Framework Programs). A cell is red only when that institution has a
              gap in that column — not because another university is incomplete.
              {isAll && coverage.by_institution_truncated
                ? ' Showing the 40 institutions with the most programs missing those fields. Open a country tab for the full list.'
                : null}
            </p>
          </div>
          <InstitutionCoverageTable
            rows={institutionRows}
            showCountry={isAll}
            emptyLabel={
              isAll
                ? 'No institutions are missing a major, sub-major, course, level, or program URL.'
                : 'No institutions with programs in this country.'
            }
          />
        </div>
      ) : null}
    </div>
  );
}

const FrameworkHierarchySummaryPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const location = useLocation();
  const [hierarchy, setHierarchy] = useState<AcademicHierarchySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState('all');
  const [expandedLevels, setExpandedLevels] = useState<Set<number>>(new Set());
  const [expandedPrograms, setExpandedPrograms] = useState<Set<number>>(new Set());
  const [expandedMajors, setExpandedMajors] = useState<Set<number>>(new Set());

  const selectedCountry = useMemo(() => {
    const countries = hierarchy?.coverage?.by_country ?? [];
    return countries.find(row => countryTabKey(row) === selectedTab) ?? null;
  }, [hierarchy, selectedTab]);
  const isAllTab = selectedTab === 'all' || !selectedCountry;
  const visibleLevels = useMemo(() => {
    const levels = hierarchy?.levels ?? [];
    if (isAllTab) return levels;
    return filterLevelsForCountry(levels, new Set(selectedCountry.program_ids ?? []));
  }, [hierarchy, isAllTab, selectedCountry]);

  const loadHierarchy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AcademicHierarchySummary>('academia/hierarchy');
      setHierarchy(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hierarchy');
      setHierarchy(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Remount + pathname: re-fetch when returning from NZ Mapping Review (or other tabs).
  useEffect(() => {
    void loadHierarchy();
  }, [loadHierarchy, location.pathname]);

  const content = (
    <>
      <div className="flex flex-wrap items-center justify-end gap-2 px-6 pt-4">
        <button
          type="button"
          onClick={() => void loadHierarchy()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-bg px-3 py-1.5 text-sm text-text-main hover:border-accent/40 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} />
          Refresh coverage
        </button>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading hierarchy...
        </div>
      ) : error ? (
        <div className="px-6 py-10 text-sm text-alert">{error}</div>
      ) : (
        <div className="space-y-6 px-6 py-5">
          {hierarchy?.coverage ? (
            <CoveragePanel
              coverage={hierarchy.coverage}
              selectedTab={selectedTab}
              onSelectTab={setSelectedTab}
            />
          ) : null}

          {!visibleLevels.length ? (
            <div className="text-sm text-text-muted">
              No levels defined yet.{' '}
              <Link to={LEVELS_PATH} className="font-semibold text-accent hover:underline">
                Create a level
              </Link>{' '}
              to start building the LPMC tree.
            </div>
          ) : (
            <div className="rounded-xl border border-border-subtle">
              <div className="border-b border-border-subtle bg-surface-bg px-4 py-3">
                <p className="text-sm font-semibold text-text-main">Level tree</p>
                <p className="text-xs text-text-muted">
                  {isAllTab
                    ? 'Active programs with an offering, grouped by level (union across countries). Sub-major counts are distinct catalog sub-majors linked to those programs.'
                    : `Programs with an active offering in ${countryTabLabel(selectedCountry)}. Counts are this country only.`}
                </p>
              </div>
              <div className="divide-y divide-border-subtle/70">
                {visibleLevels.map(level => {
                  const levelOpen = expandedLevels.has(level.id);
                  const programCount = level.programs.length;
                  const majorCount =
                    level.major_count ??
                    new Set(level.programs.flatMap(program => program.majors.map(major => major.id)))
                      .size;
                  const subMajorCount = level.sub_major_count ?? 0;
                  const courseCount = level.programs.reduce(
                    (sum, program) =>
                      sum + program.majors.reduce((inner, major) => inner + major.courses.length, 0),
                    0
                  );
                  return (
                    <div key={level.id} className="px-4 py-4">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedLevels(prev => {
                            const next = new Set(prev);
                            next.has(level.id) ? next.delete(level.id) : next.add(level.id);
                            return next;
                          })
                        }
                        className="flex w-full items-center gap-2 text-left"
                      >
                        {levelOpen ? (
                          <ChevronDown size={18} className="text-text-muted" />
                        ) : (
                          <ChevronRight size={18} className="text-text-muted" />
                        )}
                        <span className="text-base font-bold text-text-main">{level.name}</span>
                        <FrameworkHierarchyId value={level.id} />
                        <span className="text-xs text-text-muted">
                          {programCount} program{programCount === 1 ? '' : 's'} · {majorCount} major
                          {majorCount === 1 ? '' : 's'} · {subMajorCount} sub-major
                          {subMajorCount === 1 ? '' : 's'} · {courseCount} course
                          {courseCount === 1 ? '' : 's'}
                        </span>
                      </button>
                      {levelOpen ? (
                        <div className="mt-3 ml-6 space-y-3 border-l border-border-subtle pl-4">
                          {level.programs.length === 0 ? (
                            <p className="text-sm text-text-muted">
                              No programs.{' '}
                              <Link to={PROGRAMS_PATH} className="font-semibold text-accent hover:underline">
                                Add a program
                              </Link>
                            </p>
                          ) : (
                            level.programs.map(program => {
                              const programOpen = expandedPrograms.has(program.id);
                              const programCourseCount = program.majors.reduce(
                                (sum, major) => sum + major.courses.length,
                                0
                              );
                              const programSubMajorCount = program.sub_major_count ?? 0;
                              return (
                                <div key={program.id}>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedPrograms(prev => {
                                        const next = new Set(prev);
                                        next.has(program.id) ? next.delete(program.id) : next.add(program.id);
                                        return next;
                                      })
                                    }
                                    className="flex w-full items-center gap-2 text-left"
                                  >
                                    {programOpen ? (
                                      <ChevronDown size={16} className="text-text-muted" />
                                    ) : (
                                      <ChevronRight size={16} className="text-text-muted" />
                                    )}
                                    <Link
                                      to={PROGRAMS_PATH}
                                      onClick={e => e.stopPropagation()}
                                      className="text-sm font-semibold text-accent hover:underline"
                                    >
                                      {program.name}
                                    </Link>
                                    <FrameworkHierarchyId value={program.id} />
                                    <FrameworkHierarchyId label="Level ID" value={level.id} />
                                    <span className="text-xs text-text-muted">
                                      {program.majors.length} major
                                      {program.majors.length === 1 ? '' : 's'} · {programSubMajorCount}{' '}
                                      sub-major{programSubMajorCount === 1 ? '' : 's'} ·{' '}
                                      {programCourseCount} course{programCourseCount === 1 ? '' : 's'}
                                    </span>
                                  </button>
                                  {programOpen ? (
                                    <div className="mt-2 ml-6 space-y-3 border-l border-border-subtle/70 pl-4">
                                      {program.majors.length === 0 ? (
                                        <p className="text-sm text-text-muted">
                                          No majors.{' '}
                                          <Link
                                            to={MAJORS_PATH}
                                            className="font-semibold text-accent hover:underline"
                                          >
                                            Add a major
                                          </Link>
                                        </p>
                                      ) : (
                                        program.majors.map(major => {
                                          const majorOpen = expandedMajors.has(major.id);
                                          return (
                                            <div key={major.id}>
                                              <button
                                                type="button"
                                                onClick={() =>
                                                  setExpandedMajors(prev => {
                                                    const next = new Set(prev);
                                                    next.has(major.id)
                                                      ? next.delete(major.id)
                                                      : next.add(major.id);
                                                    return next;
                                                  })
                                                }
                                                className="flex w-full items-center gap-2 text-left"
                                              >
                                                {majorOpen ? (
                                                  <ChevronDown size={16} className="text-text-muted" />
                                                ) : (
                                                  <ChevronRight size={16} className="text-text-muted" />
                                                )}
                                                <Link
                                                  to={MAJORS_PATH}
                                                  onClick={e => e.stopPropagation()}
                                                  className="text-sm font-semibold text-text-main hover:text-accent hover:underline"
                                                >
                                                  {major.name}
                                                </Link>
                                                <FrameworkHierarchyId value={major.id} />
                                                <FrameworkHierarchyId label="Program ID" value={program.id} />
                                                <span className="text-xs text-text-muted">
                                                  {major.courses.length} course
                                                  {major.courses.length === 1 ? '' : 's'}
                                                </span>
                                              </button>
                                              {majorOpen ? (
                                                <ul className="mt-2 ml-6 space-y-1 border-l border-border-subtle/70 pl-4">
                                                  {major.courses.length === 0 ? (
                                                    <li className="text-sm text-text-muted">
                                                      No courses yet (optional).{' '}
                                                      <Link
                                                        to={courseFilterPath(level.id, program.id, major.id)}
                                                        className="font-semibold text-accent hover:underline"
                                                      >
                                                        Add a course
                                                      </Link>
                                                    </li>
                                                  ) : (
                                                    major.courses.map(course => (
                                                      <li
                                                        key={course.id}
                                                        className="flex flex-wrap items-center gap-2 text-sm"
                                                      >
                                                        <span className="font-medium text-text-main">
                                                          {level.name} &gt; {program.name} &gt; {major.name}{' '}
                                                          &gt; {course.name}
                                                        </span>
                                                        <FrameworkHierarchyId value={course.id} />
                                                        <FrameworkHierarchyId
                                                          label="Major ID"
                                                          value={major.id}
                                                        />
                                                        <FrameworkHierarchyId
                                                          label="Program ID"
                                                          value={program.id}
                                                        />
                                                        {course.code ? (
                                                          <span className="rounded bg-surface-bg px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-text-muted">
                                                            {course.code}
                                                          </span>
                                                        ) : null}
                                                      </li>
                                                    ))
                                                  )}
                                                </ul>
                                              ) : null}
                                            </div>
                                          );
                                        })
                                      )}
                                    </div>
                                  ) : null}
                                </div>
                              );
                            })
                          )}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
      {!embedded ? (
        <p className="mt-4 px-6 pb-6 text-xs text-text-muted">
          Country coverage counts programs with an active institution offering, then intersects{' '}
          <span className="font-medium text-text-main">program_education_major_mappings</span> for
          major / sub-major coverage (same source NZ Mapping Review writes).
        </p>
      ) : null}
    </>
  );

  if (embedded) return content;

  return (
    <div className="space-y-6">
      <AcademiaBreadcrumbs
        items={[
          { label: 'Academia Hub', path: '/academia' },
          { label: 'Academic Framework', path: FRAMEWORK_SECTION_PATH },
          { label: 'Summary View' },
        ]}
      />
      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="border-b border-border-subtle px-6 py-4">
          <h2 className="text-xl font-bold text-text-main">Academic Hierarchy Summary</h2>
          <p className="mt-1 text-sm text-text-muted">
            Catalog totals and how many offered programs have a major, sub-major, course, level, and
            program URL. Country tabs show PEM mapping % — use Refresh after NZ Mapping Review.
          </p>
        </div>
        {content}
      </div>
    </div>
  );
};

export default FrameworkHierarchySummaryPage;
