import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { FullTimeStudyYearRecord } from '../types/fullTimeStudyYear';
import { FALLBACK_FULL_TIME_STUDY_YEARS } from '../types/fullTimeStudyYear';

export function useFullTimeStudyYears() {
  const query = useQuery<FullTimeStudyYearRecord[]>({
    queryKey: ['full-time-study-years'],
    queryFn: () => apiFetch('full-time-study-years'),
    staleTime: 1000 * 60 * 60,
  });

  const options = query.data?.length ? query.data : FALLBACK_FULL_TIME_STUDY_YEARS;

  return {
    options,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findFullTimeStudyYear(
  options: FullTimeStudyYearRecord[],
  code: string | null | undefined,
  levelId?: number | string | null
): FullTimeStudyYearRecord | undefined {
  if (!code) return undefined;
  const normalized = code.trim();
  const levelNormalized =
    levelId === null || levelId === undefined || levelId === ''
      ? null
      : Number(levelId);
  return options.find(option => {
    if (option.code !== normalized) return false;
    if (levelNormalized == null || !Number.isFinite(levelNormalized)) return true;
    return option.level_id === levelNormalized;
  });
}

export function filterFullTimeStudyYearsByLevel(
  options: FullTimeStudyYearRecord[],
  levelId: number | string | null | undefined
): FullTimeStudyYearRecord[] {
  if (levelId === null || levelId === undefined || levelId === '') return [];
  const normalized = Number(levelId);
  if (!Number.isFinite(normalized)) return [];
  return options.filter(option => option.level_id === normalized);
}

