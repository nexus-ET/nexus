import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  History,
  Loader2,
  Pencil,
  Plus,
  Power,
  PowerOff,
  Settings2,
  Trash2,
  X,
} from 'lucide-react';
import type { InstitutionTypeRecord } from '../../types/institutionTypes';
import {
  fetchInstitutionTypes,
  institutionTypeSelectOptions,
  resolveLegacyInstitutionTypeId,
} from '../../types/institutionTypes';
import {
  INSTITUTIONS_NEW_PATH,
  institutionEditPath,
  institutionHistoryPath,
} from '../../config/academiaHubNav';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import type { DegreeRecord } from '../../types/academicFramework';
import type { EducationMajorRecord } from '../../types/educationMajor';
import type { EducationSubMajorRecord } from '../../types/educationSubMajor';
import type { GlobalAcademicTemplate } from '../../types/academicCalendar';
import {
  DEFAULT_INSTITUTION_SUMMARY_SORT,
  INSTITUTION_SUMMARY_COLUMN_DEFS,
  INSTITUTION_SUMMARY_COLUMNS_STORAGE_KEY,
  INSTITUTION_SUMMARY_COLUMNS_VERSION,
  type InstitutionSummaryColumnKey,
  type InstitutionSummaryListResponse,
  type InstitutionSummaryRecord,
  type InstitutionSummarySortBy,
  type InstitutionSummarySortOrder,
} from '../../types/institutionSummary';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import InstitutionsTableSkeleton from './InstitutionsTableSkeleton';
import SearchableSelect from './SearchableSelect';
import InstitutionFilterSelect from './InstitutionFilterSelect';
import { useConfirmation } from '../../context/ConfirmationContext';
import {
  applyFilterParamUpdates,
  appendMultiParam,
  readMultiParam,
  type FilterParamValue,
} from '../../utils/filterParams';
import type { CampusRecord } from '../../types/institutions';
import { campusDescriptionPreview } from '../../utils/campusDescription';

interface GeographyOption {
  id: number;
  name: string;
}

async function fetchGeographyOptions(
  endpoint: 'academia/states' | 'academia/cities',
  scopeKey: 'country_id' | 'state_id',
  scopeIds: string[],
  extraParams?: Record<string, string | undefined>
): Promise<GeographyOption[]> {
  if (scopeIds.length === 0) return [];

  const fetchForScope = (scopeId: string) =>
    fetchAcademiaListItems<GeographyOption>(endpoint, {
      ...extraParams,
      [scopeKey]: scopeId,
    });

  if (scopeIds.length === 1) {
    return fetchForScope(scopeIds[0]);
  }

  const batches = await Promise.all(scopeIds.map(fetchForScope));
  const byId = new Map<number, GeographyOption>();
  for (const batch of batches) {
    for (const item of batch) {
      byId.set(item.id, item);
    }
  }
  return Array.from(byId.values()).sort((left, right) => left.name.localeCompare(right.name));
}

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

const SORTABLE_COLUMNS: InstitutionSummarySortBy[] = [
  'id',
  'name',
  'city',
  'state',
  'country',
  'institution_type',
  'level_count',
  'program_count',
  'major_count',
  'sub_major_count',
  'course_count',
  'campus_count',
  'college_count',
  'intake_count',
  'status',
];

const isSortableColumn = (
  key: InstitutionSummaryColumnKey
): key is InstitutionSummarySortBy => SORTABLE_COLUMNS.includes(key as InstitutionSummarySortBy);

/** Prefer snake_case API fields; fall back to camelCase if a proxy renames them. */
function summaryCount(
  row: InstitutionSummaryRecord,
  key:
    | 'level_count'
    | 'program_count'
    | 'major_count'
    | 'sub_major_count'
    | 'course_count'
    | 'campus_count'
    | 'college_count'
    | 'intake_count'
    | 'picture_count'
): number {
  const direct = row[key];
  if (typeof direct === 'number' && Number.isFinite(direct)) return direct;
  const camel = key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
  const fallback = (row as Record<string, unknown>)[camel];
  return typeof fallback === 'number' && Number.isFinite(fallback) ? fallback : 0;
}

const COUNT_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
  'level_count',
  'program_count',
  'major_count',
  'sub_major_count',
  'course_count',
  'campus_count',
  'college_count',
  'intake_count',
  'picture_count',
]);

/** UI wizard steps (1–5). Campuses share step 1 after Institution+Campuses merge. */
const INSTITUTION_COLUMN_STEP: Partial<Record<InstitutionSummaryColumnKey, number>> = {
  name: 1,
  campus_count: 1,
  college_count: 2,
  level_count: 3,
  program_count: 3,
  major_count: 3,
  sub_major_count: 3,
  course_count: 3,
  intake_count: 4,
  picture_count: 5,
};

const CENTER_TEXT_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
  'city',
  'state',
  'country',
  'institution_type',
]);

const ID_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>(['id', 'institution_type_id']);

const CENTER_ALIGNED_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
  ...ID_COLUMN_KEYS,
  ...CENTER_TEXT_COLUMN_KEYS,
  ...COUNT_COLUMN_KEYS,
  'status',
  'published',
]);

const STACKED_HEADER_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
  ...COUNT_COLUMN_KEYS,
  'status',
  'published',
]);

const COLUMN_WIDTHS: Partial<Record<InstitutionSummaryColumnKey, string>> = {
  id: '4.5%',
  name: '13%',
  city: '7%',
  state: '7%',
  country: '7%',
  institution_type: '9%',
  institution_type_id: '6%',
  level_count: '5.5%',
  program_count: '6.5%',
  major_count: '6%',
  sub_major_count: '6%',
  course_count: '6%',
  campus_count: '7%',
  college_count: '7%',
  intake_count: '6%',
  picture_count: '6.5%',
  status: '6%',
  published: '7%',
};

