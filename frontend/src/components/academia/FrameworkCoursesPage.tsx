import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { levelSelectOptions } from '../../constants/levels';
import { useAcademiaLevels } from '../../hooks/useLevels';
import {
  COURSES_PATH,
  PROGRAMS_PATH,
  type CourseListResponse,
  type CourseRecord,
  type DegreeRecord,
} from '../../types/academicFramework';
import type { EducationMajorRecord } from '../../types/educationMajor';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import CourseFormModal from './CourseFormModal';
import EntityStatusBadge from './EntityStatusBadge';
import FrameworkSortableHeader from './FrameworkSortableHeader';
import FrameworkTablePagination from './FrameworkTablePagination';
import SearchableSelect from './SearchableSelect';
import { useConfirmation } from '../../context/ConfirmationContext';

type SortBy = 'name' | 'code';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE_OPTIONS = [20, 50] as const;

const FrameworkCoursesPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const { levels } = useAcademiaLevels();
  const [searchParams] = useSearchParams();

  const [degrees, setDegrees] = useState<DegreeRecord[]>([]);
  const [majors, setMajors] = useState<EducationMajorRecord[]>([]);
  const [courses, setCourses] = useState<CourseRecord[]>([]);
  const [loadingDegrees, setLoadingDegrees] = useState(false);
  const [loadingMajors, setLoadingMajors] = useState(false);
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filterLevelId, setFilterLevelId] = useState(searchParams.get('levelId') || '');
  const [filterProgramId, setFilterProgramId] = useState(
    searchParams.get('programId') || searchParams.get('degreeId') || ''
  );
  const [filterMajorId, setFilterMajorId] = useState(searchParams.get('majorId') || '');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const [modalOpen, setModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState<CourseRecord | null>(null);

  const showHierarchyColumns = !filterLevelId && !filterMajorId && !filterProgramId;

  const programOptions = useMemo(
    () => degrees.map(degree => ({ value: String(degree.id), label: degree.name })),
    [degrees]
  );

  const majorOptions = useMemo(
    () =>
      majors.map(major => ({
        value: String(major.id),
        label: major.label,
      })),
    [majors]
  );

  const loadPrograms = useCallback(async (levelId: string) => {
    setLoadingDegrees(true);
    try {
      const params: Record<string, string | undefined> = {};
      if (levelId) params.level_id = levelId;
      const data = await fetchAcademiaListItems<DegreeRecord>('academia/degrees', params);
      setDegrees(data);
    } finally {
      setLoadingDegrees(false);
    }
  }, []);

  const loadMajors = useCallback(
    async (programId: string) => {
      setLoadingMajors(true);
      try {
        const params: Record<string, string | undefined> = {};
        if (programId) params.program_id = programId;
        else if (filterLevelId) params.level_id = filterLevelId;
        const data = await fetchAcademiaListItems<EducationMajorRecord>(
          'academia/education-majors',
          params
        );
        setMajors(data);
      } finally {
        setLoadingMajors(false);
      }
    },
    [filterLevelId]
  );

  const fetchCourses = useCallback(
    async ({
      levelId,
      majorId,
      programId,
      activePage = page,
    }: {
      levelId: string;
      majorId: string;
      programId: string;
      activePage?: number;
    }) => {
      setLoadingCourses(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (majorId) params.set('major_id', majorId);
        if (levelId) params.set('level_id', levelId);
        if (programId) params.set('degree_id', programId);
        if (search.trim()) params.set('q', search.trim());
        params.set('page', String(activePage));
        params.set('page_size', String(pageSize));
        params.set('sort_by', sortBy);
        params.set('sort_dir', sortDir);

        const data = await apiFetch<CourseListResponse>(`academia/courses?${params.toString()}`);
        setCourses(Array.isArray(data.items) ? data.items : []);
        setTotal(data.total || 0);
        setTotalPages(data.total_pages || 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load courses');
        setCourses([]);
        setTotal(0);
        setTotalPages(0);
      } finally {
        setLoadingCourses(false);
      }
    },
    [page, pageSize, search, sortBy, sortDir]
  );

  const loadCourses = useCallback(
    async (activePage?: number) => {
      await fetchCourses({
        levelId: filterLevelId,
        majorId: filterMajorId,
        programId: filterProgramId,
        activePage: activePage ?? page,
      });
    },
    [fetchCourses, filterProgramId, filterLevelId, filterMajorId, page]
  );

  useEffect(() => {
    void loadPrograms(filterLevelId);
  }, [filterLevelId, loadPrograms]);

  useEffect(() => {
    void loadMajors(filterProgramId);
  }, [filterProgramId, loadMajors]);

  useEffect(() => {
    if (!filterProgramId || loadingDegrees) return;
    if (degrees.length > 0 && !degrees.some(degree => String(degree.id) === filterProgramId)) {
      setFilterProgramId('');
    }
  }, [degrees, filterProgramId, loadingDegrees]);

  useEffect(() => {
    if (!filterMajorId || loadingMajors) return;
    if (majors.length > 0 && !majors.some(major => String(major.id) === filterMajorId)) {
      setFilterMajorId('');
    }
  }, [filterMajorId, loadingMajors, majors]);

  useEffect(() => {
    setPage(1);
  }, [filterLevelId, filterProgramId, filterMajorId, search, pageSize, sortBy, sortDir]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchCourses({
        levelId: filterLevelId,
        majorId: filterMajorId,
        programId: filterProgramId,
        activePage: page,
      });
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [
    fetchCourses,
    filterLevelId,
    filterProgramId,
    filterMajorId,
    search,
    pageSize,
    sortBy,
    sortDir,
    page,
  ]);

  const toggleSort = (column: SortBy) => {
    if (sortBy === column) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir('asc');
  };

  const openCreate = () => {
    setEditingCourse(null);
    setModalOpen(true);
  };

  const openEdit = async (course: CourseRecord) => {
    setEditingCourse(course);
    setModalOpen(true);
    try {
      const fresh = await apiFetch<CourseRecord>(`academia/courses/${course.id}`);
      setEditingCourse(fresh);
    } catch {
      // Keep list-row data if the detail fetch fails.
    }
  };

  const handleDelete = async (course: CourseRecord) => {
    if (!(await openConfirm({
      title: 'Delete course?',
      message: `Delete course "${course.name || course.label}"?`,
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) return;
    try {
      await apiFetch(`academia/courses/${course.id}`, { method: 'DELETE' });
      void loadCourses();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete course');
    }
  };

  const handleCourseSaved = useCallback(() => {
    setPage(1);
    void fetchCourses({
      levelId: filterLevelId,
      majorId: filterMajorId,
      programId: filterProgramId,
      activePage: 1,
    });
  }, [fetchCourses, filterProgramId, filterLevelId, filterMajorId]);

  const formatCourseHierarchy = (course: CourseRecord): string => {
    const courseName = (course.name || course.label || '').trim();
    const crumb = (course.hierarchy_breadcrumb || '').trim();
    if (crumb && courseName) {
      const suffix = ` > ${courseName}`;
      if (crumb.endsWith(suffix)) {
        const withoutCourse = crumb.slice(0, -suffix.length).trim();
        if (withoutCourse) return withoutCourse;
      }
    }
    if (crumb) return crumb;
    if (course.major_names?.length) return course.major_names.join(', ');
    if (course.major_name) return course.major_name;
    return '—';
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: PROGRAMS_PATH },
            { label: 'Courses', path: COURSES_PATH },
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
              <h2 className="text-xl font-bold text-text-main">Courses</h2>
              <p className="text-sm text-text-muted">
                All courses are listed by default. Filter by Level → Program → Major, or add courses optionally.
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Add New Course
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 border-b border-border-subtle px-6 py-4 md:grid-cols-4">
          <SearchableSelect
            label="Level"
            value={filterLevelId}
            options={[{ value: '', label: 'All levels' }, ...levelSelectOptions(levels)]}
            onChange={value => {
              setFilterLevelId(value);
              setFilterProgramId('');
              setFilterMajorId('');
            }}
            placeholder="All levels"
          />
          <SearchableSelect
            label="Program"
            value={filterProgramId}
            options={[{ value: '', label: 'All programs' }, ...programOptions]}
            onChange={value => {
              setFilterProgramId(value);
              setFilterMajorId('');
            }}
            placeholder={loadingDegrees ? 'Loading programs...' : 'All programs'}
            disabled={loadingDegrees}
          />
          <SearchableSelect
            label="Major"
            value={filterMajorId}
            options={[{ value: '', label: 'All majors' }, ...majorOptions]}
            onChange={setFilterMajorId}
            placeholder={loadingMajors ? 'Loading majors...' : 'All majors'}
            disabled={loadingMajors}
          />
          <label className="space-y-1 text-sm">
            <span className="font-medium text-text-main">Search</span>
            <input
              type="text"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="Search by name or code..."
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
        </div>

        {loadingCourses ? (
          <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading courses...
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-sm text-alert">{error}</div>
        ) : courses.length === 0 ? (
          <div className="px-6 py-10 text-sm text-text-muted">
            No courses found{search.trim() ? ' matching your search' : ''}.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <FrameworkSortableHeader
                      label="Course name"
                      column="name"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    {showHierarchyColumns ? (
                      <th className="px-6 py-3 font-semibold">Affiliated Majors</th>
                    ) : null}
                    <FrameworkSortableHeader
                      label="Course code"
                      column="code"
                      sortBy={sortBy}
                      sortDir={sortDir}
                      onSort={toggleSort}
                    />
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {courses.map(course => (
                    <tr key={course.id} className="border-t border-border-subtle/70">
                      <td className="px-6 py-3 font-medium text-text-main">
                        {course.name || course.label}
                      </td>
                      {showHierarchyColumns ? (
                        <td className="max-w-xs px-6 py-3 text-text-muted">
                          {formatCourseHierarchy(course)}
                        </td>
                      ) : null}
                      <td className="px-6 py-3 text-text-muted">{course.code || '—'}</td>
                      <td className="px-6 py-3">
                        <EntityStatusBadge isActive={course.is_active} />
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => openEdit(course)}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDelete(course)}
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

      <CourseFormModal
        open={modalOpen}
        course={editingCourse}
        presetMajorId={filterMajorId}
        onClose={() => setModalOpen(false)}
        onSaved={handleCourseSaved}
      />
    </div>
  );
};

export default FrameworkCoursesPage;
