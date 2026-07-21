import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { INSTITUTION_TYPE_OPTIONS } from '../../schemas/wizard/step1-institution';
import {
  INSTITUTIONS_NEW_PATH,
  institutionEditPath,
  institutionHistoryPath,
} from '../../config/academiaHubNav';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import type { DegreeRecord } from '../../types/academicFramework';
import type { EducationMajorRecord } from '../../types/educationMajor';
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
import { useConfirmation } from '../../context/ConfirmationContext';

interface GeographyOption {
  id: number;
  name: string;
}

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

const SORTABLE_COLUMNS: InstitutionSummarySortBy[] = [
  'name',
  'city',
  'state',
  'country',
  'institution_type',
  'program_count',
  'major_count',
  'course_count',
  'campus_count',
  'college_count',
  'intake_count',
  'status',
];

const isSortableColumn = (
  key: InstitutionSummaryColumnKey
): key is InstitutionSummarySortBy => SORTABLE_COLUMNS.includes(key as InstitutionSummarySortBy);

const COUNT_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
  'level_count',
  'program_count',
  'major_count',
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

const CENTER_ALIGNED_COLUMN_KEYS = new Set<InstitutionSummaryColumnKey>([
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
  name: '14%',
  city: '7%',
  state: '7%',
  country: '7%',
  institution_type: '9%',
  level_count: '5.5%',
  program_count: '6.5%',
  major_count: '6%',
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

const normalizeVisibleColumns = (
  columns: Set<InstitutionSummaryColumnKey>
): Set<InstitutionSummaryColumnKey> => {
  columns.delete('created_at');
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
  const [intakeTemplates, setIntakeTemplates] = useState<GlobalAcademicTemplate[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<Set<InstitutionSummaryColumnKey>>(
    readVisibleColumns
  );
  const [columnMenuOpen, setColumnMenuOpen] = useState(false);
  const [togglingStatusId, setTogglingStatusId] = useState<number | null>(null);
  const columnMenuRef = useRef<HTMLDivElement | null>(null);

  const page = Math.max(Number(searchParams.get('page') || '1'), 1);
  const rawPageSize = Number(searchParams.get('page_size') || '25');
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawPageSize)
    ? (rawPageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : 25;
  const sortBy = (searchParams.get('sort_by') as InstitutionSummarySortBy) || DEFAULT_INSTITUTION_SUMMARY_SORT.sortBy;
  const sortOrder =
    (searchParams.get('sort_order') as InstitutionSummarySortOrder) ||
    DEFAULT_INSTITUTION_SUMMARY_SORT.sortOrder;
  const countryId = searchParams.get('country_id') || '';
  const stateId = searchParams.get('state_id') || '';
  const cityId = searchParams.get('city_id') || '';
  const statusFilter = searchParams.get('status') || '';
  const institutionType = searchParams.get('institution_type') || '';
  const programId = searchParams.get('program_id') || '';
  const majorId = searchParams.get('major_id') || '';
  const templateId = searchParams.get('template_id') || '';
  const query = searchParams.get('q') || '';

  const updateParams = useCallback(
    (updates: Record<string, string | null>, options?: { resetPage?: boolean }) => {
      setSearchParams(
        prev => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(updates)) {
            if (value == null || value === '') next.delete(key);
            else next.set(key, value);
          }
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
      countryId ||
      stateId ||
      cityId ||
      statusFilter ||
      institutionType ||
      programId ||
      majorId ||
      templateId
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
      updateParams({ q: searchDraft || null });
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [query, searchDraft, updateParams]);

  useEffect(() => {
    setSearchDraft(query);
  }, [query]);

  useEffect(() => {
    void fetchAcademiaListItems<GeographyOption>('academia/countries')
      .then(setCountries)
      .catch(() => setCountries([]));
    void fetchAcademiaListItems<DegreeRecord>('academia/degrees', { sort_by: 'name', sort_dir: 'asc' })
      .then(setPrograms)
      .catch(() => setPrograms([]));
    void fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
      sort_by: 'name',
      sort_dir: 'asc',
    })
      .then(setMajors)
      .catch(() => setMajors([]));
    void apiFetch<GlobalAcademicTemplate[]>('academia/academic-templates')
      .then(data => setIntakeTemplates(Array.isArray(data) ? data : []))
      .catch(() => setIntakeTemplates([]));
  }, []);

  useEffect(() => {
    if (!countryId) {
      setStates([]);
      return;
    }
    void fetchAcademiaListItems<GeographyOption>('academia/states', { country_id: countryId })
      .then(setStates)
      .catch(() => setStates([]));
  }, [countryId]);

  useEffect(() => {
    if (!countryId) {
      setCities([]);
      return;
    }
    void fetchAcademiaListItems<GeographyOption>('academia/cities', {
      country_id: countryId,
      state_id: stateId || undefined,
    })
      .then(setCities)
      .catch(() => setCities([]));
  }, [countryId, stateId]);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set('q', query.trim());
      if (countryId) params.set('country_id', countryId);
      if (stateId) params.set('state_id', stateId);
      if (cityId) params.set('city_id', cityId);
      if (statusFilter === 'active') params.set('is_active', 'true');
      if (statusFilter === 'inactive') params.set('is_active', 'false');
      if (institutionType) params.set('institution_type', institutionType);
      if (programId) params.set('program_id', programId);
      if (majorId) params.set('major_id', majorId);
      if (templateId) params.set('template_id', templateId);
      params.set('page', String(page));
      params.set('page_size', String(pageSize));
      params.set('sort_by', sortBy);
      params.set('sort_order', sortOrder);

      const data = await apiFetch<InstitutionSummaryListResponse>(
        `academia/institutions/summary?${params.toString()}`
      );
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 0);
      setActiveCount(data.active_count ?? 0);
      setInactiveCount(data.inactive_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institutions');
      setItems([]);
      setTotal(0);
      setTotalPages(0);
      setActiveCount(0);
      setInactiveCount(0);
    } finally {
      setLoading(false);
    }
  }, [
    cityId,
    countryId,
    institutionType,
    templateId,
    majorId,
    page,
    pageSize,
    programId,
    query,
    sortBy,
    sortOrder,
    stateId,
    statusFilter,
  ]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadSummary();
    }, 150);
    return () => window.clearTimeout(timeout);
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
      updateParams(
        { sort_order: sortOrder === 'asc' ? 'desc' : 'asc', page: String(page) },
        { resetPage: false }
      );
      return;
    }
    updateParams({ sort_by: column, sort_order: 'asc', page: String(page) }, { resetPage: false });
  };

  const toggleColumn = (key: InstitutionSummaryColumnKey) => {
    setVisibleColumns(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (key === 'name') return prev;
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

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
            ? row.level_count ?? 0
            : key === 'program_count'
              ? row.program_count ?? 0
              : key === 'major_count'
                ? row.major_count ?? 0
                : key === 'course_count'
                  ? row.course_count ?? 0
                  : key === 'campus_count'
                    ? row.campus_count ?? 0
                    : key === 'college_count'
                      ? row.college_count ?? 0
                      : key === 'intake_count'
                        ? row.intake_count ?? 0
                        : row.picture_count ?? 0;
      const isUnavailable = key !== 'name' && value === 0;
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
            {row.institution_type || '—'}
          </span>
        );
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

  const selectClassName =
    'rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-accent';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
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
            <div className="absolute left-0 z-20 mt-2 w-56 rounded-xl border border-border-subtle bg-card p-3 shadow-lg">
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
                      disabled={column.key === 'name'}
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
        <button
          type="button"
          onClick={() => navigate(INSTITUTIONS_NEW_PATH)}
          className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
        >
          <Plus size={16} />
          Add Institution
        </button>
      </div>

      <div className="space-y-4 rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
          <input
            type="search"
            value={searchDraft}
            onChange={event => setSearchDraft(event.target.value)}
            placeholder="Search institution names..."
            className="w-full max-w-md rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 font-semibold text-success">
              {activeCount} Active
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-text-muted/10 px-3 py-1 font-semibold text-text-muted">
              {inactiveCount} Inactive
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 px-6 md:grid-cols-2 xl:grid-cols-4">
          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Country</span>
            <select
              value={countryId}
              onChange={event =>
                updateParams({
                  country_id: event.target.value || null,
                  state_id: null,
                  city_id: null,
                })
              }
              className={`${selectClassName} w-full`}
            >
              <option value="">All countries</option>
              {countries.map(country => (
                <option key={country.id} value={String(country.id)}>
                  {country.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">State</span>
            <select
              value={stateId}
              disabled={!countryId}
              onChange={event =>
                updateParams({
                  state_id: event.target.value || null,
                  city_id: null,
                })
              }
              className={`${selectClassName} w-full disabled:opacity-50`}
            >
              <option value="">{countryId ? 'All states' : 'Select country first'}</option>
              {states.map(state => (
                <option key={state.id} value={String(state.id)}>
                  {state.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">City</span>
            <select
              value={cityId}
              disabled={!stateId}
              onChange={event => updateParams({ city_id: event.target.value || null })}
              className={`${selectClassName} w-full disabled:opacity-50`}
            >
              <option value="">{stateId ? 'All cities' : 'Select state first'}</option>
              {cities.map(city => (
                <option key={city.id} value={String(city.id)}>
                  {city.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Status</span>
            <select
              value={statusFilter}
              onChange={event => updateParams({ status: event.target.value || null })}
              className={`${selectClassName} w-full`}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Program Type</span>
            <select
              value={institutionType}
              onChange={event => updateParams({ institution_type: event.target.value || null })}
              className={`${selectClassName} w-full`}
            >
              <option value="">All program types</option>
              {INSTITUTION_TYPE_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Program</span>
            <select
              value={programId}
              onChange={event => updateParams({ program_id: event.target.value || null })}
              className={`${selectClassName} w-full`}
            >
              <option value="">All programs</option>
              {programs.map(program => (
                <option key={program.id} value={program.id}>
                  {program.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Major</span>
            <select
              value={majorId}
              onChange={event => updateParams({ major_id: event.target.value || null })}
              className={`${selectClassName} w-full`}
            >
              <option value="">All majors</option>
              {majors.map(major => (
                <option key={major.id} value={String(major.id)}>
                  {major.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Intakes</span>
            <select
              value={templateId}
              onChange={event => updateParams({ template_id: event.target.value || null })}
              className={`${selectClassName} w-full`}
            >
              <option value="">All intakes</option>
              {intakeTemplates.map(template => (
                <option key={template.id} value={String(template.id)}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
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
                {items.map(row => (
                  <tr key={row.id} className="hover:bg-surface-bg/40">
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
                ))}
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
            onPageChange={nextPage => updateParams({ page: String(nextPage) }, { resetPage: false })}
            onPageSizeChange={nextSize => updateParams({ page_size: String(nextSize) })}
          />
        ) : null}
      </div>
    </div>
  );
};

export default InstitutionsManagePage;
