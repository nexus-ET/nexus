import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type {
  ProspectDetail,
  ProspectsFilters,
  ProspectsListResponse,
  ProspectsSummary,
} from '../types/prospect';

function buildProspectsQuery(filters: ProspectsFilters, cursor?: string | null): string {
  const params = new URLSearchParams();
  params.set('limit', '50');
  if (cursor) params.set('cursor', cursor);
  if (filters.q.trim()) params.set('q', filters.q.trim());
  if (filters.source && filters.source !== 'ALL') params.set('source', filters.source);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  return `leads/prospects?${params.toString()}`;
}

export function useProspectsSummary() {
  return useQuery<ProspectsSummary>({
    queryKey: ['prospects', 'summary'],
    queryFn: () => apiFetch('leads/prospects/summary'),
    staleTime: 60_000,
  });
}

export function useProspectsInfinite(filters: ProspectsFilters) {
  return useInfiniteQuery<ProspectsListResponse>({
    queryKey: ['prospects', 'list', filters],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => apiFetch(buildProspectsQuery(filters, pageParam)),
    getNextPageParam: lastPage => lastPage.next_cursor ?? undefined,
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
