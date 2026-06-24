import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export interface ReportsSyncSchedule {
  mode: 'automated' | 'manual' | string;
  interval_value: number;
  interval_unit: string;
  interval_label: string;
  configured_schedule?: string | null;
  scheduler_enabled: boolean;
  scheduler_active: boolean;
  scheduler_is_leader: boolean;
  next_scheduled_run_at?: string | null;
  help_text: string;
}

export function useReportsSyncSchedule() {
  return useQuery({
    queryKey: ['reports-sync-schedule'],
    queryFn: () => apiFetch('reports/sync-schedule') as Promise<ReportsSyncSchedule>,
    staleTime: 60_000,
  });
}
