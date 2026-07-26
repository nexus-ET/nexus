import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import {
  buildExceptionLogsApiQuery,
  type ExceptionLogsQueryState,
} from '../utils/reportsUrl';

export interface ExceptionLogRecord {
  id: number;
  severity: string;
  source: string;
  category: string;
  status: string;
  triggered_by_user: string;
  triggered_by_user_id?: number | null;
  message: string;
  details: string[];
  page_path?: string | null;
  exception_type?: string | null;
  related_resource?: string | null;
  related_id?: string | null;
  attempt_timestamp: string;
  resolved_at?: string | null;
  resolution_comment?: string | null;
}

export interface ExceptionLogsResponse {
  logs: ExceptionLogRecord[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

async function fetchExceptionLogs(query: ExceptionLogsQueryState): Promise<ExceptionLogsResponse> {
  const qs = buildExceptionLogsApiQuery(query);
  return apiFetch(`reports/exception-logs?${qs}`) as Promise<ExceptionLogsResponse>;
}

export function useExceptionLogs(query: ExceptionLogsQueryState) {
  return useQuery({
    queryKey: ['exception-logs', query],
    queryFn: () => fetchExceptionLogs(query),
    staleTime: 5000,
    placeholderData: previous => previous,
  });
}
