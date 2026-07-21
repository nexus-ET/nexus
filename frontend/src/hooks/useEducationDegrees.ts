import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { EducationDegreeRecord } from '../types/educationDegree';
import { FALLBACK_EDUCATION_DEGREES } from '../types/educationDegree';

export function useEducationDegrees(levelId?: number | null) {
  const query = useQuery<EducationDegreeRecord[]>({
    queryKey: ['education-degrees', levelId ?? 'all'],
    queryFn: () => {
      const params = new URLSearchParams();
      if (levelId) params.set('level_id', String(levelId));
      const queryString = params.toString();
      return apiFetch(queryString ? `education-degrees?${queryString}` : 'education-degrees');
    },
    staleTime: 1000 * 60 * 60,
  });

  const degrees = query.data?.length ? query.data : FALLBACK_EDUCATION_DEGREES.filter(degree =>
    levelId ? degree.level_id === levelId : true
  );

  return {
    degrees,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findEducationDegree(
  degrees: EducationDegreeRecord[],
  code: string | null | undefined
): EducationDegreeRecord | undefined {
  if (!code) return undefined;
  return degrees.find(degree => degree.code === code.trim().toUpperCase());
}

export function findOtherEducationDegree(
  degrees: EducationDegreeRecord[]
): EducationDegreeRecord | undefined {
  return degrees.find(degree => degree.is_other);
}
