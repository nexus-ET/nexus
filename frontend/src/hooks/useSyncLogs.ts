import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import {
  buildSyncLogsApiQuery,
  type SyncLogsQueryState,
} from '../utils/reportsUrl';

export interface SyncLogRecord {
  id: number;
  sync_mode: string;
  triggered_by_user: string;
  triggered_by_user_id?: number | null;
  source: string;
  status: string;
  results_count: number;
  message?: string | null;
  forms_processed: number;
  leads_seen: number;
  leads_created: number;
  leads_skipped: number;
  errors: string[];
  attempt_timestamp: string;
  completed_at?: string | null;
}

export interface SyncLogsResponse {
  logs: SyncLogRecord[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

async function fetchSyncLogs(query: SyncLogsQueryState): Promise<SyncLogsResponse> {
  const qs = buildSyncLogsApiQuery(query);
  return apiFetch(`reports/sync-logs?${qs}`) as Promise<SyncLogsResponse>;
}

export function useSyncLogs(query: SyncLogsQueryState) {
  return useQuery({
    queryKey: ['sync-logs', query],
    queryFn: () => fetchSyncLogs(query),
    staleTime: 5000,
    placeholderData: previous => previous,
  });
}
