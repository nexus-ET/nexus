import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { EducationMajorRecord } from '../types/educationMajor';
import { FALLBACK_EDUCATION_MAJORS } from '../types/educationMajor';

export function useEducationMajors() {
  const query = useQuery<EducationMajorRecord[]>({
    queryKey: ['education-majors'],
    queryFn: () => apiFetch('education-majors'),
    staleTime: 1000 * 60 * 60,
  });

  const majors = query.data?.length ? query.data : FALLBACK_EDUCATION_MAJORS;

  return {
    majors,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export { findEducationMajor, isKnownEducationMajor } from '../types/educationMajor';
