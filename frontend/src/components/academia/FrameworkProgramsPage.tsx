import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { MAJORS_PATH } from '../../types/academicFramework';
import type { EducationMajorListResponse, EducationMajorRecord } from '../../types/educationMajor';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import EducationMajorFormModal from './EducationMajorFormModal';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import MajorColorSwatch from './MajorColorSwatch';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'name' | 'code';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = [20, 50] as const;

const FrameworkProgramsPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const [majors, setMajors] = useState<EducationMajorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMajor, setEditingMajor] = useState<EducationMajorRecord | null>(null);

  const loadMajors = useCallback(
    async (activePage = page) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (search.trim()) params.set('q', search.trim());
        params.set('catalog_only', 'true');
        params.set('page', String(activePage));
        params.set('page_size', String(pageSize));
        params.set('sort_by', sortBy);
        params.set('sort_dir', sortDir);

        const data = await apiFetch<EducationMajorListResponse>(
          `academia/education-majors?${params.toString()}`
        );
        setMajors(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load majors');
        setMajors([]);
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
    const timeout = window.setTimeout(() => void loadMajors(page), 250);
    return () => window.clearTimeout(timeout);
  }, [loadMajors, page]);

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
    void loadMajors(1);
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: MAJORS_PATH },
            { label: 'Majors' },
          ]}
        />
      )}

      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        <div
          className={`flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4 ${
            embedded ? 'justify-end' : ''
          }`}
        >
          {embedded ? null : (
            <div>
              <h2 className="text-xl font-bold text-text-main">Majors</h2>
              <p className="text-sm text-text-muted">
                Catalog majors/disciplines (LPMC step 3). Assign them when creating or editing a program.
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              setEditingMajor(null);
              setModalOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Create Major
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-4 border-b border-border-subtle px-6 py-4">
          <label className="block min-w-[240px] flex-1 space-y-1 text-sm">
            <span className="font-medium text-text-main">Search</span>
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search majors..."
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
        ) : majors.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No majors found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkSortableHeader
                      label="Major"
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
                    <th className="px-6 py-3 font-semibold">Programs by level</th>
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {majors.map(major => (
                    <tr key={major.id} className="border-t border-border-subtle/70">
                      <td className="px-6 py-3 font-semibold text-text-main">
                        <div className="flex items-center gap-2">
                          <MajorColorSwatch color={major.color} label={major.label} />
                          <span>{major.label}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-text-muted">{major.code || '—'}</td>
                      <td className="px-6 py-3">
                        {major.level_program_counts && major.level_program_counts.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {major.level_program_counts.map(levelCount => (
                              <span
                                key={`${major.id}-${levelCount.level_id}`}
                                className="inline-flex items-center gap-1 rounded-full border border-border-subtle/70 bg-surface-bg/60 px-2 py-0.5 text-[11px] text-text-main"
                                title={`${levelCount.program_count} program${
                                  levelCount.program_count === 1 ? '' : 's'
                                } mapped at ${levelCount.level_name}`}
                              >
                                <span className="font-medium">{levelCount.level_name}</span>
                                <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent">
                                  {levelCount.program_count}
                                </span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={major.is_active ?? true} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingMajor(major);
                              setModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            type="button"
                            disabled={major.is_other}
                            onClick={async () => {
                              if (!(await openConfirm({
                                title: 'Delete major?',
                                message: `Delete major "${major.label}"?`,
                                confirmLabel: 'Delete',
                                variant: 'danger',
                              }))) return;
                              await apiFetch(`academia/education-majors/${major.id}`, {
                                method: 'DELETE',
                              });
                              void loadMajors();
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10 disabled:opacity-40"
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

      <EducationMajorFormModal
        open={modalOpen}
        major={editingMajor}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
      />
    </div>
  );
};

export default FrameworkProgramsPage;
