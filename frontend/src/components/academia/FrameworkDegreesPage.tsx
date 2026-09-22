import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import {
  applyFilterParamUpdates,
  appendMultiParam,
  readMultiParam,
  type FilterParamValue,
} from '../../utils/filterParams';
import {
  PEM_MAPPINGS_CHANGED_EVENT,
  readPemMappingsChangedAt,
} from '../../utils/pemMappingEvents';
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
/** Gap filters hit live program_education_major_mappings (same table Mapping Review writes). */
const PEM_GAP_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'both', label: 'Unmapped (no PEM)' },
  { value: 'sub_major', label: 'Major only (no sub)' },
] as const;
type PemGap = (typeof PEM_GAP_OPTIONS)[number]['value'];

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
  const location = useLocation();
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
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [flash, setFlash] = useState<{ tone: 'success' | 'error'; text: string } | null>(
    null
  );
  const loadSeqRef = useRef(0);
  const pemBumpRef = useRef<string | null>(readPemMappingsChangedAt());
  const flashTimerRef = useRef<number | null>(null);

  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1);
  const rawPageSize = Number.parseInt(searchParams.get('page_size') || '50', 10);
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawPageSize)
    ? (rawPageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : 50;
  const searchQuery = searchParams.get('q') || '';
  const [searchDraft, setSearchDraft] = useState(searchQuery);
  const filterLevelId = searchParams.get('level_id') || '';
  const filterMajorIds = readMultiParam(searchParams, 'major_id');
  const filterSubMajorIds = readMultiParam(searchParams, 'sub_major_id');
  const filterCountryIds = readMultiParam(searchParams, 'country_id');
  const filterInstitutionIds = readMultiParam(searchParams, 'institution_id');
  const rawPemGap = searchParams.get('pem_gap') || '';
  // Legacy `major` was identical to `both` (no PEM row ⇒ no major). Normalize.
  const normalizedPemGap = rawPemGap === 'major' ? 'both' : rawPemGap;
  const filterPemGap: PemGap = PEM_GAP_OPTIONS.some(option => option.value === normalizedPemGap)
    ? (normalizedPemGap as PemGap)
    : '';
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
    const seq = ++loadSeqRef.current;
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
      if (filterPemGap) params.set('pem_gap', filterPemGap);
      params.set('page', String(activePage));
      params.set('page_size', String(pageSize));
      params.set('sort_by', sortBy);
      params.set('sort_dir', sortDir);

      const data = await apiFetch<DegreeListResponse>(`academia/degrees?${params.toString()}`);
      if (seq !== loadSeqRef.current) return;
      const items = Array.isArray(data.items) ? data.items : [];
      const nextTotalPages = data.total_pages || 0;
      setDegrees(items);
      setTotal(data.total || 0);
      setTotalPages(nextTotalPages);
      if (items.length === 0 && nextTotalPages > 0 && activePage > nextTotalPages) {
        updateFilterParams({ page: String(nextTotalPages) }, { resetPage: false });
      }
    } catch (err) {
      if (seq !== loadSeqRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load programs');
      setDegrees([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      if (seq === loadSeqRef.current) setLoading(false);
    }
  }, [
    countryFilterKey,
    filterLevelId,
    filterPemGap,
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

  // Remount / tab return / PEM apply bump: always hit live degrees API (no React Query cache).
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadDegrees(page);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadDegrees, page, location.pathname, location.key]);

  useEffect(() => {
    const refetchIfPemBumped = () => {
      const at = readPemMappingsChangedAt();
      if (!at || at === pemBumpRef.current) return;
      pemBumpRef.current = at;
      void loadDegrees(page);
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') refetchIfPemBumped();
    };
    window.addEventListener(PEM_MAPPINGS_CHANGED_EVENT, refetchIfPemBumped);
    window.addEventListener('focus', refetchIfPemBumped);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener(PEM_MAPPINGS_CHANGED_EVENT, refetchIfPemBumped);
      window.removeEventListener('focus', refetchIfPemBumped);
      document.removeEventListener('visibilitychange', onVisible);
    };
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

  const pageDegreeIds = useMemo(() => degrees.map(degree => degree.id), [degrees]);
  const selectedCount = selectedIds.size;
  const allPageSelected =
    pageDegreeIds.length > 0 && pageDegreeIds.every(id => selectedIds.has(id));
  const somePageSelected =
    pageDegreeIds.some(id => selectedIds.has(id)) && !allPageSelected;

  useEffect(() => {
    setSelectedIds(new Set());
  }, [
    searchQuery,
    filterLevelId,
    majorFilterKey,
    subMajorFilterKey,
    countryFilterKey,
    institutionFilterKey,
    filterPemGap,
    pageSize,
  ]);

  useEffect(() => {
    return () => {
      if (flashTimerRef.current != null) window.clearTimeout(flashTimerRef.current);
    };
  }, []);

  const showFlash = (tone: 'success' | 'error', text: string) => {
    if (flashTimerRef.current != null) window.clearTimeout(flashTimerRef.current);
    setFlash({ tone, text });
    flashTimerRef.current = window.setTimeout(() => setFlash(null), 6000);
  };

  const toggleOne = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllPage = () => {
    if (allPageSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        for (const id of pageDegreeIds) next.delete(id);
        return next;
      });
      return;
    }
    setSelectedIds(prev => {
      const next = new Set(prev);
      for (const id of pageDegreeIds) next.add(id);
      return next;
    });
  };

  const institutionIdForDelete =
    filterInstitutionIds.length === 1 ? Number(filterInstitutionIds[0]) : null;

  const handleDeleteOne = async (degree: DegreeRecord) => {
    if (
      !(await openConfirm({
        title: 'Delete program?',
        message: `Delete program "${degree.name}"?`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }
    setDeleting(true);
    try {
      const params = new URLSearchParams();
      if (institutionIdForDelete) {
        params.set('institution_id', String(institutionIdForDelete));
      }
      const query = params.toString();
      await apiFetch(`academia/degrees/${degree.id}${query ? `?${query}` : ''}`, {
        method: 'DELETE',
      });
      setSelectedIds(prev => {
        if (!prev.has(degree.id)) return prev;
        const next = new Set(prev);
        next.delete(degree.id);
        return next;
      });
      showFlash('success', `Deleted “${degree.name}”.`);
      void loadDegrees(page);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete program';
      setError(message);
      showFlash('error', message);
      await openConfirm({
        title: 'Could not delete program',
        message,
        confirmLabel: 'OK',
        variant: 'warning',
        mode: 'alert',
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleBulkDelete = async () => {
    if (!selectedCount || deleting) return;
    if (
      !(await openConfirm({
        title: 'Delete selected programs?',
        message: `Delete ${selectedCount} selected program${
          selectedCount === 1 ? '' : 's'
        }? This permanently removes them and cannot be undone.`,
        confirmLabel: 'Delete selected',
        variant: 'danger',
      }))
    ) {
      return;
    }
    const ids = Array.from(selectedIds);
    setDeleting(true);
    try {
      const result = await apiFetch<{ deleted: number; skipped: number; ids: number[] }>(
        'academia/degrees/bulk-delete',
        {
          method: 'POST',
          body: JSON.stringify({
            ids,
            ...(institutionIdForDelete
              ? { institution_id: institutionIdForDelete }
              : {}),
          }),
        }
      );
      setSelectedIds(new Set());
      showFlash(
        'success',
        `Deleted ${result.deleted} program${result.deleted === 1 ? '' : 's'}${
          result.skipped ? ` (${result.skipped} skipped)` : ''
        }.`
      );
      void loadDegrees(page);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Bulk delete failed';
      setError(message);
      showFlash('error', message);
    } finally {
      setDeleting(false);
    }
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

  const bulkDeleteButton = (
    <button
      type="button"
      disabled={!selectedCount || deleting}
      onClick={() => void handleBulkDelete()}
      className="inline-flex h-[38px] shrink-0 items-center gap-2 rounded-xl border border-alert/40 bg-alert/10 px-4 text-sm font-semibold text-alert disabled:opacity-50"
    >
      {deleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
      {deleting
        ? 'Deleting…'
        : `Delete selected${selectedCount ? ` (${selectedCount})` : ''}`}
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
          <label className={`block ${FILTER_FIELD_CLASS} space-y-1 text-sm`}>
            <span className="font-medium text-text-main">PEM mapping</span>
            <select
              value={filterPemGap}
              onChange={e =>
                updateFilterParams({ pem_gap: e.target.value || null })
              }
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              {PEM_GAP_OPTIONS.map(option => (
                <option key={option.value || 'all'} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadDegrees(page)}
            disabled={loading}
            className="inline-flex h-[38px] shrink-0 items-center gap-2 self-end rounded-xl border border-border-subtle px-3 text-sm font-medium text-text-main hover:bg-surface-bg disabled:opacity-50"
            title="Reload programs and PEM gap counts from the live database"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} />
            Refresh
          </button>
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
          {bulkDeleteButton}
          {createProgramButton}
        </div>

        {flash ? (
          <div
            role="status"
            className={`mx-6 mt-4 rounded-xl border px-4 py-3 text-sm ${
              flash.tone === 'success'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-text-main'
                : 'border-alert/30 bg-alert/5 text-alert'
            }`}
          >
            {flash.text}
          </div>
        ) : null}

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
                    <th className="w-10 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        ref={el => {
                          if (el) el.indeterminate = somePageSelected;
                        }}
                        onChange={toggleAllPage}
                        disabled={deleting || pageDegreeIds.length === 0}
                        className="h-4 w-4 rounded border-border-subtle"
                        aria-label="Select all programs on this page"
                      />
                    </th>
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
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(degree.id)}
                          onChange={() => toggleOne(degree.id)}
                          disabled={deleting}
                          className="h-4 w-4 rounded border-border-subtle"
                          aria-label={`Select ${degree.name}`}
                        />
                      </td>
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
                            disabled={deleting}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10 disabled:opacity-50"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteOne(degree)}
                            disabled={deleting}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10 disabled:opacity-50"
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
