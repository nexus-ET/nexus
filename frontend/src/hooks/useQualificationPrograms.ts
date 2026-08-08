import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { QualificationProgramRecord } from '../types/qualificationProgram';

export function useQualificationPrograms() {
  const query = useQuery<QualificationProgramRecord[]>({
    queryKey: ['qualification-programs'],
    queryFn: () => apiFetch('programs'),
    staleTime: 1000 * 60 * 10,
  });

  return {
    programs: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findQualificationProgram(
  programs: QualificationProgramRecord[],
  code: string | null | undefined
): QualificationProgramRecord | undefined {
  if (!code) return undefined;
  const normalized = code.trim().toUpperCase();
  return programs.find(program => program.code.toUpperCase() === normalized);
}
