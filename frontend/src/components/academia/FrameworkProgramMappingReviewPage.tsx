import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckSquare, Loader2, Square } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import type { EducationMajorRecord } from '../../types/educationMajor';
import type { EducationSubMajorRecord } from '../../types/educationSubMajor';
import SearchableSelect from './SearchableSelect';

export interface ProgramMappingSuggestion {
  institution_id: number;
  institution_name: string;
  program_id: number | null;
  program_title: string;
  suggested_major: string;
  suggested_sub_major: string;
  category: string;
  status: string;
  education_major_id: number | null;
  education_sub_major_id: number | null;
  current_education_major_id?: number | null;
  current_education_sub_major_id?: number | null;
  current_major_label?: string | null;
  current_sub_major_label?: string | null;
  already_mapped?: boolean;
  applicable: boolean;
  apply_note: string | null;
}

interface ProgramMappingSuggestionsResponse {
  generated_at: string | null;
  revised_at: string | null;
  total: number;
  unmapped_count: number;
  ambiguous_count: number;
  applicable_count: number;
  already_mapped_count?: number;
  items: ProgramMappingSuggestion[];
}

interface BulkApplyResponse {
  applied: number;
  skipped: number;
  skipped_existing?: number;
  skipped_duplicate_in_request?: number;
  errors: Array<{ program_id: number; detail: string }>;
}

interface RowOverride {
  education_major_id: number | null;
  education_sub_major_id: number | null;
}

export interface FrameworkProgramMappingReviewConfig {
  title: string;
  description: string;
  embeddedDescription: string;
  suggestionsEndpoint: string;
  bulkApplyScope: { nz_scope_only?: boolean; ca_scope_only?: boolean };
  loadingLabel: string;
  loadErrorLabel: string;
}

const formatBulkApplyResult = (
  response: BulkApplyResponse,
  sentCount: number
): string => {
  const parts: string[] = [];
  parts.push(`Sent ${sentCount} row(s).`);
  if (response.applied > 0) {
    parts.push(`Saved ${response.applied} mapping(s).`);
    parts.push('They leave this queue and appear under Framework → Degrees (Majors / Sub-majors).');
  } else {
    parts.push('No mappings were changed in the database.');
  }
  const skippedExisting = response.skipped_existing ?? response.skipped;
  const skippedDupes = response.skipped_duplicate_in_request ?? 0;
  const errorCount = response.errors?.length ?? 0;

  if (skippedExisting > 0) {
    parts.push(`${skippedExisting} already had this exact mapping.`);
  }
  if (skippedDupes > 0) {
    parts.push(`${skippedDupes} duplicate row(s) in the request were ignored.`);
  }
  if (errorCount > 0) {
    parts.push(`${errorCount} row(s) failed validation.`);
  }
  return parts.join(' ');
};

const rowKey = (item: ProgramMappingSuggestion): string =>
  `${item.program_id ?? 'missing'}-${item.program_title}-${item.institution_id}`;

const idsEqual = (a: RowOverride, b: RowOverride): boolean =>
  a.education_major_id === b.education_major_id &&
  a.education_sub_major_id === b.education_sub_major_id;

