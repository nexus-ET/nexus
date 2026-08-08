import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import EmptyListMessage from './ui/EmptyListMessage';
import {
  ADMISSION_VALUE_NOTE_MAX_LENGTH,
  FALLBACK_CATEGORY_OPTIONS,
  FALLBACK_PLATFORM_OPTIONS,
  PLATFORM_DEFAULT_CATEGORY,
  emptyDigitalPresenceLinkForm,
  formToLinkPayload,
  linkToForm,
  validateDigitalPresenceLinkForm,
  type DigitalPlatform,
  type DigitalPresenceCategoryOption,
  type DigitalPresenceLinkFormState,
  type DigitalPresenceLinkRecord,
  type DigitalPresenceLinksResponse,
  type DigitalPlatformOption,
} from '../types/digitalPresenceLink';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
} from './studentInfoFormStyles';

interface DigitalPresenceTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const RequiredLabel: React.FC<{ htmlFor?: string; children: React.ReactNode }> = ({
  htmlFor,
  children,
}) => (
  <label htmlFor={htmlFor} className={labelClass}>
    {children}
    <span className="text-red-600" aria-hidden="true">
      {' '}
      *
    </span>
  </label>
);

function truncateUrl(url: string | null, max = 42): string {
  if (!url) return '—';
  if (url.length <= max) return url;
  return `${url.slice(0, max - 1)}…`;
}

