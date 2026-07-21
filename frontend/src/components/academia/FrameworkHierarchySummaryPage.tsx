import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../../utils/api';
import {
  COURSES_PATH,
  FRAMEWORK_SECTION_PATH,
  LEVELS_PATH,
  MAJORS_PATH,
  PROGRAMS_PATH,
  type AcademicHierarchySummary,
} from '../../types/academicFramework';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';

const courseFilterPath = (levelId: number, programId: string, majorId: number) =>
  `${COURSES_PATH}?levelId=${levelId}&programId=${encodeURIComponent(programId)}&majorId=${majorId}`;

const FrameworkHierarchySummaryPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const [hierarchy, setHierarchy] = useState<AcademicHierarchySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedLevels, setExpandedLevels] = useState<Set<number>>(new Set());
  const [expandedPrograms, setExpandedPrograms] = useState<Set<string>>(new Set());
  const [expandedMajors, setExpandedMajors] = useState<Set<number>>(new Set());

  const loadHierarchy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AcademicHierarchySummary>('academia/hierarchy');
      setHierarchy(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hierarchy');
      setHierarchy(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHierarchy();
  }, [loadHierarchy]);

  const content = (
    <>
      {loading ? (
        <div className="flex items-center gap-2 px-6 py-10 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading hierarchy...
        </div>
      ) : error ? (
        <div className="px-6 py-10 text-sm text-alert">{error}</div>
      ) : !hierarchy?.levels?.length ? (
        <div className="px-6 py-10 text-sm text-text-muted">
          No levels defined yet.{' '}
          <Link to={LEVELS_PATH} className="font-semibold text-accent hover:underline">
            Create a level
          </Link>{' '}
          to start building the LPMC tree.
        </div>
      ) : (
        <div className="divide-y divide-border-subtle/70">
          {hierarchy.levels.map(level => {
            const levelOpen = expandedLevels.has(level.id);
            const programCount = level.programs.length;
            const majorCount = level.programs.reduce((sum, program) => sum + program.majors.length, 0);
            const courseCount = level.programs.reduce(
              (sum, program) =>
                sum + program.majors.reduce((inner, major) => inner + major.courses.length, 0),
              0
            );
            return (
              <div key={level.id} className="px-6 py-4">
                <button type="button" onClick={() => setExpandedLevels(prev => { const next = new Set(prev); next.has(level.id) ? next.delete(level.id) : next.add(level.id); return next; })} className="flex w-full items-center gap-2 text-left">
                  {levelOpen ? <ChevronDown size={18} className="text-text-muted" /> : <ChevronRight size={18} className="text-text-muted" />}
                  <span className="text-base font-bold text-text-main">{level.name}</span>
                  <span className="text-xs text-text-muted">{programCount} program{programCount === 1 ? '' : 's'} · {majorCount} major{majorCount === 1 ? '' : 's'} · {courseCount} course{courseCount === 1 ? '' : 's'}</span>
                </button>
                {levelOpen ? (
                  <div className="mt-3 ml-6 space-y-3 border-l border-border-subtle pl-4">
                    {level.programs.length === 0 ? (
                      <p className="text-sm text-text-muted">No programs. <Link to={PROGRAMS_PATH} className="font-semibold text-accent hover:underline">Add a program</Link></p>
                    ) : level.programs.map(program => {
                      const programOpen = expandedPrograms.has(program.id);
                      const programCourseCount = program.majors.reduce((sum, major) => sum + major.courses.length, 0);
                      return (
                        <div key={program.id}>
                          <button type="button" onClick={() => setExpandedPrograms(prev => { const next = new Set(prev); next.has(program.id) ? next.delete(program.id) : next.add(program.id); return next; })} className="flex w-full items-center gap-2 text-left">
                            {programOpen ? <ChevronDown size={16} className="text-text-muted" /> : <ChevronRight size={16} className="text-text-muted" />}
                            <Link to={PROGRAMS_PATH} onClick={e => e.stopPropagation()} className="text-sm font-semibold text-accent hover:underline">{program.name}</Link>
                            <span className="text-xs text-text-muted">{program.majors.length} major{program.majors.length === 1 ? '' : 's'} · {programCourseCount} course{programCourseCount === 1 ? '' : 's'}</span>
                          </button>
                          {programOpen ? (
                            <div className="mt-2 ml-6 space-y-3 border-l border-border-subtle/70 pl-4">
                              {program.majors.length === 0 ? (
                                <p className="text-sm text-text-muted">No majors. <Link to={MAJORS_PATH} className="font-semibold text-accent hover:underline">Add a major</Link></p>
                              ) : program.majors.map(major => {
                                const majorOpen = expandedMajors.has(major.id);
                                return (
                                  <div key={major.id}>
                                    <button type="button" onClick={() => setExpandedMajors(prev => { const next = new Set(prev); next.has(major.id) ? next.delete(major.id) : next.add(major.id); return next; })} className="flex w-full items-center gap-2 text-left">
                                      {majorOpen ? <ChevronDown size={16} className="text-text-muted" /> : <ChevronRight size={16} className="text-text-muted" />}
                                      <Link to={MAJORS_PATH} onClick={e => e.stopPropagation()} className="text-sm font-semibold text-text-main hover:text-accent hover:underline">{major.name}</Link>
                                      <span className="text-xs text-text-muted">{major.courses.length} course{major.courses.length === 1 ? '' : 's'}</span>
                                    </button>
                                    {majorOpen ? (
                                      <ul className="mt-2 ml-6 space-y-1 border-l border-border-subtle/70 pl-4">
                                        {major.courses.length === 0 ? (
                                          <li className="text-sm text-text-muted">
                                            No courses yet (optional).{' '}
                                            <Link to={courseFilterPath(level.id, program.id, major.id)} className="font-semibold text-accent hover:underline">Add a course</Link>
                                          </li>
                                        ) : major.courses.map(course => (
                                          <li key={course.id} className="flex flex-wrap items-center gap-2 text-sm">
                                            <span className="font-medium text-text-main">{level.name} &gt; {program.name} &gt; {major.name} &gt; {course.name}</span>
                                            {course.code ? (
                                              <span className="rounded bg-surface-bg px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-text-muted">
                                                {course.code}
                                              </span>
                                            ) : null}
                                          </li>
                                        ))}
                                      </ul>
                                    ) : null}
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      {!embedded ? (
        <p className="mt-4 px-6 pb-6 text-xs text-text-muted">
          LPMC path: <span className="font-medium text-text-main">Level &gt; Program &gt; Major &gt; Course (optional)</span>.
        </p>
      ) : null}
    </>
  );

  if (embedded) return content;

  return (
    <div className="space-y-6">
      <AcademiaBreadcrumbs items={[{ label: 'Academia Hub', path: '/academia' }, { label: 'Academic Framework', path: FRAMEWORK_SECTION_PATH }, { label: 'Summary View' }]} />
      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="border-b border-border-subtle px-6 py-4">
          <h2 className="text-xl font-bold text-text-main">Academic Hierarchy Summary</h2>
          <p className="mt-1 text-sm text-text-muted">Level &gt; Program &gt; Major &gt; Course — the standardized LPMC academic mapping tree.</p>
        </div>
        {content}
      </div>
    </div>
  );
};

export default FrameworkHierarchySummaryPage;
