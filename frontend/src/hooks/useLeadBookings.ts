import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export type LeadBookingSummary = {
  id: number;
  lead_id?: number | null;
  candidate_name?: string | null;
  date_label?: string | null;
  time_label?: string | null;
  status?: string | null;
  session_status_label?: string | null;
  admin_id?: number | null;
  admin_name?: string | null;
  scheduled_time?: string | null;
  section?: 'past' | 'today' | 'upcoming' | string | null;
};

export type LeadBookingsResponse = {
  lead_id: number;
  items: LeadBookingSummary[];
  total: number;
};

export function useLeadBookings(leadId: number | null) {
  return useQuery<LeadBookingsResponse>({
    queryKey: ['lead-bookings', leadId],
    queryFn: () => apiFetch(`leads/${leadId}/bookings`) as Promise<LeadBookingsResponse>,
    enabled: leadId != null && leadId > 0,
    staleTime: 30_000,
  });
}
