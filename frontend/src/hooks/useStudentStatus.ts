import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export type StatusDefinition = {
  id: number;
  stage_name: string;
  category: string;
  description?: string | null;
  next_stage_id?: number | null;
  is_terminal?: boolean;
};

export type StudentJourneyItem = {
  id: number;
  status_id: number;
  stage_name: string;
  category: string;
  description?: string | null;
  changed_by_type: 'system' | 'admin';
  changed_by_user_id?: number | null;
  changed_by_label: string;
  comments?: string | null;
  created_at: string;
};

export type StudentJourneyResponse = {
  student_id: number;
  items: StudentJourneyItem[];
};

export function useStatusDefinitions() {
  return useQuery<{ items: StatusDefinition[] }>({
    queryKey: ['status-definitions'],
    queryFn: () => apiFetch('leads/status-definitions'),
    staleTime: 5 * 60_000,
  });
}

export function useStudentJourney(studentId: number | null) {
  return useQuery<StudentJourneyResponse>({
    queryKey: ['student-journey', studentId],
    queryFn: () => apiFetch(`leads/${studentId}/journey`),
    enabled: studentId != null && !Number.isNaN(studentId),
    staleTime: 30_000,
  });
}

export function useUpdateStudentStatus(studentId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { status_definition_id: number; comments?: string | null }) =>
      apiFetch(`leads/${studentId}/pipeline-status`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      if (studentId != null) {
        queryClient.invalidateQueries({ queryKey: ['student-journey', studentId] });
        queryClient.invalidateQueries({ queryKey: ['prospects', 'detail', studentId] });
        queryClient.invalidateQueries({ queryKey: ['prospects', 'list'] });
      }
    },
  });
}
