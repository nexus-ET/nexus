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

export interface CounselorFollowupSentDocument {
  label: string;
  url?: string | null;
  link_unavailable?: boolean;
}

export interface CounselorFollowupItem {
  id: number;
  lead_id: number;
  counselor_id?: string | null;
  counselor_name?: string | null;
  status_id: number;
  status_key: string;
  status_heading: string;
  points_discussed: string;
  action_items?: string | null;
  target_completion_date?: string | null;
  created_at: string;
  email_sent?: boolean | null;
  email_error?: string | null;
  checklist_email_to?: string | null;
  checklist_email_sent_at?: string | null;
  checklist_sent_documents?: CounselorFollowupSentDocument[] | null;
}

export interface CounselorFollowupCreatePayload {
  status_id: number;
  points_discussed: string;
  action_items?: string | null;
  target_completion_date?: string | null;
  send_document_checklist_email?: boolean;
  checklist_program_level?: string | null;
  checklist_scope?: 'global' | 'country_specific' | null;
  checklist_country_id?: number | null;
}

export interface CounselorFollowupUpdatePayload {
  status_id: number;
  points_discussed: string;
  action_items?: string | null;
  target_completion_date?: string | null;
}

function sortStatusesByHeading(
  items: CounselorStatusMasterItem[]
): CounselorStatusMasterItem[] {
  return [...items].sort((a, b) =>
    a.status_heading.localeCompare(b.status_heading, undefined, { sensitivity: 'base' })
  );
}

export function useCounselorFollowupStatuses(enabled = true) {
  return useQuery<{ items: CounselorStatusMasterItem[] }>({
    queryKey: ['counselor-followup-statuses'],
    queryFn: () => apiFetch('leads/counselor-followup-statuses'),
    enabled,
    staleTime: 60_000,
    select: data => ({
      ...data,
      items: sortStatusesByHeading(data.items ?? []),
    }),
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

export function useUpdateLeadFollowup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      followupId,
      payload,
    }: {
      leadId: number;
      followupId: number;
      payload: CounselorFollowupUpdatePayload;
    }) =>
      apiFetch(`leads/${leadId}/followups/${followupId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }) as Promise<CounselorFollowupItem>,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['lead-followups', variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ['offline-leads'] });
    },
  });
}
