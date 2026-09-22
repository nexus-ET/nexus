import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type {
  ProspectDetail,
  ProspectsFilters,
  ProspectsListResponse,
  ProspectsSummary,
} from '../types/prospect';
import type { BookingRowForProfile } from '../utils/candidateProfileLoader';

/** Build `leads/prospects` query string. Exported for unit checks. */
export function buildProspectsQuery(filters: ProspectsFilters): string {
  const params = new URLSearchParams();
  const pageSize = filters.pageSize || 50;
  const page = Math.max(1, filters.page || 1);
  const offset = (page - 1) * pageSize;
  const q = filters.q.trim();
  params.set('limit', String(pageSize));
  params.set('offset', String(offset));
  if (q) params.set('q', q);
  if (filters.source && filters.source !== 'ALL') params.set('source', filters.source);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  // Stage category is for browsing the queue. Name/email/phone search must not be
  // constrained to the current pipeline stage (e.g. Document Readiness has
  // category=Documentation, but "Hey" may still be Counselling).
  // Backend also ignores category when q is set (defense in depth).
  if (filters.category.trim() && !q) {
    params.set('category', filters.category.trim());
  }
  if (filters.contactStatus && filters.contactStatus !== 'all') {
    params.set('contact_status', filters.contactStatus);
  }
  return `leads/prospects?${params.toString()}`;
}

/** Tunnel-bound list/search: prefer a firm 30s budget over the default 60s. */
const PROSPECTS_LIST_TIMEOUT_MS = 30_000;
/** Detail fetch: fail into empty/error UI before UAT tab waits expire (~45s). */
const PROSPECTS_DETAIL_TIMEOUT_MS = 25_000;

export function useProspectsSummary() {
  return useQuery<ProspectsSummary>({
    queryKey: ['prospects', 'summary'],
    queryFn: () => apiFetch('leads/prospects/summary', { timeoutMs: PROSPECTS_LIST_TIMEOUT_MS }),
    staleTime: 60_000,
  });
}

export function useProspectsPage(filters: ProspectsFilters) {
  return useQuery<ProspectsListResponse>({
    queryKey: ['prospects', 'list', filters],
    queryFn: () =>
      apiFetch(buildProspectsQuery(filters), { timeoutMs: PROSPECTS_LIST_TIMEOUT_MS }),
    placeholderData: previous => previous,
  });
}

export function useProspectDetail(leadId: number | null) {
  return useQuery<ProspectDetail>({
    queryKey: ['prospects', 'detail', leadId],
    queryFn: ({ signal }) =>
      apiFetch(`leads/${leadId}`, { signal, timeoutMs: PROSPECTS_DETAIL_TIMEOUT_MS }),
    enabled: leadId != null && !Number.isNaN(leadId),
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
    // Avoid indefinite "Loading lead details..." when the tunnel/API stalls.
    retry: 1,
    retryDelay: 1500,
  });
}

export function useLeadProfileBooking(leadId: number | null, enabled = true) {
  return useQuery<BookingRowForProfile>({
    queryKey: ['leads', 'profile-booking', leadId],
    queryFn: () =>
      apiFetch(`leads/${leadId}/profile-booking`, { timeoutMs: PROSPECTS_DETAIL_TIMEOUT_MS }),
    enabled: enabled && leadId != null && !Number.isNaN(leadId),
    staleTime: 60_000,
    retry: 1,
    retryDelay: 1500,
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
