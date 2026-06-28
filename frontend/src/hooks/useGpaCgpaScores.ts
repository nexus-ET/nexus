import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { GpaCgpaScoreRecord } from '../types/gpaCgpaScore';
import { FALLBACK_GPA_CGPA_SCORES } from '../types/gpaCgpaScore';

export function useGpaCgpaScores() {
  const query = useQuery<GpaCgpaScoreRecord[]>({
    queryKey: ['gpa-cgpa-scores'],
    queryFn: () => apiFetch('gpa-cgpa-scores'),
    staleTime: 1000 * 60 * 60,
  });

  const scores = query.data?.length ? query.data : FALLBACK_GPA_CGPA_SCORES;

  return {
    scores,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findGpaCgpaScore(
  scores: GpaCgpaScoreRecord[],
  code: string | null | undefined
): GpaCgpaScoreRecord | undefined {
  if (!code) return undefined;
  return scores.find(score => score.code === code.trim().toUpperCase());
}
