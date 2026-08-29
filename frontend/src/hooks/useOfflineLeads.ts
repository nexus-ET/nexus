import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebouncedValue } from './useDebouncedValue';
import { apiFetch } from '../utils/api';
import { phoneLocalToDigits } from '../utils/phoneCountry';
import type {
  OfflineLeadCreatePayload,
  OfflineLeadDuplicateCheck,
  OfflineLeadListResponse,
  OfflineLeadsQuery,
} from '../types/offlineLead';

function buildOfflineLeadsUrl(query: OfflineLeadsQuery): string {
  const params = new URLSearchParams();
  params.set('page', String(query.page));
  params.set('page_size', String(query.pageSize));
  if (query.q.trim()) params.set('q', query.q.trim());
  if (query.status !== 'ALL') params.set('status', query.status);
  params.set('sort_by', query.sortBy);
  params.set('sort_dir', query.sortDir);
  return `leads/offline?${params.toString()}`;
}

export function useOfflineLeads(query: OfflineLeadsQuery) {
  return useQuery<OfflineLeadListResponse>({
    queryKey: ['offline-leads', query],
    queryFn: () => apiFetch(buildOfflineLeadsUrl(query)),
    placeholderData: previous => previous,
    refetchOnMount: 'always',
  });
}

export function useCreateOfflineLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OfflineLeadCreatePayload) =>
      apiFetch('leads/offline', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['offline-leads'] });
    },
  });
}

export function useUpdateOfflineLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: OfflineLeadCreatePayload }) =>
      apiFetch(`leads/offline/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['offline-leads'] });
    },
  });
}

function buildDuplicateCheckUrl(
  email: string,
  phoneCountryIso2: string,
  phoneLocal: string,
  excludeLeadId?: number
): string {
  const params = new URLSearchParams();
  params.set('email', email.trim());
  params.set('phone_country_iso2', phoneCountryIso2.trim());
  params.set('phone_local', phoneLocalToDigits(phoneLocal));
  if (excludeLeadId) params.set('exclude_lead_id', String(excludeLeadId));
  return `leads/offline/check-duplicates?${params.toString()}`;
}

export function useOfflineLeadDuplicateCheck(
  email: string,
  phoneCountryIso2: string,
  phoneLocal: string,
  excludeLeadId?: number,
  enabled = true
) {
  const debouncedEmail = useDebouncedValue(email.trim(), 400);
  const debouncedPhoneCountry = useDebouncedValue(phoneCountryIso2.trim(), 400);
  const debouncedPhoneLocal = useDebouncedValue(phoneLocalToDigits(phoneLocal), 400);

  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(debouncedEmail);
  const phoneReady =
    Boolean(debouncedPhoneCountry) && debouncedPhoneLocal.length === 10;
  const shouldCheck = enabled && (emailReady || phoneReady);

  const query = useQuery<OfflineLeadDuplicateCheck>({
    queryKey: [
      'offline-lead-duplicates',
      debouncedEmail,
      debouncedPhoneCountry,
      debouncedPhoneLocal,
      excludeLeadId ?? null,
    ],
    queryFn: () =>
      apiFetch(
        buildDuplicateCheckUrl(
          debouncedEmail,
          debouncedPhoneCountry,
          debouncedPhoneLocal,
          excludeLeadId
        )
      ),
    enabled: shouldCheck,
    staleTime: 30_000,
  });

  return {
    emailTaken: Boolean(query.data?.email_taken),
    phoneTaken: Boolean(query.data?.phone_taken),
    isChecking: query.isFetching,
  };
}
