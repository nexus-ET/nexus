import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, Power, PowerOff, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems, normalizePaginatedList, type PaginatedListResponse } from '../../utils/academiaList';
import { getAcademiaNavItem, getAcademiaSectionLabel } from '../../config/academiaHubNav';
import { ACADEMIA_ENTITY_CONFIG } from '../../types/academiaHub';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import SearchableSelect from './SearchableSelect';
import ReadOnlyIdField, { entityIdCellClass, formatEntityId } from './ReadOnlyIdField';
import { useConfirmation } from '../../context/ConfirmationContext';
import {
  fetchGeographyStatusImpact,
  geographyEntityTypeFromKey,
} from '../../utils/geographyStatus';

type EntityRecord = Record<string, unknown>;

interface AcademiaEntityPageProps {
  sectionKey?: string;
  entityKey?: string;
  embedded?: boolean;
}

const OPTIONS_ENDPOINTS: Record<string, string> = {
  countries: 'academia/countries',
  states: 'academia/states',
  cities: 'academia/cities',
  institutions: 'academia/institutions',
  campuses: 'academia/campuses',
  programs: 'academia/programs',
};

const PAGE_SIZE_OPTIONS = [20, 50] as const;

const GEOGRAPHY_SORT_COLUMNS: Record<string, string[]> = {
  countries: ['name', 'iso2', 'dial_code', 'is_active'],
  states: ['name', 'region_code', 'country_name', 'is_active'],
};

const formatCellValue = (value: unknown): string => {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
};

