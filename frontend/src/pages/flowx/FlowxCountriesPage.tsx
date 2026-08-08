import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, EyeOff, Globe2, Plus, Trash2, Users, X } from 'lucide-react';
import {
  useEnsureFlowxCountry,
  useFlowxCountries,
  useRemoveFlowxCountry,
} from '../../hooks/useFlowx';
import { useCountries } from '../../hooks/useCountries';
import {
  FLOWX_MACRO_REGIONS,
  getFlowxMacroRegion,
  getFlowxRegionMeta,
  loadHiddenFlowxRegions,
  saveHiddenFlowxRegions,
  type FlowxMacroRegion,
} from '../../config/flowxRegions';
import type { FlowxCountrySummary } from '../../types/flowx';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import ConfirmationModal from '../../components/ConfirmationModal';
import { CountryFlag } from '../../utils/countryFlag';

const FlowxCountriesPage: React.FC = () => {
  const countriesQuery = useFlowxCountries();
  const { countries: catalog } = useCountries();
  const ensureMutation = useEnsureFlowxCountry();
  const removeMutation = useRemoveFlowxCountry();

  const [addOpen, setAddOpen] = useState(false);
  const [addQuery, setAddQuery] = useState('');
  const [addError, setAddError] = useState<string | null>(null);
  const [selectedIso, setSelectedIso] = useState<Set<string>>(new Set());
  const [pendingRemove, setPendingRemove] = useState<FlowxCountrySummary | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  /** After a blocked remove (open journeys), next confirm archives journeys too. */
  const [forceRemove, setForceRemove] = useState(false);
  const [hiddenRegions, setHiddenRegions] = useState<Set<FlowxMacroRegion>>(() =>
    loadHiddenFlowxRegions()
  );

  const activeIso = useMemo(
    () => new Set((countriesQuery.data ?? []).map(c => c.country_iso2.toUpperCase())),
    [countriesQuery.data]
  );

  const addCandidates = useMemo(() => {
    const q = addQuery.trim().toLowerCase();
    return catalog
      .filter(c => !activeIso.has(c.iso2.toUpperCase()))
      .filter(c => {
        if (!q) return true;
        const region = getFlowxRegionMeta(getFlowxMacroRegion(c.iso2));
        return (
          c.name.toLowerCase().includes(q) ||
          c.iso2.toLowerCase().includes(q) ||
          region.code.toLowerCase().includes(q) ||
          region.label.toLowerCase().includes(q)
        );
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [catalog, activeIso, addQuery]);

  const byRegion = useMemo(() => {
    const groups = Object.fromEntries(
      FLOWX_MACRO_REGIONS.map(region => [region.key, [] as FlowxCountrySummary[]])
    ) as Record<FlowxMacroRegion, FlowxCountrySummary[]>;

    for (const country of countriesQuery.data ?? []) {
      groups[getFlowxMacroRegion(country.country_iso2)].push(country);
    }
    for (const key of Object.keys(groups) as FlowxMacroRegion[]) {
      groups[key].sort((a, b) => a.country_name.localeCompare(b.country_name));
    }
    return groups;
  }, [countriesQuery.data]);

  const regionColumns = useMemo(
    () =>
      FLOWX_MACRO_REGIONS.map(region => {
        const countries = byRegion[region.key];
        return {
          ...region,
          countries,
          institution_count: countries.reduce((sum, c) => sum + (c.institution_count ?? 0), 0),
          college_count: countries.reduce((sum, c) => sum + (c.college_count ?? 0), 0),
          students_processed: countries.reduce((sum, c) => sum + (c.students_processed ?? 0), 0),
          students_in_process: countries.reduce((sum, c) => sum + (c.students_in_process ?? 0), 0),
        };
      }),
    [byRegion]
  );

  const visibleColumns = useMemo(
    () => regionColumns.filter(region => !hiddenRegions.has(region.key)),
    [regionColumns, hiddenRegions]
  );

  const setRegionHidden = (key: FlowxMacroRegion, hidden: boolean) => {
    setHiddenRegions(prev => {
      const next = new Set(prev);
      if (hidden) next.add(key);
      else next.delete(key);
      // Keep at least one region visible so the page never goes blank.
      if (next.size >= FLOWX_MACRO_REGIONS.length) return prev;
      saveHiddenFlowxRegions(next);
      return next;
    });
  };

  const selectedVisibleCount = useMemo(
    () => addCandidates.filter(c => selectedIso.has(c.iso2.toUpperCase())).length,
    [addCandidates, selectedIso]
  );

  const allVisibleSelected =
    addCandidates.length > 0 && selectedVisibleCount === addCandidates.length;

  const openAddModal = () => {
    setAddError(null);
    setAddQuery('');
    setSelectedIso(new Set());
    setAddOpen(true);
  };

  const closeAddModal = () => {
    if (ensureMutation.isPending) return;
    setAddOpen(false);
    setAddQuery('');
    setSelectedIso(new Set());
    setAddError(null);
  };

  const toggleSelected = (iso2: string) => {
    const key = iso2.toUpperCase();
    setSelectedIso(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleSelectVisible = () => {
    setSelectedIso(prev => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        for (const country of addCandidates) next.delete(country.iso2.toUpperCase());
      } else {
        for (const country of addCandidates) next.add(country.iso2.toUpperCase());
      }
      return next;
    });
  };

  const handleAddSelected = async () => {
    const codes = [...selectedIso];
    if (!codes.length) {
      setAddError('Select at least one country.');
      return;
    }
    setAddError(null);
    const failures: string[] = [];
    for (const iso2 of codes) {
      try {
        await ensureMutation.mutateAsync(iso2);
      } catch (err) {
        failures.push(`${iso2}: ${err instanceof Error ? err.message : 'failed'}`);
      }
    }
    if (failures.length) {
      setAddError(
        failures.length === codes.length
          ? failures.join(' · ')
          : `Added ${codes.length - failures.length}; failed: ${failures.join(' · ')}`
      );
      setSelectedIso(new Set(failures.map(f => f.split(':')[0])));
      return;
    }
    closeAddModal();
  };

  const openJourneys = pendingRemove?.students_in_process ?? 0;
  const removeWithForce = forceRemove || openJourneys > 0;

  const closeRemoveModal = () => {
    if (removeMutation.isPending) return;
    setPendingRemove(null);
    setRemoveError(null);
    setForceRemove(false);
  };

  const handleRemove = async () => {
    if (!pendingRemove) return;
    setRemoveError(null);
    const iso2 = pendingRemove.country_iso2;
    try {
      await removeMutation.mutateAsync({ iso2, force: removeWithForce });
      setPendingRemove(null);
      setForceRemove(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to remove country';
      setRemoveError(message);
      if (/active student journey/i.test(message) || /Remove anyway/i.test(message)) {
        setForceRemove(true);
      }
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-text-main">Country Workflows</h2>
          <p className="text-sm text-text-muted">
            Destinations grouped by global compliance taxonomy. Hide regions for a cleaner view.
          </p>
        </div>
        <button
          type="button"
          onClick={openAddModal}
          className="inline-flex items-center gap-2 rounded-xl border border-accent/40 bg-accent/10 px-3 py-2 text-sm font-semibold text-text-main transition hover:bg-accent/20"
        >
          <Plus size={15} />
          Add countries
        </button>
      </div>

      <div className="flex shrink-0 flex-wrap gap-2">
        {FLOWX_MACRO_REGIONS.map(region => {
          const hidden = hiddenRegions.has(region.key);
          const count = byRegion[region.key]?.length ?? 0;
          return (
            <button
              key={region.key}
              type="button"
              title={hidden ? `Show ${region.label}` : `Hide ${region.label}`}
              onClick={() => setRegionHidden(region.key, !hidden)}
              className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition ${
                hidden
                  ? 'border-dashed border-border-subtle bg-transparent text-text-muted opacity-70'
                  : 'border-border-subtle bg-card text-text-main'
              }`}
            >
              {hidden ? <EyeOff size={14} /> : <Eye size={14} />}
              <span className="tabular-nums text-text-muted">{region.code}</span>
              <span>{region.label}</span>
              <span className="tabular-nums text-text-muted">{count}</span>
            </button>
          );
        })}
      </div>

      {countriesQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading country workflows…</p>
      ) : countriesQuery.isError ? (
        <p className="text-sm text-red-700">Failed to load country workflows.</p>
      ) : visibleColumns.length === 0 ? (
        <p className="text-sm text-text-muted">All regions are hidden. Unhide one above to continue.</p>
      ) : (
        <div className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
          <div className="flex h-full min-h-[28rem] gap-4 pb-1">
            {visibleColumns.map(region => (
              <section
                key={region.key}
                className="flex h-full min-w-[17rem] flex-1 flex-col overflow-hidden rounded-2xl border border-border-subtle bg-surface-bg/60"
              >
                <header className="shrink-0 border-b border-accent bg-accent px-3 py-2.5 text-white">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/80">
                        {region.code}
                      </p>
                      <h3 className="text-xl font-bold leading-snug text-white">{region.label}</h3>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <span className="text-[11px] font-semibold tabular-nums text-white/80">
                        {region.countries.length}
                      </span>
                      <button
                        type="button"
                        title={`Hide ${region.label}`}
                        aria-label={`Hide ${region.label}`}
                        onClick={() => setRegionHidden(region.key, true)}
                        className="rounded-lg p-1.5 text-white/80 transition hover:bg-white/15 hover:text-white"
                      >
                        <EyeOff size={14} />
                      </button>
                    </div>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-white/75">
                    {region.traits}
                  </p>
                  <p className="mt-1.5 text-[10px] leading-snug tabular-nums text-white/75">
                    {region.institution_count} Institutions · {region.college_count} Colleges ·{' '}
                    {region.students_processed} Processed · {region.students_in_process} In Process
                  </p>
                </header>

                <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="p-2">
                  {region.countries.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-border-subtle bg-card px-3 py-5 text-center text-xs text-text-muted">
                      No countries yet — use Add countries
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {region.countries.map(country => (
                        <CountryCard
                          key={country.id}
                          country={country}
                          onRemove={() => {
                            setRemoveError(null);
                            setForceRemove((country.students_in_process ?? 0) > 0);
                            setPendingRemove(country);
                          }}
                          removing={
                            removeMutation.isPending &&
                            pendingRemove?.country_iso2 === country.country_iso2
                          }
                        />
                      ))}
                    </div>
                  )}
                </HeadlessScrollArea>
              </section>
            ))}
          </div>
        </div>
      )}

      {addOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="flowx-add-country-title"
            className="flex max-h-[min(90vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-border-subtle px-4 py-3">
              <div>
                <h3 id="flowx-add-country-title" className="text-base font-bold text-text-main">
                  Add destination countries
                </h3>
                <p className="text-xs text-text-muted">
                  Select one or more countries to create FlowX process templates.
                </p>
              </div>
              <button
                type="button"
                onClick={closeAddModal}
                disabled={ensureMutation.isPending}
                className="rounded-lg p-1.5 text-text-muted hover:bg-surface-bg hover:text-text-main disabled:opacity-50"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2 border-b border-border-subtle px-4 py-3">
              <input
                type="search"
                value={addQuery}
                onChange={e => setAddQuery(e.target.value)}
                placeholder="Search by name, ISO, or region…"
                autoFocus
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-accent/50"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={toggleSelectVisible}
                  disabled={addCandidates.length === 0 || ensureMutation.isPending}
                  className="text-xs font-semibold text-accent hover:underline disabled:opacity-50"
                >
                  {allVisibleSelected ? 'Clear visible' : 'Select all visible'}
                </button>
                <span className="text-[11px] text-text-muted">
                  {selectedIso.size} selected
                  {addQuery.trim() ? ` · ${selectedVisibleCount} in results` : ''}
                </span>
              </div>
              {addError ? <p className="text-xs text-red-700">{addError}</p> : null}
            </div>
            <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="p-2">
              {addCandidates.length === 0 ? (
                <p className="px-3 py-6 text-center text-sm text-text-muted">
                  {addQuery.trim()
                    ? 'No matching countries left to add.'
                    : 'All catalog countries are already on FlowX.'}
                </p>
              ) : (
                <ul className="space-y-1">
                  {addCandidates.map(country => {
                    const region = getFlowxRegionMeta(getFlowxMacroRegion(country.iso2));
                    const checked = selectedIso.has(country.iso2.toUpperCase());
                    return (
                      <li key={country.iso2}>
                        <label
                          className={`flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-accent/10 ${
                            checked ? 'bg-accent/10' : ''
                          } ${ensureMutation.isPending ? 'pointer-events-none opacity-60' : ''}`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSelected(country.iso2)}
                            className="h-4 w-4 shrink-0 rounded border-border-subtle accent-[var(--color-accent,#322f86)]"
                          />
                          <CountryFlag iso2={country.iso2} size="md" className="rounded-md" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-text-main">
                              <span className="mr-1.5 text-[11px] font-medium text-text-muted">
                                {country.iso2}
                              </span>
                              {country.name}
                            </span>
                            <span className="text-[11px] text-text-muted">
                              {region.code} · {region.label}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </HeadlessScrollArea>
            <div className="flex items-center justify-end gap-2 border-t border-border-subtle px-4 py-3">
              <button
                type="button"
                onClick={closeAddModal}
                disabled={ensureMutation.isPending}
                className="rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm font-semibold text-text-muted transition hover:text-text-main disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleAddSelected()}
                disabled={ensureMutation.isPending || selectedIso.size === 0}
                className="inline-flex items-center gap-2 rounded-xl border border-accent/40 bg-accent/10 px-3 py-2 text-sm font-semibold text-text-main transition hover:bg-accent/20 disabled:opacity-50"
              >
                <Plus size={15} />
                {ensureMutation.isPending
                  ? 'Adding…'
                  : `Add ${selectedIso.size || ''} country${selectedIso.size === 1 ? '' : 'ies'}`.trim()}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmationModal
        open={Boolean(pendingRemove)}
        title="Remove country from FlowX?"
        message={
          pendingRemove ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg/80 px-3 py-2.5">
                <CountryFlag iso2={pendingRemove.country_iso2} size="lg" />
                <div className="min-w-0">
                  <p className="truncate font-semibold text-text-main">
                    {pendingRemove.country_name}
                  </p>
                  <p className="text-xs text-text-muted">
                    {pendingRemove.country_iso2} · {pendingRemove.name}
                  </p>
                </div>
              </div>

              <div
                role="alert"
                className="rounded-xl border border-amber-300/80 bg-amber-50 px-3 py-2.5 text-amber-950"
              >
                <p className="text-sm font-semibold">Warning before removal</p>
                <p className="mt-1 text-xs leading-5">
                  This removes the destination from the FlowX country catalog. It does not delete
                  Academia institutions or colleges for this country.
                </p>
              </div>

              {openJourneys > 0 || forceRemove ? (
                <div
                  role="alert"
                  className="rounded-xl border border-red-300/80 bg-red-50 px-3 py-2.5 text-red-950"
                >
                  <p className="text-sm font-semibold">Open student journeys</p>
                  <p className="mt-1 text-xs leading-5">
                    <strong>{openJourneys || pendingRemove.enrollment_count}</strong> active/paused
                    journey(s) will be archived so this country can be removed. Completed journey
                    history is kept.
                  </p>
                </div>
              ) : null}

              {removeError ? (
                <div
                  role="alert"
                  className="rounded-xl border border-red-300/80 bg-red-50 px-3 py-2.5 text-sm text-red-900"
                >
                  {removeError}
                </div>
              ) : null}

              <ul className="list-disc space-y-1.5 pl-5 text-xs leading-5 text-text-muted">
                <li>
                  <strong className="font-semibold text-text-main">
                    {pendingRemove.enrollment_count}
                  </strong>{' '}
                  student journey(s) linked in total ·{' '}
                  <strong className="font-semibold text-text-main">{openJourneys}</strong> in
                  process.
                </li>
                <li>
                  <strong className="font-semibold text-text-main">
                    {pendingRemove.students_processed ?? 0}
                  </strong>{' '}
                  completed / processed student(s) remain in history.
                </li>
                <li>
                  Process template stages and checklist items for this country will leave the active
                  catalog (archived).
                </li>
                <li>You can add the country again later to restore an active workflow.</li>
              </ul>
            </div>
          ) : (
            ''
          )
        }
        confirmLabel={
          removeMutation.isPending
            ? 'Removing…'
            : removeWithForce
              ? 'Remove anyway'
              : 'Remove country'
        }
        variant="danger"
        onConfirm={() => {
          if (!removeMutation.isPending) void handleRemove();
        }}
        onCancel={closeRemoveModal}
      />
    </div>
  );
};

function CountryCard({
  country,
  onRemove,
  removing,
}: {
  country: FlowxCountrySummary;
  onRemove: () => void;
  removing?: boolean;
}) {
  const institutions = country.institution_count ?? 0;
  const colleges = country.college_count ?? 0;
  const processed = country.students_processed ?? 0;
  const inProcess = country.students_in_process ?? 0;

  return (
    <div className="relative rounded-xl border border-border-subtle bg-card transition hover:border-accent/40 hover:bg-accent/5">
      <Link to={`/flowx/countries/${country.country_iso2}`} className="block p-3.5 pr-10">
        <div className="flex items-start justify-between gap-2">
          <div className="inline-flex min-w-0 items-center gap-2.5">
            <CountryFlag iso2={country.country_iso2} size="md" className="rounded-md" />
            <div className="min-w-0">
              <p className="truncate text-base font-bold text-text-main">
                <span className="mr-1.5 text-xs font-semibold text-text-muted">
                  {country.country_iso2}
                </span>
                {country.country_name}
              </p>
              <p className="truncate text-xs text-text-muted">{country.name}</p>
            </div>
          </div>
          <Globe2 size={15} className="mt-0.5 shrink-0 text-text-muted" />
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-muted">
          <span>{country.stage_count} stages</span>
          <span>{country.template_task_count} items</span>
          <span className="inline-flex items-center gap-1">
            <Users size={12} />
            {country.enrollment_count} enrolled
          </span>
        </div>
        <p className="mt-1.5 text-xs leading-snug tabular-nums text-text-muted">
          {institutions} Institutions · {colleges} Colleges · {processed} Processed · {inProcess}{' '}
          In Process
        </p>
      </Link>
      <button
        type="button"
        title="Remove country"
        aria-label={`Remove ${country.country_name}`}
        disabled={removing}
        onClick={e => {
          e.preventDefault();
          e.stopPropagation();
          onRemove();
        }}
        className="absolute right-2 top-2 rounded-lg p-1.5 text-text-muted transition hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

export default FlowxCountriesPage;
