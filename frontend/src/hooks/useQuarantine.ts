import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export interface QuarantineRecord {
  id: number;
  raw_incoming_lead_id?: number | null;
  meta_leadgen_id: string;
  original_payload: Record<string, unknown>;
  normalized_payload: Record<string, unknown>;
  error_reason: string;
  error_code: string;
  source: string;
  sync_mode: string;
  triggered_by_user: string;
  lead_id?: number | null;
  reprocessed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuarantineListResponse {
  records: QuarantineRecord[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

export function useQuarantineRecords(page: number, limit: number) {
  return useQuery({
    queryKey: ['quarantine-records', page, limit],
    queryFn: () =>
      apiFetch(`admin/quarantine?page=${page}&limit=${limit}`) as Promise<QuarantineListResponse>,
    staleTime: 10_000,
  });
}

export function useQuarantineMutations() {
  const queryClient = useQueryClient();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['quarantine-records'] });
    void queryClient.invalidateQueries({ queryKey: ['ingestion-quality'] });
  };

  const updateRecord = useMutation({
    mutationFn: ({ id, normalized_payload }: { id: number; normalized_payload: Record<string, unknown> }) =>
      apiFetch(`admin/quarantine/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ normalized_payload }),
      }) as Promise<QuarantineRecord>,
    onSuccess: invalidate,
  });

  const reprocessRecord = useMutation({
    mutationFn: ({ id, normalized_payload }: { id: number; normalized_payload: Record<string, unknown> }) =>
      apiFetch(`admin/quarantine/${id}/reprocess`, {
        method: 'POST',
        body: JSON.stringify({ normalized_payload }),
      }),
    onSuccess: invalidate,
  });

  const deleteRecord = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`admin/quarantine/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: invalidate,
  });

  return { updateRecord, reprocessRecord, deleteRecord };
}
