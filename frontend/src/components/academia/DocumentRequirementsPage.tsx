import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, FileText, Loader2, Pencil, Plus, Trash2, Upload, X } from 'lucide-react';

import SearchableMultiSelect from './SearchableMultiSelect';
import { useConfirmation } from '../../context/ConfirmationContext';
import { useCountries } from '../../hooks/useCountries';
import { useAcademiaLevels } from '../../hooks/useLevels';
import {
  mergeLevelOptions,
  resolveProgramLevels,
  type DocumentRequirementPayload,
  type DocumentRequirementRecord,
  type DocumentTemplateDownloadResponse,
} from '../../types/documentRequirement';
import { apiFetch, apiFetchBlobDownload, apiUpload } from '../../utils/api';

const DEFAULT_ACCEPTED_FORMAT = 'PDF, JPEG, or PNG';
const DEFAULT_PROGRAM_LEVEL = 'Undergraduate';

const emptyForm = (): DocumentRequirementPayload & { file: File | null } => ({
  document_name: '',
  description: '',
  accepted_format: DEFAULT_ACCEPTED_FORMAT,
  program_levels: [DEFAULT_PROGRAM_LEVEL],
  is_mandatory: true,
  is_global: false,
  country_ids: [],
  file: null,
});

const DocumentRequirementsPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const { countries } = useCountries();
  const { levels: catalogLevels } = useAcademiaLevels();
  const [items, setItems] = useState<DocumentRequirementRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [filterLevel, setFilterLevel] = useState('');
  const [filterCountryIds, setFilterCountryIds] = useState<string[]>([]);
  const [filterGlobal, setFilterGlobal] = useState<'all' | 'global' | 'specific'>('all');
  const [appliedLevel, setAppliedLevel] = useState('');
  const [appliedCountryIds, setAppliedCountryIds] = useState<string[]>([]);
  const [appliedGlobal, setAppliedGlobal] = useState<'all' | 'global' | 'specific'>('all');

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<DocumentRequirementRecord | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);

  const [checklistOpen, setChecklistOpen] = useState(false);
  const [checklistScope, setChecklistScope] = useState<'global' | 'country_specific'>('global');
  const [checklistCountryId, setChecklistCountryId] = useState('');
  const [checklistLevel, setChecklistLevel] = useState('');
  const [checklistLevelsWithDocs, setChecklistLevelsWithDocs] = useState<string[]>([]);
  const [checklistLevelsLoading, setChecklistLevelsLoading] = useState(false);
  const [checklistGenerating, setChecklistGenerating] = useState(false);
  const [checklistError, setChecklistError] = useState<string | null>(null);
  const [checklistCountrySpecificAvailable, setChecklistCountrySpecificAvailable] =
    useState(false);
  const [checklistMappedCountries, setChecklistMappedCountries] = useState<
    { id: number; name: string }[]
  >([]);
  const [checklistScopeLoading, setChecklistScopeLoading] = useState(false);

  const catalogLevelNames = useMemo(
    () => catalogLevels.map(level => level.name).filter(Boolean),
    [catalogLevels]
  );

  const levelsWithDocsSet = useMemo(
    () => new Set(checklistLevelsWithDocs.map(name => name.trim()).filter(Boolean)),
    [checklistLevelsWithDocs]
  );

  const countryOptions = useMemo(
    () =>
      countries.map(country => ({
        value: String(country.id),
        label: country.name,
      })),
    [countries]
  );

  const filterLevelOptions = useMemo(
    () => mergeLevelOptions(catalogLevelNames),
    [catalogLevelNames]
  );

  const levelOptions = useMemo(
    () => mergeLevelOptions(catalogLevelNames, form.program_levels),
    [catalogLevelNames, form.program_levels]
  );

  const loadRequirements = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('page', '1');
      params.set('page_size', '100');
      if (appliedLevel) params.set('program_level', appliedLevel);
      if (appliedGlobal === 'global') params.set('is_global', 'true');
      if (appliedGlobal === 'specific') params.set('is_global', 'false');
      appliedCountryIds.forEach(id => params.append('country_id', id));
      const data = await apiFetch<{ items: DocumentRequirementRecord[] }>(
        `document-requirements?${params.toString()}`
      );
      const rows = Array.isArray(data.items) ? data.items : [];
      rows.sort((a, b) => {
        const aTime = a.created_at ? Date.parse(a.created_at) : Number.NaN;
        const bTime = b.created_at ? Date.parse(b.created_at) : Number.NaN;
        if (Number.isFinite(aTime) && Number.isFinite(bTime) && aTime !== bTime) {
          return aTime - bTime;
        }
        return (a.id ?? 0) - (b.id ?? 0);
      });
      setItems(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load document requirements');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [appliedCountryIds, appliedGlobal, appliedLevel]);

  useEffect(() => {
    void loadRequirements();
  }, [loadRequirements]);

  const applyFilters = () => {
    setAppliedLevel(filterLevel);
    setAppliedCountryIds(filterCountryIds);
    setAppliedGlobal(filterGlobal);
  };

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
    setDrawerOpen(true);
  };

  const checklistCountryOptions = useMemo(
    () =>
      checklistMappedCountries.map(country => ({
        value: String(country.id),
        label: country.name,
      })),
    [checklistMappedCountries]
  );

  const loadChecklistLevels = useCallback(
    async (scope: 'global' | 'country_specific', countryId: string) => {
      if (scope === 'country_specific' && !countryId) {
        setChecklistLevelsWithDocs([]);
        setChecklistLevel('');
        setChecklistLevelsLoading(false);
        setChecklistError(null);
        return;
      }
      setChecklistLevelsLoading(true);
      setChecklistError(null);
      try {
        const params = new URLSearchParams();
        params.set('scope', scope);
        if (scope === 'country_specific' && countryId) {
          params.set('country_id', countryId);
        }
        const data = await apiFetch<{ program_levels: string[] }>(
          `document-requirements/checklist-levels?${params.toString()}`
        );
        const levels = Array.isArray(data.program_levels) ? data.program_levels : [];
        setChecklistLevelsWithDocs(levels);
        setChecklistLevel(prev => {
          if (prev && levels.includes(prev)) return prev;
          return catalogLevelNames.find(name => levels.includes(name)) || '';
        });
      } catch (err) {
        setChecklistLevelsWithDocs([]);
        setChecklistLevel('');
        setChecklistError(
          err instanceof Error ? err.message : 'Failed to load levels with documents'
        );
      } finally {
        setChecklistLevelsLoading(false);
      }
    },
    [catalogLevelNames]
  );

  const loadChecklistScope = useCallback(async () => {
    setChecklistScopeLoading(true);
    try {
      const data = await apiFetch<{
        country_specific_available: boolean;
        countries: { id: number; name: string }[];
      }>('document-requirements/checklist-scope');
      const mapped = Array.isArray(data.countries) ? data.countries : [];
      setChecklistCountrySpecificAvailable(Boolean(data.country_specific_available));
      setChecklistMappedCountries(mapped);
      return {
        available: Boolean(data.country_specific_available),
        countries: mapped,
      };
    } catch (err) {
      setChecklistCountrySpecificAvailable(false);
      setChecklistMappedCountries([]);
      setChecklistError(
        err instanceof Error ? err.message : 'Failed to load checklist scope options'
      );
      return { available: false, countries: [] as { id: number; name: string }[] };
    } finally {
      setChecklistScopeLoading(false);
    }
  }, []);

  const openChecklist = () => {
    setChecklistOpen(true);
    setChecklistScope('global');
    setChecklistCountryId('');
    setChecklistLevel('');
    setChecklistError(null);
    setChecklistCountrySpecificAvailable(false);
    setChecklistMappedCountries([]);
    void loadChecklistScope();
    void loadChecklistLevels('global', '');
  };

  const closeChecklist = () => {
    if (checklistGenerating) return;
    setChecklistOpen(false);
    setChecklistScope('global');
    setChecklistCountryId('');
    setChecklistLevel('');
    setChecklistError(null);
    setChecklistCountrySpecificAvailable(false);
    setChecklistMappedCountries([]);
  };

  const handleChecklistScopeChange = (nextScope: 'global' | 'country_specific') => {
    if (nextScope === 'country_specific' && !checklistCountrySpecificAvailable) return;
    setChecklistScope(nextScope);
    if (nextScope === 'global') {
      setChecklistCountryId('');
      void loadChecklistLevels('global', '');
      return;
    }
    void loadChecklistLevels('country_specific', checklistCountryId);
  };

  const handleChecklistCountryChange = (nextCountryId: string) => {
    setChecklistCountryId(nextCountryId);
    void loadChecklistLevels('country_specific', nextCountryId);
  };

  const handleCreateChecklistPdf = async () => {
    if (!checklistLevel || !levelsWithDocsSet.has(checklistLevel)) return;
    if (checklistScope === 'country_specific' && !checklistCountryId) return;
    if (checklistScope === 'country_specific' && !checklistCountrySpecificAvailable) return;
    setChecklistGenerating(true);
    setChecklistError(null);
    try {
      const body: {
        program_level: string;
        scope: 'global' | 'country_specific';
        country_id?: number;
      } = {
        program_level: checklistLevel,
        scope: checklistScope,
      };
      if (checklistScope === 'country_specific') {
        body.country_id = Number(checklistCountryId);
      }
      const { blob, filename } = await apiFetchBlobDownload('document-requirements/checklists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const sanitizeSegment = (value: string) =>
        value
          .trim()
          .replace(/ /g, '_')
          .replace(/[/\\]/g, '')
          .replace(/\.\./g, '')
          .replace(/[^A-Za-z0-9._\-]+/g, '')
          .replace(/_+/g, '_')
          .replace(/^[._]+|[._]+$/g, '');
      const levelSegment = sanitizeSegment(checklistLevel) || 'Level';
      const countryName =
        checklistMappedCountries.find(country => String(country.id) === checklistCountryId)
          ?.name || '';
      const countrySegment =
        checklistScope === 'country_specific' ? sanitizeSegment(countryName) : '';
      const fallbackName = countrySegment
        ? `DOCUMENT_CHECKLIST_${levelSegment}_${countrySegment}.pdf`
        : `DOCUMENT_CHECKLIST_${levelSegment}.pdf`;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename || fallbackName;
      anchor.click();
      URL.revokeObjectURL(url);
      setChecklistOpen(false);
      setChecklistScope('global');
      setChecklistCountryId('');
      setChecklistLevel('');
      setChecklistCountrySpecificAvailable(false);
      setChecklistMappedCountries([]);
    } catch (err) {
      setChecklistError(
        err instanceof Error ? err.message : 'Failed to create document checklist PDF'
      );
    } finally {
      setChecklistGenerating(false);
    }
  };

  const openEdit = (row: DocumentRequirementRecord) => {
    const levels = resolveProgramLevels(row);
    setEditing(row);
    setForm({
      document_name: row.document_name,
      description: row.description || '',
      accepted_format: row.accepted_format?.trim() || DEFAULT_ACCEPTED_FORMAT,
      program_levels: levels.length > 0 ? levels : [DEFAULT_PROGRAM_LEVEL],
      is_mandatory: row.is_mandatory,
      is_global: row.is_global,
      country_ids: (row.countries || []).map(c => c.id),
      file: null,
    });
    setFormError(null);
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    if (saving) return;
    setDrawerOpen(false);
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
  };

  const handleSave = async () => {
    setFormError(null);
    if (!form.document_name.trim()) {
      setFormError('Document name is required.');
      return;
    }
    if (form.program_levels.length === 0) {
      setFormError('Select at least one program level.');
      return;
    }
    if (!form.is_global && form.country_ids.length === 0) {
      setFormError('Select at least one country, or enable Apply Globally.');
      return;
    }

    const payload: DocumentRequirementPayload = {
      document_name: form.document_name.trim(),
      description: form.description?.trim() || null,
      accepted_format: form.accepted_format?.trim() || null,
      program_levels: form.program_levels,
      is_mandatory: form.is_mandatory,
      is_global: form.is_global,
      country_ids: form.is_global ? [] : form.country_ids,
    };

    setSaving(true);
    try {
      let saved: DocumentRequirementRecord;
      if (editing) {
        saved = await apiFetch<DocumentRequirementRecord>(
          `document-requirements/${editing.id}`,
          { method: 'PUT', body: JSON.stringify(payload) }
        );
      } else {
        saved = await apiFetch<DocumentRequirementRecord>('document-requirements', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }

      if (form.file) {
        const body = new FormData();
        body.append('file', form.file);
        saved = await apiUpload(`document-requirements/${saved.id}/template`, body);
      }

      setDrawerOpen(false);
      setEditing(null);
      setForm(emptyForm());
      void loadRequirements();
      void saved;
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save requirement');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (row: DocumentRequirementRecord) => {
    if (
      !(await openConfirm({
        title: 'Delete document requirement?',
        message: `Delete "${row.document_name}"? Linked country mappings will be removed.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }
    try {
      await apiFetch(`document-requirements/${row.id}`, { method: 'DELETE' });
      void loadRequirements();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete requirement');
    }
  };

  const handleDownload = async (row: DocumentRequirementRecord) => {
    try {
      const data = await apiFetch<DocumentTemplateDownloadResponse>(
        `document-requirements/${row.id}/template`
      );
      const url = data.download_url || data.file_url;
      if (!url) throw new Error('No download URL available');
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to open template');
    }
  };

  const checklistModal =
    checklistOpen && typeof document !== 'undefined'
      ? createPortal(
          <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4">
            <button
              type="button"
              className="absolute inset-0 cursor-default"
              aria-label="Close checklist dialog"
              onClick={closeChecklist}
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="checklist-dialog-title"
              className="relative z-10 w-full max-w-md rounded-2xl border border-border-subtle bg-card p-5 shadow-2xl"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3
                    id="checklist-dialog-title"
                    className="text-lg font-semibold text-text-main"
                  >
                    Create document checklist
                  </h3>
                  <p className="mt-1 text-xs text-text-muted">
                    Choose a scope and program level that has assigned documents, then create a
                    PDF.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeChecklist}
                  disabled={checklistGenerating}
                  className="rounded-lg p-2 text-text-muted hover:bg-black/5 disabled:opacity-50"
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="mt-4 space-y-4">
                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-text-main">Scope</span>
                  <select
                    value={checklistScope}
                    onChange={event =>
                      handleChecklistScopeChange(
                        event.target.value as 'global' | 'country_specific'
                      )
                    }
                    disabled={
                      checklistGenerating || checklistLevelsLoading || checklistScopeLoading
                    }
                    className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60"
                  >
                    <option value="global">Global</option>
                    <option
                      value="country_specific"
                      disabled={!checklistCountrySpecificAvailable}
                    >
                      {checklistCountrySpecificAvailable
                        ? 'Country-Specific'
                        : 'Country-Specific — No country-specific documents'}
                    </option>
                  </select>
                  {!checklistScopeLoading && !checklistCountrySpecificAvailable ? (
                    <span className="block text-xs text-text-muted">
                      No country-specific documents
                    </span>
                  ) : null}
                </label>

                {checklistScope === 'country_specific' && checklistCountrySpecificAvailable ? (
                  <label className="block space-y-1 text-sm">
                    <span className="font-medium text-text-main">Country</span>
                    <select
                      value={checklistCountryId}
                      onChange={event => handleChecklistCountryChange(event.target.value)}
                      disabled={checklistGenerating || checklistLevelsLoading}
                      className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60"
                    >
                      <option value="">Select a country...</option>
                      {checklistCountryOptions.map(option => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                <div className="space-y-2">
                  <span className="block text-sm font-medium text-text-main">Level</span>
                  {checklistLevelsLoading || checklistScopeLoading ? (
                    <div className="flex items-center gap-2 py-4 text-sm text-text-muted">
                      <Loader2 size={14} className="animate-spin" />
                      Loading levels...
                    </div>
                  ) : catalogLevelNames.length === 0 ? (
                    <p className="py-2 text-sm text-text-muted">No catalog levels available.</p>
                  ) : checklistScope === 'country_specific' && !checklistCountryId ? (
                    <p className="py-2 text-sm text-text-muted">
                      Select a country to see available levels.
                    </p>
                  ) : (
                    <fieldset className="space-y-2">
                      <legend className="sr-only">Program level</legend>
                      {catalogLevelNames.map(name => {
                        const enabled = levelsWithDocsSet.has(name);
                        return (
                          <label
                            key={name}
                            className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
                              enabled
                                ? 'border-border-subtle bg-surface-bg text-text-main'
                                : 'cursor-not-allowed border-border-subtle/60 bg-black/[0.03] text-text-muted opacity-60'
                            }`}
                          >
                            <input
                              type="radio"
                              name="checklist-program-level"
                              value={name}
                              checked={checklistLevel === name}
                              disabled={!enabled || checklistGenerating}
                              onChange={() => setChecklistLevel(name)}
                              className="accent-accent"
                            />
                            <span className="flex-1">{name}</span>
                            {!enabled ? (
                              <span className="text-[11px] text-text-muted">No documents</span>
                            ) : null}
                          </label>
                        );
                      })}
                    </fieldset>
                  )}
                </div>
              </div>

              {checklistError ? (
                <p className="mt-3 text-sm text-alert">{checklistError}</p>
              ) : null}

              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={closeChecklist}
                  disabled={checklistGenerating}
                  className="rounded-xl border border-border-subtle px-4 py-2 text-sm text-text-main hover:bg-black/5 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreateChecklistPdf()}
                  disabled={
                    checklistGenerating ||
                    checklistLevelsLoading ||
                    !checklistLevel ||
                    !levelsWithDocsSet.has(checklistLevel) ||
                    (checklistScope === 'country_specific' && !checklistCountryId)
                  }
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
                >
                  {checklistGenerating ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <FileText size={14} />
                  )}
                  Create PDF
                </button>
              </div>
            </div>
          </div>,
          document.body
        )
      : null;

  const drawer =
    drawerOpen && typeof document !== 'undefined'
      ? createPortal(
          <div className="fixed inset-0 z-[120] flex justify-end bg-black/50">
            <button
              type="button"
              className="h-full flex-1 cursor-default"
              aria-label="Close drawer"
              onClick={closeDrawer}
            />
            <div className="flex h-dvh max-h-dvh w-full max-w-4xl flex-col overflow-hidden border-l border-border-subtle bg-card shadow-xl">
              <div className="flex shrink-0 items-center justify-between border-b border-border-subtle bg-card px-5 py-4">
                <div>
                  <h3 className="text-lg font-semibold text-text-main">
                    {editing ? 'Edit requirement' : 'Add requirement'}
                  </h3>
                  <p className="text-xs text-text-muted">
                    Program document checklist with optional sample template.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeDrawer}
                  className="rounded-lg p-2 text-text-muted hover:bg-black/5"
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-4">
                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-text-main">Document name</span>
                  <input
                    type="text"
                    value={form.document_name}
                    onChange={event =>
                      setForm(prev => ({ ...prev, document_name: event.target.value }))
                    }
                    className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 outline-none focus:border-accent"
                    maxLength={150}
                  />
                </label>

                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-text-main">Description</span>
                  <textarea
                    value={form.description || ''}
                    onChange={event =>
                      setForm(prev => ({ ...prev, description: event.target.value }))
                    }
                    rows={3}
                    className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 outline-none focus:border-accent"
                  />
                </label>

                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-text-main">Accepted Format</span>
                  <input
                    type="text"
                    value={form.accepted_format || ''}
                    onChange={event =>
                      setForm(prev => ({ ...prev, accepted_format: event.target.value }))
                    }
                    className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 outline-none focus:border-accent"
                  />
                </label>

                <SearchableMultiSelect
                  label="Program levels"
                  values={form.program_levels}
                  options={levelOptions}
                  onChange={values =>
                    setForm(prev => ({
                      ...prev,
                      program_levels: values.map(String).filter(Boolean),
                    }))
                  }
                  placeholder="Select one or more levels..."
                  hint="Choose every program level this requirement applies to."
                />

                <label className="flex items-center gap-2 text-sm text-text-main">
                  <input
                    type="checkbox"
                    checked={form.is_mandatory}
                    onChange={event =>
                      setForm(prev => ({ ...prev, is_mandatory: event.target.checked }))
                    }
                    className="rounded border-border-subtle"
                  />
                  Mandatory document
                </label>

                <label className="flex items-center gap-2 text-sm text-text-main">
                  <input
                    type="checkbox"
                    checked={form.is_global}
                    onChange={event =>
                      setForm(prev => ({
                        ...prev,
                        is_global: event.target.checked,
                        country_ids: event.target.checked ? [] : prev.country_ids,
                      }))
                    }
                    className="rounded border-border-subtle"
                  />
                  Apply globally
                </label>

                <SearchableMultiSelect
                  label="Countries"
                  values={form.country_ids.map(String)}
                  options={countryOptions}
                  onChange={values =>
                    setForm(prev => ({
                      ...prev,
                      country_ids: values.map(Number).filter(Number.isFinite),
                    }))
                  }
                  placeholder="Select countries..."
                  disabled={form.is_global}
                  hint={
                    form.is_global
                      ? 'Hidden while Apply globally is enabled.'
                      : 'Required when the requirement is country-specific.'
                  }
                />

                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-text-main">
                    {editing?.template ? 'Replace template' : 'Sample template'}
                  </span>
                  <div className="flex items-center gap-2 rounded-xl border border-dashed border-border-subtle bg-surface-bg px-3 py-3">
                    <Upload size={16} className="text-text-muted" />
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.gif,application/pdf,image/*"
                      onChange={event =>
                        setForm(prev => ({
                          ...prev,
                          file: event.target.files?.[0] || null,
                        }))
                      }
                      className="w-full text-xs text-text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
                    />
                  </div>
                  {editing?.template && !form.file ? (
                    <p className="text-xs text-text-muted">
                      Current: {editing.template.template_name}
                    </p>
                  ) : null}
                  {form.file ? (
                    <p className="text-xs text-text-muted">Selected: {form.file.name}</p>
                  ) : null}
                </label>

                {formError ? <p className="text-sm text-alert">{formError}</p> : null}
              </div>

              <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border-subtle bg-card px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
                <button
                  type="button"
                  onClick={closeDrawer}
                  disabled={saving}
                  className="rounded-xl border border-border-subtle px-4 py-2 text-sm text-text-main hover:bg-black/5"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                  {editing ? 'Save changes' : 'Create'}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div
      className={`w-full min-w-0 max-w-none ${embedded ? 'space-y-4' : 'space-y-6'}`}
    >
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-border-subtle bg-surface-bg p-4">
        <label className="block min-w-[180px] flex-1 space-y-1 text-sm">
          <span className="font-medium text-text-main">Program Level</span>
          <select
            value={filterLevel}
            onChange={event => setFilterLevel(event.target.value)}
            className="w-full rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm outline-none focus:border-accent"
          >
            <option value="">All levels</option>
            {filterLevelOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <div className="min-w-[240px] flex-[1.4]">
          <SearchableMultiSelect
            label="Countries"
            values={filterCountryIds}
            options={countryOptions}
            onChange={setFilterCountryIds}
            placeholder="Filter by countries..."
            emptyMessage="No countries found"
          />
        </div>

        <label className="block min-w-[160px] space-y-1 text-sm">
          <span className="font-medium text-text-main">Scope</span>
          <select
            value={filterGlobal}
            onChange={event =>
              setFilterGlobal(event.target.value as 'all' | 'global' | 'specific')
            }
            className="w-full rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm outline-none focus:border-accent"
          >
            <option value="all">All</option>
            <option value="global">Global only</option>
            <option value="specific">Country-specific</option>
          </select>
        </label>

        <button
          type="button"
          onClick={applyFilters}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          Apply filters
        </button>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void openChecklist()}
            className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm font-medium text-text-main hover:bg-black/5"
          >
            <FileText size={16} />
            Create document checklist
          </button>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm font-medium text-text-main hover:bg-black/5"
          >
            <Plus size={16} />
            Add requirement
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading...
        </div>
      ) : error ? (
        <div className="py-10 text-sm text-alert">{error}</div>
      ) : items.length === 0 ? (
        <div className="py-10 text-sm text-text-muted">No document requirements found.</div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-border-subtle">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="w-12 px-3 py-3 font-medium tabular-nums">#</th>
                <th className="px-4 py-3 font-medium">Document</th>
                <th className="px-4 py-3 font-medium">Requirement</th>
                <th className="px-4 py-3 font-medium">Level</th>
                <th className="px-4 py-3 font-medium">Countries</th>
                <th className="px-4 py-3 font-medium">Accepted Format</th>
                <th className="px-4 py-3 font-medium">Template</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row, index) => {
                const levels = resolveProgramLevels(row);
                return (
                  <tr key={row.id} className="border-t border-border-subtle align-top">
                    <td className="w-12 px-3 py-3 tabular-nums text-text-muted">{index + 1}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-text-main">{row.document_name}</div>
                      {row.description ? (
                        <p className="mt-1 max-w-md text-xs text-text-muted">{row.description}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      {row.is_mandatory ? (
                        <span className="rounded-full bg-alert/10 px-2 py-0.5 text-[11px] font-medium text-alert">
                          Mandatory
                        </span>
                      ) : (
                        <span className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-medium text-text-muted">
                          Optional
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-main">
                      {levels.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {levels.map(level => (
                            <span
                              key={level}
                              className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-medium text-text-main"
                            >
                              {level}
                            </span>
                          ))}
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-main">
                      {row.is_global
                        ? 'Global'
                        : (row.countries || []).map(c => c.name).join(', ') || '—'}
                    </td>
                    <td className="px-4 py-3 text-text-main">
                      {row.accepted_format?.trim() ? row.accepted_format : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {row.template ? (
                        <button
                          type="button"
                          onClick={() => void handleDownload(row)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-medium text-text-main hover:bg-black/5"
                        >
                          <Download size={14} />
                          {row.template.template_name}
                        </button>
                      ) : (
                        <span className="text-xs text-text-muted">No template</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(row)}
                          className="rounded-lg p-2 text-text-muted hover:bg-black/5 hover:text-text-main"
                          aria-label={`Edit ${row.document_name}`}
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(row)}
                          className="rounded-lg p-2 text-text-muted hover:bg-alert/10 hover:text-alert"
                          aria-label={`Delete ${row.document_name}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {drawer}
      {checklistModal}
    </div>
  );
};

export default DocumentRequirementsPage;