const FrameworkProgramMappingReviewPage: React.FC<{
  config: FrameworkProgramMappingReviewConfig;
  embedded?: boolean;
}> = ({ config, embedded = false }) => {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [meta, setMeta] = useState<Omit<ProgramMappingSuggestionsResponse, 'items'> | null>(null);
  const [items, setItems] = useState<ProgramMappingSuggestion[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<Record<string, RowOverride>>({});
  const [institutionFilter, setInstitutionFilter] = useState('');
  const [showInapplicable, setShowInapplicable] = useState(false);
  const [catalogMajors, setCatalogMajors] = useState<EducationMajorRecord[]>([]);
  const [catalogSubMajors, setCatalogSubMajors] = useState<EducationSubMajorRecord[]>([]);

  const loadCatalog = useCallback(async () => {
    try {
      const [majors, subMajors] = await Promise.all([
        fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
          catalog_only: 'true',
          active_only: 'true',
          sort_by: 'name',
          sort_dir: 'asc',
        }),
        fetchAcademiaListItems<EducationSubMajorRecord>('academia/education-sub-majors', {
          sort_by: 'name',
          sort_dir: 'asc',
        }),
      ]);
      setCatalogMajors(majors);
      setCatalogSubMajors(subMajors);
    } catch {
      setCatalogMajors([]);
      setCatalogSubMajors([]);
    }
  }, []);

  const loadSuggestions = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = Boolean(opts?.silent);
    if (!silent) {
      setLoading(true);
      setError(null);
      setResultMessage(null);
    }
    try {
      const [data] = await Promise.all([
        apiFetch<ProgramMappingSuggestionsResponse>(config.suggestionsEndpoint),
        loadCatalog(),
      ]);
      setMeta({
        generated_at: data.generated_at,
        revised_at: data.revised_at,
        total: data.total,
        unmapped_count: data.unmapped_count,
        ambiguous_count: data.ambiguous_count,
        applicable_count: data.applicable_count,
        already_mapped_count: data.already_mapped_count ?? 0,
      });
      setItems(Array.isArray(data.items) ? data.items : []);
      setSelected(new Set());
      setOverrides({});
    } catch (err) {
      setError(err instanceof Error ? err.message : config.loadErrorLabel);
      if (!silent) {
        setItems([]);
        setMeta(null);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [config.loadErrorLabel, config.suggestionsEndpoint, loadCatalog]);

  useEffect(() => {
    void loadSuggestions();
  }, [loadSuggestions]);

  const majorOptions = useMemo(
    () =>
      catalogMajors
        .filter(major => major.program_id == null)
        .map(major => ({
          value: String(major.id),
          label: major.label,
          color: major.color,
        })),
    [catalogMajors]
  );

  const institutionOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const item of items) {
      if (!showInapplicable && !item.applicable) continue;
      seen.set(item.institution_id, item.institution_name);
    }
    return [...seen.entries()]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([id, name]) => ({ value: String(id), label: name }));
  }, [items, showInapplicable]);

  const getBaselineIds = useCallback((item: ProgramMappingSuggestion): RowOverride => {
    return {
      education_major_id: item.education_major_id,
      education_sub_major_id: item.education_sub_major_id,
    };
  }, []);

  const getEffectiveIds = useCallback(
    (item: ProgramMappingSuggestion): RowOverride => {
      const key = rowKey(item);
      const override = overrides[key];
      if (override) return override;
      return getBaselineIds(item);
    },
    [getBaselineIds, overrides]
  );

  const isRowDirty = useCallback(
    (item: ProgramMappingSuggestion): boolean => {
      const key = rowKey(item);
      const override = overrides[key];
      if (!override) return false;
      return !idsEqual(override, getBaselineIds(item));
    },
    [getBaselineIds, overrides]
  );

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      if (institutionFilter && String(item.institution_id) !== institutionFilter) {
        return false;
      }
      if (!showInapplicable && !item.applicable) {
        return false;
      }
      return true;
    });
  }, [institutionFilter, items, showInapplicable]);

  const canSelectItem = useCallback(
    (item: ProgramMappingSuggestion): boolean => {
      if (!item.program_id) return false;
      const ids = getEffectiveIds(item);
      return Boolean(ids.education_major_id);
    },
    [getEffectiveIds]
  );

  const selectableItems = useMemo(
    () => filteredItems.filter(item => canSelectItem(item)),
    [canSelectItem, filteredItems]
  );

  const dirtyItems = useMemo(
    () => items.filter(item => Boolean(item.program_id) && isRowDirty(item) && canSelectItem(item)),
    [canSelectItem, isRowDirty, items]
  );

  const applyReadyCount = useMemo(() => {
    const keys = new Set<string>();
    for (const item of items) {
      const key = rowKey(item);
      if (!canSelectItem(item)) continue;
      if (selected.has(key) || isRowDirty(item)) keys.add(key);
    }
    return keys.size;
  }, [canSelectItem, isRowDirty, items, selected]);

  const allSelectableChecked =
    selectableItems.length > 0 && selectableItems.every(item => selected.has(rowKey(item)));

  const setRowOverride = (item: ProgramMappingSuggestion, next: RowOverride) => {
    const key = rowKey(item);
    setOverrides(prev => ({ ...prev, [key]: next }));
    if (!next.education_major_id || !item.program_id) {
      setSelected(prev => {
        if (!prev.has(key)) return prev;
        const copy = new Set(prev);
        copy.delete(key);
        return copy;
      });
    } else {
      setSelected(prev => {
        if (prev.has(key)) return prev;
        const copy = new Set(prev);
        copy.add(key);
        return copy;
      });
    }
  };

  const toggleRow = (item: ProgramMappingSuggestion) => {
    if (!canSelectItem(item)) return;
    const key = rowKey(item);
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allSelectableChecked) {
      setSelected(prev => {
        const next = new Set(prev);
        for (const item of selectableItems) next.delete(rowKey(item));
        return next;
      });
      return;
    }
    setSelected(prev => {
      const next = new Set(prev);
      for (const item of selectableItems) next.add(rowKey(item));
      return next;
    });
  };

  const handleSubmit = async () => {
    const payloadItems: Array<{
      program_id: number;
      education_major_id: number;
      education_sub_major_id: number | null;
    }> = [];
    const seenPrograms = new Set<number>();

    for (const item of items) {
      if (!item.program_id || !canSelectItem(item)) continue;
      const key = rowKey(item);
      const include = selected.has(key) || isRowDirty(item);
      if (!include) continue;
      if (seenPrograms.has(item.program_id)) continue;
      seenPrograms.add(item.program_id);
      const ids = getEffectiveIds(item);
      if (!ids.education_major_id) continue;
      payloadItems.push({
        program_id: item.program_id,
        education_major_id: ids.education_major_id,
        education_sub_major_id: ids.education_sub_major_id,
      });
    }

    if (payloadItems.length === 0) {
      setResultMessage(null);
      setError(
        'Nothing to apply. Change a major/sub-major dropdown, or check at least one row.'
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    setResultMessage(null);
    try {
      const response = await apiFetch<BulkApplyResponse>('academia/program-mappings/bulk-apply', {
        method: 'POST',
        body: JSON.stringify({
          items: payloadItems,
          ...config.bulkApplyScope,
        }),
      });
      const errorCount = response.errors?.length ?? 0;
      const summary = formatBulkApplyResult(response, payloadItems.length);
      setResultMessage(summary);
      if (errorCount) {
        setError(
          response.errors.map(row => `Program ${row.program_id}: ${row.detail}`).join('\n')
        );
      } else if (
        response.applied === 0 &&
        (response.skipped_existing ?? response.skipped) === 0 &&
        (response.skipped_duplicate_in_request ?? 0) === 0
      ) {
        setError(
          'API returned applied=0 with no skips. Check that major and sub-major belong together.'
        );
      }
      await loadSuggestions({ silent: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to apply mappings';
      setResultMessage(null);
      setError(`Apply failed: ${message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-muted">
        <Loader2 size={16} className="animate-spin" />
        {config.loadingLabel}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {!embedded ? (
        <div>
          <h2 className="text-xl font-bold text-text-main">{config.title}</h2>
          <p className="text-sm text-text-muted">{config.description}</p>
        </div>
      ) : (
        <p className="text-sm text-text-muted">{config.embeddedDescription}</p>
      )}

      {meta ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-text-muted">
              Suggestions generated{' '}
              {meta.generated_at
                ? new Date(meta.generated_at).toLocaleString()
                : 'unknown'}
              {meta.revised_at && meta.revised_at !== meta.generated_at
                ? ` · revised ${new Date(meta.revised_at).toLocaleString()}`
                : null}
              {(meta.already_mapped_count ?? 0) > 0
                ? ` · ${meta.already_mapped_count} already mapped (excluded)`
                : null}
            </div>
            <button
              type="button"
              onClick={() => void loadSuggestions()}
              disabled={loading || submitting}
              className="rounded-lg border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-main hover:bg-surface-bg disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-text-muted">Queue size</div>
              <div className="text-2xl font-bold text-text-main">{meta.total}</div>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-text-muted">Still unmapped</div>
              <div className="text-2xl font-bold text-text-main">{meta.unmapped_count}</div>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-text-muted">Ambiguous</div>
              <div className="text-2xl font-bold text-text-main">{meta.ambiguous_count}</div>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-text-muted">Applicable now</div>
              <div className="text-2xl font-bold text-text-main">{meta.applicable_count}</div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-[240px]">
          <SearchableSelect
            label="Institution"
            value={institutionFilter}
            options={[
              { value: '', label: 'All institutions' },
              ...institutionOptions,
            ]}
            onChange={setInstitutionFilter}
            placeholder="All institutions"
          />
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm text-text-main">
          <input
            type="checkbox"
            checked={showInapplicable}
            onChange={event => setShowInapplicable(event.target.checked)}
            className="rounded border-border-subtle"
          />
          Show inapplicable / ambiguous rows
        </label>
      </div>

      {resultMessage ? (
        <div
          role="status"
          className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-text-main"
        >
          {resultMessage}
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="whitespace-pre-wrap rounded-xl border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert"
        >
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-2xl border border-border-subtle">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
            <tr>
              <th className="px-4 py-3 font-semibold">
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  className="inline-flex items-center gap-2 text-text-muted hover:text-text-main"
                  title={allSelectableChecked ? 'Clear selection' : 'Select all editable rows'}
                >
                  {allSelectableChecked ? <CheckSquare size={16} /> : <Square size={16} />}
                  Select
                </button>
              </th>
              <th className="px-4 py-3 font-semibold">Program</th>
              <th className="px-4 py-3 font-semibold">Institution</th>
              <th className="min-w-[14rem] px-4 py-3 font-semibold">Major</th>
              <th className="min-w-[14rem] px-4 py-3 font-semibold">Sub-major</th>
              <th className="px-4 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.map(item => {
              const key = rowKey(item);
              const ids = getEffectiveIds(item);
              const canSelect = canSelectItem(item);
              const checked = selected.has(key);
              const dirty = isRowDirty(item);
              const subOptions = catalogSubMajors
                .filter(sub => !ids.education_major_id || sub.major_id === ids.education_major_id)
                .map(sub => ({
                  value: String(sub.id),
                  label: sub.name,
                }));
              return (
                <tr
                  key={key}
                  className={`border-t border-border-subtle/70 ${
                    dirty
                      ? 'bg-amber-500/5'
                      : !item.applicable
                        ? 'bg-surface-bg/60 text-text-muted'
                        : ''
                  }`}
                >
                  <td className="px-4 py-3 align-top">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!canSelect}
                      onChange={() => toggleRow(item)}
                      className="rounded border-border-subtle disabled:opacity-40"
                      title={
                        canSelect
                          ? dirty
                            ? 'Edited — Apply will save this row even if unchecked'
                            : 'Apply this mapping on submit'
                          : item.apply_note || 'Not eligible for bulk apply'
                      }
                    />
                    {dirty ? (
                      <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                        Edited
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="font-semibold text-text-main">{item.program_title}</div>
                    <div className="text-xs text-text-muted">
                      {item.program_id ? `ID ${item.program_id}` : 'Program ID missing'}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">{item.institution_name}</td>
                  <td className="px-4 py-3 align-top">
                    <SearchableSelect
                      value={ids.education_major_id ? String(ids.education_major_id) : ''}
                      options={[{ value: '', label: 'Select major' }, ...majorOptions]}
                      onChange={value => {
                        const majorId = value ? Number(value) : null;
                        const currentSub = ids.education_sub_major_id;
                        const subStillValid =
                          currentSub != null &&
                          catalogSubMajors.some(
                            sub => sub.id === currentSub && sub.major_id === majorId
                          );
                        setRowOverride(item, {
                          education_major_id: majorId,
                          education_sub_major_id: subStillValid ? currentSub : null,
                        });
                      }}
                      placeholder="Select major"
                      disabled={!item.program_id}
                    />
                  </td>
                  <td className="px-4 py-3 align-top">
                    <SearchableSelect
                      value={
                        ids.education_sub_major_id ? String(ids.education_sub_major_id) : ''
                      }
                      options={[
                        { value: '', label: 'Major only / none' },
                        ...subOptions,
                      ]}
                      onChange={value => {
                        const subId = value ? Number(value) : null;
                        let majorId = ids.education_major_id;
                        if (subId != null) {
                          const sub = catalogSubMajors.find(entry => entry.id === subId);
                          if (sub) majorId = sub.major_id;
                        }
                        setRowOverride(item, {
                          education_major_id: majorId,
                          education_sub_major_id: subId,
                        });
                      }}
                      placeholder="Select sub-major"
                      disabled={!item.program_id || !ids.education_major_id}
                    />
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="inline-flex items-center gap-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                          item.applicable
                            ? 'bg-sky-500/15 text-sky-700 dark:text-sky-300'
                            : 'bg-surface-bg text-text-muted'
                        }`}
                      >
                        {item.status || (item.applicable ? 'ready' : 'blocked')}
                      </span>
                    </div>
                    {item.apply_note ? (
                      <div className="mt-1 text-xs text-text-muted">{item.apply_note}</div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filteredItems.length === 0 ? (
        <p className="text-sm text-text-muted">
          No rows match the current filters.
          {(meta?.already_mapped_count ?? 0) > 0
            ? ` ${meta?.already_mapped_count} already-mapped program(s) were excluded from this queue.`
            : null}
        </p>
      ) : null}

      <div className="sticky bottom-0 z-20 flex flex-col gap-2 rounded-2xl border border-border-subtle bg-card px-4 py-3 shadow-lg">
        {(resultMessage || error) && (
          <div className="text-sm">
            {resultMessage ? (
              <div role="status" className="text-emerald-700 dark:text-emerald-300">
                {resultMessage}
              </div>
            ) : null}
            {error ? (
              <div role="alert" className="whitespace-pre-wrap text-alert">
                {error}
              </div>
            ) : null}
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-text-muted">
            {selected.size} selected · {dirtyItems.length} edited · {selectableItems.length}{' '}
            editable in view
            <span className="ml-1 text-xs opacity-80">
              (Apply saves edited dropdowns and/or checked rows)
            </span>
          </div>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || applyReadyCount === 0}
            title={
              applyReadyCount === 0
                ? 'Change a major/sub-major dropdown, or check at least one row'
                : `Apply ${applyReadyCount} mapping(s)`
            }
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
            Apply mappings
            {applyReadyCount > 0 ? ` (${applyReadyCount})` : ''}
          </button>
        </div>
      </div>
    </div>
  );
};

export default FrameworkProgramMappingReviewPage;
