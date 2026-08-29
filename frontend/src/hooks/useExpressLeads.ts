import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebouncedValue } from './useDebouncedValue';
import { apiFetch } from '../utils/api';
import { phoneLocalToDigits } from '../utils/phoneCountry';
import type {
  ExpressLeadCreatePayload,
  ExpressLeadCreated,
  ExpressLeadDuplicateCheck,
} from '../types/expressLead';

function buildDuplicateCheckUrl(
  email: string,
  phoneCountryIso2: string,
  phoneLocal: string
): string {
  const params = new URLSearchParams();
  params.set('email', email.trim());
  params.set('phone_country_iso2', phoneCountryIso2.trim());
  params.set('phone_local', phoneLocalToDigits(phoneLocal));
  return `leads/express/check-duplicates?${params.toString()}`;
}

export function useExpressLeadDuplicateCheck(
  email: string,
  phoneCountryIso2: string,
  phoneLocal: string,
  enabled = true
) {
  const debouncedEmail = useDebouncedValue(email.trim(), 400);
  const debouncedPhoneCountry = useDebouncedValue(phoneCountryIso2.trim(), 400);
  const debouncedPhoneLocal = useDebouncedValue(phoneLocalToDigits(phoneLocal), 400);

  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(debouncedEmail);
  const phoneReady = Boolean(debouncedPhoneCountry) && debouncedPhoneLocal.length === 10;
  const shouldCheck = enabled && (emailReady || phoneReady);

  const query = useQuery<ExpressLeadDuplicateCheck>({
    queryKey: [
      'express-lead-duplicates',
      debouncedEmail,
      debouncedPhoneCountry,
      debouncedPhoneLocal,
    ],
    queryFn: () =>
      apiFetch(
        buildDuplicateCheckUrl(debouncedEmail, debouncedPhoneCountry, debouncedPhoneLocal)
      ),
    enabled: shouldCheck,
    staleTime: 30_000,
  });

  return {
    emailMatch: query.data?.email_match ?? null,
    phoneMatch: query.data?.phone_match ?? null,
    isChecking: query.isFetching,
  };
}

export function useCreateExpressLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ExpressLeadCreatePayload) =>
      apiFetch('leads/express', {
        method: 'POST',
        body: JSON.stringify(payload),
      }) as Promise<ExpressLeadCreated>,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['express-lead-duplicates'] });
      queryClient.invalidateQueries({ queryKey: ['offline-leads'] });
      queryClient.invalidateQueries({ queryKey: ['active-leads'] });
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
    },
  });
}
