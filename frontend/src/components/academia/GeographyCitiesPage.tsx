import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, Power, PowerOff, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems, normalizePaginatedList, type PaginatedListResponse } from '../../utils/academiaList';
import { fetchGeographyStatusImpact } from '../../utils/geographyStatus';
import { filterTimeZones, suggestTimezoneFromLocation } from '../../utils/ianaTimezones';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import SearchableSelect from './SearchableSelect';
import { useConfirmation } from '../../context/ConfirmationContext';

interface CountryOption {
  id: number;
  name: string;
  iso2?: string;
  iso_code?: string;
}

interface StateOption {
  id: number;
  name: string;
  country_id: number;
  region_code?: string | null;
}

interface CityRecord {
  id: number;
  name: string;
  country_id: number;
  state_id: number;
  time_zone?: string | null;
  postal_code_prefix?: string | null;
  is_active: boolean;
  sort_order: number;
  country_name?: string | null;
  state_name?: string | null;
  region_code?: string | null;
}

type CitySortBy = 'name' | 'state' | 'country' | 'time_zone' | 'is_active';

const CITY_LIST_PATH = '/academia/geography/cities';
const PAGE_SIZE_OPTIONS = [20, 50] as const;

const emptyForm = {
  name: '',
  country_id: '',
  state_id: '',
  time_zone: '',
  postal_code_prefix: '',
  sort_order: 0,
  is_active: true,
};

const GeographyCitiesPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const navigate = useNavigate();
  const { recordId } = useParams();
  const isNew = recordId === 'new';
  const isDetail = Boolean(recordId);

  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [filterStates, setFilterStates] = useState<StateOption[]>([]);
  const [formStates, setFormStates] = useState<StateOption[]>([]);
  const [rows, setRows] = useState<CityRecord[]>([]);
  const [record, setRecord] = useState<CityRecord | null>(null);
  const [formState, setFormState] = useState(emptyForm);
  const [filterCountryId, setFilterCountryId] = useState('');
  const [filterStateId, setFilterStateId] = useState('');
  const [listQuery, setListQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [togglingStatusId, setTogglingStatusId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<CitySortBy>('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const loadCountries = useCallback(async () => {
    const data = await fetchAcademiaListItems<CountryOption>('academia/countries');
    setCountries(data);
  }, []);

  const loadStatesForCountry = useCallback(async (countryId: string): Promise<StateOption[]> => {
    if (!countryId) return [];
    return fetchAcademiaListItems<StateOption>('academia/states', {
      country_id: countryId,
    });
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (listQuery.trim()) params.set('q', listQuery.trim());
      if (filterCountryId) params.set('country_id', filterCountryId);
      if (filterStateId) params.set('state_id', filterStateId);
      params.set('page', String(page));
      params.set('page_size', String(pageSize));
      params.set('sort_by', sortBy);
      params.set('sort_dir', sortDir);
      const data = normalizePaginatedList<CityRecord>(
        await apiFetch<PaginatedListResponse<CityRecord> | CityRecord[]>(
          `academia/cities?${params.toString()}`
        )
      );
      setRows(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cities');
      setRows([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [filterCountryId, filterStateId, listQuery, page, pageSize, sortBy, sortDir]);

  const loadRecord = useCallback(async () => {
    if (!recordId || isNew) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<CityRecord>(`academia/cities/${recordId}`);
      setRecord(data);
      setFormState({
        name: data.name,
        country_id: String(data.country_id),
        state_id: String(data.state_id),
        time_zone: data.time_zone || '',
        postal_code_prefix: data.postal_code_prefix || '',
        sort_order: data.sort_order ?? 0,
        is_active: data.is_active,
      });
      const states = await loadStatesForCountry(String(data.country_id));
      setFormStates(states);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load city');
      setRecord(null);
    } finally {
      setLoading(false);
    }
  }, [isNew, loadStatesForCountry, recordId]);

  useEffect(() => {
    void loadCountries();
  }, [loadCountries]);

  useEffect(() => {
    if (!isDetail) return;
    if (isNew) {
      setLoading(false);
      setFormState(emptyForm);
      setFormStates([]);
      setRecord(null);
      return;
    }
    void loadRecord();
  }, [isDetail, isNew, loadRecord]);

  useEffect(() => {
    if (isDetail) return undefined;
    setPage(current => (current === 1 ? current : 1));
  }, [filterCountryId, filterStateId, isDetail, listQuery, pageSize, sortBy, sortDir]);

  useEffect(() => {
    if (isDetail) return undefined;
    const timeout = window.setTimeout(() => {
      void loadList();
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [isDetail, loadList]);

  useEffect(() => {
    if (!filterCountryId) {
      setFilterStates(prev => (prev.length === 0 ? prev : []));
      setFilterStateId(prev => (prev === '' ? prev : ''));
      return;
    }
    void loadStatesForCountry(filterCountryId).then(setFilterStates);
  }, [filterCountryId, loadStatesForCountry]);

  useEffect(() => {
    if (!isDetail) return;
    if (!formState.country_id) {
      setFormStates([]);
      return;
    }
    void loadStatesForCountry(formState.country_id).then(setFormStates);
  }, [formState.country_id, isDetail, loadStatesForCountry]);

  const countryOptions = useMemo(
    () =>
      countries.map(country => ({
        value: String(country.id),
        label: country.name,
      })),
    [countries]
  );

  const filterStateOptions = useMemo(
    () =>
      filterStates.map(state => ({
        value: String(state.id),
        label: state.region_code ? `${state.name} (${state.region_code})` : state.name,
      })),
    [filterStates]
  );

  const formStateOptions = useMemo(
    () =>
      formStates.map(state => ({
        value: String(state.id),
        label: state.region_code ? `${state.name} (${state.region_code})` : state.name,
      })),
    [formStates]
  );

  const timezoneOptions = useMemo(
    () =>
      filterTimeZones('').map(zone => ({
        value: zone,
        label: zone,
      })),
    []
  );

  const breadcrumbs = useMemo(() => {
    const items = [
      { label: 'Academia Hub', path: '/academia' },
      { label: 'Geography', path: CITY_LIST_PATH },
      { label: 'Cities', path: CITY_LIST_PATH },
    ];
    if (isNew) items.push({ label: 'New City' });
    else if (isDetail && record) items.push({ label: record.name });
    return items;
  }, [isDetail, isNew, record]);

  const handleFilterCountryChange = (value: string) => {
    setFilterCountryId(value);
    setFilterStateId('');
  };

  const resolveSuggestedTimezone = useCallback(
    (countryId: string, stateId: string, states: StateOption[] = formStates) => {
      const country = countries.find(item => String(item.id) === countryId);
      const state = states.find(item => String(item.id) === stateId);
      return suggestTimezoneFromLocation({
        countryIso2: country?.iso2 || country?.iso_code,
        countryName: country?.name,
        stateRegionCode: state?.region_code,
        stateName: state?.name,
      });
    },
    [countries, formStates]
  );

  const handleFormCountryChange = (value: string) => {
    const suggested = resolveSuggestedTimezone(value, '');
    setFormState(previous => ({
      ...previous,
      country_id: value,
      state_id: '',
      time_zone: suggested ?? '',
    }));
  };

  const handleFormStateChange = (value: string) => {
    const suggested = resolveSuggestedTimezone(formState.country_id, value);
    setFormState(previous => ({
      ...previous,
      state_id: value,
      // Keep prior timezone when no confident match so the user can adjust manually.
      time_zone: suggested ?? previous.time_zone,
    }));
  };

  const handleSave = async () => {
    if (!formState.name.trim() || !formState.country_id || !formState.state_id) {
      setError('City name, country, and state are required.');
      return;
    }
    if (record?.is_active && !formState.is_active) {
      let message = `Set "${formState.name.trim()}" to Inactive?`;
      try {
        const impact = await fetchGeographyStatusImpact('city', Number(recordId), false);
        message = impact.message;
        if (impact.has_links) {
          message += `\n\nLinked: ${[
            impact.institutions ? `${impact.institutions} institutions` : null,
            impact.campuses ? `${impact.campuses} campuses` : null,
            impact.colleges ? `${impact.colleges} colleges` : null,
          ]
            .filter(Boolean)
            .join(', ')}.`;
        }
      } catch {
        /* keep default message */
      }
      if (
        !(await openConfirm({
          title: 'Deactivate city?',
          message,
          confirmLabel: 'Deactivate',
          variant: 'danger',
        }))
      ) {
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: formState.name.trim(),
        country_id: Number(formState.country_id),
        state_id: Number(formState.state_id),
        time_zone: formState.time_zone.trim() || null,
        postal_code_prefix: formState.postal_code_prefix.trim() || null,
        sort_order: Number(formState.sort_order) || 0,
        is_active: formState.is_active,
      };
      if (isNew) {
        await apiFetch<CityRecord>('academia/cities', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        navigate(CITY_LIST_PATH);
        return;
      }
      const updated = await apiFetch<CityRecord>(`academia/cities/${recordId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      setRecord(updated);
      setFormState({
        name: updated.name,
        country_id: String(updated.country_id),
        state_id: String(updated.state_id),
        time_zone: updated.time_zone || '',
        postal_code_prefix: updated.postal_code_prefix || '',
        sort_order: updated.sort_order ?? 0,
        is_active: updated.is_active,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save city');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async (row: CityRecord) => {
    const nextActive = !row.is_active;
    let message = nextActive
      ? `Set "${row.name}" to Active?`
      : `Set "${row.name}" to Inactive?`;
    if (!nextActive) {
      try {
        const impact = await fetchGeographyStatusImpact('city', row.id, false);
        message = impact.message;
        if (impact.has_links) {
          message += `\n\nLinked: ${[
            impact.institutions ? `${impact.institutions} institutions` : null,
            impact.campuses ? `${impact.campuses} campuses` : null,
            impact.colleges ? `${impact.colleges} colleges` : null,
          ]
            .filter(Boolean)
            .join(', ')}.`;
        }
      } catch {
        /* keep default */
      }
    }
    if (
      !(await openConfirm({
        title: nextActive ? 'Activate city?' : 'Deactivate city?',
        message,
        confirmLabel: nextActive ? 'Activate' : 'Deactivate',
        variant: nextActive ? 'warning' : 'danger',
      }))
    ) {
      return;
    }

    setTogglingStatusId(row.id);
    try {
      const updated = await apiFetch<CityRecord>(`academia/cities/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: nextActive }),
      });
      setRows(previous => previous.map(item => (item.id === row.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update city status');
    } finally {
      setTogglingStatusId(null);
    }
  };

  const toggleSort = (column: CitySortBy) => {
    if (sortBy === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir('asc');
  };

  const handleDelete = async () => {
    if (!recordId || isNew) return;
    if (!(await openConfirm({
      title: 'Delete city?',
      message: 'Delete this city?',
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`academia/cities/${recordId}`, { method: 'DELETE' });
      navigate(CITY_LIST_PATH);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete city');
      setSaving(false);
    }
  };

  if (isDetail && recordId && !isNew && !loading && !record && error) {
    return <Navigate to={CITY_LIST_PATH} replace />;
  }

  if (isDetail) {
    return (
      <div className={embedded ? 'space-y-4' : 'space-y-6'}>
        {embedded ? null : <AcademiaBreadcrumbs items={breadcrumbs} />}
        <div className={`${embedded ? '' : 'rounded-2xl border border-border-subtle bg-card '}p-6 shadow-sm`}>
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-text-main">
                {isNew ? 'New City' : 'Edit City'}
              </h2>
              <p className="text-sm text-text-muted">Geography</p>
            </div>
            {!isNew ? (
              <button
                type="button"
                onClick={handleDelete}
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
              <SearchableSelect
                label="Country"
                value={formState.country_id}
                options={countryOptions}
                onChange={handleFormCountryChange}
                placeholder="Select country..."
                required
              />
              <SearchableSelect
                label="State / Province"
                value={formState.state_id}
                options={formStateOptions}
                onChange={handleFormStateChange}
                placeholder={formState.country_id ? 'Select state...' : 'Select a country first'}
                required
                disabled={!formState.country_id}
                emptyMessage={
                  formState.country_id ? 'No states found for this country.' : 'Select a country first.'
                }
              />
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="font-medium text-text-main">City name *</span>
                <input
                  type="text"
                  value={formState.name}
                  onChange={event => setFormState(previous => ({ ...previous, name: event.target.value }))}
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                  required
                />
              </label>
              <div className="space-y-1">
                <SearchableSelect
                  label="Time zone"
                  value={formState.time_zone}
                  options={timezoneOptions}
                  onChange={value => setFormState(previous => ({ ...previous, time_zone: value }))}
                  placeholder="Search time zone (e.g. Tokyo)..."
                />
                <p className="text-xs text-text-muted">
                  Auto-selected from country/state when a match is available. Change it if needed.
                </p>
              </div>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-text-main">Postal code prefix</span>
                <input
                  type="text"
                  value={formState.postal_code_prefix}
                  onChange={event =>
                    setFormState(previous => ({ ...previous, postal_code_prefix: event.target.value }))
                  }
                  placeholder="Optional"
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-text-main">Sort order</span>
                <input
                  type="number"
                  value={formState.sort_order}
                  onChange={event =>
                    setFormState(previous => ({
                      ...previous,
                      sort_order: Number(event.target.value) || 0,
                    }))
                  }
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-text-main md:col-span-2">
                <input
                  type="checkbox"
                  checked={formState.is_active}
                  onChange={event =>
                    setFormState(previous => ({ ...previous, is_active: event.target.checked }))
                  }
                />
                Active
              </label>

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
                  to={CITY_LIST_PATH}
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
          {embedded ? (
            <Link
              to={`${CITY_LIST_PATH}/new`}
              className="ml-auto inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg transition-opacity hover:opacity-90"
            >
              <Plus size={16} />
              Add City
            </Link>
          ) : (
            <>
              <div>
                <h2 className="text-xl font-bold text-text-main">Cities</h2>
                <p className="text-sm text-text-muted">Geography</p>
              </div>
              <Link
                to={`${CITY_LIST_PATH}/new`}
                className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg transition-opacity hover:opacity-90"
              >
                <Plus size={16} />
                Add City
              </Link>
            </>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 border-b border-border-subtle px-6 py-4 md:grid-cols-4">
          <SearchableSelect
            label="Filter by country"
            value={filterCountryId}
            options={countryOptions}
            onChange={handleFilterCountryChange}
            placeholder="All countries"
          />
          <SearchableSelect
            label="Filter by state"
            value={filterStateId}
            options={filterStateOptions}
            onChange={setFilterStateId}
            placeholder={filterCountryId ? 'All states' : 'Select country first'}
            disabled={!filterCountryId}
          />
          <label className="space-y-1 text-sm md:col-span-2">
            <span className="font-medium text-text-main">Search cities</span>
            <input
              type="text"
              value={listQuery}
              onChange={event => setListQuery(event.target.value)}
              placeholder="Search by city, time zone, or postal prefix..."
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : rows.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No cities found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkSortableHeader
                      label="City"
                      column="name"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="State"
                      column="state"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="Country"
                      column="country"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="Time zone"
                      column="time_zone"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Region code</th>
                    <FrameworkSortableHeader
                      label="Status"
                      column="is_active"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => (
                    <tr key={row.id} className="border-t border-border-subtle/70">
                      <td className="px-6 py-3 text-text-main">{row.name}</td>
                      <td className="px-6 py-3 text-text-main">{row.state_name || '—'}</td>
                      <td className="px-6 py-3 text-text-main">{row.country_name || '—'}</td>
                      <td className="px-6 py-3 text-text-main">{row.time_zone || '—'}</td>
                      <td className="px-6 py-3 text-text-main">{row.region_code || '—'}</td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={row.is_active} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            disabled={togglingStatusId === row.id}
                            onClick={() => void handleToggleStatus(row)}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-bg hover:text-text-main disabled:opacity-50"
                            title={row.is_active ? 'Set inactive' : 'Set active'}
                          >
                            {togglingStatusId === row.id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : row.is_active ? (
                              <PowerOff size={14} />
                            ) : (
                              <Power size={14} />
                            )}
                            {row.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <Link
                            to={`${CITY_LIST_PATH}/${row.id}`}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent transition-colors hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </Link>
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
              onPageChange={setPage}
              onPageSizeChange={size => setPageSize(size as (typeof PAGE_SIZE_OPTIONS)[number])}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default GeographyCitiesPage;
