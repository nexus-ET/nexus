import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import DigitalPresenceLinksList from './DigitalPresenceLinksList';
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

interface DigitalPresenceTabProps {
  bookingId: number;
  compact?: boolean;
}

const inputClass =
  'w-full rounded-md border border-border-subtle bg-card px-2.5 py-1.5 text-xs text-text-main focus:outline-none focus:ring-1 focus:ring-sky-400/40 min-h-[32px]';

const labelClass = 'block text-[11px] font-bold text-text-main mb-1';

const sectionClass = 'rounded-lg border border-border-subtle bg-card/80 p-3 space-y-3';

const fieldErrorClass = 'mt-1 text-[10px] text-red-600';

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

const DigitalPresenceTab: React.FC<DigitalPresenceTabProps> = ({ bookingId, compact = false }) => {
  const [links, setLinks] = useState<DigitalPresenceLinkRecord[]>([]);
  const [platformOptions, setPlatformOptions] =
    useState<DigitalPlatformOption[]>(FALLBACK_PLATFORM_OPTIONS);
  const [categoryOptions, setCategoryOptions] =
    useState<DigitalPresenceCategoryOption[]>(FALLBACK_CATEGORY_OPTIONS);
  const [form, setForm] = useState<DigitalPresenceLinkFormState>(emptyDigitalPresenceLinkForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
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

  const openAddModal = () => {
    resetForm();
    setShowModal(true);
    setSuccess(null);
    setError(null);
    setModalError(null);
  };

  const closeModal = () => {
    resetForm();
    setShowModal(false);
    setModalError(null);
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
    setShowModal(true);
    setSuccess(null);
    setError(null);
    setModalError(null);
    setFieldErrors({});
  };

  const handleSave = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const errors = validateDigitalPresenceLinkForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setModalError('Please complete all required fields before saving.');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setModalError(null);
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
      closeModal();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save link.';
      setModalError(message);
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (linkId: number) => {
    try {
      setDeletingId(linkId);
      setError(null);
      const response = (await apiFetch(`${apiPath}/${linkId}`, {
        method: 'DELETE',
      })) as DigitalPresenceLinksResponse;
      setLinks(response.links);
      setSuccess('Link deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete link.');
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        <Loader2 size={20} className="animate-spin mr-2" />
        <span className="text-sm">Loading digital presence…</span>
      </div>
    );
  }

  return (
    <div className={`flex flex-1 min-h-0 flex-col ${compact ? '' : ''}`}>
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
        <section className={sectionClass}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-xs font-bold text-text-main uppercase tracking-wide">
                Digital Presence
              </h3>
              <p className="text-[11px] text-text-muted mt-1">
                Optional links that showcase your technical, professional, academic, or creative work.
              </p>
            </div>
            <button
              type="button"
              onClick={openAddModal}
              className="inline-flex items-center gap-1 rounded-md bg-sky-700 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-sky-800 shrink-0"
            >
              <Plus size={12} />
              Add Link
            </button>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          ) : null}
          {success ? (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
              {success}
            </div>
          ) : null}

          <DigitalPresenceLinksList
            links={links}
            deletingId={deletingId}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </section>
      </div>

      {showModal ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/40">
          <div
            className="w-full max-w-lg rounded-lg border border-border-subtle bg-card shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="digital-presence-modal-title"
          >
            <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
              <h4 id="digital-presence-modal-title" className="text-sm font-bold text-text-main">
                {editingId ? 'Edit Link' : 'Add Link'}
              </h4>
              <button
                type="button"
                onClick={closeModal}
                className="rounded-md border border-border-subtle p-1 text-text-muted hover:bg-surface-bg"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleSave} noValidate className="px-4 py-4 space-y-3">
              {modalError ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {modalError}
                </div>
              ) : null}
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

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  disabled={saving}
                  className="rounded-md border border-border-subtle px-4 py-2 text-xs font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-md bg-sky-700 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                  {editingId ? 'Update Link' : 'Save Link'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default DigitalPresenceTab;
