import React, { useCallback, useEffect, useMemo, useState } from 'react';

import DatePicker from 'react-datepicker';

import 'react-datepicker/dist/react-datepicker.css';

import {

  ArrowRightLeft,

  Calendar,

  CalendarCheck,

  Loader2,

  Map,

  MessageSquare,

  RefreshCw,

  Sparkles,

  X,

} from 'lucide-react';

import { apiFetch, hasValidSession } from '../utils/api';

import { categoryBadgeClass } from '../utils/statusBadges';

import CounsellingSessionPanel from '../components/CounsellingSessionPanel';

import BookingOverviewMetrics, {
  type BookingMetricKey,
} from '../components/BookingOverviewMetrics';

import SessionOutcomeSection from '../components/SessionOutcomeSection';

import InteractionLogDrawer from '../components/InteractionLogDrawer';

import StudentJourneyPanel from '../components/StudentJourneyPanel';



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



interface SessionModalState {

  booking: MyBooking;

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

const MyBookings: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [calendarToday, setCalendarToday] = useState('');
  const [groupedBookings, setGroupedBookings] = useState<MyBookingsGroupedResponse | null>(null);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reassignModal, setReassignModal] = useState<ReassignModalState | null>(null);
  const [interactionBookingId, setInteractionBookingId] = useState<number | null>(null);
  const [sessionModal, setSessionModal] = useState<SessionModalState | null>(null);
  const [journeyPanel, setJourneyPanel] = useState<JourneyPanelState | null>(null);
  const [activeMetric, setActiveMetric] = useState<BookingMetricKey>('today');

  const viewAllBookings = groupedBookings?.view_all_bookings ?? false;

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

  const bookings = useMemo(() => {
    if (!groupedBookings) return [];
    const sectionBookings = groupedBookings[activeMetric] ?? [];
    if (!selectedDate) return sectionBookings;
    return sectionBookings.filter(booking => booking.scheduled_time.startsWith(selectedDate));
  }, [groupedBookings, activeMetric, selectedDate]);



  useEffect(() => {

    if (!hasValidSession()) return;

    apiFetch('users/me')

      .then(user => setCurrentUserId((user as CurrentUser).id))

      .catch(() => setError('Failed to load your profile.'));

  }, []);



  useEffect(() => {
    loadBookings();
  }, [loadBookings]);

  const handleMetricClick = (metric: BookingMetricKey) => {
    setActiveMetric(metric);
    setSelectedDate(null);
  };

  const handleDateChange = (date: Date | null) => {
    if (!date) return;
    setSelectedDate(toIsoDate(date));
  };

  const jumpToToday = () => {
    if (calendarToday) {
      setActiveMetric('today');
      setSelectedDate(calendarToday);
    }
  };



  const selectedDateLabel = selectedDate
    ? parseIsoDate(selectedDate).toLocaleDateString(undefined, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : METRIC_LABELS[activeMetric];

  const isToday = Boolean(selectedDate && calendarToday && selectedDate === calendarToday);



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

        className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${categoryBadgeClass(

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

        className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-accent/20"

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

          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100"

        >

          <Map size={14} />

          View Journey

        </button>

      ) : null}

      <button

        type="button"

        onClick={() => setSessionModal({ booking })}

        className="inline-flex items-center gap-1 rounded-lg border border-violet-300 bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-900 hover:bg-violet-100"

      >

        <Sparkles size={14} />

        Session

      </button>

      {booking.status === 'SCHEDULED' && booking.admin_id === currentUserId && (

        <button

          type="button"

          onClick={() => openReassignModal(booking)}

          className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-card"

        >

          <ArrowRightLeft size={14} />

          Reassign

        </button>

      )}

    </div>

  );



  return (

    <div className="p-6 md:p-8 space-y-6">

      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">

        <div>

          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2">

            <CalendarCheck size={24} />

            My Bookings

          </h1>

          <p className="text-sm text-text-muted mt-1">
            {viewAllBookings
              ? 'All counselling sessions handled across the team. Use the overview cards to browse past, today, and upcoming bookings.'
              : 'Counselling sessions you have handled. Use the overview cards to browse past, today, and upcoming bookings.'}
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



      <div className="rounded-xl border border-border-subtle bg-card p-4 flex flex-col sm:flex-row sm:items-center gap-3">

        <label className="text-xs font-semibold uppercase tracking-wide text-text-muted flex items-center gap-1.5 whitespace-nowrap">

          <Calendar size={14} />

          Select date

        </label>

        <DatePicker

          selected={selectedDate ? parseIsoDate(selectedDate) : null}

          onChange={handleDateChange}

          dateFormat="EEE, d MMM yyyy"

          className="w-full sm:w-[220px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main"

          calendarClassName="nexus-roster-datepicker"

          popperClassName="nexus-datepicker-popper"

          portalId="nexus-datepicker-portal"

          popperPlacement="bottom-start"

          popperProps={{ strategy: 'fixed' }}

        />

        {selectedDate ? (
          <button
            type="button"
            onClick={() => setSelectedDate(null)}
            className="text-xs font-semibold text-accent hover:underline whitespace-nowrap"
          >
            Show all in section
          </button>
        ) : null}

        {!isToday && selectedDate ? (
          <button
            type="button"
            onClick={jumpToToday}
            className="text-xs font-semibold text-accent hover:underline whitespace-nowrap"
          >
            Jump to today
          </button>
        ) : null}

        <span className="text-sm text-text-muted sm:ml-auto">{selectedDateLabel}</span>

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



      <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">

        {loading ? (

          <div className="flex items-center justify-center py-16 text-text-muted">

            <Loader2 size={24} className="animate-spin mr-2" />

            Loading bookings…

          </div>

        ) : bookings.length === 0 ? (

          <div className="px-6 py-12 text-center">

            <Calendar size={28} className="mx-auto text-text-muted mb-3" />

            <p className="text-sm font-medium text-text-main">
              {selectedDate
                ? `No bookings on ${selectedDateLabel}`
                : `No ${METRIC_LABELS[activeMetric].toLowerCase()}`}
            </p>
            <p className="text-xs text-text-muted mt-1">
              {selectedDate
                ? `Try another date or clear the date filter to see all ${METRIC_LABELS[activeMetric].toLowerCase()}.`
                : viewAllBookings
                  ? 'Assigned counselling sessions will appear here once they are recorded.'
                  : 'Sessions you have handled will appear here once they are assigned to you.'}
            </p>

          </div>

        ) : (

          <div className="overflow-x-auto">

            <table className="min-w-full text-sm">

              <thead className="bg-surface-bg/80 border-b border-border-subtle">

                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-text-muted">

                  <th className="px-4 py-3">Candidate</th>
                  {viewAllBookings ? <th className="px-4 py-3">Counsellor</th> : null}
                  <th className="px-4 py-3">Location &amp; Country</th>

                  <th className="px-4 py-3">Course Interest</th>

                  <th className="px-4 py-3">Current Status</th>

                  <th className="px-4 py-3">Date &amp; Time</th>

                  <th className="px-4 py-3 text-right">Actions</th>

                </tr>

              </thead>

              <tbody className="divide-y divide-border-subtle">

                {bookings.map(booking => (

                  <tr key={booking.id} className="hover:bg-surface-bg/40">

                    <td className="px-4 py-3 font-medium text-text-main">{booking.candidate_name}</td>
                    {viewAllBookings ? (
                      <td className="px-4 py-3 text-text-muted">{booking.admin_name || '—'}</td>
                    ) : null}
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



      {sessionModal && (

        <div

          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40"

          role="dialog"

          aria-modal="true"

          aria-labelledby="counselling-session-title"

        >

          <div

            className="w-full max-w-6xl max-h-[92vh] rounded-2xl border border-border-subtle bg-card shadow-2xl flex flex-col overflow-hidden"

          >

            <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle bg-surface-bg shrink-0">

              <div>

                <h3

                  id="counselling-session-title"

                  className="text-lg font-semibold text-text-main flex items-center gap-2"

                >

                  <Sparkles size={18} className="text-violet-700" />

                  Counselling Session

                </h3>

                <p className="text-sm text-text-muted mt-0.5">

                  {sessionModal.booking.candidate_name} · {sessionModal.booking.date_label} ·{' '}

                  {sessionModal.booking.time_label}

                </p>

              </div>

              <button

                type="button"

                onClick={() => setSessionModal(null)}

                className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"

                aria-label="Close counselling session dialog"

              >

                <X size={16} />

              </button>

            </div>

            <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-5 py-5 space-y-8">

              <CounsellingSessionPanel

                bookingId={sessionModal.booking.id}

                candidateName={sessionModal.booking.candidate_name}

              />

              <div className="border-t border-border-subtle pt-6">

                <SessionOutcomeSection

                  bookingId={sessionModal.booking.id}

                  onStatusUpdated={() => loadBookings(false)}

                />

              </div>

            </div>

          </div>

        </div>

      )}

    </div>

  );

};



export default MyBookings;

