import { useEffect, useMemo, useState } from 'react';
import {
  useAdminIntelTerms,
  useBulkDeleteIntelTerms,
  useCreateIntelTerm,
  useDeleteIntelTerm,
  useUpdateIntelTerm,
  type IntelGlossaryWritePayload,
} from '../../hooks/useNexusIntel';
import {
  INTEL_CATEGORIES,
  INTEL_COUNTRIES,
  INTEL_LIFECYCLE_STAGES,
  intelCountryLabel,
  type IntelGlossaryTerm,
} from '../../types/nexusIntel';
import { useConfirmation } from '../../context/ConfirmationContext';

type FlashHandler = (tone: 'success' | 'info' | 'warning' | 'error', text: string) => void;

const EMPTY_FORM: IntelGlossaryWritePayload = {
  term_name: '',
  slug: '',
  category: 'Visa',
  country_code: 'AU',
  lifecycle_stage: '5_Visa',
  short_definition: '',
  full_explanation: '',
  official_source_url: '',
  tags: [],
  is_student_facing: true,
  status: 'ACTIVE',
};

function termToForm(term: IntelGlossaryTerm): IntelGlossaryWritePayload {
  return {
    term_name: term.term_name,
    slug: term.slug,
    category: term.category,
    country_code: term.country_code,
    lifecycle_stage: term.lifecycle_stage,
    short_definition: term.short_definition,
    full_explanation: term.full_explanation || '',
    official_source_url: term.official_source_url || '',
    tags: term.tags || [],
    is_student_facing: term.is_student_facing,
    status: term.status,
  };
}

function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

interface Props {
  onFlash: FlashHandler;
}

const PAGE_SIZES = [10, 25, 50, 100];

