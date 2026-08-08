import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, API_SYNC_TIMEOUT_MS } from '../utils/api';
import type {
  CountryComparisonItem,
  FutureInsightsResponse,
  IntelAcademyModule,
  IntelAiChatHistoryResponse,
  IntelAiChatResponse,
  IntelAiThreadDetailResponse,
  IntelAiThreadsResponse,
  IntelGlossaryListResponse,
  IntelGlossaryTerm,
  IntelPreferences,
  IntelScrapeReview,
  IntelScrapeRunResult,
  IntelScraperConfig,
  IntelSortBy,
  IntelSortDir,
  IntelTooltipPayload,
  IntelTrivia,
  IntelTriviaAnswerResponse,
  ProofOfFundsResponse,
} from '../types/nexusIntel';
import type { RoiBenchmarkResponse } from '../utils/roiCalculator';

export interface FxRateResponse {
  base: string;
  quote: string;
  rate: number;
  as_of: string;
  source: string;
  notes: string[];
}

export interface IntelTermsQuery {
  q?: string;
  country_code?: string;
  lifecycle_stage?: string;
  category?: string;
  sort_by?: IntelSortBy;
  sort_dir?: IntelSortDir;
  page?: number;
  page_size?: number;
}

function toQuery(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === '') return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function useIntelTerms(query: IntelTermsQuery) {
  return useQuery({
    queryKey: ['intel-terms', query],
    queryFn: () =>
      apiFetch<IntelGlossaryListResponse>(
        `intel/terms${toQuery({
          q: query.q,
          country_code: query.country_code,
          lifecycle_stage: query.lifecycle_stage,
          category: query.category,
          sort_by: query.sort_by,
          sort_dir: query.sort_dir,
          page: query.page ?? 1,
          page_size: query.page_size ?? 25,
        })}`
      ),
    staleTime: 60_000,
  });
}

export function useIntelTooltip(slug: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: ['intel-tooltip', slug],
    queryFn: () => apiFetch<IntelTooltipPayload>(`intel/terms/${slug}/tooltip`),
    enabled: Boolean(slug) && enabled,
    staleTime: 1000 * 60 * 60,
  });
}

export function useIntelPreferences() {
  return useQuery({
    queryKey: ['intel-preferences'],
    queryFn: () => apiFetch<IntelPreferences>('intel/preferences'),
    staleTime: 60_000,
  });
}

export function useUpdateIntelPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<IntelPreferences>) =>
      apiFetch<IntelPreferences>('intel/preferences', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: data => {
      queryClient.setQueryData(['intel-preferences'], data);
    },
  });
}

export function useDailyTrivia(enabled = true) {
  return useQuery({
    queryKey: ['intel-trivia-daily'],
    queryFn: () => apiFetch<IntelTrivia | null>('intel/trivia/daily'),
    enabled,
    staleTime: 60_000,
  });
}

export function useAnswerTrivia() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { trivia_id: string; selected_option_index: number }) =>
      apiFetch<IntelTriviaAnswerResponse>('intel/trivia/answer', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intel-trivia-daily'] });
      queryClient.invalidateQueries({ queryKey: ['intel-preferences'] });
    },
  });
}

export function useIntelAcademy() {
  return useQuery({
    queryKey: ['intel-academy'],
    queryFn: () => apiFetch<IntelAcademyModule[]>('intel/academy'),
    staleTime: 1000 * 60 * 10,
  });
}

