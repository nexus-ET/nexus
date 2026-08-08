import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  Briefcase,
  Calculator,
  ClipboardList,
  Compass,
  FlaskConical,
  GraduationCap,
  Link2,
  School,
  Sparkles,
  User,
} from 'lucide-react';
import CandidateProfilePanel from './CandidateProfilePanel';
import CounsellingSessionPanel from './CounsellingSessionPanel';
import FutureInsightsTab from './FutureInsightsTab';
import RoiCalculatorTab from './RoiCalculatorTab';
import type { ProfilePanelTab } from '../types/profilePanel';
import type { BookingRowForProfile } from '../utils/candidateProfileLoader';
import { apiFetch } from '../utils/api';

type TabId = 'session' | 'future_insights' | 'roi_calculator' | ProfilePanelTab;

const TAB_DEFS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'aspirations', label: 'Aspirations', icon: <Sparkles size={16} /> },
  { id: 'session', label: 'Session', icon: <Sparkles size={16} /> },
  { id: 'future_insights', label: 'Future Insights', icon: <Compass size={16} /> },
  { id: 'roi_calculator', label: 'ROI Calculator', icon: <Calculator size={16} /> },
  { id: 'university_shortlist', label: 'Shortlist', icon: <School size={16} /> },
  { id: 'profile', label: 'Personal', icon: <User size={16} /> },
  { id: 'academia', label: 'Academia', icon: <GraduationCap size={16} /> },
  { id: 'non_academia', label: 'Non-Academia', icon: <BookOpen size={16} /> },
  { id: 'digital_presence', label: 'Digital Presence', icon: <Link2 size={16} /> },
  { id: 'test_scores', label: 'Test Scores', icon: <ClipboardList size={16} /> },
  { id: 'work_projects', label: 'Professional', icon: <Briefcase size={16} /> },
  { id: 'projects_research', label: 'Projects & Research', icon: <FlaskConical size={16} /> },
];

function isProfileTab(tab: TabId): tab is ProfilePanelTab {
  return tab !== 'session' && tab !== 'future_insights' && tab !== 'roi_calculator';
}

type Props = {
  bookingId: number;
  candidateName: string;
  onStatusUpdated?: () => void | Promise<void>;
};

const IntakeSessionWorkspace: React.FC<Props> = ({
  bookingId,
  candidateName,
  onStatusUpdated,
}) => {
  const [tab, setTab] = useState<TabId>('aspirations');

  const bookingQuery = useQuery({
    queryKey: ['bookings', 'mine', bookingId, 'activity-for-profile'],
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
    <section className="rounded-xl border border-border-subtle bg-card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg/60 px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-violet-700">
            Sub-Process 1.1
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <BookOpen size={16} className="text-violet-700" />
            Initial Profile &amp; Background Assessment
          </h3>
          <p className="mt-0.5 text-xs text-text-muted">
            Session notes and student profile workspace.
          </p>
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-border-subtle px-2 pt-2 custom-scrollbar">
        {TAB_DEFS.map(item => {
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`inline-flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-3.5 py-2.5 text-base font-semibold transition-colors ${
                active
                  ? 'border-violet-600 bg-violet-50/80 text-violet-900'
                  : 'border-transparent text-text-muted hover:bg-surface-bg hover:text-text-main'
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </div>

      <div className={isProfileTab(tab) ? 'min-h-[28rem]' : 'p-4 space-y-4'}>
        {tab === 'session' && (
          <CounsellingSessionPanel
            bookingId={bookingId}
            candidateName={candidateName}
            onStatusUpdated={onStatusUpdated}
          />
        )}

        {tab === 'future_insights' && (
          <div className="-m-4 min-h-[28rem]">
            <FutureInsightsTab bookingId={bookingId} />
          </div>
        )}

        {tab === 'roi_calculator' && (
          <div className="-m-4 min-h-[28rem]">
            <RoiCalculatorTab bookingId={bookingId} />
          </div>
        )}

        {isProfileTab(tab) && (
          <CandidateProfilePanel
            key={bookingForProfile.id}
            booking={bookingForProfile}
            variant="embedded"
            activeTab={tab}
            onTabChange={next => setTab(next)}
            showTabBar={false}
          />
        )}
      </div>
    </section>
  );
};

export default IntakeSessionWorkspace;
