import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export interface CounselorStatusMasterItem {
  id: number;
  status_key: string;
  status_heading: string;
  default_description: string;
  is_active: boolean;
  sort_order: number;
}

export interface CounselorFollowupItem {
  id: number;
  lead_id: number;
  counselor_id?: string | null;
  status_id: number;
  status_key: string;
  status_heading: string;
  points_discussed: string;
  action_items?: string | null;
  target_completion_date?: string | null;
  created_at: string;
}

export interface CounselorFollowupCreatePayload {
  status_id: number;
  points_discussed: string;
  action_items?: string | null;
  target_completion_date?: string | null;
}

export function useCounselorFollowupStatuses(enabled = true) {
  return useQuery<{ items: CounselorStatusMasterItem[] }>({
    queryKey: ['counselor-followup-statuses'],
    queryFn: () => apiFetch('leads/counselor-followup-statuses'),
    enabled,
    staleTime: 60_000,
  });
}

export function useLeadFollowups(leadId: number | null, enabled = true) {
  return useQuery<{ items: CounselorFollowupItem[]; total: number }>({
    queryKey: ['lead-followups', leadId],
    queryFn: () => apiFetch(`leads/${leadId}/followups`),
    enabled: enabled && leadId != null,
  });
}

export function useCreateLeadFollowup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      payload,
    }: {
      leadId: number;
      payload: CounselorFollowupCreatePayload;
    }) =>
      apiFetch(`leads/${leadId}/followups`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }) as Promise<CounselorFollowupItem>,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['lead-followups', variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ['offline-leads'] });
    },
  });
}
