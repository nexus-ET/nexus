import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import {
  applyFilterParamUpdates,
  appendMultiParam,
  readMultiParam,
  type FilterParamValue,
} from '../../utils/filterParams';
import { useAcademiaLevels } from '../../hooks/useLevels';
import { levelSelectOptions } from '../../constants/levels';
import {
  PROGRAMS_PATH,
  type DegreeListResponse,
  type DegreeRecord,
} from '../../types/academicFramework';
import type { CountryRecord } from '../../types/country';
import type { EducationMajorRecord } from '../../types/educationMajor';
import type { EducationSubMajorRecord } from '../../types/educationSubMajor';
import type { InstitutionRecord } from '../../types/institutions';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import DegreeFormModal from './DegreeFormModal';
import EntityStatusBadge from './EntityStatusBadge';
import { FrameworkIdCell, FrameworkIdHeader } from './FrameworkIdDisplay';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination, {
  FRAMEWORK_PAGE_SIZE_OPTIONS,
} from './FrameworkTablePagination';
import InstitutionFilterSelect from './InstitutionFilterSelect';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'level' | 'name' | 'code';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = FRAMEWORK_PAGE_SIZE_OPTIONS;
const FILTER_FIELD_CLASS = 'min-w-[200px]';
const SORT_BY_OPTIONS: SortBy[] = ['level', 'name', 'code'];

function sameIdList(left: string[], right: string[]): boolean {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  return left.every((id, index) => id === right[index]);
}

function programUrlHref(url: string): string {
  const trimmed = url.trim();
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function asNameList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map(item => {
        if (typeof item === 'string') return item.trim();
        if (item && typeof item === 'object') {
          const record = item as { label?: unknown; name?: unknown };
          const label = record.label ?? record.name;
          return typeof label === 'string' ? label.trim() : '';
        }
        return '';
      })
      .filter(Boolean);
  }
  if (typeof value === 'string' && value.trim()) {
    return value
      .split(',')
      .map(part => part.trim())
      .filter(Boolean);
  }
  return [];
}

function resolveMappedNames(
  names: unknown,
  ids: unknown,
  catalog: Array<{ id: number; label?: string | null; name?: string | null }>
): string[] {
  const fromNames = asNameList(names);
  if (fromNames.length) return fromNames;
  const idList = Array.isArray(ids)
    ? ids.map(Number).filter(id => Number.isInteger(id) && id > 0)
    : [];
  if (!idList.length || !catalog.length) return [];
  const byId = new Map(catalog.map(item => [item.id, (item.label || item.name || '').trim()]));
  return [...new Set(idList.map(id => byId.get(id) || '').filter(Boolean))];
}

