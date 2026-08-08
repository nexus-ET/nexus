import { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Search } from 'lucide-react';
import {
  INTEL_CATEGORIES,
  INTEL_COUNTRIES,
  INTEL_LIFECYCLE_STAGES,
  intelCountryLabel,
  type IntelSortBy,
  type IntelSortDir,
} from '../../types/nexusIntel';
import { useIntelTerms } from '../../hooks/useNexusIntel';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import IntelTooltip from '../../components/nexus-intel/IntelTooltip';
import GlossaryTermsAdmin from '../../components/nexus-intel/GlossaryTermsAdmin';
import { canAccessAcademiaHub } from '../../utils/academiaAccess';

const PAGE_SIZES = [10, 25, 50, 100];

type SortableColumn = Exclude<IntelSortBy, 'alpha' | 'updated'> | 'updated';

const COLUMNS: Array<{ key: SortableColumn; label: string }> = [
  { key: 'term', label: 'Term' },
  { key: 'country', label: 'Country' },
  { key: 'category', label: 'Category' },
  { key: 'lifecycle', label: 'Stage' },
  { key: 'definition', label: 'Definition' },
  { key: 'source', label: 'Source' },
];

interface ShellContext {
  currentUser?: {
    role?: string | null;
    admin_role?: { name?: string | null } | null;
    is_superuser?: boolean;
  } | null;
}

const FLASH_STYLES = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  info: 'border-accent/30 bg-accent/10 text-text-main',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-alert/30 bg-alert/10 text-alert',
} as const;

const KnowledgeHubPage: React.FC = () => {
  const context = useOutletContext<ShellContext>();
  const canManageTerms = canAccessAcademiaHub(context?.currentUser);
  const [flash, setFlash] = useState<{ tone: keyof typeof FLASH_STYLES; text: string } | null>(
    null
  );
  const [q, setQ] = useState('');
  const [country, setCountry] = useState('');
  const [lifecycle, setLifecycle] = useState('');
  const [category, setCategory] = useState('');
  const [sortBy, setSortBy] = useState<SortableColumn>('updated');
  const [sortDir, setSortDir] = useState<IntelSortDir>('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const debouncedQ = useDebouncedValue(q, 300);

  const query = useMemo(
    () => ({
      q: debouncedQ,
      country_code: country || undefined,
      lifecycle_stage: lifecycle || undefined,
      category: category || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      page,
      page_size: pageSize,
    }),
    [debouncedQ, country, lifecycle, category, sortBy, sortDir, page, pageSize]
  );

  const termsQuery = useIntelTerms(query);
  const data = termsQuery.data;

  const handleSort = (column: SortableColumn) => {
    setPage(1);
    if (sortBy === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir(column === 'updated' ? 'desc' : 'asc');
  };

  const SortIcon = ({ column }: { column: SortableColumn }) => {
    if (sortBy !== column) return <ArrowUpDown size={12} className="opacity-40" />;
    return sortDir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
  };

  return (
    <div className="space-y-4">
      {flash ? (
        <div
          role="status"
          className={`rounded-xl border px-4 py-3 text-sm font-medium ${FLASH_STYLES[flash.tone]}`}
        >
          {flash.text}
        </div>
      ) : null}

      {canManageTerms ? (
        <GlossaryTermsAdmin
          onFlash={(tone, text) => {
            setFlash({ tone, text });
            window.setTimeout(() => setFlash(null), 6000);
          }}
        />
      ) : (
        <>
          <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={q}
                onChange={e => {
                  setPage(1);
                  setQ(e.target.value);
                }}
                placeholder="Search terms, definitions, categories…"
                className="w-full rounded-xl border border-border-subtle bg-surface-bg py-2.5 pl-9 pr-3 text-sm outline-none focus:border-accent"
              />
            </div>
            <div className="grid gap-2 md:grid-cols-3">
              <select
                value={country}
                onChange={e => {
                  setPage(1);
                  setCountry(e.target.value);
                }}
                className="rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              >
                <option value="">All countries</option>
                {INTEL_COUNTRIES.map(code => (
                  <option key={code} value={code}>
                    {intelCountryLabel(code)}
                  </option>
                ))}
              </select>
              <select
                value={lifecycle}
                onChange={e => {
                  setPage(1);
                  setLifecycle(e.target.value);
                }}
                className="rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              >
                <option value="">All lifecycle stages</option>
                {INTEL_LIFECYCLE_STAGES.map(stage => (
                  <option key={stage.value} value={stage.value}>
                    {stage.label}
                  </option>
                ))}
              </select>
              <select
                value={category}
                onChange={e => {
                  setPage(1);
                  setCategory(e.target.value);
                }}
                className="rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              >
                <option value="">All categories</option>
                {INTEL_CATEGORIES.map(item => (
                  <option key={item} value={item}>
                    {item.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
          </section>

          <section className="rounded-2xl border border-border-subtle bg-card">
            <div className="headless-scroll-viewport overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-surface-bg text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    {COLUMNS.map(column => (
                      <th key={column.key} className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => handleSort(column.key)}
                          className={`inline-flex items-center gap-1.5 font-semibold uppercase tracking-wide transition-colors hover:text-text-main ${
                            sortBy === column.key ? 'text-text-main' : ''
                          }`}
                        >
                          {column.label}
                          <SortIcon column={column.key} />
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {termsQuery.isLoading ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-text-muted">
                        Loading terminology…
                      </td>
                    </tr>
                  ) : !data?.items.length ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-text-muted">
                        No terms match your filters.
                      </td>
                    </tr>
                  ) : (
                    data.items.map(term => (
                      <tr key={term.id} className="border-t border-border-subtle align-top">
                        <td className="px-4 py-3 font-semibold text-text-main">
                          <IntelTooltip termSlug={term.slug}>{term.term_name}</IntelTooltip>
                        </td>
                        <td className="px-4 py-3">{intelCountryLabel(term.country_code)}</td>
                        <td className="px-4 py-3">{term.category.replace('_', ' ')}</td>
                        <td className="px-4 py-3">{term.lifecycle_stage.replace('_', ' ')}</td>
                        <td className="px-4 py-3 text-text-muted">{term.short_definition}</td>
                        <td className="px-4 py-3">
                          {term.official_source_url ? (
                            <a
                              href={term.official_source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-accent hover:underline"
                            >
                              Official <ExternalLink size={12} />
                            </a>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle px-4 py-3 text-sm">
              <p className="text-text-muted">
                {data ? `${data.total} terms · page ${data.page} of ${data.total_pages}` : '—'}
                {sortBy !== 'updated' || sortDir !== 'desc'
                  ? ` · Sorted by ${COLUMNS.find(c => c.key === sortBy)?.label || sortBy} (${sortDir === 'asc' ? 'A→Z' : 'Z→A'})`
                  : ''}
              </p>
              <div className="flex items-center gap-2">
                <select
                  value={pageSize}
                  onChange={e => {
                    setPage(1);
                    setPageSize(Number(e.target.value));
                  }}
                  className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
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
                  disabled={!data || page >= data.total_pages}
                  onClick={() => setPage(p => p + 1)}
                  className="rounded-lg border border-border-subtle px-3 py-1 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default KnowledgeHubPage;
