import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { TargetCourseRecord, TargetProgramRecord } from '../types/targetProgram';
import { FALLBACK_TARGET_COURSES, FALLBACK_TARGET_PROGRAMS } from '../types/targetProgram';

export function useTargetPrograms() {
  const query = useQuery<TargetProgramRecord[]>({
    queryKey: ['target-programs'],
    queryFn: () => apiFetch('target-programs'),
    staleTime: 1000 * 60 * 60,
  });

  const programs = query.data?.length ? query.data : FALLBACK_TARGET_PROGRAMS;

  return {
    programs,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function useTargetCourses(programCode: string | undefined) {
  const normalized = programCode?.trim().toUpperCase() || '';
  const query = useQuery<TargetCourseRecord[]>({
    queryKey: ['target-courses', normalized],
    queryFn: () => apiFetch(`target-programs/${encodeURIComponent(normalized)}/courses`),
    enabled: Boolean(normalized),
    staleTime: 1000 * 60 * 60,
  });

  const courses = query.data?.length
    ? query.data
    : normalized
      ? FALLBACK_TARGET_COURSES.filter(course => course.program_code === normalized)
      : [];

  return {
    courses,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findTargetProgram(
  programs: TargetProgramRecord[],
  code: string | null | undefined
): TargetProgramRecord | undefined {
  if (!code) return undefined;
  return programs.find(program => program.code === code.trim().toUpperCase());
}

export function findTargetCourse(
  courses: TargetCourseRecord[],
  code: string | null | undefined
): TargetCourseRecord | undefined {
  if (!code) return undefined;
  return courses.find(course => course.code === code.trim().toUpperCase());
}