const GlossaryTermsAdmin: React.FC<Props> = ({ onFlash }) => {
  const openConfirm = useConfirmation();
  const [q, setQ] = useState('');
  const [country, setCountry] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('ALL');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<IntelGlossaryWritePayload>(EMPTY_FORM);
  const [tagsInput, setTagsInput] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const termsQuery = useAdminIntelTerms(
    {
      q: q || undefined,
      country_code: country || undefined,
      category: category || undefined,
      status,
      page,
      page_size: pageSize,
      sort_by: 'updated',
      sort_dir: 'desc',
    },
    true
  );
  const createTerm = useCreateIntelTerm();
  const updateTerm = useUpdateIntelTerm();
  const deleteTerm = useDeleteIntelTerm();
  const bulkDelete = useBulkDeleteIntelTerms();

  const items = termsQuery.data?.items || [];
  const itemIds = useMemo(() => items.map(item => item.id), [items]);
  const totalPages = termsQuery.data?.total_pages || 1;
  const total = termsQuery.data?.total || 0;
  const saving = createTerm.isPending || updateTerm.isPending;
  const deleting = deleteTerm.isPending || bulkDelete.isPending;
  const selectedCount = selectedIds.size;
  const allPageSelected = itemIds.length > 0 && itemIds.every(id => selectedIds.has(id));
  const somePageSelected = itemIds.some(id => selectedIds.has(id)) && !allPageSelected;

  // Clear selection when filters or page size change (not when paging).
  useEffect(() => {
    setSelectedIds(new Set());
  }, [q, country, category, status, pageSize]);

  const formTitle = useMemo(
    () => (editingId ? 'Edit glossary term' : 'Add glossary term'),
    [editingId]
  );

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setTagsInput('');
    setShowForm(false);
  };

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setTagsInput('');
    setShowForm(true);
  };

  const openEdit = (term: IntelGlossaryTerm) => {
    setEditingId(term.id);
    setForm(termToForm(term));
    setTagsInput((term.tags || []).join(', '));
    setShowForm(true);
  };

  const toggleOne = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllPage = () => {
    if (allPageSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        for (const id of itemIds) next.delete(id);
        return next;
      });
      return;
    }
    setSelectedIds(prev => {
      const next = new Set(prev);
      for (const id of itemIds) next.add(id);
      return next;
    });
  };

  const submitForm = () => {
    const termName = form.term_name.trim();
    const shortDefinition = form.short_definition.trim();
    const slugValue = (form.slug || '').trim();
    const sourceUrl = (form.official_source_url || '').trim();

    if (termName.length < 2) {
      onFlash('warning', 'Enter a term name (at least 2 characters).');
      return;
    }
    if (shortDefinition.length < 8) {
      onFlash(
        'warning',
        'Enter a short definition (at least 8 characters) before creating the term.'
      );
      return;
    }
    if (sourceUrl && !isValidHttpUrl(sourceUrl)) {
      onFlash(
        'warning',
        'Official source URL is invalid. Enter a full URL starting with http:// or https://, or leave it blank.'
      );
      return;
    }

    const payload: IntelGlossaryWritePayload = {
      term_name: termName,
      category: form.category,
      country_code: form.country_code,
      lifecycle_stage: form.lifecycle_stage,
      short_definition: shortDefinition,
      full_explanation: (form.full_explanation || '').trim() || null,
      official_source_url: sourceUrl || null,
      tags: tagsInput
        .split(',')
        .map(tag => tag.trim())
        .filter(Boolean),
      is_student_facing: Boolean(form.is_student_facing),
      status: form.status || 'ACTIVE',
    };
    if (slugValue) {
      payload.slug = slugValue;
    }

    if (editingId) {
      updateTerm.mutate(
        { id: editingId, data: payload },
        {
          onSuccess: () => {
            onFlash('success', 'Term updated.');
            resetForm();
          },
          onError: error => {
            onFlash('error', error instanceof Error ? error.message : 'Update failed.');
          },
        }
      );
      return;
    }

    createTerm.mutate(payload, {
      onSuccess: () => {
        onFlash('success', 'Term created.');
        resetForm();
      },
      onError: error => {
        onFlash('error', error instanceof Error ? error.message : 'Create failed.');
      },
    });
  };

  const handleDeleteOne = async (term: IntelGlossaryTerm) => {
    const confirmed = await openConfirm({
      title: 'Delete glossary term?',
      message: `Delete “${term.term_name}”? This permanently removes the glossary term and cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    deleteTerm.mutate(term.id, {
      onSuccess: () => {
        setSelectedIds(prev => {
          const next = new Set(prev);
          next.delete(term.id);
          return next;
        });
        if (editingId === term.id) resetForm();
        onFlash('success', `Deleted “${term.term_name}”.`);
      },
      onError: error => {
        onFlash('error', error instanceof Error ? error.message : 'Delete failed.');
      },
    });
  };

  const handleBulkDelete = async () => {
    if (!selectedCount) return;
    const confirmed = await openConfirm({
      title: 'Delete selected terms?',
      message: `Delete ${selectedCount} selected term${
        selectedCount === 1 ? '' : 's'
      }? This permanently removes them and cannot be undone.`,
      confirmLabel: 'Delete selected',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    const ids = Array.from(selectedIds);
    bulkDelete.mutate(ids, {
      onSuccess: result => {
        setSelectedIds(new Set());
        if (editingId && ids.includes(editingId)) resetForm();
        onFlash(
          'success',
          `Deleted ${result.deleted} term${result.deleted === 1 ? '' : 's'}${
            result.skipped ? ` (${result.skipped} skipped)` : ''
          }.`
        );
      },
      onError: error => {
        onFlash('error', error instanceof Error ? error.message : 'Bulk delete failed.');
      },
    });
  };

  return (
    <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-text-main">Glossary Terms</h2>
          <p className="text-sm text-text-muted">
            Create, edit, and delete living glossary terms for all subscribed destinations.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!selectedCount || deleting}
            onClick={handleBulkDelete}
            className="rounded-xl border border-alert/40 bg-alert/10 px-4 py-2 text-sm font-semibold text-alert disabled:opacity-50"
          >
            {bulkDelete.isPending
              ? 'Deleting…'
              : `Delete selected${selectedCount ? ` (${selectedCount})` : ''}`}
          </button>
          <button
            type="button"
            onClick={openCreate}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white"
          >
            Add term
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={e => {
            setPage(1);
            setQ(e.target.value);
          }}
          placeholder="Search terms…"
          className="min-w-[12rem] flex-1 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
        />
        <select
          value={country}
          onChange={e => {
            setPage(1);
            setCountry(e.target.value);
          }}
          className="rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
        >
          <option value="">All countries</option>
          {INTEL_COUNTRIES.map(code => (
            <option key={code} value={code}>
              {intelCountryLabel(code)}
            </option>
          ))}
        </select>
        <select
          value={category}
          onChange={e => {
            setPage(1);
            setCategory(e.target.value);
          }}
          className="rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
        >
          <option value="">All categories</option>
          {INTEL_CATEGORIES.map(item => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={e => {
            setPage(1);
            setStatus(e.target.value);
          }}
          className="rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
        >
          <option value="ALL">All statuses</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="DRAFT">DRAFT</option>
          <option value="ARCHIVED">ARCHIVED</option>
        </select>
      </div>

      {showForm ? (
        <div className="rounded-xl border border-border-subtle bg-surface-bg p-3 space-y-3">
          <h3 className="text-sm font-bold text-text-main">{formTitle}</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Term name</span>
              <input
                value={form.term_name}
                onChange={e => setForm(prev => ({ ...prev, term_name: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              />
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Slug (optional)</span>
              <input
                value={form.slug || ''}
                onChange={e => setForm(prev => ({ ...prev, slug: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              />
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Country</span>
              <select
                value={form.country_code}
                onChange={e => setForm(prev => ({ ...prev, country_code: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              >
                {INTEL_COUNTRIES.map(code => (
                  <option key={code} value={code}>
                    {intelCountryLabel(code)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Category</span>
              <select
                value={form.category}
                onChange={e => setForm(prev => ({ ...prev, category: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              >
                {INTEL_CATEGORIES.map(item => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Lifecycle stage</span>
              <select
                value={form.lifecycle_stage}
                onChange={e => setForm(prev => ({ ...prev, lifecycle_stage: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              >
                {INTEL_LIFECYCLE_STAGES.map(stage => (
                  <option key={stage.value} value={stage.value}>
                    {stage.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Status</span>
              <select
                value={form.status || 'ACTIVE'}
                onChange={e => setForm(prev => ({ ...prev, status: e.target.value }))}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              >
                <option value="ACTIVE">ACTIVE</option>
                <option value="DRAFT">DRAFT</option>
                <option value="ARCHIVED">ARCHIVED</option>
              </select>
            </label>
          </div>
          <label className="block text-xs font-semibold text-text-muted space-y-1">
            <span>Short definition</span>
            <textarea
              value={form.short_definition}
              onChange={e => setForm(prev => ({ ...prev, short_definition: e.target.value }))}
              rows={2}
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
            />
          </label>
          <label className="block text-xs font-semibold text-text-muted space-y-1">
            <span>Full explanation</span>
            <textarea
              value={form.full_explanation || ''}
              onChange={e => setForm(prev => ({ ...prev, full_explanation: e.target.value }))}
              rows={4}
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
            />
          </label>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Official source URL</span>
              <input
                value={form.official_source_url || ''}
                onChange={e =>
                  setForm(prev => ({ ...prev, official_source_url: e.target.value }))
                }
                placeholder="https://example.gov/…"
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              />
            </label>
            <label className="text-xs font-semibold text-text-muted space-y-1">
              <span>Tags (comma-separated)</span>
              <input
                value={tagsInput}
                onChange={e => setTagsInput(e.target.value)}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              />
            </label>
          </div>
          <label className="inline-flex items-center gap-2 text-sm font-semibold text-text-main">
            <input
              type="checkbox"
              checked={Boolean(form.is_student_facing)}
              onChange={e =>
                setForm(prev => ({ ...prev, is_student_facing: e.target.checked }))
              }
              className="h-4 w-4"
            />
            Student-facing tip
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={submitForm}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : editingId ? 'Save changes' : 'Create term'}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="rounded-lg border border-border-subtle px-3 py-1.5 text-xs font-semibold"
            >
              Cancel
            </button>
            <span className="text-xs text-text-muted">
              Required: term name + short definition. URL must start with http:// or https:// if
              provided.
            </span>
          </div>
        </div>
      ) : null}

      <p className="text-xs text-text-muted">{total} term(s)</p>
      <div className="headless-scroll-viewport overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase text-text-muted">
            <tr>
              <th className="py-2 pr-3 w-10">
                <input
                  type="checkbox"
                  checked={allPageSelected}
                  ref={el => {
                    if (el) el.indeterminate = somePageSelected;
                  }}
                  onChange={toggleAllPage}
                  className="h-4 w-4"
                  aria-label="Select all terms on this page"
                />
              </th>
              <th className="py-2 pr-3">Term</th>
              <th className="py-2 pr-3">Country</th>
              <th className="py-2 pr-3">Category</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map(term => {
              const checked = selectedIds.has(term.id);
              return (
                <tr key={term.id} className="border-t border-border-subtle align-top">
                  <td className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleOne(term.id)}
                      className="h-4 w-4"
                      aria-label={`Select ${term.term_name}`}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <div className="font-semibold text-text-main">{term.term_name}</div>
                    <div className="text-xs text-text-muted">{term.slug}</div>
                    <p className="mt-1 text-xs text-text-muted line-clamp-2">
                      {term.short_definition}
                    </p>
                  </td>
                  <td className="py-2 pr-3">{intelCountryLabel(term.country_code)}</td>
                  <td className="py-2 pr-3">{term.category}</td>
                  <td className="py-2 pr-3">{term.status}</td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-border-subtle px-2 py-1 text-xs font-semibold"
                        onClick={() => openEdit(term)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-border-subtle px-2 py-1 text-xs font-semibold text-alert"
                        disabled={deleting}
                        onClick={() => handleDeleteOne(term)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!items.length ? (
              <tr>
                <td colSpan={6} className="py-4 text-sm text-text-muted">
                  No terms match these filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-text-muted">
          {total} terms · page {page} of {totalPages}
        </p>
        <div className="flex items-center gap-2">
          <select
            value={pageSize}
            onChange={e => {
              setPage(1);
              setPageSize(Number(e.target.value));
            }}
            className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
            aria-label="Terms per page"
          >
            {PAGE_SIZES.map(size => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
            className="rounded-lg border border-border-subtle px-3 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            className="rounded-lg border border-border-subtle px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
};

export default GlossaryTermsAdmin;
