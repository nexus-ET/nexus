import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import {
  ArrowRightLeft,
  Bot,
  Calendar,
  CalendarCheck,
  ChevronLeft,
  ChevronRight,
  History,
  Loader2,
  Mail,
  MessageSquare,
  Phone,
  RefreshCw,
  UserPlus,
  UserRound,
  X,
} from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';

type ViewMode = 'active' | 'past';

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

const getBookingDateKey = (booking: MyBooking): string => toIsoDate(new Date(booking.scheduled_time));

const sortDateKeys = (keys: string[]): string[] => [...keys].sort((a, b) => a.localeCompare(b));

const formatSelectedDateLabel = (iso: string): string =>
  parseIsoDate(iso).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

const groupBookingsByDate = (items: MyBooking[]): Map<string, MyBooking[]> => {
  const grouped = new Map<string, MyBooking[]>();
  for (const booking of items) {
    const key = getBookingDateKey(booking);
    const existing = grouped.get(key) ?? [];
    existing.push(booking);
    grouped.set(key, existing);
  }
  for (const [key, dayBookings] of grouped) {
    dayBookings.sort(
      (a, b) => new Date(a.scheduled_time).getTime() - new Date(b.scheduled_time).getTime()
    );
    grouped.set(key, dayBookings);
  }
  return grouped;
};

type CommunicationParticipant = 'candidate' | 'ai_agent' | 'handoff_admin' | 'system';

interface MyBooking {
  id: number;
  scheduled_time: string;
  admin_id: number | null;
  admin_name?: string | null;
  lead_id?: number | null;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  candidate_stage?: string | null;
  candidate_stage_label?: string | null;
  status: 'PENDING' | 'SCHEDULED' | 'CANCELLED';
  notes?: string | null;
  time_label: string;
  date_label: string;
  section: 'past' | 'today' | 'upcoming';
}