const DigitalPresenceTab: React.FC<DigitalPresenceTabProps> = ({ bookingId, compact = false }) => {
  const [links, setLinks] = useState<DigitalPresenceLinkRecord[]>([]);
  const [platformOptions, setPlatformOptions] =
    useState<DigitalPlatformOption[]>(FALLBACK_PLATFORM_OPTIONS);
  const [categoryOptions, setCategoryOptions] =
    useState<DigitalPresenceCategoryOption[]>(FALLBACK_CATEGORY_OPTIONS);
  const [form, setForm] = useState<DigitalPresenceLinkFormState>(emptyDigitalPresenceLinkForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const apiPath = `bookings/mine/${bookingId}/digital-presence-links`;

  const loadLinks = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as DigitalPresenceLinksResponse;
    setLinks(response.links);
    if (response.platform_options?.length) setPlatformOptions(response.platform_options);
    if (response.category_options?.length) setCategoryOptions(response.category_options);
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loadLinks()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load digital presence links.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadLinks]);

  const resetForm = () => {
    setForm(emptyDigitalPresenceLinkForm());
    setEditingId(null);
    setFieldErrors({});
  };

  const handleCancelForm = () => {
    resetForm();
    setError(null);
  };

  const updateForm = (patch: Partial<DigitalPresenceLinkFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    const clearedKeys = Object.keys(patch);
    if (clearedKeys.length) {
      setFieldErrors(prev => {
        const next = { ...prev };
        clearedKeys.forEach(key => delete next[key]);
        return next;
      });
    }
  };

  const handlePlatformChange = (value: string) => {
    if (!value) {
      updateForm({ platform_name: '', category: '' });
      return;
    }
    const platform = value as DigitalPlatform;
    updateForm({
      platform_name: platform,
      category: PLATFORM_DEFAULT_CATEGORY[platform],
    });
  };

  const handleEdit = (link: DigitalPresenceLinkRecord) => {
    setForm(linkToForm(link));
    setEditingId(link.id);
    setSuccess(null);
    setError(null);
    setFieldErrors({});
  };

  const handleSave = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const errors = validateDigitalPresenceLinkForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please complete all required fields before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const payload = formToLinkPayload(form);
      const response = (await apiFetch(
        editingId ? `${apiPath}/${editingId}` : apiPath,
        {
          method: editingId ? 'PUT' : 'POST',
          body: JSON.stringify(payload),
        }
      )) as DigitalPresenceLinksResponse;
      setLinks(response.links);
      setSuccess(editingId ? 'Link updated.' : 'Link added.');
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save link.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (linkId: number) => {
    try {
      setDeletingId(linkId);
      setError(null);
      setSuccess(null);
      const response = (await apiFetch(`${apiPath}/${linkId}`, {
        method: 'DELETE',
      })) as DigitalPresenceLinksResponse;
      setLinks(response.links);
      if (editingId === linkId) {
        resetForm();
      }
      setSuccess('Link deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete link.');
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading digital presence…
      </div>
    );
  }

  const recordsTable = (
    <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-3 h-full">
      <div>
        <h4 className="text-sm font-semibold text-text-main">Links on file</h4>
        <p className="text-xs text-text-muted mt-0.5">
          Optional links that showcase technical, professional, academic, or creative work.
        </p>
      </div>
      {links.length === 0 ? (
        <EmptyListMessage
          compact
          message="No digital presence links yet. Use the form on the right to add one."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-subtle">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-surface-bg text-text-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Platform</th>
                <th className="px-3 py-2 font-semibold">Category</th>
                <th className="px-3 py-2 font-semibold">URL</th>
                <th className="px-3 py-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {links.map(link => (
                <tr
                  key={link.id}
                  className={`border-t border-border-subtle bg-card ${
                    editingId === link.id ? 'ring-1 ring-inset ring-sky-300' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-text-main">
                    {link.platform_label || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">
                    {link.category_label || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">
                    {link.url ? (
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sky-700 hover:text-sky-900"
                        title={link.url}
                      >
                        {truncateUrl(link.url)}
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleEdit(link)}
                        className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-800 hover:bg-sky-100"
                        aria-label={`Edit ${link.platform_label || 'link'}`}
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(link.id)}
                        disabled={deletingId === link.id}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                        aria-label={`Delete ${link.platform_label || 'link'}`}
                      >
                        {deletingId === link.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const linkForm = (
    <form
      onSubmit={handleSave}
      noValidate
      className="rounded-xl border border-border-subtle bg-card p-4 space-y-3 h-full"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-text-main">
            {editingId ? 'Edit link' : 'Add link'}
          </h4>
          <p className="text-xs text-text-muted mt-0.5">
            Platform, URL, category, and optional admission value.
          </p>
        </div>
        {editingId ? (
          <button
            type="button"
            onClick={handleCancelForm}
            className="text-xs font-semibold text-text-muted hover:text-text-main"
          >
            Clear / New
          </button>
        ) : null}
      </div>

      <div>
        <RequiredLabel htmlFor="digital-platform">Platform</RequiredLabel>
        <select
          id="digital-platform"
          className={fieldClass(Boolean(fieldErrors.platform_name))}
          value={form.platform_name}
          onChange={e => handlePlatformChange(e.target.value)}
        >
          <option value="">Select platform</option>
          {platformOptions.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {fieldErrors.platform_name ? (
          <p className={fieldErrorClass}>{fieldErrors.platform_name}</p>
        ) : null}
      </div>

      <div>
        <RequiredLabel htmlFor="digital-url">URL</RequiredLabel>
        <input
          id="digital-url"
          type="text"
          inputMode="url"
          autoComplete="url"
          className={fieldClass(Boolean(fieldErrors.url))}
          value={form.url}
          onChange={e => updateForm({ url: e.target.value })}
          placeholder="github.com/username or https://linkedin.com/in/you"
        />
        {fieldErrors.url ? <p className={fieldErrorClass}>{fieldErrors.url}</p> : null}
      </div>

      <div>
        <RequiredLabel htmlFor="digital-category">Category</RequiredLabel>
        <select
          id="digital-category"
          className={fieldClass(Boolean(fieldErrors.category))}
          value={form.category}
          onChange={e => updateForm({ category: e.target.value as typeof form.category })}
        >
          <option value="">Select category</option>
          {categoryOptions.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {fieldErrors.category ? (
          <p className={fieldErrorClass}>{fieldErrors.category}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor="digital-admission-note" className={labelClass}>
          Value to Admission
        </label>
        <textarea
          id="digital-admission-note"
          className={`${fieldClass(Boolean(fieldErrors.admission_value_note))} min-h-[88px] resize-y`}
          value={form.admission_value_note}
          onChange={e => updateForm({ admission_value_note: e.target.value })}
          maxLength={ADMISSION_VALUE_NOTE_MAX_LENGTH}
          placeholder="Optional: explain how this link supports your application."
        />
        {fieldErrors.admission_value_note ? (
          <p className={fieldErrorClass}>{fieldErrors.admission_value_note}</p>
        ) : null}
      </div>

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          {editingId ? 'Update Link' : 'Save Link'}
        </button>
      </div>
    </form>
  );

  return (
    <div className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      <div
        className={
          compact
            ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 p-4'
            : 'space-y-4'
        }
      >
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        {success ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {success}
          </div>
        ) : null}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          {recordsTable}
          {linkForm}
        </div>
      </div>
    </div>
  );
};

export default DigitalPresenceTab;
