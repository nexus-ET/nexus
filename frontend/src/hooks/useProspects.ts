import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type {
  ProspectDetail,
  ProspectsFilters,
  ProspectsListResponse,
  ProspectsSummary,
} from '../types/prospect';
import type { BookingRowForProfile } from '../utils/candidateProfileLoader';

function buildProspectsQuery(filters: ProspectsFilters): string {
  const params = new URLSearchParams();
  const pageSize = filters.pageSize || 50;
  const page = Math.max(1, filters.page || 1);
  const offset = (page - 1) * pageSize;
  params.set('limit', String(pageSize));
  params.set('offset', String(offset));
  if (filters.q.trim()) params.set('q', filters.q.trim());
  if (filters.source && filters.source !== 'ALL') params.set('source', filters.source);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  if (filters.category.trim()) params.set('category', filters.category.trim());
  if (filters.contactStatus) {
    params.set('contact_status', filters.contactStatus);
  }
  return `leads/prospects?${params.toString()}`;
}

export function useProspectsSummary() {
  return useQuery<ProspectsSummary>({
    queryKey: ['prospects', 'summary'],
    queryFn: () => apiFetch('leads/prospects/summary'),
    staleTime: 60_000,
  });
}

export function useProspectsPage(filters: ProspectsFilters) {
  return useQuery<ProspectsListResponse>({
    queryKey: ['prospects', 'list', filters],
    queryFn: () => apiFetch(buildProspectsQuery(filters)),
    placeholderData: previous => previous,
  });
}

export function useProspectDetail(leadId: number | null) {
  return useQuery<ProspectDetail>({
    queryKey: ['prospects', 'detail', leadId],
    queryFn: () => apiFetch(`leads/${leadId}`),
    enabled: leadId != null && !Number.isNaN(leadId),
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
  });
}

export function useLeadProfileBooking(leadId: number | null, enabled = true) {
  return useQuery<BookingRowForProfile>({
    queryKey: ['leads', 'profile-booking', leadId],
    queryFn: () => apiFetch(`leads/${leadId}/profile-booking`),
    enabled: enabled && leadId != null && !Number.isNaN(leadId),
    staleTime: 60_000,
  });
}

export function useUpdateProspectStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, status }: { leadId: number; status: string }) =>
      apiFetch(`leads/${leadId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['prospects', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['prospects', 'detail', variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ['prospects', 'summary'] });
    },
  });
}

export function useUpdateProspectNotes(leadId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notes: string) =>
      apiFetch(`leads/${leadId}/notes`, {
        method: 'PATCH',
        body: JSON.stringify({ notes }),
      }),
    onSuccess: data => {
      if (leadId != null) {
        queryClient.setQueryData(['prospects', 'detail', leadId], data);
      }
    },
  });
}
