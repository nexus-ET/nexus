import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { useAcademiaLevels } from '../../hooks/useLevels';
import { levelSelectOptions } from '../../constants/levels';
import {
  PROGRAMS_PATH,
  type DegreeListResponse,
  type DegreeRecord,
} from '../../types/academicFramework';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import DegreeFormModal from './DegreeFormModal';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'level' | 'name' | 'code';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = [20, 50] as const;

const FrameworkDegreesPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const { levels } = useAcademiaLevels();
  const [degrees, setDegrees] = useState<DegreeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterLevelId, setFilterLevelId] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingDegree, setEditingDegree] = useState<DegreeRecord | null>(null);

  const loadDegrees = useCallback(
    async (activePage = page) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (search.trim()) params.set('q', search.trim());
        if (filterLevelId) params.set('level_id', filterLevelId);
        params.set('page', String(activePage));
        params.set('page_size', String(pageSize));
        params.set('sort_by', sortBy);
        params.set('sort_dir', sortDir);

        const data = await apiFetch<DegreeListResponse>(`academia/degrees?${params.toString()}`);
        setDegrees(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load programs');
        setDegrees([]);
        setTotal(0);
        setTotalPages(0);
      } finally {
        setLoading(false);
      }
    },
    [filterLevelId, page, pageSize, search, sortBy, sortDir]
  );

  useEffect(() => {
    setPage(1);
  }, [filterLevelId, search, pageSize, sortBy, sortDir]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadDegrees(page);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadDegrees, page]);

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
    void loadDegrees(1);
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: PROGRAMS_PATH },
            { label: 'Programs' },
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
              <h2 className="text-xl font-bold text-text-main">Programs</h2>
              <p className="text-sm text-text-muted">
                Qualification programs under each level (LPMC step 2). Majors and courses are added separately.
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              setEditingDegree(null);
              setModalOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Create Program
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-4 border-b border-border-subtle px-6 py-4">
          <label className="block min-w-[200px] space-y-1 text-sm">
            <span className="font-medium text-text-main">Level</span>
            <select
              value={filterLevelId}
              onChange={e => setFilterLevelId(e.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              <option value="">All levels</option>
              {levelSelectOptions(levels).map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block min-w-[240px] flex-1 space-y-1 text-sm">
            <span className="font-medium text-text-main">Search</span>
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search programs..."
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
        ) : degrees.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No programs found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkSortableHeader
                      label="Level"
                      column="level"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="Program"
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
                    <th className="px-6 py-3 font-semibold">Majors</th>
                    <th className="px-6 py-3 font-semibold">Description</th>
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {degrees.map(degree => (
                    <tr key={degree.id} className="border-t border-border-subtle/70">
                      <td className="px-6 py-3 text-text-muted">{degree.level_name || '—'}</td>
                      <td className="px-6 py-3 font-semibold text-text-main">{degree.name}</td>
                      <td className="px-6 py-3 text-text-muted">{degree.code}</td>
                      <td className="px-6 py-3 text-text-muted">{degree.major_count ?? 0}</td>
                      <td className="max-w-md px-6 py-3 text-text-muted">{degree.description || '—'}</td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={degree.is_active} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingDegree(degree);
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
                              if (!(await openConfirm({
                                title: 'Delete program?',
                                message: `Delete program "${degree.name}"?`,
                                confirmLabel: 'Delete',
                                variant: 'danger',
                              }))) return;
                              await apiFetch(`academia/degrees/${degree.id}`, { method: 'DELETE' });
                              void loadDegrees();
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

      <DegreeFormModal
        open={modalOpen}
        degree={editingDegree}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
      />
    </div>
  );
};

export default FrameworkDegreesPage;
