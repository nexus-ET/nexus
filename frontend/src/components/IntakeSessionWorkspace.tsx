import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  Calculator,
  ChevronDown,
  Compass,
  NotebookPen,
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

type TabId =
  | 'session'
  | 'future_insights'
  | 'roi_calculator'
  | ProfilePanelTab;

type LeafTabDef = {
  type: 'leaf';
  id: TabId;
  label: string;
  icon: React.ReactNode;
};

type GroupTabDef = {
  type: 'group';
  id: string;
  label: string;
  icon: React.ReactNode;
  children: Array<{ id: TabId; label: string; icon: React.ReactNode }>;
};

type TabNavItem = LeafTabDef | GroupTabDef;

const TAB_NAV: TabNavItem[] = [
  { type: 'leaf', id: 'session', label: 'SESSION', icon: <NotebookPen size={15} strokeWidth={2.25} /> },
  {
    type: 'group',
    id: 'profile',
    label: 'PROFILE',
    icon: <User size={15} strokeWidth={2.25} />,
    children: [
      { id: 'aspirations', label: 'Aspirations', icon: <Sparkles size={13} strokeWidth={2.25} /> },
      { id: 'profile', label: 'Personal', icon: <User size={13} strokeWidth={2.25} /> },
    ],
  },
  {
    type: 'group',
    id: 'discovery',
    label: 'DISCOVERY',
    icon: <Compass size={15} strokeWidth={2.25} />,
    children: [
      { id: 'university_shortlist', label: 'Shortlist', icon: <School size={13} strokeWidth={2.25} /> },
      { id: 'future_insights', label: 'Future Insights', icon: <Compass size={13} strokeWidth={2.25} /> },
    ],
  },
  {
    type: 'leaf',
    id: 'roi_calculator',
    label: 'ROI CALCULATOR',
    icon: <Calculator size={15} strokeWidth={2.25} />,
  },
];

function findGroupForTab(tab: TabId): GroupTabDef | undefined {
  return TAB_NAV.find(
    (item): item is GroupTabDef =>
      item.type === 'group' && item.children.some(child => child.id === tab)
  );
}

function isProfileTab(tab: TabId): tab is Exclude<ProfilePanelTab, 'billing'> {
  return (
    tab !== 'session' &&
    tab !== 'future_insights' &&
    tab !== 'roi_calculator'
  );
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
  const [tab, setTab] = useState<TabId>('session');
  const activeGroup = findGroupForTab(tab);

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

  const selectTopTab = (item: TabNavItem) => {
    if (item.type === 'group') {
      const stillInGroup = item.children.some(child => child.id === tab);
      setTab(stillInGroup ? tab : item.children[0].id);
      return;
    }
    setTab(item.id);
  };

  return (
    <section className="overflow-hidden rounded-xl border border-border-subtle bg-card shadow-[0_1px_0_rgba(50,47,134,0.04)]">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border-subtle bg-gradient-to-r from-accent/[0.06] via-surface-bg to-surface-bg px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent/70">
            Sub-Process 1.1
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
              <BookOpen size={14} />
            </span>
            Initial Profile &amp; Background Assessment
          </h3>
        </div>
      </div>

      <div className="border-b border-border-subtle bg-card">
        <nav
          className="flex gap-0.5 overflow-x-auto overflow-y-hidden px-2 pt-2 custom-scrollbar"
          aria-label="Student workspace"
          role="tablist"
        >
          {TAB_NAV.map(item => {
            const active =
              item.type === 'group'
                ? item.children.some(child => child.id === tab)
                : tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                aria-haspopup={item.type === 'group' ? 'true' : undefined}
                onClick={() => selectTopTab(item)}
                className={`group relative inline-flex shrink-0 items-center gap-2 rounded-t-lg px-3.5 py-2.5 text-base font-semibold transition-colors ${
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
                <span
                  className={`whitespace-nowrap ${
                    item.type === 'group' ||
                    item.id === 'roi_calculator' ||
                    item.id === 'session'
                      ? 'tracking-wide'
                      : ''
                  }`}
                >
                  {item.label}
                </span>
                {item.type === 'group' ? (
                  <ChevronDown
                    size={14}
                    className={`opacity-70 transition-transform ${active ? 'rotate-180' : ''}`}
                  />
                ) : null}
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

      <div className={isProfileTab(tab) ? 'min-h-[28rem]' : 'space-y-4 p-4'}>
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
