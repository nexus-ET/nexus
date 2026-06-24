import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export interface QuarantineReasonBreakdown {
  reason: string;
  label: string;
  count: number;
}

export interface IngestionQualityReport {
  total_received: number;
  total_processed: number;
  total_pending: number;
  total_promoted: number;
  total_quarantined: number;
  total_reprocessed: number;
  clean_ratio_percent: number;
  quarantine_ratio_percent: number;
  quarantine_reasons: QuarantineReasonBreakdown[];
  sync_mode_filter?: string | null;
}

export function useIngestionQuality(params: {
  startDate?: string;
  endDate?: string;
  syncMode?: string;
}) {
  const qs = new URLSearchParams();
  if (params.startDate) qs.set('start_date', params.startDate);
  if (params.endDate) qs.set('end_date', params.endDate);
  if (params.syncMode) qs.set('sync_mode', params.syncMode);

  return useQuery({
    queryKey: ['ingestion-quality', params],
    queryFn: () =>
      apiFetch(`reports/ingestion-quality?${qs.toString()}`) as Promise<IngestionQualityReport>,
    staleTime: 30_000,
  });
}
