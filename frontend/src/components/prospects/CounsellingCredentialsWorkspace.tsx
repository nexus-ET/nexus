import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  Briefcase,
  ChevronDown,
  ClipboardList,
  FlaskConical,
  GraduationCap,
  Link2,
} from 'lucide-react';
import CandidateProfilePanel from '../CandidateProfilePanel';
import type { ProfilePanelTab } from '../../types/profilePanel';
import type { BookingRowForProfile } from '../../utils/candidateProfileLoader';
import { apiFetch } from '../../utils/api';
import { useCounsellingProcessNodes } from './CounsellingProcessStrip';

type TabId = Extract<
  ProfilePanelTab,
  | 'academia'
  | 'non_academia'
  | 'test_scores'
  | 'digital_presence'
  | 'work_projects'
  | 'projects_research'
>;

type GroupTabDef = {
  type: 'group';
  id: string;
  label: string;
  icon: React.ReactNode;
  children: Array<{ id: TabId; label: string; icon: React.ReactNode }>;
};

const TAB_NAV: GroupTabDef[] = [
  {
    type: 'group',
    id: 'credentials',
    label: 'CREDENTIALS',
    icon: <GraduationCap size={15} strokeWidth={2.25} />,
    children: [
      { id: 'academia', label: 'Academia', icon: <GraduationCap size={13} strokeWidth={2.25} /> },
      { id: 'non_academia', label: 'Non-Academia', icon: <BookOpen size={13} strokeWidth={2.25} /> },
      { id: 'test_scores', label: 'Test Scores', icon: <ClipboardList size={13} strokeWidth={2.25} /> },
      { id: 'digital_presence', label: 'Digital Presence', icon: <Link2 size={13} strokeWidth={2.25} /> },
    ],
  },
  {
    type: 'group',
    id: 'experience',
    label: 'EXPERIENCE',
    icon: <Briefcase size={15} strokeWidth={2.25} />,
    children: [
      { id: 'work_projects', label: 'Professional', icon: <Briefcase size={13} strokeWidth={2.25} /> },
      {
        id: 'projects_research',
        label: 'Projects & Research',
        icon: <FlaskConical size={13} strokeWidth={2.25} />,
      },
    ],
  },
];

function findGroupForTab(tab: TabId): GroupTabDef | undefined {
  return TAB_NAV.find(item => item.children.some(child => child.id === tab));
}

type Props = {
  bookingId: number;
  candidateName: string;
};

const CounsellingCredentialsWorkspace: React.FC<Props> = ({ bookingId, candidateName }) => {
  const [tab, setTab] = useState<TabId>('academia');
  const activeGroup = findGroupForTab(tab);
  const nodes = useCounsellingProcessNodes();
  const subprocessTitle =
    nodes.find(node => node.code === '1.3')?.title || 'Destination shortlist discussion';

  const bookingQuery = useQuery({
    queryKey: ['bookings', 'mine', bookingId, 'activity-for-credentials'],
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
            Sub-Process 1.3
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
              <GraduationCap size={14} />
            </span>
            {subprocessTitle}
          </h3>
        </div>
      </div>

      <div className="border-b border-border-subtle bg-card">
        <nav
          className="flex gap-0.5 overflow-x-auto overflow-y-hidden px-2 pt-2 custom-scrollbar"
          aria-label="Credentials and experience workspace"
          role="tablist"
        >
          {TAB_NAV.map(item => {
            const active = item.children.some(child => child.id === tab);
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                aria-haspopup="true"
                onClick={() => {
                  const stillInGroup = item.children.some(child => child.id === tab);
                  setTab(stillInGroup ? tab : item.children[0].id);
                }}
                className={`group relative inline-flex shrink-0 items-center gap-2 rounded-t-lg px-3.5 py-2.5 text-base font-semibold tracking-wide transition-colors ${
                  active
                    ? 'bg-surface-bg text-accent'
                    : 'text-text-muted hover:bg-surface-bg/70 hover:text-text-main'
                }`}
              >
                <span
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
                    active
                      ? 'bg-accent text-text-dark-bg'
                      : 'bg-surface-bg text-text-muted group-hover:bg-card group-hover:text-accent'
                  }`}
                >
                  {item.icon}
                </span>
                <span className="whitespace-nowrap">{item.label}</span>
                <ChevronDown
                  size={14}
                  className={`opacity-70 transition-transform ${active ? 'rotate-180' : ''}`}
                />
                <span
                  className={`pointer-events-none absolute inset-x-2 -bottom-px h-0.5 rounded-full transition-opacity ${
                    active ? 'bg-accent opacity-100' : 'opacity-0'
                  }`}
                />
              </button>
            );
          })}
        </nav>

        {activeGroup ? (
          <div className="flex flex-wrap items-center gap-3 border-t border-border-subtle/70 bg-surface-bg px-3 py-2.5">
            <div className="hidden items-center gap-2 sm:flex">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                {activeGroup.label}
              </span>
              <span className="h-3 w-px bg-border-subtle" aria-hidden />
            </div>
            <div
              className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-card p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]"
              role="tablist"
              aria-label={`${activeGroup.label} sections`}
            >
              {activeGroup.children.map(child => {
                const active = tab === child.id;
                return (
                  <button
                    key={child.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setTab(child.id)}
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
                      active
                        ? 'bg-accent text-text-dark-bg shadow-sm'
                        : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
                    }`}
                  >
                    {child.icon}
                    {child.label}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      <div className="min-h-[28rem]">
        <CandidateProfilePanel
          key={bookingForProfile.id}
          booking={bookingForProfile}
          variant="embedded"
          activeTab={tab}
          onTabChange={next => {
            if (
              next === 'academia' ||
              next === 'non_academia' ||
              next === 'test_scores' ||
              next === 'digital_presence' ||
              next === 'work_projects' ||
              next === 'projects_research'
            ) {
              setTab(next);
            }
          }}
          showTabBar={false}
        />
      </div>
    </section>
  );
};

export default CounsellingCredentialsWorkspace;
