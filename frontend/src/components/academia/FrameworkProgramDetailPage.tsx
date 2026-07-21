import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import {
  COURSES_PATH,
  DEGREES_PATH,
  PROGRAMS_PATH,
  type CourseRecord,
  type ProgramRecord,
} from '../../types/academicFramework';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import CourseFormModal from './CourseFormModal';
import ProgramFormModal from './ProgramFormModal';
import { useConfirmation } from '../../context/ConfirmationContext';

const FrameworkProgramDetailPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const { programId = '' } = useParams();
  const [program, setProgram] = useState<ProgramRecord | null>(null);
  const [courses, setCourses] = useState<CourseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [programModalOpen, setProgramModalOpen] = useState(false);
  const [courseModalOpen, setCourseModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState<CourseRecord | null>(null);

  const loadData = useCallback(async () => {
    if (!programId) return;
    setLoading(true);
    setError(null);
    try {
      const [programData, courseData] = await Promise.all([
        apiFetch<ProgramRecord>(`academia/programs/${programId}`),
        apiFetch<CourseRecord[]>(`academia/programs/${programId}/courses`),
      ]);
      setProgram(programData);
      setCourses(Array.isArray(courseData) ? courseData : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load program');
      setProgram(null);
      setCourses([]);
    } finally {
      setLoading(false);
    }
  }, [programId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const openCreateCourse = () => {
    setEditingCourse(null);
    setCourseModalOpen(true);
  };

  const openEditCourse = (course: CourseRecord) => {
    setEditingCourse(course);
    setCourseModalOpen(true);
  };

  const handleDeleteCourse = async (course: CourseRecord) => {
    if (
      !(await openConfirm({
        title: 'Delete course?',
        message: `Delete course "${course.name}"?`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) return;
    try {
      await apiFetch(`academia/courses/${course.id}`, { method: 'DELETE' });
      void loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete course');
    }
  };

  if (!loading && !program && error) {
    return <Navigate to={PROGRAMS_PATH} replace />;
  }

  const programName = program?.name || program?.label || 'Program';
  const hierarchyLabel = program?.degree_name
    ? `${program.degree_name} > ${programName}`
    : programName;

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: DEGREES_PATH },
            { label: 'Programs', path: PROGRAMS_PATH },
            { label: programName },
          ]}
        />
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading...
        </div>
      ) : program ? (
        <>
          <div className="rounded-2xl border border-border-subtle bg-card p-6 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  {program.degree_name || 'Degree'}
                </p>
                <h2 className="text-2xl font-bold text-text-main">{programName}</h2>
                <p className="mt-2 rounded-lg bg-surface-bg px-3 py-1.5 text-xs text-text-muted">
                  Target: {hierarchyLabel}
                </p>
                <p className="mt-2 max-w-2xl text-sm text-text-muted">
                  {program.description || 'No description provided.'}
                </p>
                <p className="mt-2 text-xs text-text-muted">
                  {program.course_count ?? courses.length} mapped course
                  {(program.course_count ?? courses.length) === 1 ? '' : 's'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setProgramModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-3 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg"
              >
                <Pencil size={16} />
                Edit Program
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
              <div>
                <h3 className="text-lg font-bold text-text-main">Courses in this program</h3>
                <p className="text-sm text-text-muted">
                  Manage courses mapped under {hierarchyLabel}.
                </p>
              </div>
              <div className="flex gap-2">
                <Link
                  to={`${COURSES_PATH}?programId=${program.id}&degreeId=${program.degree_id}`}
                  className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted hover:text-text-main"
                >
                  View in Courses
                </Link>
                <button
                  type="button"
                  onClick={openCreateCourse}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
                >
                  <Plus size={16} />
                  Academic Mapping
                </button>
              </div>
            </div>

            {courses.length === 0 ? (
              <div className="px-6 py-10 text-sm text-text-muted">
                No courses mapped yet. Use Academic Mapping to create the first one.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                    <tr>
                      <th className="px-6 py-3 font-semibold">Target path</th>
                      <th className="px-6 py-3 font-semibold">Course</th>
                      <th className="px-6 py-3 font-semibold">Code</th>
                      <th className="px-6 py-3 font-semibold">Level</th>
                      <th className="px-6 py-3 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {courses.map(course => (
                      <tr key={course.id} className="border-t border-border-subtle/70">
                        <td className="max-w-xs px-6 py-3 text-xs text-text-muted">
                          {course.hierarchy_breadcrumb ||
                            `${program.degree_name || ''} > ${programName} > ${course.name || course.label}`}
                        </td>
                        <td className="px-6 py-3 font-medium text-text-main">
                          {course.name || course.label}
                        </td>
                        <td className="px-6 py-3 text-text-muted">{course.code}</td>
                        <td className="px-6 py-3 text-text-main">{course.level || '—'}</td>
                        <td className="px-6 py-3">
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => openEditCourse(course)}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                            >
                              <Pencil size={14} />
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDeleteCourse(course)}
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
            )}
          </div>
        </>
      ) : null}

      <ProgramFormModal
        open={programModalOpen}
        program={program}
        onClose={() => setProgramModalOpen(false)}
        onSaved={() => void loadData()}
      />

      <CourseFormModal
        open={courseModalOpen}
        course={editingCourse}
        onClose={() => setCourseModalOpen(false)}
        onSaved={() => {
          void loadData();
        }}
      />
    </div>
  );
};

export default FrameworkProgramDetailPage;
