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
  _name?: string,
  _levelId?: number,
  _programs?: unknown,
  _excludeId?: number | string | null,
  _institutionId?: number | null,
  _countryId?: number | null
): boolean {
  // Uniqueness is server-side (country + institution + level + name).
  // Dual degrees exist at multiple unis; never block Edit from a client list.
  return false;
}

export function isDuplicateMajorName(
  label: string,
  programId: number | string,
  majors: Array<{ id: number; label: string; program_id?: number | string | null }>,
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
