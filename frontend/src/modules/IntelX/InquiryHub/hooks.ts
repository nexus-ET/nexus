import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../utils/api';
import type { InquiryFaq, InquiryFaqList, InquiryFaqPayload, InquiryNode } from './types';

const faqKey = ['intel-inquiry-faqs'] as const;

export function useInquiryTaxonomy() {
  return useQuery({
    queryKey: ['intel-inquiry-taxonomy'],
    queryFn: () => apiFetch<InquiryNode[]>('intel/inquiry-hub/taxonomy'),
    staleTime: 1000 * 60 * 60,
  });
}

export function useInquiryFaqs(paths: string[], search: string) {
  const params = new URLSearchParams();
  paths.forEach(path => params.append('path', path));
  if (search.trim()) params.set('q', search.trim());
  return useQuery({
    queryKey: [...faqKey, paths, search.trim()],
    queryFn: () => apiFetch<InquiryFaqList>(`intel/inquiry-hub/faqs?${params.toString()}`),
  });
}

export function useCreateInquiryFaq() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: InquiryFaqPayload) =>
      apiFetch<InquiryFaq>('intel/inquiry-hub/faqs', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: faqKey }),
  });
}

export function useUpdateInquiryFaq() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: Partial<InquiryFaqPayload> & { id: string }) =>
      apiFetch<InquiryFaq>(`intel/inquiry-hub/faqs/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: faqKey }),
  });
}

export function useDeleteInquiryFaq() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`intel/inquiry-hub/faqs/${id}`, { method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: faqKey }),
  });
}