function formatInstitutionNames(names?: string[] | null): string {
  if (!names || names.length === 0) return '';
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]}, ${names[1]}`;
  return `${names[0]} +${names.length - 1}`;
}

function NameChips({ names }: { names?: string[] | null }) {
  if (!names || names.length === 0) {
    return <span className="text-text-muted">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {names.map((name, index) => (
        <span
          key={`${name}-${index}`}
          className="inline-flex items-center rounded-full border border-border-subtle/70 bg-surface-bg/60 px-2 py-0.5 text-[11px] text-text-main"
        >
          {name}
        </span>
      ))}
    </div>
  );
}

const FrameworkDegreesPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const { levels } = useAcademiaLevels();
  const [searchParams, setSearchParams] = useSearchParams();
  const [degrees, setDegrees] = useState<DegreeRecord[]>([]);
  const [catalogMajors, setCatalogMajors] = useState<EducationMajorRecord[]>([]);
  const [catalogSubMajors, setCatalogSubMajors] = useState<EducationSubMajorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countries, setCountries] = useState<CountryRecord[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingDegree, setEditingDegree] = useState<DegreeRecord | null>(null);

  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1);
  const rawPageSize = Number.parseInt(searchParams.get('page_size') || '20', 10);
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawPageSize)
    ? (rawPageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : 20;
  const searchQuery = searchParams.get('q') || '';
  const [searchDraft, setSearchDraft] = useState(searchQuery);
  const filterLevelId = searchParams.get('level_id') || '';
  const filterMajorIds = readMultiParam(searchParams, 'major_id');
  const filterSubMajorIds = readMultiParam(searchParams, 'sub_major_id');
  const filterCountryIds = readMultiParam(searchParams, 'country_id');
  const filterInstitutionIds = readMultiParam(searchParams, 'institution_id');
  const rawSortBy = searchParams.get('sort_by') as SortBy | null;
  const sortBy: SortBy = rawSortBy && SORT_BY_OPTIONS.includes(rawSortBy) ? rawSortBy : 'name';
  const rawSortDir = searchParams.get('sort_dir');
  const sortDir: SortDir = rawSortDir === 'desc' ? 'desc' : 'asc';

  const filterInstitutionIdsRef = useRef(filterInstitutionIds);
  filterInstitutionIdsRef.current = filterInstitutionIds;

  const updateFilterParams = useCallback(
    (updates: Record<string, FilterParamValue>, options?: { resetPage?: boolean }) => {
      setSearchParams(
        prev => {
          const next = new URLSearchParams(prev);
          applyFilterParamUpdates(next, updates);
          if (options?.resetPage !== false && !('page' in updates)) {
            next.set('page', '1');
          }
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  useEffect(() => {
    void fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
      catalog_only: 'true',
      sort_by: 'name',
      sort_dir: 'asc',
    })
      .then(setCatalogMajors)
      .catch(() => setCatalogMajors([]));
    void fetchAcademiaListItems<EducationSubMajorRecord>('academia/education-sub-majors', {
      sort_by: 'name',
      sort_dir: 'asc',
    })
      .then(setCatalogSubMajors)
      .catch(() => setCatalogSubMajors([]));
    void fetchAcademiaListItems<CountryRecord>('academia/countries', {
      with_institutions: 'true',
      sort_by: 'name',
      sort_dir: 'asc',
    })
      .then(setCountries)
      .catch(() => setCountries([]));
  }, []);

  const countryFilterKey = filterCountryIds.join(',');
  const institutionFilterKey = filterInstitutionIds.join(',');
  const majorFilterKey = filterMajorIds.join(',');
  const subMajorFilterKey = filterSubMajorIds.join(',');

  useEffect(() => {
    const extra: Record<string, string | string[] | undefined> = {
      sort_by: 'name',
      sort_order: 'asc',
    };
    if (countryFilterKey) extra.country_id = countryFilterKey.split(',').filter(Boolean);
    void fetchAcademiaListItems<InstitutionRecord>('academia/institutions/summary', extra)
      .then(rows => {
        setInstitutions(rows);
        const allowed = new Set(rows.map(row => String(row.id)));
        const current = filterInstitutionIdsRef.current;
        const next = current.filter(id => allowed.has(id));
        if (!sameIdList(current, next)) {
          updateFilterParams({ institution_id: next }, { resetPage: false });
        }
      })
      .catch(() => setInstitutions([]));
  }, [countryFilterKey, updateFilterParams]);

  const visibleSubMajors = useMemo(() => {
    if (!filterMajorIds.length) return catalogSubMajors;
    const allowed = new Set(filterMajorIds);
    return catalogSubMajors.filter(item => allowed.has(String(item.major_id)));
  }, [catalogSubMajors, filterMajorIds]);

  const applyMajorFilter = (values: string[]) => {
    const updates: Record<string, FilterParamValue> = { major_id: values };
    if (values.length && filterSubMajorIds.length) {
      const allowed = new Set(values);
      const nextSubs = filterSubMajorIds.filter(id => {
        const selected = catalogSubMajors.find(item => String(item.id) === id);
        return selected ? allowed.has(String(selected.major_id)) : false;
      });
      if (!sameIdList(filterSubMajorIds, nextSubs)) {
        updates.sub_major_id = nextSubs;
      }
    }
    updateFilterParams(updates);
  };

  const loadDegrees = useCallback(async (activePage: number) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.set('q', searchQuery.trim());
      if (filterLevelId) params.set('level_id', filterLevelId);
      appendMultiParam(params, 'major_id', majorFilterKey ? majorFilterKey.split(',') : []);
      appendMultiParam(params, 'sub_major_id', subMajorFilterKey ? subMajorFilterKey.split(',') : []);
      appendMultiParam(params, 'country_id', countryFilterKey ? countryFilterKey.split(',') : []);
      appendMultiParam(params, 'institution_id', institutionFilterKey ? institutionFilterKey.split(',') : []);
      params.set('page', String(activePage));
      params.set('page_size', String(pageSize));
      params.set('sort_by', sortBy);
      params.set('sort_dir', sortDir);

      const data = await apiFetch<DegreeListResponse>(`academia/degrees?${params.toString()}`);
      const items = Array.isArray(data.items) ? data.items : [];
      const nextTotalPages = data.total_pages || 0;
      setDegrees(items);
      setTotal(data.total || 0);
      setTotalPages(nextTotalPages);
      if (items.length === 0 && nextTotalPages > 0 && activePage > nextTotalPages) {
        updateFilterParams({ page: String(nextTotalPages) }, { resetPage: false });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load programs');
      setDegrees([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [
    countryFilterKey,
    filterLevelId,
    institutionFilterKey,
    majorFilterKey,
    pageSize,
    searchQuery,
    sortBy,
    sortDir,
    subMajorFilterKey,
    updateFilterParams,
  ]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (searchDraft === searchQuery) return;
      updateFilterParams({ q: searchDraft.trim() || null });
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [searchDraft, searchQuery, updateFilterParams]);

  useEffect(() => {
    setSearchDraft(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadDegrees(page);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadDegrees, page]);

  const toggleSort = (column: SortBy) => {
    if (sortBy === column) {
      updateFilterParams(
        { sort_dir: sortDir === 'asc' ? 'desc' : 'asc' },
        { resetPage: false }
      );
      return;
    }
    updateFilterParams({ sort_by: column, sort_dir: 'asc' }, { resetPage: false });
  };

  const handleSaved = () => {
    void loadDegrees(page);
  };

  const createProgramButton = (
    <button
      type="button"
      onClick={() => {
        setEditingDegree(null);
        setModalOpen(true);
      }}
      className="inline-flex h-[38px] shrink-0 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-semibold text-text-dark-bg"
    >
      <Plus size={16} />
      Create Program
    </button>
  );

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: PROGRAMS_PATH },
            { label: 'Programs' },
          ]}
        />
      )}

      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        {embedded ? null : (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
            <div>
              <h2 className="text-xl font-bold text-text-main">Programs</h2>
              <p className="text-sm text-text-muted">
                Qualification programs under each level (LPMC step 2). Majors and courses are added separately.
              </p>
            </div>
          </div>
        )}

        {!loading && !error && degrees.length > 0 ? (
          <FrameworkTablePagination
            variant="top"
            page={page}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={nextPage =>
              updateFilterParams({ page: String(nextPage) }, { resetPage: false })
            }
            onPageSizeChange={size =>
              updateFilterParams({
                page_size: String(size as (typeof PAGE_SIZE_OPTIONS)[number]),
              })
            }
          />
        ) : null}

        <div className="flex flex-wrap items-end gap-4 border-b border-border-subtle px-6 py-4">
          <div className={`${FILTER_FIELD_CLASS} shrink-0`}>
            <InstitutionFilterSelect
              label="Country"
              singleValue={filterCountryIds[0] || ''}
              multiValues={filterCountryIds}
              options={countries.map(country => ({
                value: String(country.id),
                label: country.name,
              }))}
              allLabel="All countries"
              onSingleChange={value => updateFilterParams({ country_id: value ? [value] : [] })}
              onMultiChange={values => updateFilterParams({ country_id: values })}
              placeholder="All countries"
            />
          </div>
          <div className={`${FILTER_FIELD_CLASS} shrink-0`}>
            <InstitutionFilterSelect
              label="Institution"
              singleValue={filterInstitutionIds[0] || ''}
              multiValues={filterInstitutionIds}
              options={institutions.map(institution => ({
                value: String(institution.id),
                label: institution.name,
              }))}
              allLabel="All institutions"
              onSingleChange={value => updateFilterParams({ institution_id: value ? [value] : [] })}
              onMultiChange={values => updateFilterParams({ institution_id: values })}
              placeholder="All institutions"
              emptyMessage={
                filterCountryIds.length
                  ? 'No institutions for selected countries'
                  : 'No institutions found'
              }
            />
          </div>
          <label className={`block ${FILTER_FIELD_CLASS} space-y-1 text-sm`}>
            <span className="font-medium text-text-main">Level</span>
            <select
              value={filterLevelId}
              onChange={e => updateFilterParams({ level_id: e.target.value || null })}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              <option value="">All levels</option>
              {levelSelectOptions(levels).map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <div className={`${FILTER_FIELD_CLASS} shrink-0`}>
            <InstitutionFilterSelect
              label="Majors"
              singleValue={filterMajorIds[0] || ''}
              multiValues={filterMajorIds}
              options={catalogMajors.map(major => ({
                value: String(major.id),
                label: major.label,
                color: major.color,
              }))}
              allLabel="All majors"
              onSingleChange={value => applyMajorFilter(value ? [value] : [])}
              onMultiChange={applyMajorFilter}
              placeholder="All majors"
            />
          </div>
          <div className={`${FILTER_FIELD_CLASS} shrink-0`}>
            <InstitutionFilterSelect
              label="Sub-majors"
              singleValue={filterSubMajorIds[0] || ''}
              multiValues={filterSubMajorIds}
              options={visibleSubMajors.map(item => ({
                value: String(item.id),
                label:
                  filterMajorIds.length === 1 || !item.major_label
                    ? item.name
                    : `${item.name} (${item.major_label})`,
                color: item.major_color,
              }))}
              allLabel="All sub-majors"
              onSingleChange={value => updateFilterParams({ sub_major_id: value ? [value] : [] })}
              onMultiChange={values => updateFilterParams({ sub_major_id: values })}
              placeholder="All sub-majors"
            />
          </div>
          <label className="block min-w-[240px] flex-1 space-y-1 text-sm">
            <span className="font-medium text-text-main">Search</span>
            <div className="relative">
              <input
                type="text"
                value={searchDraft}
                onChange={e => setSearchDraft(e.target.value)}
                placeholder="Search programs..."
                className="w-full rounded-xl border border-border-subtle bg-surface-bg py-2 pl-3 pr-9 text-sm outline-none focus:border-accent"
              />
              {searchDraft ? (
                <button
                  type="button"
                  onClick={() => setSearchDraft('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-black/5 hover:text-text-main"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
          </label>
          {createProgramButton}
        </div>

        {error && degrees.length > 0 ? (
          <div className="px-6 pt-4 text-sm text-alert">{error}</div>
        ) : null}

        {loading && degrees.length === 0 ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading...
          </div>
        ) : error && degrees.length === 0 ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : degrees.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No programs found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkIdHeader />
                    <FrameworkIdHeader label="Level ID" />
                    <FrameworkSortableHeader
                      label="Level"
                      column="level"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="min-w-[10rem] px-6 py-3 font-semibold">Institution</th>
                    <FrameworkSortableHeader
                      label="Program"
                      column="name"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="min-w-[10rem] px-6 py-3 font-semibold">Majors</th>
                    <th className="min-w-[10rem] px-6 py-3 font-semibold">Sub-majors</th>
                    <th className="min-w-[9rem] whitespace-nowrap px-6 py-3 font-semibold">
                      Program URL
                    </th>
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {degrees.map(degree => (
                    <tr key={degree.id} className="border-t border-border-subtle/70">
                      <FrameworkIdCell value={degree.id} />
                      <FrameworkIdCell value={degree.level_id} />
                      <td className="px-6 py-3 text-text-muted">{degree.level_name || '—'}</td>
                      <td className="min-w-[10rem] px-6 py-3 text-text-muted">
                        {formatInstitutionNames(degree.institution_names) || '—'}
                      </td>
                      <td className="px-6 py-3 font-semibold text-text-main">{degree.name}</td>
                      <td className="min-w-[10rem] px-6 py-3">
                        <NameChips
                          names={resolveMappedNames(
                            degree.major_names,
                            degree.major_ids,
                            catalogMajors
                          )}
                        />
                      </td>
                      <td className="min-w-[10rem] px-6 py-3">
                        <NameChips
                          names={resolveMappedNames(
                            degree.sub_major_names,
                            degree.sub_major_ids,
                            catalogSubMajors
                          )}
                        />
                      </td>
                      <td className="min-w-[9rem] whitespace-nowrap px-6 py-3">
                        {degree.program_url?.trim() ? (
                          <a
                            href={programUrlHref(degree.program_url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="whitespace-nowrap font-medium text-accent hover:underline"
                          >
                            View Program
                          </a>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={degree.is_active} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingDegree(degree);
                              setModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              if (!(await openConfirm({
                                title: 'Delete program?',
                                message: `Delete program "${degree.name}"?`,
                                confirmLabel: 'Delete',
                                variant: 'danger',
                              }))) return;
                              try {
                                const params = new URLSearchParams();
                                if (filterInstitutionIds.length === 1) {
                                  params.set('institution_id', filterInstitutionIds[0]);
                                }
                                const query = params.toString();
                                await apiFetch(
                                  `academia/degrees/${degree.id}${query ? `?${query}` : ''}`,
                                  { method: 'DELETE' }
                                );
                                void loadDegrees(page);
                              } catch (err) {
                                const message =
                                  err instanceof Error ? err.message : 'Failed to delete program';
                                setError(message);
                                await openConfirm({
                                  title: 'Could not delete program',
                                  message,
                                  confirmLabel: 'OK',
                                  variant: 'warning',
                                  mode: 'alert',
                                });
                              }
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                          >
                            <Trash2 size={14} />
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <FrameworkTablePagination
              page={page}
              pageSize={pageSize}
              total={total}
              totalPages={totalPages}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              onPageChange={nextPage => updateFilterParams({ page: String(nextPage) }, { resetPage: false })}
              onPageSizeChange={size =>
                updateFilterParams({ page_size: String(size as (typeof PAGE_SIZE_OPTIONS)[number]) })
              }
            />
          </>
        )}
      </div>

      <DegreeFormModal
        open={modalOpen}
        degree={editingDegree}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
      />
    </div>
  );
};

export default FrameworkDegreesPage;
