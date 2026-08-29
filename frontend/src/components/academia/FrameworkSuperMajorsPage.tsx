import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { SUPER_MAJORS_PATH } from '../../types/academicFramework';
import type {
  EducationSuperMajorListResponse,
  EducationSuperMajorRecord,
} from '../../types/educationSuperMajor';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import EducationSuperMajorFormModal from './EducationSuperMajorFormModal';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkDescriptionModal from './FrameworkDescriptionModal';
import { FrameworkIdCell, FrameworkIdHeader } from './FrameworkIdDisplay';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination, {
  FRAMEWORK_PAGE_SIZE_OPTIONS,
} from './FrameworkTablePagination';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'name' | 'code' | 'sort_order';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = FRAMEWORK_PAGE_SIZE_OPTIONS;

const FrameworkSuperMajorsPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const [items, setItems] = useState<EducationSuperMajorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('sort_order');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<EducationSuperMajorRecord | null>(null);
  const [descriptionView, setDescriptionView] = useState<{
    title: string;
    description: string;
  } | null>(null);

  const loadItems = useCallback(
    async (activePage = page) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (search.trim()) params.set('q', search.trim());
        params.set('active_only', 'false');
        params.set('page', String(activePage));
        params.set('page_size', String(pageSize));
        params.set('sort_by', sortBy);
        params.set('sort_dir', sortDir);

        const data = await apiFetch<EducationSuperMajorListResponse>(
          `academia/education-super-majors?${params.toString()}`
        );
        setItems(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load super-majors');
        setItems([]);
        setTotal(0);
        setTotalPages(0);
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, search, sortBy, sortDir]
  );

  useEffect(() => {
    setPage(1);
  }, [search, pageSize, sortBy, sortDir]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void loadItems(page), 250);
    return () => window.clearTimeout(timeout);
  }, [loadItems, page]);

  const toggleSort = (column: SortBy) => {
    if (sortBy === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir('asc');
  };

  const handleSaved = () => {
    setPage(1);
    void loadItems(1);
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: SUPER_MAJORS_PATH },
            { label: 'Super-Majors' },
          ]}
        />
      )}

      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        {!loading && !error && items.length > 0 ? (
          <FrameworkTablePagination
            variant="top"
            page={page}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={setPage}
            onPageSizeChange={size =>
              setPageSize(size as (typeof PAGE_SIZE_OPTIONS)[number])
            }
          />
        ) : null}
        <div className="flex flex-wrap items-end gap-3 border-b border-border-subtle px-6 py-4">
          <label className="block min-w-[240px] flex-1 space-y-1 text-sm">
            <span className="font-medium text-text-main">Search</span>
            <div className="relative">
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search super-majors..."
                className="w-full rounded-xl border border-border-subtle bg-surface-bg py-2 pl-3 pr-9 text-sm outline-none focus:border-accent"
              />
              {search ? (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-black/5 hover:text-text-main"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
          </label>
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Create Super-Major
          </button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : items.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No super-majors found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkIdHeader />
                    <FrameworkSortableHeader
                      label="Super-Major"
                      column="name"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="Code"
                      column="code"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Description</th>
                    <th className="px-6 py-3 font-semibold">Majors</th>
                    <FrameworkSortableHeader
                      label="Sort"
                      column="sort_order"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(item => (
                    <tr key={item.id} className="border-t border-border-subtle/70">
                      <FrameworkIdCell value={item.id} />
                      <td className="px-6 py-3 font-semibold text-text-main">{item.name}</td>
                      <td className="px-6 py-3 text-text-muted">{item.code || '—'}</td>
                      <td className="px-6 py-3 text-text-muted">
                        {item.description?.replace(/\s+/g, ' ').trim() ? (
                          <button
                            type="button"
                            onClick={() =>
                              setDescriptionView({
                                title: item.name,
                                description: item.description || '',
                              })
                            }
                            className="text-xs font-semibold text-accent hover:underline"
                          >
                            View Desc
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-6 py-3 tabular-nums text-text-main">
                        {item.major_count ?? 0}
                      </td>
                      <td className="px-6 py-3 tabular-nums text-text-muted">{item.sort_order}</td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={item.is_active ?? true} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditing(item);
                              setModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              if (
                                !(await openConfirm({
                                  title: 'Delete super-major?',
                                  message: `Delete super-major "${item.name}"? Linked majors will keep their rows with Super-Major cleared.`,
                                  confirmLabel: 'Delete',
                                  variant: 'danger',
                                }))
                              ) {
                                return;
                              }
                              await apiFetch(`academia/education-super-majors/${item.id}`, {
                                method: 'DELETE',
                              });
                              void loadItems();
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                          >
                            <Trash2 size={14} />
                            Delete
                          </button>
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
              onPageSizeChange={size =>
                setPageSize(size as (typeof PAGE_SIZE_OPTIONS)[number])
              }
            />
          </>
        )}
      </div>

      <EducationSuperMajorFormModal
        open={modalOpen}
        superMajor={editing}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
      />

      <FrameworkDescriptionModal
        open={Boolean(descriptionView)}
        title={descriptionView?.title || ''}
        description={descriptionView?.description || ''}
        onClose={() => setDescriptionView(null)}
      />
    </div>
  );
};

export default FrameworkSuperMajorsPage;