interface MyBookingsResponse {
  past: MyBooking[];
  today: MyBooking[];
  upcoming: MyBooking[];
  calendar_today: string;
  total_count: number;
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

interface BookingCommunicationMessage {
  id: number | string;
  participant: CommunicationParticipant;
  participant_label: string;
  text: string;
  created_at: string;
  media_url?: string | null;
  file_name?: string | null;
}

interface BookingCommunicationsResponse {
  booking_id: number;
  lead_id?: number | null;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  candidate_stage?: string | null;
  candidate_stage_label?: string | null;
  admin_name?: string | null;
  message_count: number;
  messages: BookingCommunicationMessage[];
}

interface CommunicationsModalState {
  booking: MyBooking;
  loading: boolean;
  data: BookingCommunicationsResponse | null;
}

interface DateNavigatedSectionProps {
  title: string;
  description: string;
  emptyMessage: string;
  noDateMessage: string;
  jumpLabel: string;
  bookings: MyBooking[];
  selectedDate: string;
  onSelectedDateChange: (iso: string) => void;
  defaultDate: (dateKeys: string[]) => string | null;
  renderCard: (booking: MyBooking) => React.ReactNode;
}

const DateNavigatedBookingSection: React.FC<DateNavigatedSectionProps> = ({
  title,
  description,
  emptyMessage,
  noDateMessage,
  jumpLabel,
  bookings,
  selectedDate,
  onSelectedDateChange,
  defaultDate,
  renderCard,
}) => {
  const grouped = useMemo(() => groupBookingsByDate(bookings), [bookings]);
  const dateKeys = useMemo(() => sortDateKeys([...grouped.keys()]), [grouped]);
  const highlightDates = useMemo(
    () => [{ 'highlighted-custom-booking': dateKeys.map(parseIsoDate) }],
    [dateKeys]
  );

  useEffect(() => {
    if (dateKeys.length === 0) return;
    if (!selectedDate || !dateKeys.includes(selectedDate)) {
      const fallback = defaultDate(dateKeys);
      if (fallback) onSelectedDateChange(fallback);
    }
  }, [dateKeys, defaultDate, onSelectedDateChange, selectedDate]);

  if (bookings.length === 0) {
    return (
      <section className="space-y-3">
        <div>
          <h3 className="text-base font-semibold text-text-main">{title}</h3>
          <p className="text-xs text-text-muted mt-0.5">{description}</p>
        </div>
        <p className="text-sm text-text-muted italic rounded-xl border border-dashed border-border-subtle px-4 py-6">
          {emptyMessage}
        </p>
      </section>
    );
  }

  const currentIndex = selectedDate ? dateKeys.indexOf(selectedDate) : -1;
  const dayBookings = selectedDate ? grouped.get(selectedDate) ?? [] : [];
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex >= 0 && currentIndex < dateKeys.length - 1;

  const goToRelativeDate = (offset: number) => {
    if (currentIndex < 0) return;
    const nextIndex = currentIndex + offset;
    if (nextIndex >= 0 && nextIndex < dateKeys.length) {
      onSelectedDateChange(dateKeys[nextIndex]);
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-text-main">{title}</h3>
        <p className="text-xs text-text-muted mt-0.5">{description}</p>
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface-bg/70 p-4 space-y-4">
        <div className="flex flex-col xl:flex-row xl:items-center gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => goToRelativeDate(-1)}
              disabled={!hasPrev}
              className="inline-flex items-center justify-center rounded-lg border border-border-subtle bg-card p-2 text-text-main hover:bg-surface-bg disabled:opacity-40 disabled:cursor-not-allowed"
              title="Previous date with bookings"
              aria-label="Previous date with bookings"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              onClick={() => goToRelativeDate(1)}
              disabled={!hasNext}
              className="inline-flex items-center justify-center rounded-lg border border-border-subtle bg-card p-2 text-text-main hover:bg-surface-bg disabled:opacity-40 disabled:cursor-not-allowed"
              title="Next date with bookings"
              aria-label="Next date with bookings"
            >
              <ChevronRight size={18} />
            </button>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center gap-2 flex-1">
            <label className="text-xs font-semibold uppercase tracking-wide text-text-muted whitespace-nowrap flex items-center gap-1.5">
              <Calendar size={14} />
              Select date
            </label>
            <DatePicker
              selected={selectedDate ? parseIsoDate(selectedDate) : null}
              onChange={date => {
                if (date) onSelectedDateChange(toIsoDate(date));
              }}
              highlightDates={highlightDates}
              dateFormat="EEE, d MMM yyyy"
              className="w-full sm:w-[220px] rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              calendarClassName="nexus-roster-datepicker"
              popperClassName="nexus-datepicker-popper"
              portalId="nexus-datepicker-portal"
              popperPlacement="bottom-start"
              popperProps={{ strategy: 'fixed' }}
            />
            <button
              type="button"
              onClick={() => {
                const fallback = defaultDate(dateKeys);
                if (fallback) onSelectedDateChange(fallback);
              }}
              className="text-xs font-semibold text-accent hover:underline whitespace-nowrap self-start sm:self-auto"
            >
              {jumpLabel}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 font-semibold text-text-main">
            {dayBookings.length} session{dayBookings.length === 1 ? '' : 's'} on selected date
          </span>
          {currentIndex >= 0 && dateKeys.length > 1 && (
            <span className="text-text-muted">
              Date {currentIndex + 1} of {dateKeys.length} with bookings
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 text-text-muted">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent/30 border border-accent/40" />
            Highlighted days have bookings
          </span>
        </div>

        {selectedDate && (
          <p className="text-sm font-medium text-text-main">{formatSelectedDateLabel(selectedDate)}</p>
        )}
      </div>

      {dayBookings.length === 0 ? (
        <p className="text-sm text-text-muted italic rounded-xl border border-dashed border-border-subtle px-4 py-6">
          {noDateMessage}
        </p>
      ) : (
        <div className="space-y-3">{dayBookings.map(booking => renderCard(booking))}</div>
      )}
    </section>
  );
};

const sectionMeta = {
  today: {
    title: "Today's Bookings",
    description: 'Sessions scheduled for today.',
    empty: 'No bookings assigned to you for today.',
  },
  upcoming: {
    title: 'Upcoming Bookings',
    description: 'Browse future sessions by date using the calendar and navigation controls.',
    empty: 'No upcoming bookings assigned to you.',
    noDate: 'No bookings on this date. Pick a highlighted day or use the previous/next controls.',
    jump: 'Jump to next booked date',
  },
} as const;

const pastSectionMeta = {
  title: 'Past Interviews',
  description: 'Browse past interviews by date. View messages and current candidate status.',
  empty: 'No past interviews yet. Completed sessions assigned to you will appear here.',
  noDate: 'No interviews on this date. Pick a highlighted day or use the previous/next controls.',
  jump: 'Jump to most recent interview',
};

const participantStyles: Record<
  CommunicationParticipant,
  { badge: string; bubble: string; icon: React.ReactNode }
> = {
  candidate: {
    badge: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    bubble: 'bg-emerald-50 border-emerald-200 text-emerald-950',
    icon: <UserRound size={12} />,
  },
  ai_agent: {
    badge: 'bg-sky-100 text-sky-800 border-sky-200',
    bubble: 'bg-sky-50 border-sky-200 text-sky-950',
    icon: <Bot size={12} />,
  },
  handoff_admin: {
    badge: 'bg-amber-100 text-amber-900 border-amber-200',
    bubble: 'bg-amber-50 border-amber-200 text-amber-950',
    icon: <UserPlus size={12} />,
  },
  system: {
    badge: 'bg-slate-100 text-slate-700 border-slate-200',
    bubble: 'bg-slate-50 border-slate-200 text-slate-800',
    icon: <MessageSquare size={12} />,
  },
};

const stageBadgeClass = (stage?: string | null): string => {
  switch (stage) {
    case 'AI_ACTIVE':
      return 'bg-sky-100 text-sky-800 border-sky-200';
    case 'HANDOFF':
      return 'bg-amber-100 text-amber-900 border-amber-200';
    case 'ARCHIVE':
      return 'bg-slate-100 text-slate-700 border-slate-200';
    default:
      return 'bg-surface-bg text-text-muted border-border-subtle';
  }
};

const formatCommunicationTime = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const MyBookings: React.FC = () => {
  const [viewMode, setViewMode] = useState<ViewMode>('active');
  const [bookings, setBookings] = useState<MyBookingsResponse>({
    past: [],
    today: [],
    upcoming: [],
    calendar_today: '',
    total_count: 0,
  });
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reassignModal, setReassignModal] = useState<ReassignModalState | null>(null);
  const [communicationsModal, setCommunicationsModal] = useState<CommunicationsModalState | null>(null);
  const [upcomingSelectedDate, setUpcomingSelectedDate] = useState('');
  const [pastSelectedDate, setPastSelectedDate] = useState('');
  const communicationsEndRef = useRef<HTMLDivElement | null>(null);

  const defaultUpcomingDate = useCallback((dateKeys: string[]) => dateKeys[0] ?? null, []);
  const defaultPastDate = useCallback((dateKeys: string[]) => dateKeys[dateKeys.length - 1] ?? null, []);

  const loadBookings = useCallback(async (showSpinner = true) => {
    if (!hasValidSession()) return;
    try {
      if (showSpinner) setLoading(true);
      setError(null);
      const data = (await apiFetch('bookings/mine')) as MyBookingsResponse;
      setBookings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load your bookings.');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      if (!hasValidSession()) return;
      try {
        const user = (await apiFetch('users/me')) as CurrentUser;
        setCurrentUserId(user.id);
      } catch {
        setError('Failed to load your profile.');
      }
      await loadBookings();
    };
    bootstrap();
  }, [loadBookings]);

  useEffect(() => {
    if (communicationsModal && !communicationsModal.loading) {
      communicationsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [communicationsModal]);

  const openReassignModal = async (booking: MyBooking) => {
    if (!currentUserId) return;

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

  const openCommunicationsModal = async (booking: MyBooking) => {
    setCommunicationsModal({ booking, loading: true, data: null });
    try {
      const data = (await apiFetch(
        `bookings/mine/${booking.id}/communications`
      )) as BookingCommunicationsResponse;
      setCommunicationsModal({ booking, loading: false, data });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation history.');
      setCommunicationsModal(null);
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
      await loadBookings(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reassign booking.');
      setReassignModal(prev => (prev ? { ...prev, submitting: false } : prev));
    }
  };

  const renderStageBadge = (
    stage?: string | null,
    label?: string | null
  ) => (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${stageBadgeClass(stage)}`}
    >
      {label || 'Status unknown'}
    </span>
  );

  const renderActiveBookingCard = (booking: MyBooking) => (
    <div
      key={booking.id}
      className="rounded-xl border border-border-subtle bg-card p-4 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4"
    >
      <div className="space-y-2 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-bg px-2.5 py-1 text-xs font-semibold text-text-main">
            <UserRound size={12} />
            {booking.candidate_name}
          </span>
          <span className="text-xs text-text-muted">
            {booking.date_label} · {booking.time_label}
          </span>
        </div>

        <div className="flex flex-wrap gap-3 text-xs text-text-muted">
          {booking.candidate_phone && (
            <span className="inline-flex items-center gap-1">
              <Phone size={12} />
              {booking.candidate_phone}
            </span>
          )}
          {booking.candidate_email && (
            <span className="inline-flex items-center gap-1">
              <Mail size={12} />
              {booking.candidate_email}
            </span>
          )}
        </div>

        {booking.notes && (
          <p className="text-xs text-text-muted border-t border-border-subtle/60 pt-2">{booking.notes}</p>
        )}
      </div>

      <button
        type="button"
        onClick={() => openReassignModal(booking)}
        className="inline-flex items-center justify-center gap-2 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-xs font-semibold text-text-main hover:bg-card shrink-0"
      >
        <ArrowRightLeft size={14} />
        Reassign
      </button>
    </div>
  );

  const renderPastBookingCard = (booking: MyBooking) => (
    <div
      key={booking.id}
      className="rounded-xl border border-border-subtle bg-card p-4 flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4"
    >
      <div className="space-y-3 min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-bg px-2.5 py-1 text-xs font-semibold text-text-main">
                <UserRound size={12} />
                {booking.candidate_name}
              </span>
              {renderStageBadge(booking.candidate_stage, booking.candidate_stage_label)}
            </div>
            <p className="text-xs text-text-muted mt-2">
              Interviewed on {booking.date_label} · {booking.time_label}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-3 text-xs text-text-muted">
          {booking.candidate_phone && (
            <span className="inline-flex items-center gap-1">
              <Phone size={12} />
              {booking.candidate_phone}
            </span>
          )}
          {booking.candidate_email && (
            <span className="inline-flex items-center gap-1">
              <Mail size={12} />
              {booking.candidate_email}
            </span>
          )}
        </div>

        {booking.notes && (
          <p className="text-xs text-text-muted border-t border-border-subtle/60 pt-2">{booking.notes}</p>
        )}
      </div>

      <button
        type="button"
        onClick={() => openCommunicationsModal(booking)}
        className="inline-flex items-center justify-center gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-xs font-semibold text-text-main hover:bg-accent/20 shrink-0"
      >
        <MessageSquare size={14} />
        View Conversation
      </button>
    </div>
  );

  const renderActiveSection = (section: keyof typeof sectionMeta, items: MyBooking[]) => {
    const meta = sectionMeta[section];
    return (
      <section className="space-y-3">
        <div>
          <h3 className="text-base font-semibold text-text-main">{meta.title}</h3>
          <p className="text-xs text-text-muted mt-0.5">{meta.description}</p>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-text-muted italic rounded-xl border border-dashed border-border-subtle px-4 py-6">
            {meta.empty}
          </p>
        ) : (
          <div className="space-y-3">{items.map(booking => renderActiveBookingCard(booking))}</div>
        )}
      </section>
    );
  };

  const activeCount = bookings.today.length + bookings.upcoming.length;
  const pastCount = bookings.past.length;

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2">
            <CalendarCheck size={24} />
            My Bookings
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Manage upcoming sessions and review candidates you have previously interviewed.
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

      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-xl border border-border-subtle bg-surface-bg p-1">
          <button
            type="button"
            onClick={() => setViewMode('active')}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
              viewMode === 'active'
                ? 'bg-card text-text-main shadow-sm'
                : 'text-text-muted hover:text-text-main'
            }`}
          >
            <CalendarCheck size={16} />
            Active Bookings
            <span className="rounded-full bg-surface-bg px-2 py-0.5 text-[11px]">{activeCount}</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('past')}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
              viewMode === 'past'
                ? 'bg-card text-text-main shadow-sm'
                : 'text-text-muted hover:text-text-main'
            }`}
          >
            <History size={16} />
            Past Interviews
            <span className="rounded-full bg-surface-bg px-2 py-0.5 text-[11px]">{pastCount}</span>
          </button>
        </div>

        <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-2 inline-flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Total assigned
          </span>
          <span className="text-lg font-bold text-text-main">{bookings.total_count}</span>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="rounded-2xl border border-border-subtle bg-card p-5 space-y-8">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-text-muted">
            <Loader2 size={24} className="animate-spin mr-2" />
            Loading your bookings...
          </div>
        ) : viewMode === 'active' ? (
          <>
            {renderActiveSection('today', bookings.today)}
            <DateNavigatedBookingSection
              title={sectionMeta.upcoming.title}
              description={sectionMeta.upcoming.description}
              emptyMessage={sectionMeta.upcoming.empty}
              noDateMessage={sectionMeta.upcoming.noDate}
              jumpLabel={sectionMeta.upcoming.jump}
              bookings={bookings.upcoming}
              selectedDate={upcomingSelectedDate}
              onSelectedDateChange={setUpcomingSelectedDate}
              defaultDate={defaultUpcomingDate}
              renderCard={renderActiveBookingCard}
            />
          </>
        ) : bookings.past.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-subtle px-4 py-10 text-center">
            <History size={28} className="mx-auto text-text-muted mb-3" />
            <p className="text-sm font-medium text-text-main">No past interviews yet</p>
            <p className="text-xs text-text-muted mt-1">{pastSectionMeta.empty}</p>
          </div>
        ) : (
          <DateNavigatedBookingSection
            title={pastSectionMeta.title}
            description={pastSectionMeta.description}
            emptyMessage={pastSectionMeta.empty}
            noDateMessage={pastSectionMeta.noDate}
            jumpLabel={pastSectionMeta.jump}
            bookings={bookings.past}
            selectedDate={pastSelectedDate}
            onSelectedDateChange={setPastSelectedDate}
            defaultDate={defaultPastDate}
            renderCard={renderPastBookingCard}
          />
        )}
      </div>

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
                <p className="text-xs text-text-muted mt-1">Only admins free at this slot are shown.</p>
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
                  Loading available admins...
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

      {communicationsModal && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40"
          onClick={() => setCommunicationsModal(null)}
        >
          <div
            className="w-full max-w-4xl max-h-[85vh] rounded-2xl border border-border-subtle bg-card shadow-2xl flex flex-col overflow-hidden"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle bg-surface-bg">
              <div>
                <h3 className="text-lg font-semibold text-text-main">Conversation History</h3>
                <p className="text-sm text-text-muted mt-0.5">
                  {communicationsModal.data?.candidate_name || communicationsModal.booking.candidate_name}
                </p>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  {renderStageBadge(
                    communicationsModal.data?.candidate_stage ?? communicationsModal.booking.candidate_stage,
                    communicationsModal.data?.candidate_stage_label ??
                      communicationsModal.booking.candidate_stage_label
                  )}
                  <span className="text-xs text-text-muted">
                    Interview: {communicationsModal.booking.date_label} · {communicationsModal.booking.time_label}
                  </span>
                </div>
                {communicationsModal.data && (
                  <p className="text-xs text-text-muted mt-1">
                    {communicationsModal.data.message_count}{' '}
                    {communicationsModal.data.message_count === 1 ? 'message' : 'messages'}
                    {communicationsModal.data.admin_name
                      ? ` · Assigned admin: ${communicationsModal.data.admin_name}`
                      : ''}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setCommunicationsModal(null)}
                className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"
                aria-label="Close conversation popup"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 custom-scrollbar bg-surface-bg/40">
              {communicationsModal.loading ? (
                <div className="flex items-center justify-center py-16 text-text-muted">
                  <Loader2 size={22} className="animate-spin mr-2" />
                  Loading conversation...
                </div>
              ) : !communicationsModal.data || communicationsModal.data.messages.length === 0 ? (
                <div className="rounded-xl border border-border-subtle bg-card px-4 py-8 text-center">
                  <MessageSquare size={28} className="mx-auto text-text-muted mb-2" />
                  <p className="text-sm text-text-main font-medium">No messages found</p>
                  <p className="text-xs text-text-muted mt-1">
                    {communicationsModal.data?.lead_id
                      ? 'This candidate has no recorded messages yet.'
                      : 'This booking is not linked to a lead conversation.'}
                  </p>
                </div>
              ) : (
                communicationsModal.data.messages.map(message => {
                  const styles = participantStyles[message.participant];
                  return (
                    <div
                      key={`${message.id}-${message.created_at}`}
                      className="rounded-xl border border-border-subtle bg-card p-3"
                    >
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${styles.badge}`}
                        >
                          {styles.icon}
                          {message.participant_label}
                        </span>
                        <span className="text-[11px] text-text-muted whitespace-nowrap">
                          {formatCommunicationTime(message.created_at)}
                        </span>
                      </div>
                      <div
                        className={`rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap break-words ${styles.bubble}`}
                      >
                        {message.text || '—'}
                      </div>
                      {message.media_url && (
                        <a
                          href={message.media_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-block mt-2 text-xs text-accent hover:underline"
                        >
                          View attachment{message.file_name ? `: ${message.file_name}` : ''}
                        </a>
                      )}
                    </div>
                  );
                })
              )}
              <div ref={communicationsEndRef} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MyBookings;
