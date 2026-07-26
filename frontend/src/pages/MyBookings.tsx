import React, { useCallback, useEffect, useMemo, useState } from 'react';

import DatePicker from 'react-datepicker';

import 'react-datepicker/dist/react-datepicker.css';

import {

  ArrowRightLeft,

  Calendar,

  CalendarCheck,

  Loader2,

  Map as MapIcon,

  MessageSquare,

  RefreshCw,

  Sparkles,

  X,

} from 'lucide-react';

import { apiFetch, hasValidSession } from '../utils/api';

import { categoryBadgeClass } from '../utils/statusBadges';

import BookingOverviewMetrics, {
  type BookingMetricKey,
} from '../components/BookingOverviewMetrics';

import InteractionLogDrawer from '../components/InteractionLogDrawer';

import CounsellingSessionModal from '../components/CounsellingSessionModal';

import StudentJourneyPanel from '../components/StudentJourneyPanel';
import PeriodAgendaShell, { type PeriodDaySummary } from '../components/PeriodAgendaShell';



const toIsoDate = (value: Date): string => {

  const year = value.getFullYear();

  const month = String(value.getMonth() + 1).padStart(2, '0');

  const day = String(value.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;

};



const parseIsoDate = (value: string): Date => {

  const [year, month, day] = value.split('-').map(Number);

  return new Date(year, month - 1, day);

};



interface MyBooking {

  id: number;

  scheduled_time: string;

  admin_id: number | null;

  admin_name?: string | null;

  lead_id?: number | null;

  candidate_name: string;

  candidate_email?: string | null;

  candidate_phone?: string | null;

  status: 'PENDING' | 'SCHEDULED' | 'CANCELLED' | 'COMPLETED';

  notes?: string | null;

  current_location?: string | null;

  preferred_country?: string | null;

  course_interest?: string | null;

  status_definition_id?: number | null;

  status_stage_name?: string | null;

  status_category?: string | null;

  admission_stage?: string | null;

  admission_stage_label?: string | null;

  admission_stage_category?: string | null;

  session_status_label?: string | null;

  time_label: string;

  date_label: string;

  section: 'past' | 'today' | 'upcoming';

}



interface MyBookingsGroupedResponse {
  past: MyBooking[];
  today: MyBooking[];
  upcoming: MyBooking[];
  calendar_today: string;
  total_count: number;
  view_all_bookings: boolean;
}



interface AvailableAdmin {

  id: number;

  name: string;

  email: string;

}



interface CurrentUser {

  id: number;

}



interface ReassignModalState {

  booking: MyBooking;

  loading: boolean;

  submitting: boolean;

  admins: AvailableAdmin[];

}



interface JourneyPanelState {

  studentId: number;

  studentName: string;

}



const formatLocationCountry = (booking: MyBooking): string => {

  const location = (booking.current_location || '').trim();

  const country = (booking.preferred_country || '').trim();

  if (location && country) return `${location} → ${country}`;

  return location || country || '—';

};



const METRIC_LABELS: Record<BookingMetricKey, string> = {
  past: 'Past bookings',
  today: "Today's bookings",
  upcoming: 'Upcoming bookings',
};

type DateFilterMode = 'single' | 'multiple';

const localToday = (): Date => {
  const today = new Date();
  return new Date(today.getFullYear(), today.getMonth(), today.getDate());
};

const MyBookings: React.FC = () => {
  const [dateFilterMode, setDateFilterMode] = useState<DateFilterMode>('single');
  const [startDate, setStartDate] = useState<Date | null>(() => localToday());
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [calendarToday, setCalendarToday] = useState('');
  const [groupedBookings, setGroupedBookings] = useState<MyBookingsGroupedResponse | null>(null);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reassignModal, setReassignModal] = useState<ReassignModalState | null>(null);
  const [interactionBookingId, setInteractionBookingId] = useState<number | null>(null);
  const [sessionBooking, setSessionBooking] = useState<MyBooking | null>(null);
  const [journeyPanel, setJourneyPanel] = useState<JourneyPanelState | null>(null);
  const [activeMetric, setActiveMetric] = useState<BookingMetricKey>('today');
  const [periodFocusDate, setPeriodFocusDate] = useState<string | null>(null);

  const viewAllBookings = groupedBookings?.view_all_bookings ?? false;
  const isMultipleDates = dateFilterMode === 'multiple';
  const hasDateFilter = isMultipleDates ? Boolean(endDate) || Boolean(startDate) : Boolean(startDate);

  const overview = useMemo(
    () =>
      groupedBookings
        ? {
            past_count: groupedBookings.past.length,
            today_count: groupedBookings.today.length,
            upcoming_count: groupedBookings.upcoming.length,
            calendar_today: groupedBookings.calendar_today,
          }
        : null,
    [groupedBookings]
  );

  const loadBookings = useCallback(async (showSpinner = true) => {
    if (!hasValidSession()) return;

    try {
      if (showSpinner) setLoading(true);
      setError(null);

      const data = (await apiFetch('bookings/mine')) as MyBookingsGroupedResponse;
      setGroupedBookings(data);
      setCalendarToday(data.calendar_today);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load your bookings.');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!calendarToday || dateFilterMode !== 'single') return;
    setStartDate(prev => {
      // Align initial local today with the office calendar day from the API.
      if (toIsoDate(prev) === toIsoDate(localToday())) {
        return parseIsoDate(calendarToday);
      }
      return prev;
    });
  }, [calendarToday, dateFilterMode]);

  const bookings = useMemo(() => {
    if (!groupedBookings) return [];

    if (isMultipleDates && (startDate || endDate)) {
      const inRange = (booking: MyBooking): boolean => {
        const day = booking.scheduled_time.slice(0, 10);
        if (!day) return false;
        if (startDate && day < toIsoDate(startDate)) return false;
        if (endDate && day > toIsoDate(endDate)) return false;
        return true;
      };
      return [...groupedBookings.past, ...groupedBookings.today, ...groupedBookings.upcoming]
        .filter(inRange)
        .sort((a, b) => a.scheduled_time.localeCompare(b.scheduled_time));
    }

    const sectionBookings = groupedBookings[activeMetric] ?? [];
    if (!startDate) return sectionBookings;
    const selected = toIsoDate(startDate);
    return sectionBookings.filter(booking => booking.scheduled_time.startsWith(selected));
  }, [groupedBookings, activeMetric, isMultipleDates, startDate, endDate]);

  const bookingsByDay = useMemo(() => {
    const groups = new Map<string, { date: string; label: string; bookings: MyBooking[] }>();
    for (const booking of bookings) {
      const date = booking.scheduled_time.slice(0, 10);
      if (!date) continue;
      const existing = groups.get(date);
      if (existing) {
        existing.bookings.push(booking);
      } else {
        groups.set(date, {
          date,
          label:
            booking.date_label ||
            parseIsoDate(date).toLocaleDateString(undefined, {
              weekday: 'short',
              day: 'numeric',
              month: 'short',
            }),
          bookings: [booking],
        });
      }
    }
    return Array.from(groups.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [bookings]);

  const periodDaySummaries: PeriodDaySummary[] = useMemo(
    () =>
      bookingsByDay.map(group => ({
        date: group.date,
        label: group.label,
        count: group.bookings.length,
        bookedCount: group.bookings.filter(item => item.status === 'SCHEDULED').length,
        pendingCount: group.bookings.filter(item => item.status === 'PENDING').length,
      })),
    [bookingsByDay]
  );

  const periodStats = useMemo(() => {
    const scheduled = bookings.filter(item => item.status === 'SCHEDULED').length;
    const completed = bookings.filter(item => item.status === 'COMPLETED').length;
    const pending = bookings.filter(item => item.status === 'PENDING').length;
    return [
      { label: 'Total', value: bookings.length, tone: 'default' as const },
      { label: 'Scheduled', value: scheduled, tone: 'emerald' as const },
      { label: 'Completed', value: completed, tone: 'sky' as const },
      { label: 'Pending', value: pending, tone: 'amber' as const },
    ];
  }, [bookings]);

  const visiblePeriodDays = useMemo(() => {
    if (!periodFocusDate) return bookingsByDay;
    return bookingsByDay.filter(group => group.date === periodFocusDate);
  }, [bookingsByDay, periodFocusDate]);

  useEffect(() => {
    if (!isMultipleDates) {
      setPeriodFocusDate(null);
      return;
    }
    if (periodFocusDate && !bookingsByDay.some(group => group.date === periodFocusDate)) {
      setPeriodFocusDate(null);
    }
  }, [isMultipleDates, periodFocusDate, bookingsByDay]);

  useEffect(() => {
    if (!hasValidSession()) return;

    apiFetch('users/me')
      .then(user => setCurrentUserId((user as CurrentUser).id))
      .catch(() => setError('Failed to load your profile.'));
  }, []);

  useEffect(() => {
    loadBookings();
  }, [loadBookings]);

  const resolveTodayDate = useCallback((): Date => {
    if (calendarToday) return parseIsoDate(calendarToday);
    return localToday();
  }, [calendarToday]);

  const handleMetricClick = (metric: BookingMetricKey) => {
    setActiveMetric(metric);
    setDateFilterMode('single');
    setEndDate(null);
    if (metric === 'today') {
      setStartDate(resolveTodayDate());
    } else {
      // Past / upcoming overview cards must list the full section. Keeping the
      // currently selected calendar day (often "today") incorrectly filters the
      // section to zero rows while the metric still shows a non-zero count.
      setStartDate(null);
    }
  };

  const handleDateFilterModeChange = (mode: DateFilterMode) => {
    if (mode === dateFilterMode) return;
    setDateFilterMode(mode);
    if (mode === 'single') {
      setEndDate(null);
      setStartDate(prev => prev ?? resolveTodayDate());
    } else if (startDate && !endDate) {
      setEndDate(startDate);
    }
  };

  const handleStartDateChange = (date: Date | null) => {
    const next = date ?? resolveTodayDate();
    setStartDate(next);
    if (isMultipleDates && endDate && next > endDate) {
      setEndDate(next);
    }
    if (!isMultipleDates) {
      setEndDate(null);
      if (calendarToday) {
        const iso = toIsoDate(next);
        if (iso < calendarToday) setActiveMetric('past');
        else if (iso > calendarToday) setActiveMetric('upcoming');
        else setActiveMetric('today');
      }
    }
  };

  const handleEndDateChange = (date: Date | null) => {
    if (!isMultipleDates) return;
    setEndDate(date);
    if (date && startDate && date < startDate) {
      setStartDate(date);
    }
  };

  const clearDateFilter = () => {
    setDateFilterMode('single');
    setActiveMetric('today');
    setStartDate(resolveTodayDate());
    setEndDate(null);
  };

  const jumpToToday = () => {
    setActiveMetric('today');
    setDateFilterMode('single');
    setStartDate(resolveTodayDate());
    setEndDate(null);
  };

  const dateFilterLabel = useMemo(() => {
    if (!hasDateFilter) return METRIC_LABELS[activeMetric];
    if (isMultipleDates) {
      const startLabel = startDate
        ? startDate.toLocaleDateString(undefined, {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
          })
        : 'Any';
      const endLabel = endDate
        ? endDate.toLocaleDateString(undefined, {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
          })
        : 'Any';
      return `${startLabel} → ${endLabel}`;
    }
    return startDate
      ? startDate.toLocaleDateString(undefined, {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        })
      : METRIC_LABELS[activeMetric];
  }, [hasDateFilter, isMultipleDates, startDate, endDate, activeMetric]);

  const isToday = Boolean(
    !isMultipleDates && startDate && calendarToday && toIsoDate(startDate) === calendarToday
  );



  const openReassignModal = async (booking: MyBooking) => {

    if (!currentUserId || booking.status !== 'SCHEDULED') return;



    setReassignModal({

      booking,

      loading: true,

      submitting: false,

      admins: [],

    });



    try {

      const params = new URLSearchParams({

        time: booking.scheduled_time,

        exclude_booking_id: String(booking.id),

        exclude_admin_id: String(currentUserId),

      });

      const data = (await apiFetch(`admins/available?${params.toString()}`)) as {

        admins: AvailableAdmin[];

      };

      setReassignModal({

        booking,

        loading: false,

        submitting: false,

        admins: data.admins,

      });

    } catch (err) {

      setError(err instanceof Error ? err.message : 'Failed to load available admins.');

      setReassignModal(null);

    }

  };



  const handleReassign = async (targetAdminId: number) => {

    if (!reassignModal) return;

    try {

      setReassignModal(prev => (prev ? { ...prev, submitting: true } : prev));

      await apiFetch('bookings/mine/reassign', {

        method: 'POST',

        body: JSON.stringify({

          booking_id: reassignModal.booking.id,

          target_admin_id: targetAdminId,

        }),

      });

      setReassignModal(null);

      await Promise.all([loadBookings(false)]);

    } catch (err) {

      setError(err instanceof Error ? err.message : 'Failed to reassign booking.');

      setReassignModal(prev => (prev ? { ...prev, submitting: false } : prev));

    }

  };



  const renderStatusBadge = (booking: MyBooking) => {

    const label =

      booking.status_stage_name ||

      booking.admission_stage_label ||

      booking.session_status_label ||

      'Counselling';

    const category = booking.status_category || booking.admission_stage_category;

    return (

      <span

        className={`inline-flex items-center rounded-full border px-2.5 py-1 text-sm font-semibold ${categoryBadgeClass(

          category

        )}`}

      >

        {label}

      </span>

    );

  };



  const renderActions = (booking: MyBooking) => (

    <div className="flex items-center justify-end gap-2 flex-wrap">

      <button

        type="button"

        onClick={() => setInteractionBookingId(booking.id)}

        className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-sm font-semibold text-text-main hover:bg-accent/20"

      >

        <MessageSquare size={14} />

        View Interaction

      </button>

      {booking.lead_id ? (

        <button

          type="button"

          onClick={() =>

            setJourneyPanel({

              studentId: booking.lead_id!,

              studentName: booking.candidate_name,

            })

          }

          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-sm font-semibold text-slate-800 hover:bg-slate-100"

        >

          <MapIcon size={14} />

          View Journey

        </button>

      ) : null}

      <button

        type="button"

        onClick={() => setSessionBooking(booking)}

        className="inline-flex items-center gap-1 rounded-lg border border-violet-300 bg-violet-50 px-2.5 py-1.5 text-sm font-semibold text-violet-900 hover:bg-violet-100"

      >

        <Sparkles size={14} />

        Session

      </button>

      {booking.status === 'SCHEDULED' && booking.admin_id === currentUserId && (

        <button

          type="button"

          onClick={() => openReassignModal(booking)}

          className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-sm font-semibold text-text-main hover:bg-card"

        >

          <ArrowRightLeft size={14} />

          Reassign

        </button>

      )}

    </div>

  );



  return (

    <div className="absolute inset-0 min-h-0 overflow-hidden flex flex-col">

      <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4 md:p-5">
      <div className="space-y-4 pb-10">

      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">

        <div>

          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2">

            <CalendarCheck size={24} />

            My Bookings

          </h1>

          <p className="text-sm text-text-muted mt-1">
            {viewAllBookings
              ? 'All counselling sessions handled across the team. Use single or multiple dates, or the overview cards for past, today, and upcoming.'
              : 'Counselling sessions you have handled. Use single or multiple dates, or the overview cards for past, today, and upcoming.'}
          </p>

        </div>

        <button

          type="button"

          onClick={() => loadBookings()}

          disabled={loading}

          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm hover:bg-surface-bg disabled:opacity-60 self-start"

        >

          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />

          Refresh

        </button>

      </div>

      <div className="rounded-xl border border-border-subtle bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="text-sm font-semibold uppercase tracking-wide text-text-muted flex items-center gap-1.5 shrink-0">
            <Calendar size={14} />
            Date filter
          </span>
          <label className="inline-flex items-center gap-2 text-sm text-text-main cursor-pointer shrink-0">
            <input
              type="radio"
              name="my-bookings-date-mode"
              checked={!isMultipleDates}
              onChange={() => handleDateFilterModeChange('single')}
              className="accent-accent"
            />
            Single date
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-text-main cursor-pointer shrink-0">
            <input
              type="radio"
              name="my-bookings-date-mode"
              checked={isMultipleDates}
              onChange={() => handleDateFilterModeChange('multiple')}
              className="accent-accent"
            />
            Multiple dates
          </label>

          <div className="flex flex-nowrap items-center gap-2 shrink-0">
            <div className="shrink-0 [&_.react-datepicker-wrapper]:block [&_.react-datepicker__input-container]:block">
              <DatePicker
                selected={startDate}
                onChange={handleStartDateChange}
                selectsStart={isMultipleDates}
                startDate={startDate}
                endDate={isMultipleDates ? endDate : null}
                maxDate={isMultipleDates && endDate ? endDate : undefined}
                placeholderText={isMultipleDates ? 'Start date' : 'Select date'}
                dateFormat="EEE, d MMM yyyy"
                className="w-[200px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main"
                calendarClassName="nexus-roster-datepicker"
                popperClassName="nexus-datepicker-popper"
                portalId="nexus-datepicker-portal"
                withPortal
                popperPlacement="bottom-start"
                popperProps={{ strategy: 'fixed' }}
              />
            </div>
            <span className="text-sm text-text-muted shrink-0">to</span>
            <div className="shrink-0 [&_.react-datepicker-wrapper]:block [&_.react-datepicker__input-container]:block">
              <DatePicker
                selected={isMultipleDates ? endDate : null}
                onChange={handleEndDateChange}
                selectsEnd
                startDate={startDate}
                endDate={endDate}
                minDate={startDate || undefined}
                placeholderText="End date"
                dateFormat="EEE, d MMM yyyy"
                className="w-[200px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main disabled:opacity-50 disabled:cursor-not-allowed"
                calendarClassName="nexus-roster-datepicker"
                popperClassName="nexus-datepicker-popper"
                portalId="nexus-datepicker-portal"
                withPortal
                popperPlacement="bottom-start"
                popperProps={{ strategy: 'fixed' }}
                disabled={!isMultipleDates}
                isClearable={isMultipleDates}
              />
            </div>
          </div>

          {hasDateFilter ? (
            <button
              type="button"
              onClick={clearDateFilter}
              className="text-sm font-semibold text-accent hover:underline whitespace-nowrap shrink-0"
            >
              Clear dates
            </button>
          ) : null}
          {!isToday && !isMultipleDates ? (
            <button
              type="button"
              onClick={jumpToToday}
              className="text-sm font-semibold text-accent hover:underline whitespace-nowrap shrink-0"
            >
              Jump to today
            </button>
          ) : null}
          <span className="text-sm text-text-muted sm:ml-auto shrink-0">{dateFilterLabel}</span>
        </div>
      </div>



      {error && (

        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>

      )}



      <BookingOverviewMetrics

        overview={overview}

        activeMetric={activeMetric}

        loading={loading}

        onMetricClick={handleMetricClick}

      />



      <div className="rounded-2xl border border-border-subtle bg-card shrink-0">

        {loading ? (

          <div className="flex items-center justify-center py-16 text-text-muted">

            <Loader2 size={24} className="animate-spin mr-2" />

            Loading bookings…

          </div>

        ) : bookings.length === 0 ? (

          <div className="px-6 py-12 text-center">

            <Calendar size={28} className="mx-auto text-text-muted mb-3" />

            <p className="text-sm font-medium text-text-main">
              {hasDateFilter
                ? `No bookings for ${dateFilterLabel}`
                : `No ${METRIC_LABELS[activeMetric].toLowerCase()}`}
            </p>
            <p className="text-xs text-text-muted mt-1">
              {hasDateFilter
                ? isMultipleDates
                  ? 'Try another date range or clear the date filter.'
                  : `Try another date or clear the date filter to see all ${METRIC_LABELS[activeMetric].toLowerCase()}.`
                : viewAllBookings
                  ? 'Assigned counselling sessions will appear here once they are recorded.'
                  : 'Sessions you have handled will appear here once they are assigned to you.'}
            </p>

          </div>

        ) : isMultipleDates && hasDateFilter ? (
          <div className="p-4 md:p-5">
            <PeriodAgendaShell
              periodLabel={dateFilterLabel}
              totalCount={bookings.length}
              days={periodDaySummaries}
              activeDate={periodFocusDate}
              onSelectDate={setPeriodFocusDate}
              stats={periodStats}
              emptyMessage="No bookings in this date period."
            >
              <div className="space-y-4">
                {visiblePeriodDays.map(group => (
                  <section
                    key={group.date}
                    id={`my-bookings-day-${group.date}`}
                    className="rounded-xl border border-border-subtle overflow-hidden"
                  >
                    <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-surface-bg border-b border-border-subtle">
                      <div>
                        <h4 className="text-sm font-semibold text-text-main">{group.label}</h4>
                        <p className="text-[11px] text-text-muted">
                          {group.bookings.length} session{group.bookings.length === 1 ? '' : 's'}
                        </p>
                      </div>
                      <span className="text-[11px] font-semibold text-text-muted tabular-nums">
                        {group.date}
                      </span>
                    </div>
                    <div className="divide-y divide-border-subtle">
                      {group.bookings.map(booking => (
                        <div
                          key={booking.id}
                          className="flex flex-col lg:flex-row lg:items-center gap-3 px-4 py-3 hover:bg-surface-bg/40"
                        >
                          <div className="w-full lg:w-28 shrink-0">
                            <p className="text-sm font-bold text-text-main">{booking.time_label}</p>
                            <p className="text-[11px] text-text-muted mt-0.5">{booking.date_label}</p>
                          </div>
                          <div className="min-w-0 flex-1 space-y-1">
                            <p className="text-sm font-semibold text-text-main truncate">
                              {booking.candidate_name}
                            </p>
                            <p className="text-xs text-text-muted truncate">
                              {formatLocationCountry(booking)}
                              {booking.course_interest ? ` · ${booking.course_interest}` : ''}
                              {booking.admin_name ? ` · Counsellor: ${booking.admin_name}` : ''}
                            </p>
                          </div>
                          <div className="shrink-0">{renderStatusBadge(booking)}</div>
                          <div className="shrink-0 lg:ml-auto">{renderActions(booking)}</div>
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </PeriodAgendaShell>
          </div>
        ) : (

          <div className="overflow-x-auto">

            <table className="min-w-full text-sm">

              <thead className="bg-surface-bg/80 border-b border-border-subtle">

                <tr className="text-left text-sm font-semibold uppercase tracking-wide text-text-muted">

                  <th className="px-4 py-3">Candidate</th>
                  <th className="px-4 py-3">Counsellor</th>
                  <th className="px-4 py-3">Location &amp; Country</th>

                  <th className="px-4 py-3">Course Interest</th>

                  <th className="px-4 py-3">Current Status</th>

                  <th className="px-4 py-3">Date &amp; Time</th>

                  <th className="px-4 py-3 text-right">Actions</th>

                </tr>

              </thead>

              <tbody className="divide-y divide-border-subtle">

                {bookings.map(booking => (

                  <tr

                    key={booking.id}

                    className="hover:bg-surface-bg/40"

                  >

                    <td className="px-4 py-3 font-medium text-text-main">{booking.candidate_name}</td>
                    <td className="px-4 py-3 text-text-muted">{booking.admin_name || '—'}</td>
                    <td className="px-4 py-3 text-text-muted">{formatLocationCountry(booking)}</td>

                    <td className="px-4 py-3 text-text-muted">{booking.course_interest || '—'}</td>

                    <td className="px-4 py-3">{renderStatusBadge(booking)}</td>

                    <td className="px-4 py-3 text-text-muted whitespace-nowrap">

                      {booking.date_label} · {booking.time_label}

                    </td>

                    <td className="px-4 py-3">{renderActions(booking)}</td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        )}

      </div>



      <InteractionLogDrawer

        open={interactionBookingId !== null}

        bookingId={interactionBookingId}

        onClose={() => setInteractionBookingId(null)}

      />



      <CounsellingSessionModal

        open={sessionBooking !== null}

        bookingId={sessionBooking?.id ?? null}

        candidateName={sessionBooking?.candidate_name ?? ''}

        dateLabel={sessionBooking?.date_label}

        timeLabel={sessionBooking?.time_label}

        onClose={() => setSessionBooking(null)}

        onStatusUpdated={() => loadBookings(false)}

      />



      <StudentJourneyPanel

        open={journeyPanel !== null}

        studentId={journeyPanel?.studentId ?? null}

        studentName={journeyPanel?.studentName}

        onClose={() => setJourneyPanel(null)}

      />



      {reassignModal && (

        <div

          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40"

          onClick={() => !reassignModal.submitting && setReassignModal(null)}

        >

          <div

            className="w-full max-w-md rounded-2xl border border-border-subtle bg-card shadow-2xl overflow-hidden"

            onClick={event => event.stopPropagation()}

          >

            <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle bg-surface-bg">

              <div>

                <h3 className="text-lg font-semibold text-text-main">Reassign Booking</h3>

                <p className="text-sm text-text-muted mt-0.5">

                  {reassignModal.booking.candidate_name} · {reassignModal.booking.date_label} ·{' '}

                  {reassignModal.booking.time_label}

                </p>

              </div>

              <button

                type="button"

                disabled={reassignModal.submitting}

                onClick={() => setReassignModal(null)}

                className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main disabled:opacity-60"

                aria-label="Close reassign dialog"

              >

                <X size={16} />

              </button>

            </div>



            <div className="max-h-[360px] overflow-y-auto custom-scrollbar px-5 py-4">

              {reassignModal.loading ? (

                <div className="flex items-center justify-center py-10 text-text-muted">

                  <Loader2 size={20} className="animate-spin mr-2" />

                  Loading available admins…

                </div>

              ) : reassignModal.admins.length === 0 ? (

                <p className="text-sm text-text-muted text-center py-8">

                  No other admins are available for this time slot.

                </p>

              ) : (

                <div className="space-y-2">

                  {reassignModal.admins.map(admin => (

                    <button

                      key={admin.id}

                      type="button"

                      disabled={reassignModal.submitting}

                      onClick={() => handleReassign(admin.id)}

                      className="w-full text-left rounded-xl border border-border-subtle px-4 py-3 hover:bg-surface-bg disabled:opacity-60"

                    >

                      <div className="font-medium text-text-main">{admin.name}</div>

                      <div className="text-xs text-text-muted mt-0.5">{admin.email}</div>

                    </button>

                  ))}

                </div>

              )}

            </div>

          </div>

        </div>

      )}



      </div>
      </div>

    </div>

  );

};



export default MyBookings;

