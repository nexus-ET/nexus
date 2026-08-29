import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';

export type SessionPurpose = {
  label: string;
  description: string;
};

export type BookingSessionConfig = {
  slot_duration_minutes: number;
  purposes: SessionPurpose[];
  office_hours_start: string;
  office_hours_end: string;
  allow_bookings: boolean;
};

export type CounsellorOption = {
  id: number;
  name: string;
  email: string;
  phone?: string | null;
};

export type CounsellorAvailabilitySlot = {
  start: string;
  label: string;
  available: boolean;
  reason?: string | null;
  booking_id?: number | null;
  candidate_name?: string | null;
  lead_id?: number | null;
};

export type CounsellorAvailabilityDay = {
  date: string;
  admin_id: number;
  slot_duration_minutes: number;
  day_status?: string;
  bookable?: boolean;
  slots: CounsellorAvailabilitySlot[];
};

export type CounsellorAvailabilityWeekResponse = {
  admin_id: number;
  start_date: string;
  slot_duration_minutes: number;
  days: CounsellorAvailabilityDay[];
};

export type BookingContactCheck = {
  email_taken: boolean;
  phone_taken: boolean;
  email_lead_id?: number | null;
  phone_lead_id?: number | null;
};

export type StaffBookingPayload = {
  scheduled_time: string;
  admin_id: number;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  lead_id?: number | null;
  session_purpose?: string | null;
  notes?: string | null;
  create_lead?: boolean;
};

export type StaffBookingNotifications = {
  whatsapp?: string | null;
  email?: string | null;
  whatsapp_admin?: string | null;
  email_admin?: string | null;
  push?: string | null;
};

export type StaffBookingResult = {
  id: number;
  scheduled_time: string;
  admin_id: number | null;
  admin_name?: string | null;
  candidate_name: string;
  status: string;
  notifications?: StaffBookingNotifications | null;
};

function normalizePurposes(raw: unknown): SessionPurpose[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(item => {
      if (typeof item === 'string') {
        return { label: item, description: 'Counselling session category' };
      }
      if (item && typeof item === 'object' && 'label' in item) {
        const row = item as { label?: string; description?: string };
        return {
          label: String(row.label || '').trim(),
          description: String(row.description || '').trim() || 'Counselling session category',
        };
      }
      return null;
    })
    .filter((item): item is SessionPurpose => Boolean(item?.label));
}

export function useBookingSessionConfig(enabled = true) {
  return useQuery({
    queryKey: ['booking-session-config'],
    queryFn: async () => {
      const data = await apiFetch<BookingSessionConfig & { purposes: unknown }>(
        'bookings/session-config'
      );
      return {
        ...data,
        purposes: normalizePurposes(data.purposes),
      } satisfies BookingSessionConfig;
    },
    enabled,
    staleTime: 10_000,
    refetchOnMount: 'always',
  });
}

export function useCounsellors(enabled = true) {
  return useQuery({
    queryKey: ['booking-counsellors'],
    queryFn: async () => {
      const data = await apiFetch<{ counsellors: CounsellorOption[] }>('bookings/counsellors');
      return data.counsellors;
    },
    enabled,
    staleTime: 60_000,
  });
}

export function useCounsellorAvailabilityWeek(options: {
  counsellorId: number | null;
  startDate: string | null;
  days?: number;
  enabled?: boolean;
}) {
  const counsellorId = options.counsellorId;
  const startDate = options.startDate;
  const days = options.days ?? 7;
  return useQuery({
    queryKey: ['counsellor-availability-week', counsellorId, startDate, days],
    queryFn: () =>
      apiFetch<CounsellorAvailabilityWeekResponse>(
        `bookings/availability-week?admin_id=${counsellorId}&start_date=${encodeURIComponent(
          startDate || ''
        )}&days=${days}`
      ),
    enabled:
      (options.enabled ?? true) &&
      counsellorId != null &&
      counsellorId > 0 &&
      Boolean(startDate),
    staleTime: 15_000,
  });
}

export function useBookingContactCheck(options: {
  email: string;
  phone: string;
  enabled?: boolean;
}) {
  const email = options.email.trim();
  const phone = options.phone.trim();
  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const phoneReady = phone.length >= 8;
  return useQuery({
    queryKey: ['booking-contact-check', email, phone],
    queryFn: () => {
      const params = new URLSearchParams();
      if (emailReady) params.set('email', email);
      if (phoneReady) params.set('phone', phone);
      return apiFetch<BookingContactCheck>(`bookings/contact-check?${params.toString()}`);
    },
    enabled: (options.enabled ?? true) && (emailReady || phoneReady),
    staleTime: 20_000,
  });
}

export async function createStaffBooking(payload: StaffBookingPayload) {
  return apiFetch<StaffBookingResult>('bookings/staff', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