const ACTIONS_COLUMN_WIDTH = '11%';

const columnHeaderClass = (key: InstitutionSummaryColumnKey): string => {
  if (CENTER_ALIGNED_COLUMN_KEYS.has(key)) {
    return 'px-2 py-2 text-center text-xs font-semibold align-top';
  }
  if (key === 'name') {
    return 'px-2 py-2 font-semibold align-top';
  }
  return 'px-2 py-2 text-xs font-semibold align-top';
};

const columnCellClass = (key: InstitutionSummaryColumnKey): string => {
  if (ID_COLUMN_KEYS.has(key)) {
    return 'px-1.5 py-3 text-center text-sm tabular-nums align-top text-text-muted';
  }
  if (COUNT_COLUMN_KEYS.has(key)) {
    return 'px-1.5 py-3 text-center text-sm font-bold tabular-nums align-top text-text-main';
  }
  if (CENTER_TEXT_COLUMN_KEYS.has(key)) {
    return 'px-2 py-3 text-center text-sm align-top whitespace-normal break-words text-text-main';
  }
  if (key === 'status' || key === 'published') {
    return 'px-1.5 py-3 text-center align-top text-text-main';
  }
  if (key === 'name') {
    return 'px-2 py-3 align-top whitespace-normal break-words text-text-main';
  }
  return 'px-2 py-3 text-sm align-top whitespace-nowrap text-text-main';
};

const getColumnWidth = (key: InstitutionSummaryColumnKey): string | undefined =>
  COLUMN_WIDTHS[key];

const defaultVisibleColumns = (): InstitutionSummaryColumnKey[] =>
  INSTITUTION_SUMMARY_COLUMN_DEFS.filter(column => column.defaultVisible).map(column => column.key);

const LOCKED_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>(['id', 'name']);

const normalizeVisibleColumns = (
  columns: Set<InstitutionSummaryColumnKey>
): Set<InstitutionSummaryColumnKey> => {
  columns.delete('created_at');
  columns.add('id');
  columns.add('name');
  return columns;
};

const readVisibleColumns = (): Set<InstitutionSummaryColumnKey> => {
  const defaults = defaultVisibleColumns();

  try {
    const raw = localStorage.getItem(INSTITUTION_SUMMARY_COLUMNS_STORAGE_KEY);
    if (!raw) {
      return normalizeVisibleColumns(new Set(defaults));
    }

    const parsed = JSON.parse(raw) as
      | InstitutionSummaryColumnKey[]
      | { version?: number; columns?: InstitutionSummaryColumnKey[] };

    if (Array.isArray(parsed)) {
      const saved = new Set(
        parsed.filter(key => INSTITUTION_SUMMARY_COLUMN_DEFS.some(column => column.key === key))
      );
      defaults.forEach(key => saved.add(key));
      return normalizeVisibleColumns(saved);
    }

    const saved = new Set(
      (parsed.columns || []).filter(key =>
        INSTITUTION_SUMMARY_COLUMN_DEFS.some(column => column.key === key)
      )
    );
    if ((parsed.version ?? 1) < INSTITUTION_SUMMARY_COLUMNS_VERSION) {
      defaults.forEach(key => saved.add(key));
    }
    if (saved.size === 0) {
      return normalizeVisibleColumns(new Set(defaults));
    }
    return normalizeVisibleColumns(saved);
  } catch {
    return normalizeVisibleColumns(new Set(defaults));
  }
};

const formatDateTime = (value?: string | null): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
};

interface InstitutionsManagePageProps {
  embedded?: boolean;
}

