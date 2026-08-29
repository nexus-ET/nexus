import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Receipt } from 'lucide-react';
import RegistrationTab from '../RegistrationTab';
import type { BookingRowForProfile } from '../../utils/candidateProfileLoader';
import { apiFetch } from '../../utils/api';
import { useCounsellingProcessNodes } from './CounsellingProcessStrip';

type Props = {
  bookingId: number;
  candidateName: string;
  onStatusUpdated?: () => void | Promise<void>;
};

const CounsellingBillingWorkspace: React.FC<Props> = ({
  bookingId,
  candidateName,
  onStatusUpdated,
}) => {
  const nodes = useCounsellingProcessNodes();
  const subprocessTitle =
    nodes.find(node => node.code === '1.2')?.title || 'Billing';

  const bookingQuery = useQuery({
    queryKey: ['bookings', 'mine', bookingId, 'activity-for-billing'],
    queryFn: async () => {
      const data = (await apiFetch(`bookings/mine/${bookingId}/activity`)) as {
        booking?: BookingRowForProfile;
        candidate_name?: string;
      };
      const booking = data.booking;
      return {
        id: bookingId,
        candidate_name: booking?.candidate_name || data.candidate_name || candidateName,
        lead_id: booking?.lead_id ?? null,
        candidate_email: booking?.candidate_email ?? null,
        candidate_phone: booking?.candidate_phone ?? null,
        current_location: booking?.current_location ?? null,
        preferred_country: booking?.preferred_country ?? null,
        course_interest: booking?.course_interest ?? null,
        status_definition_id: booking?.status_definition_id ?? null,
        status_stage_name: booking?.status_stage_name ?? null,
        status_category: booking?.status_category ?? null,
        date_label: booking?.date_label ?? null,
        time_label: booking?.time_label ?? null,
        status: booking?.status ?? null,
        session_status_label: booking?.session_status_label ?? null,
        admin_id: booking?.admin_id ?? null,
        admin_name: booking?.admin_name ?? null,
        scheduled_time: booking?.scheduled_time ?? null,
      } satisfies BookingRowForProfile;
    },
    staleTime: 60_000,
  });

  const bookingForProfile: BookingRowForProfile = useMemo(
    () =>
      bookingQuery.data ?? {
        id: bookingId,
        candidate_name: candidateName,
      },
    [bookingQuery.data, bookingId, candidateName]
  );

  return (
    <section className="overflow-hidden rounded-xl border border-border-subtle bg-card shadow-[0_1px_0_rgba(50,47,134,0.04)]">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border-subtle bg-gradient-to-r from-accent/[0.06] via-surface-bg to-surface-bg px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent/70">
            Sub-Process 1.2
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
              <Receipt size={14} />
            </span>
            {subprocessTitle}
          </h3>
        </div>
      </div>

      <div className="border-b border-border-subtle bg-card">
        <nav
          className="flex gap-0.5 overflow-x-auto overflow-y-hidden px-2 pt-2 custom-scrollbar"
          aria-label="Candidate registration workspace"
          role="tablist"
        >
          <button
            type="button"
            role="tab"
            aria-selected
            className="group relative inline-flex shrink-0 items-center gap-2 rounded-t-lg bg-surface-bg px-3.5 py-2.5 text-base font-semibold tracking-wide text-accent"
          >
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-accent text-text-dark-bg">
              <Receipt size={15} strokeWidth={2.25} />
            </span>
            <span className="whitespace-nowrap">CANDIDATE REGISTRATION</span>
            <span className="pointer-events-none absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent opacity-100" />
          </button>
        </nav>
      </div>

      <div className="-mt-px flex min-h-[28rem] flex-col">
        <RegistrationTab
          booking={bookingForProfile}
          onStatusUpdated={() => {
            void onStatusUpdated?.();
          }}
        />
      </div>
    </section>
  );
};

export default CounsellingBillingWorkspace;
