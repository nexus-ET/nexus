export function normalizeFrameworkName(value: string): string {
  return value.trim().toLowerCase();
}

export function isDuplicateLevelName(
  name: string,
  levels: Array<{ id: number; name: string }>,
  excludeId?: number | null
): boolean {
  const normalized = normalizeFrameworkName(name);
  if (!normalized) return false;
  return levels.some(
    level =>
      level.id !== excludeId && normalizeFrameworkName(level.name) === normalized
  );
}

export function isDuplicateProgramName(
  name: string,
  levelId: number,
  programs: Array<{ id: string; name: string; level_id: number }>,
  excludeId?: string | null
): boolean {
  const normalized = normalizeFrameworkName(name);
  if (!normalized || !levelId) return false;
  return programs.some(
    program =>
      program.level_id === levelId &&
      program.id !== excludeId &&
      normalizeFrameworkName(program.name) === normalized
  );
}

export function isDuplicateMajorName(
  label: string,
  programId: string,
  majors: Array<{ id: number; label: string; program_id?: string | null }>,
  excludeId?: number | null
): boolean {
  const normalized = normalizeFrameworkName(label);
  if (!normalized || !programId) return false;
  return majors.some(
    major =>
      major.program_id === programId &&
      major.id !== excludeId &&
      normalizeFrameworkName(major.label) === normalized
  );
}

export function isDuplicateCourseName(
  name: string,
  majorId: number,
  courses: Array<{ id: number; name?: string | null; label?: string | null; major_id?: number | null }>,
  excludeId?: number | null
): boolean {
  const normalized = normalizeFrameworkName(name);
  if (!normalized || !majorId) return false;
  return courses.some(course => {
    const courseName = course.name || course.label || '';
    return (
      Number(course.major_id) === majorId &&
      course.id !== excludeId &&
      normalizeFrameworkName(courseName) === normalized
    );
  });
}