const InstitutionsManagePage: React.FC<InstitutionsManagePageProps> = () => {
  const openConfirm = useConfirmation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<InstitutionSummaryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [inactiveCount, setInactiveCount] = useState(0);
  const [searchDraft, setSearchDraft] = useState(searchParams.get('q') || '');
  const [countries, setCountries] = useState<GeographyOption[]>([]);
  const [states, setStates] = useState<GeographyOption[]>([]);
  const [cities, setCities] = useState<GeographyOption[]>([]);
  const [programs, setPrograms] = useState<DegreeRecord[]>([]);
  const [majors, setMajors] = useState<EducationMajorRecord[]>([]);
  const [subMajors, setSubMajors] = useState<EducationSubMajorRecord[]>([]);
  const [intakeTemplates, setIntakeTemplates] = useState<GlobalAcademicTemplate[]>([]);
  const [institutionTypes, setInstitutionTypes] = useState<InstitutionTypeRecord[]>([]);
  const filterCatalogsLoadedRef = useRef(false);
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;
  const [visibleColumns, setVisibleColumns] = useState<Set<InstitutionSummaryColumnKey>>(
    readVisibleColumns
  );
  const [columnMenuOpen, setColumnMenuOpen] = useState(false);
  const [togglingStatusId, setTogglingStatusId] = useState<number | null>(null);
  const [expandedCampusesInstitutionId, setExpandedCampusesInstitutionId] = useState<
    number | null
  >(null);
  const [campusesByInstitution, setCampusesByInstitution] = useState<
    Record<number, CampusRecord[]>
  >({});
  const [campusesLoadingId, setCampusesLoadingId] = useState<number | null>(null);
  const [campusesError, setCampusesError] = useState<string | null>(null);
  const columnMenuRef = useRef<HTMLDivElement | null>(null);

  const institutionTypeOptions = useMemo(
    () => institutionTypeSelectOptions(institutionTypes),
    [institutionTypes]
  );

  const page = Math.max(Number(searchParams.get('page') || '1'), 1);
  const rawPageSize = Number(searchParams.get('page_size') || '25');
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawPageSize)
    ? (rawPageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : 25;
  const sortBy = (searchParams.get('sort_by') as InstitutionSummarySortBy) || DEFAULT_INSTITUTION_SUMMARY_SORT.sortBy;
  const sortOrder =
    (searchParams.get('sort_order') as InstitutionSummarySortOrder) ||
    DEFAULT_INSTITUTION_SUMMARY_SORT.sortOrder;
  const countryIds = readMultiParam(searchParams, 'country_id');
  const stateIds = readMultiParam(searchParams, 'state_id');
  const cityIds = readMultiParam(searchParams, 'city_id');
  const statusFilter = searchParams.get('status') || '';
  const institutionTypeIds = readMultiParam(searchParams, 'institution_type_id');
  const programIds = readMultiParam(searchParams, 'program_id');
  const majorIds = readMultiParam(searchParams, 'major_id');
  const subMajorIds = readMultiParam(searchParams, 'sub_major_id');
  const templateIds = readMultiParam(searchParams, 'template_id');
  const countryId = countryIds[0] || '';
  const stateId = stateIds[0] || '';
  const cityId = cityIds[0] || '';
  const institutionTypeId = institutionTypeIds[0] || '';
  const programId = programIds[0] || '';
  const majorId = majorIds[0] || '';
  const subMajorId = subMajorIds[0] || '';
  const templateId = templateIds[0] || '';
  const query = searchParams.get('q') || '';

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

  const hasActiveFilters = Boolean(
    query ||
      countryIds.length ||
      stateIds.length ||
      cityIds.length ||
      statusFilter ||
      institutionTypeIds.length ||
      programIds.length ||
      majorIds.length ||
      subMajorIds.length ||
      templateIds.length
  );

  const clearAllFilters = () => {
    setSearchDraft('');
    setSearchParams(
      {
        sort_by: DEFAULT_INSTITUTION_SUMMARY_SORT.sortBy,
        sort_order: DEFAULT_INSTITUTION_SUMMARY_SORT.sortOrder,
        page: '1',
        page_size: String(pageSize),
      },
      { replace: true }
    );
  };

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (searchDraft === query) return;
      updateFilterParams({ q: searchDraft || null });
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [query, searchDraft, updateFilterParams]);

  useEffect(() => {
    setSearchDraft(query);
  }, [query]);

  const loadFilterCatalogs = useCallback(() => {
    if (filterCatalogsLoadedRef.current) return;
    filterCatalogsLoadedRef.current = true;
    void Promise.all([
      fetchAcademiaListItems<DegreeRecord>('academia/degrees', {
        sort_by: 'name',
        sort_dir: 'asc',
      })
        .then(setPrograms)
        .catch(() => setPrograms([])),
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        sort_by: 'name',
        sort_dir: 'asc',
      })
        .then(setMajors)
        .catch(() => setMajors([])),
      fetchAcademiaListItems<EducationSubMajorRecord>('academia/education-sub-majors', {
        sort_by: 'name',
        sort_dir: 'asc',
      })
        .then(setSubMajors)
        .catch(() => setSubMajors([])),
      apiFetch<GlobalAcademicTemplate[]>('academia/academic-templates')
        .then(nextTemplates => setIntakeTemplates(Array.isArray(nextTemplates) ? nextTemplates : []))
        .catch(() => setIntakeTemplates([])),
    ]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetchInstitutionTypes()
      .then(types => {
        if (!cancelled) setInstitutionTypes(types);
      })
      .catch(() => {
        if (!cancelled) setInstitutionTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const legacyType = searchParams.get('institution_type');
    if (!legacyType || institutionTypeIds.length || institutionTypes.length === 0) {
      return;
    }
    const mappedId = resolveLegacyInstitutionTypeId(legacyType, institutionTypes);
    updateFilterParams({
      institution_type_id: mappedId ? [mappedId] : null,
      institution_type: null,
    });
  }, [institutionTypeIds.length, institutionTypes, searchParams, updateFilterParams]);

  useEffect(() => {
    if (programIds.length || majorIds.length || subMajorIds.length || templateIds.length) {
      loadFilterCatalogs();
    }
  }, [loadFilterCatalogs, majorIds.length, programIds.length, subMajorIds.length, templateIds.length]);

  useEffect(() => {
    void fetchAcademiaListItems<GeographyOption>('academia/countries', {
      with_institutions: 'true',
      sort_by: 'name',
      sort_dir: 'asc',
    })
      .then(setCountries)
      .catch(() => setCountries([]));
  }, []);

  useEffect(() => {
    if (countryIds.length === 0) {
      setStates([]);
      return;
    }
    void fetchGeographyOptions('academia/states', 'country_id', countryIds)
      .then(setStates)
      .catch(() => setStates([]));
  }, [countryIds.join('|')]);

  useEffect(() => {
    if (countryIds.length === 0) {
      setCities([]);
      return;
    }
    const load = async () => {
      try {
        if (stateIds.length > 0) {
          setCities(
            await fetchGeographyOptions('academia/cities', 'state_id', stateIds, {
              country_id: countryIds.length === 1 ? countryIds[0] : undefined,
            })
          );
          return;
        }
        setCities(await fetchGeographyOptions('academia/cities', 'country_id', countryIds));
      } catch {
        setCities([]);
      }
    };
    void load();
  }, [countryIds.join('|'), stateIds.join('|')]);

  const summaryQueryKey = useMemo(
    () =>
      [
        query,
        countryIds.join('|'),
        stateIds.join('|'),
        cityIds.join('|'),
        statusFilter,
        institutionTypeIds.join('|'),
        programIds.join('|'),
        majorIds.join('|'),
        subMajorIds.join('|'),
        templateIds.join('|'),
        page,
        pageSize,
        sortBy,
        sortOrder,
      ].join('\0'),
    [
      cityIds.join('|'),
      countryIds.join('|'),
      institutionTypeIds.join('|'),
      majorIds.join('|'),
      page,
      pageSize,
      programIds.join('|'),
      query,
      sortBy,
      sortOrder,
      stateIds.join('|'),
      statusFilter,
      subMajorIds.join('|'),
      templateIds.join('|'),
    ]
  );

  const loadSummary = useCallback(
    async (signal?: AbortSignal) => {
      const paramsSnapshot = searchParamsRef.current;
      const q = paramsSnapshot.get('q') || '';
      const nextCountryIds = readMultiParam(paramsSnapshot, 'country_id');
      const nextStateIds = readMultiParam(paramsSnapshot, 'state_id');
      const nextCityIds = readMultiParam(paramsSnapshot, 'city_id');
      const nextStatusFilter = paramsSnapshot.get('status') || '';
      const nextInstitutionTypeIds = readMultiParam(paramsSnapshot, 'institution_type_id');
      const nextProgramIds = readMultiParam(paramsSnapshot, 'program_id');
      const nextMajorIds = readMultiParam(paramsSnapshot, 'major_id');
      const nextSubMajorIds = readMultiParam(paramsSnapshot, 'sub_major_id');
      const nextTemplateIds = readMultiParam(paramsSnapshot, 'template_id');
      const nextPage = Math.max(Number(paramsSnapshot.get('page') || '1'), 1);
      const rawNextPageSize = Number(paramsSnapshot.get('page_size') || '25');
      const nextPageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawNextPageSize)
        ? (rawNextPageSize as (typeof PAGE_SIZE_OPTIONS)[number])
        : 25;
      const nextSortBy =
        (paramsSnapshot.get('sort_by') as InstitutionSummarySortBy) ||
        DEFAULT_INSTITUTION_SUMMARY_SORT.sortBy;
      const nextSortOrder =
        (paramsSnapshot.get('sort_order') as InstitutionSummarySortOrder) ||
        DEFAULT_INSTITUTION_SUMMARY_SORT.sortOrder;

      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (q.trim()) params.set('q', q.trim());
        appendMultiParam(params, 'country_id', nextCountryIds);
        appendMultiParam(params, 'state_id', nextStateIds);
        appendMultiParam(params, 'city_id', nextCityIds);
        if (nextStatusFilter === 'active') params.set('is_active', 'true');
        if (nextStatusFilter === 'inactive') params.set('is_active', 'false');
        appendMultiParam(params, 'institution_type_id', nextInstitutionTypeIds);
        appendMultiParam(params, 'program_id', nextProgramIds);
        appendMultiParam(params, 'major_id', nextMajorIds);
        appendMultiParam(params, 'sub_major_id', nextSubMajorIds);
        appendMultiParam(params, 'template_id', nextTemplateIds);
        params.set('page', String(nextPage));
        params.set('page_size', String(nextPageSize));
        params.set('sort_by', nextSortBy);
        params.set('sort_order', nextSortOrder);

        const data = await apiFetch<InstitutionSummaryListResponse>(
          `academia/institutions/summary?${params.toString()}`,
          { signal }
        );
        if (signal?.aborted) return;
        setItems(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
        setActiveCount(data.active_count ?? 0);
        setInactiveCount(data.inactive_count ?? 0);
      } catch (err) {
        if (signal?.aborted) return;
        setError(err instanceof Error ? err.message : 'Failed to load institutions');
        setItems([]);
        setTotal(0);
        setTotalPages(0);
        setActiveCount(0);
        setInactiveCount(0);
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [summaryQueryKey]
  );

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      void loadSummary(controller.signal);
    }, 150);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [loadSummary]);

  useEffect(() => {
    localStorage.setItem(
      INSTITUTION_SUMMARY_COLUMNS_STORAGE_KEY,
      JSON.stringify({
        version: INSTITUTION_SUMMARY_COLUMNS_VERSION,
        columns: Array.from(visibleColumns),
      })
    );
  }, [visibleColumns]);

  useEffect(() => {
    if (!columnMenuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!columnMenuRef.current?.contains(event.target as Node)) {
        setColumnMenuOpen(false);
      }
    };
    window.addEventListener('mousedown', handleClick);
    return () => window.removeEventListener('mousedown', handleClick);
  }, [columnMenuOpen]);

  const toggleSort = (column: InstitutionSummarySortBy) => {
    if (sortBy === column) {
      updateFilterParams(
        { sort_order: sortOrder === 'asc' ? 'desc' : 'asc', page: String(page) },
        { resetPage: false }
      );
      return;
    }
    updateFilterParams({ sort_by: column, sort_order: 'asc', page: String(page) }, { resetPage: false });
  };

  const toggleColumn = (key: InstitutionSummaryColumnKey) => {
    setVisibleColumns(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (LOCKED_COLUMN_KEYS.has(key)) return prev;
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const toggleCampusesPanel = useCallback(
    async (institutionId: number) => {
      if (expandedCampusesInstitutionId === institutionId) {
        setExpandedCampusesInstitutionId(null);
        setCampusesError(null);
        return;
      }
      setExpandedCampusesInstitutionId(institutionId);
      setCampusesError(null);
      if (campusesByInstitution[institutionId]) return;

      setCampusesLoadingId(institutionId);
      try {
        const data = await apiFetch<CampusRecord[]>(
          `academia/campuses?institution_id=${institutionId}`
        );
        setCampusesByInstitution(current => ({
          ...current,
          [institutionId]: Array.isArray(data) ? data : [],
        }));
      } catch (err) {
        setCampusesError(
          err instanceof Error ? err.message : 'Failed to load campuses for this institution.'
        );
      } finally {
        setCampusesLoadingId(null);
      }
    },
    [campusesByInstitution, expandedCampusesInstitutionId]
  );

  const handleDeleteInstitution = async (name: string, id: number) => {
    if (!(await openConfirm({
      title: 'Delete institution?',
      message: `Delete institution "${name}" and all campuses/colleges?`,
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) return;
    try {
      await apiFetch(`academia/institutions/${id}`, { method: 'DELETE' });
      void loadSummary();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete institution');
    }
  };

  const handleToggleInstitutionStatus = async (row: InstitutionSummaryRecord) => {
    const nextActive = !row.is_active;
    if (!(await openConfirm({
      title: nextActive ? 'Activate institution?' : 'Deactivate institution?',
      message: nextActive
        ? `Set "${row.name}" to Active?`
        : `Set "${row.name}" to Inactive? Inactive institutions are hidden from active filters and outbound flows that require an active institution.`,
      confirmLabel: nextActive ? 'Activate' : 'Deactivate',
      variant: nextActive ? 'warning' : 'danger',
    }))) {
      return;
    }

    setTogglingStatusId(row.id);
    try {
      await apiFetch(`academia/institutions/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: nextActive }),
      });
      setItems(previous =>
        previous.map(item =>
          item.id === row.id ? { ...item, is_active: nextActive } : item
        )
      );
      setActiveCount(count => Math.max(0, count + (nextActive ? 1 : -1)));
      setInactiveCount(count => Math.max(0, count + (nextActive ? -1 : 1)));
      // Drop the row when the current status filter no longer matches.
      if (
        (statusFilter === 'active' && !nextActive) ||
        (statusFilter === 'inactive' && nextActive)
      ) {
        void loadSummary();
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update institution status');
    } finally {
      setTogglingStatusId(null);
    }
  };

  const visibleSubMajors = useMemo(() => {
    if (majorIds.length === 0) return subMajors;
    const allowed = new Set(majorIds);
    return subMajors.filter(item => allowed.has(String(item.major_id)));
  }, [majorIds, subMajors]);

  useEffect(() => {
    if (subMajorIds.length === 0 || majorIds.length === 0 || subMajors.length === 0) return;
    const allowed = new Set(majorIds);
    const nextSubMajorIds = subMajorIds.filter(id => {
      const selected = subMajors.find(item => String(item.id) === id);
      return selected ? allowed.has(String(selected.major_id)) : false;
    });
    if (nextSubMajorIds.length !== subMajorIds.length) {
      updateFilterParams({ sub_major_id: nextSubMajorIds.length ? nextSubMajorIds : null });
    }
  }, [majorIds, subMajorIds, subMajors, updateFilterParams]);

  const visibleColumnDefs = useMemo(
    () =>
      INSTITUTION_SUMMARY_COLUMN_DEFS.filter(
        column => column.key !== 'created_at' && visibleColumns.has(column.key)
      ),
    [visibleColumns]
  );

  const renderCell = (row: InstitutionSummaryRecord, key: InstitutionSummaryColumnKey) => {
    const wizardStep = INSTITUTION_COLUMN_STEP[key];
    if (wizardStep) {
      const value =
        key === 'name'
          ? row.name
          : key === 'level_count'
            ? summaryCount(row, 'level_count')
            : key === 'program_count'
              ? summaryCount(row, 'program_count')
              : key === 'major_count'
                ? summaryCount(row, 'major_count')
                : key === 'sub_major_count'
                  ? summaryCount(row, 'sub_major_count')
                  : key === 'course_count'
                    ? summaryCount(row, 'course_count')
                  : key === 'campus_count'
                    ? summaryCount(row, 'campus_count')
                    : key === 'college_count'
                      ? summaryCount(row, 'college_count')
                      : key === 'intake_count'
                        ? summaryCount(row, 'intake_count')
                        : summaryCount(row, 'picture_count');
      const isUnavailable = key !== 'name' && value === 0;
      if (key === 'campus_count' && value > 0) {
        const isExpanded = expandedCampusesInstitutionId === row.id;
        return (
          <button
            type="button"
            onClick={() => void toggleCampusesPanel(row.id)}
            className={`inline-block min-w-6 text-center font-bold hover:underline ${
              isExpanded ? 'text-text-main' : 'text-accent'
            }`}
            title={isExpanded ? 'Hide campus list' : 'Show campus descriptions'}
            aria-expanded={isExpanded}
            aria-label={`${row.name}: ${value} campuses. ${isExpanded ? 'Hide' : 'Show'} campus list`}
          >
            {value}
          </button>
        );
      }
      return (
        <Link
          to={`${institutionEditPath(row.id)}?step=${wizardStep}`}
          className={`inline-block font-bold hover:underline ${
            isUnavailable ? 'text-alert' : 'text-accent'
          } ${
            key === 'name' ? 'text-left' : 'min-w-6 text-center'
          }`}
          title={isUnavailable ? 'Information is not available' : undefined}
          aria-label={
            isUnavailable
              ? `${row.name}: information is not available. Open step ${wizardStep}`
              : `Edit ${row.name}, step ${wizardStep}`
          }
        >
          {value}
        </Link>
      );
    }

    switch (key) {
      case 'id':
        return row.id;
      case 'code':
        return row.code || '—';
      case 'city':
        return <span className="block text-center">{row.city_name || '—'}</span>;
      case 'state':
        return <span className="block text-center">{row.state_name || '—'}</span>;
      case 'country':
        return <span className="block text-center">{row.country_name || '—'}</span>;
      case 'institution_type':
        return (
          <span className="block text-center whitespace-normal break-words">
            {row.institution_type_name || '—'}
          </span>
        );
      case 'institution_type_id':
        return row.institution_type_id ?? '—';
      case 'status':
        return (
          <div className="flex justify-center">
            <EntityStatusBadge isActive={row.is_active} />
          </div>
        );
      case 'published': {
        const status =
          row.publish_status === 'failure' && !row.last_publish_attempt_at
            ? 'pending'
            : row.publish_status || 'pending';
        const label =
          status === 'success' ? 'Success' : status === 'failure' ? 'Failure' : 'Pending';
        const badgeClass =
          status === 'success'
            ? 'bg-emerald-100 text-emerald-800'
            : status === 'failure'
              ? 'bg-red-100 text-red-800'
              : 'bg-amber-100 text-amber-900';
        const title =
          status === 'pending'
            ? 'Publish has not been attempted yet'
            : row.last_publish_attempt_at
              ? `Last publish attempt: ${formatDateTime(row.last_publish_attempt_at)}`
              : status === 'success'
                ? 'Published successfully'
                : 'Last publish attempt failed';
        return (
          <div className="flex justify-center">
            <span
              className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${badgeClass}`}
              title={title}
            >
              {label}
            </span>
          </div>
        );
      }
      case 'created_at':
        return formatDateTime(row.created_at);
      default:
        return '—';
    }
  };

  const filterFieldClass = 'min-w-[6rem] flex-1 basis-[6rem]';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="shrink-0 text-[22px] font-bold leading-none text-text-main">
            Manage Institutions
          </h2>
          <input
            type="search"
            value={searchDraft}
            onChange={event => setSearchDraft(event.target.value)}
            placeholder="Search institution names..."
            className="w-64 max-w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent sm:w-80"
            aria-label="Search institution names"
          />
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          <div className="relative" ref={columnMenuRef}>
            <button
              type="button"
              onClick={() => setColumnMenuOpen(open => !open)}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-semibold text-text-main hover:border-accent/40"
              aria-expanded={columnMenuOpen}
              aria-haspopup="true"
            >
              <Settings2 size={16} />
              Columns
            </button>
            {columnMenuOpen ? (
              <div className="absolute right-0 z-20 mt-2 w-56 rounded-xl border border-border-subtle bg-card p-3 shadow-lg">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                  Visible columns
                </p>
                <div className="space-y-2">
                  {INSTITUTION_SUMMARY_COLUMN_DEFS.filter(column => column.key !== 'created_at').map(
                    column => (
                    <label key={column.key} className="flex items-center gap-2 text-sm text-text-main">
                      <input
                        type="checkbox"
                        checked={visibleColumns.has(column.key)}
                        disabled={LOCKED_COLUMN_KEYS.has(column.key)}
                        onChange={() => toggleColumn(column.key)}
                      />
                      {column.label}
                    </label>
                    )
                  )}
                </div>
              </div>
            ) : null}
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-text-muted/10 px-3 py-1 text-sm font-semibold text-text-muted">
            {inactiveCount} Inactive
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 text-sm font-semibold text-success">
            {activeCount} Active
          </span>
          <button
            type="button"
            onClick={() => navigate(INSTITUTIONS_NEW_PATH)}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Add Institution
          </button>
        </div>
      </div>

      <div className="space-y-4 rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="flex flex-wrap items-end gap-1.5 px-6 pt-4">
          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Country"
              singleValue={countryId}
              multiValues={countryIds}
              options={countries.map(country => ({
                value: String(country.id),
                label: country.name,
              }))}
              allLabel="All countries"
              onSingleChange={value =>
                updateFilterParams({
                  country_id: value || null,
                  state_id: null,
                  city_id: null,
                })
              }
              onMultiChange={values =>
                updateFilterParams({
                  country_id: values.length ? values : null,
                  state_id: null,
                  city_id: null,
                })
              }
              placeholder="All countries"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="State"
              singleValue={stateId}
              multiValues={stateIds}
              disabled={countryIds.length === 0}
              options={states.map(state => ({
                value: String(state.id),
                label: state.name,
              }))}
              allLabel={countryIds.length ? 'All states' : 'Select country first'}
              onSingleChange={value =>
                updateFilterParams({
                  state_id: value || null,
                  city_id: null,
                })
              }
              onMultiChange={values =>
                updateFilterParams({
                  state_id: values.length ? values : null,
                  city_id: null,
                })
              }
              placeholder={countryIds.length ? 'All states' : 'Select country first'}
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="City"
              singleValue={cityId}
              multiValues={cityIds}
              disabled={countryIds.length === 0}
              options={cities.map(city => ({
                value: String(city.id),
                label: city.name,
              }))}
              allLabel={
                stateIds.length || countryIds.length ? 'All cities' : 'Select country first'
              }
              onSingleChange={value => updateFilterParams({ city_id: value || null })}
              onMultiChange={values =>
                updateFilterParams({ city_id: values.length ? values : null })
              }
              placeholder={
                stateIds.length || countryIds.length ? 'All cities' : 'Select country first'
              }
            />
          </div>

          <div className={filterFieldClass}>
            <SearchableSelect
              label="Status"
              value={statusFilter}
              options={[
                { value: '', label: 'All statuses' },
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
              ]}
              onChange={value => updateFilterParams({ status: value || null })}
              placeholder="All statuses"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Institution Type"
              singleValue={institutionTypeId}
              multiValues={institutionTypeIds}
              options={institutionTypeOptions}
              allLabel="All institution types"
              onSingleChange={value =>
                updateFilterParams({ institution_type_id: value || null })
              }
              onMultiChange={values =>
                updateFilterParams({
                  institution_type_id: values.length ? values : null,
                })
              }
              placeholder="All institution types"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Program"
              singleValue={programId}
              multiValues={programIds}
              onOpen={loadFilterCatalogs}
              options={programs.map(program => ({
                value: program.id,
                label: program.name,
              }))}
              allLabel="All programs"
              onSingleChange={value => updateFilterParams({ program_id: value || null })}
              onMultiChange={values =>
                updateFilterParams({ program_id: values.length ? values : null })
              }
              placeholder="All programs"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Major"
              singleValue={majorId}
              multiValues={majorIds}
              onOpen={loadFilterCatalogs}
              options={majors.map(major => ({
                value: String(major.id),
                label: major.label,
                color: major.color,
              }))}
              allLabel="All majors"
              onSingleChange={value => {
                const next: Record<string, FilterParamValue> = { major_id: value || null };
                if (value && subMajorIds.length) {
                  const allowed = new Set([value]);
                  const nextSubMajorIds = subMajorIds.filter(id => {
                    const selected = subMajors.find(item => String(item.id) === id);
                    return selected ? allowed.has(String(selected.major_id)) : false;
                  });
                  if (nextSubMajorIds.length !== subMajorIds.length) {
                    next.sub_major_id = nextSubMajorIds.length ? nextSubMajorIds : null;
                  }
                }
                updateFilterParams(next);
              }}
              onMultiChange={values => {
                const next: Record<string, FilterParamValue> = {
                  major_id: values.length ? values : null,
                };
                if (values.length && subMajorIds.length) {
                  const allowed = new Set(values);
                  const nextSubMajorIds = subMajorIds.filter(id => {
                    const selected = subMajors.find(item => String(item.id) === id);
                    return selected ? allowed.has(String(selected.major_id)) : false;
                  });
                  if (nextSubMajorIds.length !== subMajorIds.length) {
                    next.sub_major_id = nextSubMajorIds.length ? nextSubMajorIds : null;
                  }
                }
                updateFilterParams(next);
              }}
              placeholder="All majors"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Sub-Majors"
              singleValue={subMajorId}
              multiValues={subMajorIds}
              onOpen={loadFilterCatalogs}
              options={visibleSubMajors.map(item => ({
                value: String(item.id),
                label:
                  majorIds.length === 1 || !item.major_label
                    ? item.name
                    : `${item.name} (${item.major_label})`,
                color: item.major_color,
              }))}
              allLabel="All sub-majors"
              onSingleChange={value => updateFilterParams({ sub_major_id: value || null })}
              onMultiChange={values =>
                updateFilterParams({ sub_major_id: values.length ? values : null })
              }
              placeholder="All sub-majors"
            />
          </div>

          <div className={filterFieldClass}>
            <InstitutionFilterSelect
              label="Intakes"
              singleValue={templateId}
              multiValues={templateIds}
              onOpen={loadFilterCatalogs}
              options={intakeTemplates.map(template => ({
                value: String(template.id),
                label: template.name,
              }))}
              allLabel="All intakes"
              onSingleChange={value => updateFilterParams({ template_id: value || null })}
              onMultiChange={values =>
                updateFilterParams({ template_id: values.length ? values : null })
              }
              placeholder="All intakes"
            />
          </div>
        </div>

        {loading && items.length === 0 ? (
          <InstitutionsTableSkeleton />
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : items.length === 0 ? (
          <div className="space-y-3 px-6 py-10 text-sm text-text-muted">
            <p>
              {hasActiveFilters
                ? 'No institutions found matching these criteria.'
                : 'No institutions found.'}
            </p>
            {hasActiveFilters ? (
              <button
                type="button"
                onClick={clearAllFilters}
                className="inline-flex items-center gap-1 font-semibold text-accent hover:underline"
              >
                <X size={14} />
                Clear All Filters
              </button>
            ) : (
              <button
                type="button"
                onClick={() => navigate(INSTITUTIONS_NEW_PATH)}
                className="font-semibold text-accent hover:underline"
              >
                Add your first institution
              </button>
            )}
          </div>
        ) : (
          <div className="relative overflow-x-hidden">
            {loading ? (
              <div className="absolute inset-x-0 top-0 z-10 h-1 overflow-hidden bg-surface-bg">
                <div className="h-full w-1/3 animate-pulse bg-accent" />
              </div>
            ) : null}
            <table className="w-full table-fixed text-left text-sm [&_td]:align-top [&_th]:align-top">
              <colgroup>
                {visibleColumnDefs.map(column => (
                  <col key={column.key} style={{ width: getColumnWidth(column.key) }} />
                ))}
                <col style={{ width: ACTIONS_COLUMN_WIDTH }} />
              </colgroup>
              <thead className="border-b border-border-subtle bg-surface-bg/60 text-text-muted">
                <tr>
                  {visibleColumnDefs.map(column =>
                    isSortableColumn(column.key) ? (
                      <FrameworkSortableHeader
                        key={column.key}
                        label={column.label}
                        column={column.key}
                        sortBy={sortBy}
                        sortDir={sortOrder}
                        onSort={toggleSort}
                        className={columnHeaderClass(column.key)}
                        align={CENTER_ALIGNED_COLUMN_KEYS.has(column.key) ? 'center' : 'left'}
                        layout={STACKED_HEADER_COLUMN_KEYS.has(column.key) ? 'stacked' : 'inline'}
                      />
                    ) : (
                      <th key={column.key} className={columnHeaderClass(column.key)}>
                        {column.label}
                      </th>
                    )
                  )}
                  <th className="px-1.5 py-2 text-center text-xs font-semibold align-top">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/70">
                {items.map(row => {
                  const campusesExpanded = expandedCampusesInstitutionId === row.id;
                  const campusesForRow = campusesByInstitution[row.id] ?? [];
                  return (
                    <Fragment key={row.id}>
                      <tr className="hover:bg-surface-bg/40">
                        {visibleColumnDefs.map(column => (
                          <td key={column.key} className={columnCellClass(column.key)}>
                            {renderCell(row, column.key)}
                          </td>
                        ))}
                        <td className="px-1.5 py-3 text-center align-top">
                          <div className="flex flex-wrap items-start justify-center gap-1">
                            <button
                              type="button"
                              onClick={() => navigate(institutionEditPath(row.id))}
                              title="Edit"
                              aria-label={`Edit ${row.name}`}
                              className="inline-flex self-start rounded-lg p-1.5 text-text-muted hover:bg-surface-bg"
                            >
                              <Pencil size={14} />
                            </button>
                            <button
                              type="button"
                              disabled={togglingStatusId === row.id}
                              onClick={() => void handleToggleInstitutionStatus(row)}
                              title={row.is_active ? 'Set Inactive' : 'Set Active'}
                              aria-label={
                                row.is_active
                                  ? `Set ${row.name} inactive`
                                  : `Set ${row.name} active`
                              }
                              className={`inline-flex self-start rounded-lg p-1.5 hover:bg-surface-bg disabled:opacity-50 ${
                                row.is_active
                                  ? 'text-alert hover:bg-alert/10'
                                  : 'text-success hover:bg-success/10'
                              }`}
                            >
                              {togglingStatusId === row.id ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : row.is_active ? (
                                <PowerOff size={14} />
                              ) : (
                                <Power size={14} />
                              )}
                            </button>
                            <Link
                              to={{ pathname: institutionHistoryPath(row.id), search: searchParams.toString() }}
                              title="History"
                              aria-label={`History for ${row.name}`}
                              className="inline-flex self-start rounded-lg p-1.5 text-text-muted hover:bg-surface-bg"
                            >
                              <History size={14} />
                            </Link>
                            <button
                              type="button"
                              onClick={() => void handleDeleteInstitution(row.name, row.id)}
                              title="Delete"
                              aria-label={`Delete ${row.name}`}
                              className="inline-flex self-start rounded-lg p-1.5 text-alert hover:bg-alert/10"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {campusesExpanded ? (
                        <tr className="bg-surface-bg/50">
                          <td
                            colSpan={visibleColumnDefs.length + 1}
                            className="px-4 py-3"
                          >
                            {campusesLoadingId === row.id ? (
                              <div className="flex items-center gap-2 text-sm text-text-muted">
                                <Loader2 size={14} className="animate-spin" />
                                Loading campuses...
                              </div>
                            ) : campusesError ? (
                              <p className="text-sm text-alert">{campusesError}</p>
                            ) : campusesForRow.length === 0 ? (
                              <p className="text-sm text-text-muted">No campuses found.</p>
                            ) : (
                              <div className="overflow-x-auto rounded-xl border border-border-subtle bg-card">
                                <table className="min-w-full text-sm">
                                  <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                                    <tr>
                                      <th className="px-3 py-2 font-semibold">ID</th>
                                      <th className="px-3 py-2 font-semibold">Campus</th>
                                      <th className="px-3 py-2 font-semibold">Location</th>
                                      <th className="px-3 py-2 font-semibold">Description</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {campusesForRow.map(campus => {
                                      const descriptionCell = campusDescriptionPreview(
                                        campus.description
                                      );
                                      return (
                                        <tr key={campus.id} className="border-t border-border-subtle/70">
                                          <td className="px-3 py-2 tabular-nums text-text-muted">
                                            {campus.id}
                                          </td>
                                          <td className="px-3 py-2 font-semibold text-text-main">
                                            {campus.name}
                                          </td>
                                          <td className="px-3 py-2 text-text-muted">
                                            {campus.location_label || '—'}
                                          </td>
                                          <td className="max-w-xl px-3 py-2 text-text-muted">
                                            <span
                                              className="block truncate"
                                              title={descriptionCell.title}
                                            >
                                              {descriptionCell.preview}
                                            </span>
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                                <div className="border-t border-border-subtle px-3 py-2">
                                  <Link
                                    to={`${institutionEditPath(row.id)}?step=1`}
                                    className="text-xs font-semibold text-accent hover:underline"
                                  >
                                    Edit campuses in institution wizard
                                  </Link>
                                </div>
                              </div>
                            )}
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

        {!error && total > 0 ? (
          <FrameworkTablePagination
            page={page}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={nextPage => updateFilterParams({ page: String(nextPage) }, { resetPage: false })}
            onPageSizeChange={nextSize => updateFilterParams({ page_size: String(nextSize) })}
          />
        ) : null}
      </div>
    </div>
  );
};

export default InstitutionsManagePage;
