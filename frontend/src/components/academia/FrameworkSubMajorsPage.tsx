import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { SUB_MAJORS_PATH } from '../../types/academicFramework';
import {
  educationMajorOptionLabel,
  type EducationMajorRecord,
} from '../../types/educationMajor';
import type {
  EducationSubMajorListResponse,
  EducationSubMajorRecord,
} from '../../types/educationSubMajor';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import EducationSubMajorFormModal from './EducationSubMajorFormModal';
import FrameworkDescriptionModal from './FrameworkDescriptionModal';
import { FrameworkIdCell, FrameworkIdHeader } from './FrameworkIdDisplay';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination, {
  FRAMEWORK_PAGE_SIZE_OPTIONS,
} from './FrameworkTablePagination';
import MajorColorSwatch from './MajorColorSwatch';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'name' | 'major';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = FRAMEWORK_PAGE_SIZE_OPTIONS;

const FrameworkSubMajorsPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const [subMajors, setSubMajors] = useState<EducationSubMajorRecord[]>([]);
  const [majors, setMajors] = useState<EducationMajorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterMajorId, setFilterMajorId] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSubMajor, setEditingSubMajor] = useState<EducationSubMajorRecord | null>(null);
  const [descriptionView, setDescriptionView] = useState<{
    title: string;
    description: string;
  } | null>(null);

  const loadSubMajors = useCallback(
    async (activePage = page) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (search.trim()) params.set('q', search.trim());
        if (filterMajorId) params.set('major_id', filterMajorId);
        params.set('page', String(activePage));
        params.set('page_size', String(pageSize));
        params.set('sort_by', sortBy);
        params.set('sort_dir', sortDir);

        const data = await apiFetch<EducationSubMajorListResponse>(
          `academia/education-sub-majors?${params.toString()}`
        );
        setSubMajors(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load sub-majors');
        setSubMajors([]);
        setTotal(0);
        setTotalPages(0);
      } finally {
        setLoading(false);
      }
    },
    [filterMajorId, page, pageSize, search, sortBy, sortDir]
  );

  useEffect(() => {
    void fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
      catalog_only: 'true',
      active_only: 'false',
    })
      .then(setMajors)
      .catch(() => setMajors([]));
  }, []);

  useEffect(() => {
    setPage(1);
  }, [search, pageSize, sortBy, sortDir, filterMajorId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void loadSubMajors(page), 250);
    return () => window.clearTimeout(timeout);
  }, [loadSubMajors, page]);

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
    void loadSubMajors(1);
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: SUB_MAJORS_PATH },
            { label: 'Sub-Majors' },
          ]}
        />
      )}

      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        {!loading && !error && subMajors.length > 0 ? (
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
                placeholder="Search sub-majors..."
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
          <label className="block min-w-[220px] space-y-1 text-sm">
            <span className="font-medium text-text-main">Parent major</span>
            <select
              value={filterMajorId}
              onChange={e => setFilterMajorId(e.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              <option value="">All majors</option>
              {majors.map(major => (
                <option key={major.id} value={String(major.id)}>
                  {educationMajorOptionLabel(major)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setEditingSubMajor(null);
              setModalOpen(true);
            }}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Create Sub-Major
          </button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : subMajors.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">No sub-majors found.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkIdHeader />
                    <FrameworkIdHeader label="Major ID" />
                    <FrameworkSortableHeader
                      label="Sub-Major"
                      column="name"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <FrameworkSortableHeader
                      label="Parent major"
                      column="major"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Description</th>
                    <th className="px-6 py-3 font-semibold">Programs by level</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {subMajors.map(item => (
                    <tr key={item.id} className="border-t border-border-subtle/70">
                      <FrameworkIdCell value={item.id} />
                      <FrameworkIdCell value={item.major_id} />
                      <td className="px-6 py-3 font-semibold text-text-main">{item.name}</td>
                      <td className="px-6 py-3 text-text-muted">
                        <div className="flex items-center gap-2">
                          <MajorColorSwatch color={item.major_color} label={item.major_label || 'Major'} />
                          <span>{item.major_label || '—'}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-text-muted">
                        {item.sub_major_description
                          ?.replace(/<[^>]*>/g, ' ')
                          .replace(/\s+/g, ' ')
                          .trim() ? (
                          <button
                            type="button"
                            onClick={() =>
                              setDescriptionView({
                                title: item.name,
                                description: item.sub_major_description || '',
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
                      <td className="px-6 py-3">
                        {item.programs_by_level && item.programs_by_level.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {item.programs_by_level.map(levelCount => (
                              <span
                                key={`${item.id}-${levelCount.level_id}`}
                                className="inline-flex items-center gap-1 rounded-full border border-border-subtle/70 bg-surface-bg/60 px-2 py-0.5 text-[11px] text-text-main"
                                title={`${levelCount.count} program${
                                  levelCount.count === 1 ? '' : 's'
                                } mapped at ${levelCount.level_name}`}
                              >
                                <span className="font-medium">{levelCount.level_name}</span>
                                <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent">
                                  {levelCount.count}
                                </span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingSubMajor(item);
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
                                  title: 'Delete sub-major?',
                                  message: `Delete sub-major "${item.name}"?`,
                                  confirmLabel: 'Delete',
                                  variant: 'danger',
                                }))
                              ) {
                                return;
                              }
                              await apiFetch(`academia/education-sub-majors/${item.id}`, {
                                method: 'DELETE',
                              });
                              void loadSubMajors();
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

      <EducationSubMajorFormModal
        open={modalOpen}
        subMajor={editingSubMajor}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
      />

      <FrameworkDescriptionModal
        open={Boolean(descriptionView)}
        title={descriptionView?.title || ''}
        description={descriptionView?.description || ''}
        stripHtml
        onClose={() => setDescriptionView(null)}
      />
    </div>
  );
};

export default FrameworkSubMajorsPage;
