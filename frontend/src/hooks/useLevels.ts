import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { LevelRecord } from '../types/level';
import { FALLBACK_LEVELS } from '../types/level';

export function useLevels() {
  const query = useQuery<LevelRecord[]>({
    queryKey: ['levels'],
    queryFn: () => apiFetch('levels'),
    staleTime: 1000 * 60 * 60,
  });

  const levels = query.data?.length ? query.data : FALLBACK_LEVELS;

  return {
    levels,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function useAcademiaLevels(enabled = true) {
  const query = useQuery<LevelRecord[]>({
    queryKey: ['academia-levels'],
    queryFn: () => apiFetch('academia/levels'),
    staleTime: 1000 * 60 * 60,
    enabled,
  });

  const levels = query.data?.length ? query.data : FALLBACK_LEVELS;

  return {
    levels,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findLevel(
  levels: LevelRecord[],
  id: number | string | null | undefined
): LevelRecord | undefined {
  if (id === null || id === undefined || id === '') return undefined;
  const normalized = Number(id);
  return levels.find(level => level.id === normalized);
}