export function useProofOfFunds() {
  return useMutation({
    mutationFn: (payload: {
      country_code: string;
      tuition: number;
      living_costs: number;
      scholarships?: number;
    }) =>
      apiFetch<ProofOfFundsResponse>('intel/workflows/proof-of-funds', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  });
}

export function useCountryComparison(countries: string[]) {
  const joined = countries.filter(Boolean).join(',');
  return useQuery({
    queryKey: ['intel-compare', joined],
    queryFn: () =>
      apiFetch<CountryComparisonItem[]>(
        `intel/workflows/compare${toQuery({ countries: joined })}`
      ),
    enabled: countries.length > 0,
  });
}

export function useFutureInsights(
  countries: string[],
  programs: string[] = [],
  institutionIds: number[] = []
) {
  const countryKey = countries.filter(Boolean).join(',');
  const programKey = programs.filter(Boolean).join(',');
  const institutionKey = institutionIds.filter(Boolean).join(',');
  return useQuery({
    queryKey: ['intel-future-insights', countryKey, programKey, institutionKey],
    queryFn: () =>
      apiFetch<FutureInsightsResponse>(
        `intel/future-insights${toQuery({
          countries: countryKey,
          programs: programKey || undefined,
          institution_ids: institutionKey || undefined,
        })}`
      ),
    enabled: countries.length > 0,
    staleTime: 60_000,
  });
}

export function useRoiBenchmarks(options: {
  country: string | null | undefined;
  institutionId?: number | null;
  metroKey?: string | null;
  enabled?: boolean;
}) {
  const country = (options.country || '').trim().toUpperCase();
  return useQuery({
    queryKey: [
      'intel-roi-benchmarks',
      country,
      options.institutionId ?? null,
      options.metroKey ?? null,
    ],
    queryFn: () =>
      apiFetch<RoiBenchmarkResponse>(
        `intel/roi-benchmarks${toQuery({
          country,
          institution_id: options.institutionId ?? undefined,
          metro_key: options.metroKey || undefined,
        })}`
      ),
    enabled: Boolean(country) && (options.enabled ?? true),
    staleTime: 60_000,
  });
}

export function useFxRate(options: {
  base: string | null | undefined;
  quote?: string;
  asOf?: string | null;
  enabled?: boolean;
}) {
  const base = (options.base || '').trim().toUpperCase();
  const quote = (options.quote || 'INR').trim().toUpperCase();
  const asOf = options.asOf || undefined;
  return useQuery({
    queryKey: ['intel-fx-rate', base, quote, asOf || null],
    queryFn: () =>
      apiFetch<FxRateResponse>(
        `intel/fx-rate${toQuery({
          base,
          quote,
          as_of: asOf,
        })}`
      ),
    enabled: Boolean(base) && (options.enabled ?? true),
    staleTime: 1000 * 60 * 60,
  });
}

export function useIntelScraperConfigs(enabled = false) {
  return useQuery({
    queryKey: ['intel-scraper-configs'],
    queryFn: () => apiFetch<IntelScraperConfig[]>('intel/admin/scraper/config'),
    enabled,
  });
}

export function useIntelScrapeReviews(enabled = false) {
  return useQuery({
    queryKey: ['intel-scrape-reviews'],
    queryFn: () => apiFetch<IntelScrapeReview[]>('intel/admin/scraper/reviews'),
    enabled,
  });
}

export function useRunIntelScraper() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input?: string | { configIds: string[] }) => {
      // Live fetches (+ Playwright fallback) can exceed the default 60s client timeout.
      const timeoutMs = API_SYNC_TIMEOUT_MS;
      if (typeof input === 'string') {
        return apiFetch<IntelScrapeRunResult>(`intel/admin/scraper/run?config_id=${input}`, {
          method: 'POST',
          timeoutMs,
        });
      }
      if (input?.configIds?.length) {
        return apiFetch<IntelScrapeRunResult>('intel/admin/scraper/run', {
          method: 'POST',
          body: JSON.stringify({ config_ids: input.configIds }),
          timeoutMs,
        });
      }
      return apiFetch<IntelScrapeRunResult>('intel/admin/scraper/run', {
        method: 'POST',
        body: JSON.stringify({}),
        timeoutMs,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intel-scraper-configs'] });
      queryClient.invalidateQueries({ queryKey: ['intel-scrape-reviews'] });
    },
  });
}

export function useUpdateScraperInterval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { configId: string; scrape_interval_hours: number }) =>
      apiFetch<IntelScraperConfig>(`intel/admin/scraper/config/${payload.configId}`, {
        method: 'PATCH',
        body: JSON.stringify({ scrape_interval_hours: payload.scrape_interval_hours }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intel-scraper-configs'] });
    },
  });
}

