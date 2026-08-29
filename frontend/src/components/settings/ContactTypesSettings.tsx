import React, { useMemo, useState } from 'react';
import { Check, Mail, Pencil, Phone, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import {
  DEFAULT_EMAIL_CONTACT_TYPES,
  DEFAULT_PHONE_CONTACT_TYPES,
  normalizeContactTypeLabel,
} from '../../constants/contactTypes';
import { useAdminSettingsStore, type ContactTypeKind } from '../../stores/adminSettingsStore';
import { apiFetch } from '../../utils/api';

type ManagerTab = ContactTypeKind;

type PendingDelete = {
  kind: ContactTypeKind;
  index: number;
  label: string;
};

const ContactTypesSettings: React.FC = () => {
  const emailContactTypes = useAdminSettingsStore(state => state.emailContactTypes);
  const phoneContactTypes = useAdminSettingsStore(state => state.phoneContactTypes);
  const addEmailType = useAdminSettingsStore(state => state.addEmailType);
  const updateEmailType = useAdminSettingsStore(state => state.updateEmailType);
  const removeEmailType = useAdminSettingsStore(state => state.removeEmailType);
  const addPhoneType = useAdminSettingsStore(state => state.addPhoneType);
  const updatePhoneType = useAdminSettingsStore(state => state.updatePhoneType);
  const removePhoneType = useAdminSettingsStore(state => state.removePhoneType);
  const resetEmailTypesToDefaults = useAdminSettingsStore(state => state.resetEmailTypesToDefaults);
  const resetPhoneTypesToDefaults = useAdminSettingsStore(
    state => state.resetPhoneTypesToDefaults
  );

  const [tab, setTab] = useState<ManagerTab>('email');
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteChecking, setDeleteChecking] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const types = tab === 'email' ? emailContactTypes : phoneContactTypes;

  const defaultsHint = useMemo(
    () =>
      tab === 'email'
        ? DEFAULT_EMAIL_CONTACT_TYPES.join(', ')
        : DEFAULT_PHONE_CONTACT_TYPES.join(', '),
    [tab]
  );

  const resetDraftState = () => {
    setDraft('');
    setError(null);
    setEditingIndex(null);
    setEditingValue('');
  };

  const handleTabChange = (next: ManagerTab) => {
    setTab(next);
    resetDraftState();
    setPendingDelete(null);
    setDeleteError(null);
  };

  const handleAdd = () => {
    const result = tab === 'email' ? addEmailType(draft) : addPhoneType(draft);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    resetDraftState();
  };

  const startEdit = (index: number, label: string) => {
    setEditingIndex(index);
    setEditingValue(label);
    setError(null);
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setEditingValue('');
    setError(null);
  };

  const saveEdit = () => {
    if (editingIndex == null) return;
    const result =
      tab === 'email'
        ? updateEmailType(editingIndex, editingValue)
        : updatePhoneType(editingIndex, editingValue);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    cancelEdit();
  };

  const requestDelete = async (index: number, label: string) => {
    setDeleteError(null);
    setDeleteChecking(true);
    setPendingDelete({ kind: tab, index, label });
    try {
      const inUse = await isContactTypeInUse(tab, label);
      if (inUse) {
        setDeleteError(
          `"${label}" is still used on academia records. Remove or reassign those contacts before deleting this type.`
        );
      }
    } catch {
      // Soft-fail: allow delete with confirmation when usage scan is unavailable.
      setDeleteError(null);
    } finally {
      setDeleteChecking(false);
    }
  };

  const confirmDelete = () => {
    if (!pendingDelete || deleteError) return;
    const result =
      pendingDelete.kind === 'email'
        ? removeEmailType(pendingDelete.index)
        : removePhoneType(pendingDelete.index);
    if (!result.ok) {
      setDeleteError(result.error);
      return;
    }
    setPendingDelete(null);
    setDeleteError(null);
    if (editingIndex === pendingDelete.index) {
      cancelEdit();
    }
  };

  const handleResetDefaults = () => {
    if (tab === 'email') {
      resetEmailTypesToDefaults();
    } else {
      resetPhoneTypesToDefaults();
    }
    resetDraftState();
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-border-subtle bg-card">
      <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-main">Contact Types</h2>
            <p className="mt-0.5 text-xs text-text-muted">
              Manage labels used in phone and email dropdowns across academia and intake forms.
            </p>
          </div>
          <button
            type="button"
            onClick={handleResetDefaults}
            className="inline-flex items-center gap-1.5 self-start rounded-lg border border-border-subtle bg-card px-3 py-1.5 text-xs font-semibold text-text-muted hover:bg-surface-bg hover:text-text-main"
            title={`Restore defaults: ${defaultsHint}`}
          >
            <RotateCcw size={12} />
            Reset {tab === 'email' ? 'email' : 'phone'} defaults
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4 md:p-5">
        <div
          className="inline-flex rounded-lg border border-border-subtle bg-surface-bg p-1"
          role="tablist"
          aria-label="Contact type category"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'email'}
            onClick={() => handleTabChange('email')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${
              tab === 'email'
                ? 'bg-accent text-text-dark-bg shadow-sm'
                : 'text-text-muted hover:text-text-main'
            }`}
          >
            <Mail size={14} />
            Email types
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'phone'}
            onClick={() => handleTabChange('phone')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${
              tab === 'phone'
                ? 'bg-accent text-text-dark-bg shadow-sm'
                : 'text-text-muted hover:text-text-main'
            }`}
          >
            <Phone size={14} />
            Phone types
          </button>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={draft}
            onChange={event => {
              setDraft(event.target.value);
              setError(null);
            }}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                event.preventDefault();
                handleAdd();
              }
            }}
            maxLength={60}
            placeholder={
              tab === 'email'
                ? 'e.g. Inquiry, Billing, Support'
                : 'e.g. Main Line, WhatsApp, Sales'
            }
            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
            aria-label={`New ${tab} contact type`}
          />
          <button
            type="button"
            onClick={handleAdd}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg hover:opacity-90 shrink-0"
          >
            <Plus size={14} />
            Add
          </button>
        </div>
        {error ? <p className="text-xs text-red-600">{error}</p> : null}

        <ul className="divide-y divide-border-subtle/70 rounded-xl border border-border-subtle overflow-hidden">
          {types.map((label, index) => {
            const isEditing = editingIndex === index;
            return (
              <li
                key={`${tab}-${label}-${index}`}
                className="flex flex-wrap items-center gap-2 bg-card px-3 py-2.5"
              >
                {isEditing ? (
                  <>
                    <input
                      type="text"
                      value={editingValue}
                      onChange={event => setEditingValue(event.target.value)}
                      onKeyDown={event => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          saveEdit();
                        }
                        if (event.key === 'Escape') {
                          event.preventDefault();
                          cancelEdit();
                        }
                      }}
                      maxLength={60}
                      className="min-w-[12rem] flex-1 rounded-md border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={saveEdit}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent text-text-dark-bg"
                      aria-label="Save contact type"
                    >
                      <Check size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={cancelEdit}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg"
                      aria-label="Cancel edit"
                    >
                      <X size={14} />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="inline-flex items-center rounded-full border border-border-subtle bg-surface-bg px-2.5 py-1 text-xs font-semibold text-text-main">
                      {label}
                    </span>
                    <span className="flex-1" />
                    <button
                      type="button"
                      onClick={() => startEdit(index, label)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg hover:text-text-main"
                      aria-label={`Edit ${label}`}
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={() => void requestDelete(index, label)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200"
                      aria-label={`Delete ${label}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {pendingDelete ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="contact-type-delete-title"
            className="w-full max-w-md rounded-2xl border border-border-subtle bg-card p-5 shadow-xl"
          >
            <h3 id="contact-type-delete-title" className="text-base font-semibold text-text-main">
              Delete contact type?
            </h3>
            <p className="mt-2 text-sm text-text-muted">
              Remove <span className="font-semibold text-text-main">{pendingDelete.label}</span> from{' '}
              {pendingDelete.kind === 'email' ? 'email' : 'phone'} dropdowns.
            </p>
            {deleteChecking ? (
              <p className="mt-3 text-xs text-text-muted">Checking whether this type is in use…</p>
            ) : null}
            {deleteError ? (
              <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                {deleteError}
              </p>
            ) : (
              <p className="mt-3 text-xs text-text-muted">
                Existing records that already use this label will keep it until they are edited.
              </p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setPendingDelete(null);
                  setDeleteError(null);
                }}
                className="rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-semibold text-text-main hover:bg-card"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={Boolean(deleteError) || deleteChecking}
                onClick={confirmDelete}
                className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

async function isContactTypeInUse(kind: ContactTypeKind, label: string): Promise<boolean> {
  const cleaned = normalizeContactTypeLabel(label);
  if (!cleaned) return false;

  // Best-effort scan of institution hub payloads the admin can already list.
  const endpoints =
    kind === 'email'
      ? ['academia/institutions?limit=100', 'academia/colleges?limit=100']
      : ['academia/institutions?limit=100', 'academia/colleges?limit=100'];

  for (const endpoint of endpoints) {
    try {
      const data = (await apiFetch(endpoint)) as unknown;
      if (payloadContainsContactType(data, kind, cleaned)) {
        return true;
      }
    } catch {
      // Endpoint may not exist or user may lack access — ignore and continue.
    }
  }
  return false;
}

function payloadContainsContactType(
  payload: unknown,
  kind: ContactTypeKind,
  label: string
): boolean {
  const target = label.toLowerCase();
  const keys =
    kind === 'email'
      ? ['email_addresses', 'emails', 'emailAddresses']
      : ['phone_numbers', 'phones', 'phoneNumbers', 'fax_numbers', 'faxNumbers'];

  const visit = (node: unknown): boolean => {
    if (!node) return false;
    if (Array.isArray(node)) {
      return node.some(visit);
    }
    if (typeof node !== 'object') return false;
    const record = node as Record<string, unknown>;
    for (const key of keys) {
      const list = record[key];
      if (!Array.isArray(list)) continue;
      for (const entry of list) {
        if (!entry || typeof entry !== 'object') continue;
        const type = String((entry as { type?: string }).type || '').trim().toLowerCase();
        const value = String((entry as { value?: string }).value || '').trim();
        if (type === target && value) return true;
      }
    }
    return Object.values(record).some(visit);
  };

  return visit(payload);
}

export default ContactTypesSettings;