const AcademiaEntityPage: React.FC<AcademiaEntityPageProps> = ({
  sectionKey: sectionKeyProp,
  entityKey: entityKeyProp,
  embedded = false,
}) => {
  const openConfirm = useConfirmation();
  const navigate = useNavigate();
  const params = useParams();
  const section = sectionKeyProp || params.section || '';
  const entity = entityKeyProp || params.entity || '';
  const recordId = params.recordId;
  const navItem = getAcademiaNavItem(section, entity);
  const config = ACADEMIA_ENTITY_CONFIG[entity];
  const isNew = recordId === 'new';
  const isDetail = Boolean(recordId);
  const geographyType = geographyEntityTypeFromKey(entity);
  const isGeographyList = Boolean(geographyType) && (entity === 'countries' || entity === 'states');
  const isStatesList = entity === 'states';

  const [rows, setRows] = useState<EntityRecord[]>([]);
  const [record, setRecord] = useState<EntityRecord | null>(null);
  const [formState, setFormState] = useState<EntityRecord>({ is_active: true, sort_order: 0 });
  const [options, setOptions] = useState<Record<string, EntityRecord[]>>({});
  const [listQuery, setListQuery] = useState('');
  const [filterCountryId, setFilterCountryId] = useState('');
  const [filterCountries, setFilterCountries] = useState<EntityRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [togglingStatusId, setTogglingStatusId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const sectionLabel = getAcademiaSectionLabel(section);

  const loadOptions = useCallback(async () => {
    if (!config) return;
    const sources = [
      ...new Set(config.fields.map(field => field.optionsSource).filter(Boolean)),
    ] as string[];
    const entries = await Promise.all(
      sources.map(async source => {
        const endpoint = OPTIONS_ENDPOINTS[source];
        if (!endpoint) return [source, []] as const;
        try {
          const data = await fetchAcademiaListItems<EntityRecord>(endpoint, {
            active_only: 'true',
          });
          return [source, data] as const;
        } catch {
          return [source, []] as const;
        }
      })
    );
    setOptions(Object.fromEntries(entries));
  }, [config]);

  const loadList = useCallback(async () => {
    if (!navItem || isDetail) return;
    setLoading(true);
    setError(null);
    try {
      if (isGeographyList) {
        const params = new URLSearchParams();
        if (listQuery.trim()) params.set('q', listQuery.trim());
        if (isStatesList && filterCountryId) params.set('country_id', filterCountryId);
        params.set('page', String(page));
        params.set('page_size', String(pageSize));
        const apiSortBy =
          sortBy === 'country_name' ? 'country' : sortBy === 'iso2' ? 'iso2' : sortBy;
        params.set('sort_by', apiSortBy);
        params.set('sort_dir', sortDir);
        const data = normalizePaginatedList<EntityRecord>(
          await apiFetch<PaginatedListResponse<EntityRecord> | EntityRecord[]>(
            `${navItem.apiPath}?${params.toString()}`
          )
        );
        setRows(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      } else {
        const query = listQuery.trim();
        const endpoint = query
          ? `${navItem.apiPath}?q=${encodeURIComponent(query)}`
          : navItem.apiPath;
        const data = normalizePaginatedList<EntityRecord>(
          await apiFetch<EntityRecord[] | PaginatedListResponse<EntityRecord>>(endpoint)
        );
        setRows(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load records');
      setRows([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [
    filterCountryId,
    isDetail,
    isGeographyList,
    isStatesList,
    listQuery,
    navItem,
    page,
    pageSize,
    sortBy,
    sortDir,
  ]);

  const loadRecord = useCallback(async () => {
    if (!navItem || !recordId || isNew) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<EntityRecord>(`${navItem.apiPath}/${recordId}`);
      setRecord(data);
      setFormState(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load record');
      setRecord(null);
    } finally {
      setLoading(false);
    }
  }, [isNew, navItem, recordId]);

  useEffect(() => {
    if (!isGeographyList) return;
    setPage(current => (current === 1 ? current : 1));
  }, [filterCountryId, isGeographyList, listQuery, pageSize, sortBy, sortDir]);

  useEffect(() => {
    if (!isStatesList || isDetail) return;
    let cancelled = false;
    void fetchAcademiaListItems<EntityRecord>('academia/countries')
      .then(data => {
        if (!cancelled) setFilterCountries(data);
      })
      .catch(() => {
        if (!cancelled) setFilterCountries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isDetail, isStatesList]);

  useEffect(() => {
    if (!navItem || !config) return;
    if (isDetail) {
      void loadRecord();
      return undefined;
    }
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      if (!cancelled) void loadList();
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [config, isDetail, loadList, loadRecord, navItem]);

  useEffect(() => {
    if (!isDetail || !config) return;
    void loadOptions();
  }, [config, isDetail, loadOptions]);

  useEffect(() => {
    if (!isNew || !config) return;
    const initial: EntityRecord = { is_active: true, sort_order: 0 };
    setRecord(null);
    setFormState(initial);
    setLoading(false);
    void loadOptions();
  }, [config, isNew, loadOptions]);

  const breadcrumbs = useMemo(() => {
    const items = [
      { label: 'Academia Hub', path: '/academia' },
      { label: sectionLabel, path: navItem?.path },
      { label: navItem?.label || entity, path: navItem?.path },
    ];
    if (isNew) {
      items.push({ label: `New ${navItem?.singular || 'Record'}` });
    } else if (isDetail && record) {
      const title = String(record.name || record.label || record.id || recordId);
      items.push({ label: title });
    }
    return items;
  }, [entity, isDetail, isNew, navItem, record, recordId, sectionLabel]);

  const countryFilterOptions = useMemo(
    () =>
      filterCountries.map(country => ({
        value: String(country.id),
        label: String(country.name || country.id),
      })),
    [filterCountries]
  );

  if (!navItem || !config) {
    return <Navigate to="/academia" replace />;
  }

  const handleFieldChange = (key: string, value: unknown) => {
    setFormState(previous => ({ ...previous, [key]: value }));
  };

  const buildPayload = () => {
    const payload: EntityRecord = {};
    for (const field of config.fields) {
      const value = formState[field.key];
      if (field.type === 'number') {
        payload[field.key] = value === '' || value === undefined ? 0 : Number(value);
        continue;
      }
      if (field.type === 'checkbox') {
        payload[field.key] = Boolean(value);
        continue;
      }
      if (field.type === 'select') {
        payload[field.key] = value === '' ? null : Number(value);
        continue;
      }
      payload[field.key] = value;
    }
    return payload;
  };

  const confirmInactiveIfNeeded = async (nextActive: boolean, name: string, id?: number) => {
    if (nextActive || !geographyType || !id) {
      return openConfirm({
        title: nextActive ? `Activate ${navItem.singular.toLowerCase()}?` : `Deactivate ${navItem.singular.toLowerCase()}?`,
        message: nextActive
          ? `Set "${name}" to Active?`
          : `Set "${name}" to Inactive?`,
        confirmLabel: nextActive ? 'Activate' : 'Deactivate',
        variant: nextActive ? 'warning' : 'danger',
      });
    }

    let message = `Set "${name}" to Inactive?`;
    try {
      const impact = await fetchGeographyStatusImpact(geographyType, id, false);
      message = impact.message;
      if (impact.has_links) {
        message += `\n\nLinked: ${[
          impact.states ? `${impact.states} states` : null,
          impact.cities ? `${impact.cities} cities` : null,
          impact.institutions ? `${impact.institutions} institutions` : null,
          impact.campuses ? `${impact.campuses} campuses` : null,
          impact.colleges ? `${impact.colleges} colleges` : null,
        ]
          .filter(Boolean)
          .join(', ')}.`;
      }
    } catch {
      message =
        `Set "${name}" to Inactive? If this location is linked to institutions, campuses, or colleges, those links will remain but the location will be hidden from active pickers.`;
    }

    return openConfirm({
      title: `Deactivate ${navItem.singular.toLowerCase()}?`,
      message,
      confirmLabel: 'Deactivate',
      variant: 'danger',
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload();
      if (
        !isNew &&
        geographyType &&
        record &&
        Boolean(record.is_active) &&
        payload.is_active === false
      ) {
        const confirmed = await confirmInactiveIfNeeded(
          false,
          String(record.name || navItem.singular),
          Number(record.id)
        );
        if (!confirmed) {
          setSaving(false);
          return;
        }
      }

      if (isNew) {
        const created = await apiFetch<EntityRecord>(navItem.apiPath, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        navigate(
          config.redirectToListAfterCreate ? navItem.path : `${navItem.path}/${created.id}`
        );
        return;
      }
      const updated = await apiFetch<EntityRecord>(`${navItem.apiPath}/${recordId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      setRecord(updated);
      setFormState(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save record');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!recordId || isNew) return;
    if (
      !(await openConfirm({
        title: `Delete ${navItem.singular.toLowerCase()}?`,
        message: `Delete this ${navItem.singular.toLowerCase()}?`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`${navItem.apiPath}/${recordId}`, { method: 'DELETE' });
      navigate(navItem.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete record');
      setSaving(false);
    }
  };

  const handleToggleStatus = async (row: EntityRecord) => {
    const id = Number(row.id);
    if (!Number.isFinite(id)) return;
    const nextActive = !Boolean(row.is_active);
    const name = String(row.name || navItem.singular);
    if (!(await confirmInactiveIfNeeded(nextActive, name, id))) return;

    setTogglingStatusId(id);
    try {
      const updated = await apiFetch<EntityRecord>(`${navItem.apiPath}/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: nextActive }),
      });
      setRows(previous =>
        previous.map(item => (Number(item.id) === id ? { ...item, ...updated } : item))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status');
    } finally {
      setTogglingStatusId(null);
    }
  };

  const toggleSort = (column: string) => {
    if (sortBy === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir('asc');
  };

  const sortableColumns = GEOGRAPHY_SORT_COLUMNS[entity] || [];

  if (isDetail) {
    return (
      <div className={embedded ? 'space-y-4' : 'space-y-6'}>
        {embedded ? null : <AcademiaBreadcrumbs items={breadcrumbs} />}
        <div
          className={`${embedded ? '' : 'rounded-2xl border border-border-subtle bg-card '}p-6 shadow-sm`}
        >
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-text-main">
                {isNew ? `New ${navItem.singular}` : `Edit ${navItem.singular}`}
              </h2>
              <p className="text-sm text-text-muted">{sectionLabel}</p>
            </div>
            {!isNew ? (
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl border border-alert/30 px-3 py-2 text-sm font-semibold text-alert transition-colors hover:bg-alert/10 disabled:opacity-50"
              >
                <Trash2 size={16} />
                Delete
              </button>
            ) : null}
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-text-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading...
            </div>
          ) : (
            <form
              className="grid grid-cols-1 gap-4 md:grid-cols-2"
              onSubmit={event => {
                event.preventDefault();
                void handleSave();
              }}
            >
              {!isNew &&
              record?.id != null &&
              (entity === 'institutions' || entity === 'campuses' || entity === 'colleges') ? (
                <ReadOnlyIdField value={Number(record.id)} />
              ) : null}
              {config.fields.map(field => {
                const value = formState[field.key];
                if (field.type === 'checkbox') {
                  return (
                    <label
                      key={field.key}
                      className="flex items-center gap-2 text-sm text-text-main md:col-span-2"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(value)}
                        onChange={event => handleFieldChange(field.key, event.target.checked)}
                      />
                      {field.label}
                    </label>
                  );
                }
                if (field.type === 'select') {
                  const source = field.optionsSource ? options[field.optionsSource] || [] : [];
                  return (
                    <label key={field.key} className="space-y-1 text-sm">
                      <span className="font-medium text-text-main">{field.label}</span>
                      <select
                        value={value === null || value === undefined ? '' : String(value)}
                        onChange={event => handleFieldChange(field.key, event.target.value)}
                        className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                        required={field.required}
                      >
                        <option value="">Select...</option>
                        {source.map(option => (
                          <option
                            key={String(option[field.optionValueKey || 'id'])}
                            value={String(option[field.optionValueKey || 'id'])}
                          >
                            {String(option[field.optionLabelKey || 'name'])}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                }
                return (
                  <label key={field.key} className="space-y-1 text-sm">
                    <span className="font-medium text-text-main">{field.label}</span>
                    <input
                      type={field.type === 'number' ? 'number' : 'text'}
                      value={value === null || value === undefined ? '' : String(value)}
                      onChange={event =>
                        handleFieldChange(
                          field.key,
                          field.type === 'number' ? event.target.value : event.target.value
                        )
                      }
                      placeholder={field.placeholder}
                      required={field.required}
                      className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    />
                  </label>
                );
              })}

              {error ? <div className="md:col-span-2 text-sm text-alert">{error}</div> : null}

              <div className="flex flex-wrap gap-3 md:col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? <Loader2 size={16} className="animate-spin" /> : null}
                  Save
                </button>
                <Link
                  to={navItem.path}
                  className="inline-flex items-center rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted transition-colors hover:text-text-main"
                >
                  Cancel
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : <AcademiaBreadcrumbs items={breadcrumbs} />}
      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
          <div>
            <h2 className="text-xl font-bold text-text-main">{navItem.label}</h2>
            <p className="text-sm text-text-muted">{sectionLabel}</p>
          </div>
          <Link
            to={`${navItem.path}/new`}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg transition-opacity hover:opacity-90"
          >
            <Plus size={16} />
            Add {navItem.singular}
          </Link>
        </div>

        <div
          className={
            isStatesList
              ? 'grid grid-cols-1 gap-3 border-b border-border-subtle px-6 py-4 md:grid-cols-4'
              : 'border-b border-border-subtle px-6 py-4'
          }
        >
          {isStatesList ? (
            <>
              <SearchableSelect
                label="Filter by country"
                value={filterCountryId}
                options={countryFilterOptions}
                onChange={setFilterCountryId}
                placeholder="All countries"
              />
              <label className="space-y-1 text-sm md:col-span-3">
                <span className="font-medium text-text-main">Search states</span>
                <input
                  type="text"
                  value={listQuery}
                  onChange={event => setListQuery(event.target.value)}
                  placeholder="Filter states..."
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                />
              </label>
            </>
          ) : (
            <input
              type="text"
              value={listQuery}
              onChange={event => setListQuery(event.target.value)}
              placeholder={`Filter ${navItem.label.toLowerCase()}...`}
              className="w-full max-w-md rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : rows.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No records found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    {config.listColumns.map(column =>
                      isGeographyList && sortableColumns.includes(column.key) ? (
                        <FrameworkSortableHeader
                          key={column.key}
                          label={column.label}
                          column={column.key}
                          sortBy={sortBy}
                          sortDir={sortDir}
                          onSort={toggleSort}
                        />
                      ) : (
                        <th key={column.key} className="px-6 py-3 font-semibold">
                          {column.label}
                        </th>
                      )
                    )}
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => {
                    const id = Number(row.id);
                    const isActive = Boolean(row.is_active);
                    return (
                      <tr key={String(row.id)} className="border-t border-border-subtle/70">
                        {config.listColumns.map(column => (
                          <td
                            key={column.key}
                            className={`px-6 py-3 ${
                              column.key === 'id' || column.key.endsWith('_id')
                                ? entityIdCellClass
                                : 'text-text-main'
                            }`}
                          >
                            {column.key === 'is_active' ? (
                              <EntityStatusBadge isActive={isActive} />
                            ) : entity !== 'countries' &&
                              entity !== 'states' &&
                              entity !== 'cities' &&
                              (column.key === 'id' || column.key.endsWith('_id')) ? (
                              formatEntityId(row[column.key] as number | string | null)
                            ) : (
                              formatCellValue(row[column.key])
                            )}
                          </td>
                        ))}
                        <td className="px-6 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {isGeographyList ? (
                              <button
                                type="button"
                                disabled={togglingStatusId === id}
                                onClick={() => void handleToggleStatus(row)}
                                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-bg hover:text-text-main disabled:opacity-50"
                                title={isActive ? 'Set inactive' : 'Set active'}
                              >
                                {togglingStatusId === id ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : isActive ? (
                                  <PowerOff size={14} />
                                ) : (
                                  <Power size={14} />
                                )}
                                {isActive ? 'Deactivate' : 'Activate'}
                              </button>
                            ) : null}
                            <Link
                              to={`${navItem.path}/${row.id}`}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent transition-colors hover:bg-accent/10"
                            >
                              <Pencil size={14} />
                              Edit
                            </Link>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {isGeographyList ? (
              <FrameworkTablePagination
                page={page}
                pageSize={pageSize}
                total={total}
                totalPages={totalPages}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                onPageChange={setPage}
                onPageSizeChange={size => setPageSize(size as (typeof PAGE_SIZE_OPTIONS)[number])}
              />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
};

export default AcademiaEntityPage;