export function useApproveScrapeReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reviewId: string) =>
      apiFetch<IntelScrapeReview>(`intel/admin/scraper/reviews/${reviewId}/approve`, {
        method: 'POST',
      }),
    onSuccess: (_data, reviewId) => {
      queryClient.setQueryData<IntelScrapeReview[]>(['intel-scrape-reviews'], old =>
        (old || []).filter(item => item.id !== reviewId)
      );
      void queryClient.refetchQueries({ queryKey: ['intel-scrape-reviews'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export function useApproveScrapeReviewsBulk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reviewIds: string[]) =>
      apiFetch<{ approved: number; skipped: number; items: IntelScrapeReview[] }>(
        'intel/admin/scraper/reviews/bulk-approve',
        {
          method: 'POST',
          body: JSON.stringify({ review_ids: reviewIds }),
        }
      ),
    onSuccess: (result, reviewIds) => {
      if (result.approved > 0) {
        queryClient.setQueryData<IntelScrapeReview[]>(['intel-scrape-reviews'], old =>
          (old || []).filter(item => !reviewIds.includes(item.id))
        );
      }
      void queryClient.refetchQueries({ queryKey: ['intel-scrape-reviews'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export type IntelGlossaryWritePayload = {
  term_name: string;
  slug?: string | null;
  category: string;
  country_code: string;
  lifecycle_stage: string;
  short_definition: string;
  full_explanation?: string | null;
  tags?: string[];
  official_source_url?: string | null;
  is_student_facing?: boolean;
  status?: string;
};

export function useAdminIntelTerms(
  query: IntelTermsQuery & { status?: string },
  enabled = false
) {
  return useQuery({
    queryKey: ['intel-admin-terms', query],
    queryFn: () =>
      apiFetch<IntelGlossaryListResponse>(
        `intel/admin/terms${toQuery({
          q: query.q,
          country_code: query.country_code,
          lifecycle_stage: query.lifecycle_stage,
          category: query.category,
          status: query.status ?? 'ALL',
          sort_by: query.sort_by,
          sort_dir: query.sort_dir,
          page: query.page ?? 1,
          page_size: query.page_size ?? 25,
        })}`
      ),
    enabled,
    staleTime: 15_000,
  });
}

export function useCreateIntelTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: IntelGlossaryWritePayload) =>
      apiFetch<IntelGlossaryTerm>('intel/admin/terms', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['intel-admin-terms'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export function useUpdateIntelTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { id: string; data: Partial<IntelGlossaryWritePayload> }) =>
      apiFetch<IntelGlossaryTerm>(`intel/admin/terms/${payload.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload.data),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['intel-admin-terms'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export function useDeleteIntelTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (termId: string) =>
      apiFetch<{ id: string; term_name: string; slug: string }>(`intel/admin/terms/${termId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['intel-admin-terms'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export function useBulkDeleteIntelTerms() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (termIds: string[]) =>
      apiFetch<{ deleted: number; skipped: number; ids: string[] }>(
        'intel/admin/terms/bulk-delete',
        {
          method: 'POST',
          body: JSON.stringify({ term_ids: termIds }),
        }
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['intel-admin-terms'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-terms'] });
    },
  });
}

export function useIntelAiHistory(threadId?: string | null, enabled = true) {
  const qs = new URLSearchParams({ limit: '30' });
  if (threadId) qs.set('thread_id', threadId);
  return useQuery({
    queryKey: ['intel-ai-history', threadId || 'all'],
    queryFn: () => apiFetch<IntelAiChatHistoryResponse>(`intel/ai/history?${qs.toString()}`),
    enabled: enabled && Boolean(threadId),
    staleTime: 30_000,
  });
}

export function useIntelAiThreads(enabled = true) {
  return useQuery({
    queryKey: ['intel-ai-threads'],
    queryFn: () => apiFetch<IntelAiThreadsResponse>('intel/ai/threads?limit=60'),
    enabled,
    staleTime: 15_000,
  });
}

export function useIntelAiThread(threadId?: string | null, enabled = true) {
  return useQuery({
    queryKey: ['intel-ai-thread', threadId || ''],
    queryFn: () =>
      apiFetch<IntelAiThreadDetailResponse>(`intel/ai/threads/${threadId}?limit=100`),
    enabled: enabled && Boolean(threadId),
    staleTime: 10_000,
  });
}

export function useIntelAiChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { prompt: string; thread_id?: string | null }) =>
      apiFetch<IntelAiChatResponse>('intel/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          prompt: body.prompt,
          thread_id: body.thread_id || undefined,
        }),
        timeoutMs: 320_000,
      }),
    onSuccess: data => {
      void queryClient.invalidateQueries({ queryKey: ['intel-ai-threads'] });
      void queryClient.invalidateQueries({ queryKey: ['intel-ai-thread', data.thread_id] });
      void queryClient.invalidateQueries({ queryKey: ['intel-ai-history', data.thread_id] });
      void queryClient.invalidateQueries({ queryKey: ['intel-ai-history', 'all'] });
    },
  });
}
