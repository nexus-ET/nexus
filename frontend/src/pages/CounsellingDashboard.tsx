import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Calendar, Loader2, RefreshCw, UserPlus, XCircle, ArrowRightLeft, X, Bot, UserRound, MessageSquare, CheckCircle2, Sparkles, Map as MapIcon } from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';
import { computeFloatingMenuPosition } from '../utils/floatingMenuPosition';
import SessionWrapUpDrawer from '../components/SessionWrapUpDrawer';
import InteractionLogDrawer from '../components/InteractionLogDrawer';
import CounsellingSessionModal from '../components/CounsellingSessionModal';
import StudentJourneyPanel from '../components/StudentJourneyPanel';
import PipelineAnalyticsPanel, { PipelineAnalyticsData } from '../components/PipelineAnalyticsPanel';
import PeriodAgendaShell, { type PeriodDaySummary } from '../components/PeriodAgendaShell';
import { useConfirmation } from '../context/ConfirmationContext';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';

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

interface GridPendingBooking {
  id: number;
  candidate_name: string;
  scheduled_time: string;
  notes?: string | null;
  lead_id?: number | null;
}

interface GridPendingQueueSlot {
  queue_position: number;
  booking: GridPendingBooking | null;
}

interface GridAdminCell {
  admin_id: number;
  admin_name?: string | null;
  status: 'available' | 'booked' | 'past' | 'complete';
  label: string;
  candidate_name?: string | null;
  booking_id?: number | null;
  lead_id?: number | null;
}

interface GridRow {
  start_time: string;
  time_label: string;
  pending_queue: GridPendingQueueSlot[];
  hidden_pending_count: number;
  admin_cells: GridAdminCell[];
}

interface GridAdmin {
  id: number;
  name: string;
}

interface DayScheduleGrid {
  date: string;
  label: string;
  section: 'past' | 'selected' | 'upcoming';
  admins: GridAdmin[];
  rows: GridRow[];
}

interface NavigationDay {
  date: string;
  label: string;
}

interface ScheduleNavigation {
  past: NavigationDay;
  selected: NavigationDay;
  upcoming: NavigationDay;
}

interface ScheduleGridResponse {
  days: DayScheduleGrid[];
  legend: Record<string, string>;
  max_bookings_per_slot: number;
  visible_pending_columns: number;
  focus_date: string;
  calendar_today: string;
  navigation: ScheduleNavigation;
}

interface PendingPanelBooking {
  id: number;
  scheduled_time: string;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  notes?: string | null;
  status: string;
  lead_id?: number | null;
}

interface PendingBookingsResponse {
  today: PendingPanelBooking[];
  upcoming: Array<{
    date: string;
    label: string;
    bookings: PendingPanelBooking[];
  }>;
}

interface AvailableAdmin {
  id: number;
  name: string;
  email: string;
}

interface ContextMenuState {
  mode: 'assign' | 'manage';
  bookingId: number;
  candidateName: string;
  scheduledTime: string;
  leadId?: number | null;
  currentAdminId?: number;
  x: number;
  y: number;
  admins: AvailableAdmin[];
  loading: boolean;
}

type CommunicationParticipant = 'candidate' | 'ai_agent' | 'handoff_admin' | 'system';

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
  lead_id: number | null;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  admin_name?: string | null;
  message_count: number;
  messages: BookingCommunicationMessage[];
}

interface CommunicationsModalState {
  bookingId: number;
  candidateName: string;
  loading: boolean;
  data: BookingCommunicationsResponse | null;
}

const adminCellClass = (status: GridAdminCell['status']): string => {
  switch (status) {
    case 'booked':
      return 'bg-red-50 text-red-900 border-red-200';
    case 'available':
      return 'bg-emerald-50 text-emerald-900 border-emerald-200';
    case 'complete':
      return 'bg-sky-50 text-sky-900 border-sky-200';
    case 'past':
      return 'bg-slate-100 text-slate-500 border-slate-200';
    default:
      return 'bg-surface-bg text-text-main border-border-subtle';
  }
};

const legendSwatchClass: Record<GridAdminCell['status'], string> = {
  available: 'bg-emerald-50 border-emerald-200',
  booked: 'bg-red-50 border-red-200',
  complete: 'bg-sky-50 border-sky-200',
  past: 'bg-slate-100 border-slate-200',
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


type DateFilterMode = 'single' | 'multiple';

const CounsellingDashboard: React.FC = () => {
  const { formatDateTime } = useBusinessTimezone();
  const openConfirm = useConfirmation();
  const [dateFilterMode, setDateFilterMode] = useState<DateFilterMode>('single');
  const [startDate, setStartDate] = useState<Date>(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), today.getDate());
  });
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [schedule, setSchedule] = useState<ScheduleGridResponse>({
    days: [],
    legend: {},
    max_bookings_per_slot: 5,
    visible_pending_columns: 3,
    focus_date: toIsoDate(new Date()),
    calendar_today: toIsoDate(new Date()),
    navigation: {
      past: { date: '', label: '' },
      selected: { date: '', label: '' },
      upcoming: { date: '', label: '' },
    },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [communicationsModal, setCommunicationsModal] = useState<CommunicationsModalState | null>(null);
  const [pendingBookings, setPendingBookings] = useState<PendingBookingsResponse>({
    today: [],
    upcoming: [],
  });
  const [pipelineAnalytics, setPipelineAnalytics] = useState<PipelineAnalyticsData | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [wrapUpDrawer, setWrapUpDrawer] = useState<{ bookingId: number; candidateName: string } | null>(null);
  const [interactionBookingId, setInteractionBookingId] = useState<number | null>(null);
  const [journeyPanel, setJourneyPanel] = useState<{
    studentId: number;
    studentName: string;
  } | null>(null);
  const [sessionModal, setSessionModal] = useState<{
    bookingId: number;
    candidateName: string;
    dateLabel?: string | null;
    timeLabel?: string | null;
  } | null>(null);
  const [periodFocusDate, setPeriodFocusDate] = useState<string | null>(null);
  const [periodShowGrid, setPeriodShowGrid] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const communicationsEndRef = useRef<HTMLDivElement | null>(null);
  const startDateRef = useRef(startDate);
  const endDateRef = useRef(endDate);
  const dateFilterModeRef = useRef(dateFilterMode);
  const suppressScheduleLoadRef = useRef(false);
  startDateRef.current = startDate;
  endDateRef.current = endDate;
  dateFilterModeRef.current = dateFilterMode;

  const isMultipleDates = dateFilterMode === 'multiple';

  const loadSchedule = useCallback(
    async (
      date: Date,
      showSpinner = true,
      options?: { mode?: DateFilterMode; end?: Date | null }
    ) => {
      if (!hasValidSession()) return;
      try {
        if (showSpinner) setLoading(true);
        setError(null);
        const params = new URLSearchParams();
        const mode = options?.mode ?? 'single';
        if (mode === 'multiple') {
          params.set('start_date', toIsoDate(date));
          params.set('end_date', toIsoDate(options?.end ?? date));
        } else {
          params.set('date', toIsoDate(date));
        }
        const data = (await apiFetch(`bookings/grid?${params.toString()}`)) as ScheduleGridResponse;
        setSchedule(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load counselling schedule.');
      } finally {
        if (showSpinner) setLoading(false);
      }
    },
    []
  );

  const loadPendingBookings = useCallback(async () => {
    if (!hasValidSession()) return;
    try {
      const data = (await apiFetch('bookings/pending')) as PendingBookingsResponse;
      setPendingBookings({
        today: Array.isArray(data.today) ? data.today : [],
        upcoming: Array.isArray(data.upcoming) ? data.upcoming : [],
      });
    } catch {
      setPendingBookings({ today: [], upcoming: [] });
    }
  }, []);

  const loadPipelineAnalytics = useCallback(async () => {
    if (!hasValidSession()) return;
    try {
      setAnalyticsLoading(true);
      const data = (await apiFetch('pipeline/analytics')) as PipelineAnalyticsData;
      setPipelineAnalytics(data);
    } catch {
      setPipelineAnalytics(null);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPendingBookings();
    loadPipelineAnalytics();
  }, [loadPendingBookings, loadPipelineAnalytics]);

  useEffect(() => {
    if (suppressScheduleLoadRef.current) {
      suppressScheduleLoadRef.current = false;
      return;
    }
    loadSchedule(startDate, true, {
      mode: dateFilterModeRef.current,
      end: endDate,
    });
  }, [startDate, endDate, loadSchedule]);

  useEffect(() => {
    const interval = setInterval(() => {
      loadSchedule(startDateRef.current, false, {
        mode: dateFilterModeRef.current,
        end: endDateRef.current,
      });
      loadPendingBookings();
      loadPipelineAnalytics();
    }, 15000);
    return () => clearInterval(interval);
  }, [loadSchedule, loadPendingBookings, loadPipelineAnalytics]);

  useEffect(() => {
    const closeMenu = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setContextMenu(null);
      }
    };
    window.addEventListener('click', closeMenu);
    return () => window.removeEventListener('click', closeMenu);
  }, []);

  useLayoutEffect(() => {
    if (!contextMenu || !menuRef.current) {
      setMenuPosition(null);
      return;
    }

    const reposition = () => {
      if (!menuRef.current || !contextMenu) return;
      const rect = menuRef.current.getBoundingClientRect();
      setMenuPosition(
        computeFloatingMenuPosition(contextMenu.x, contextMenu.y, rect.width, rect.height)
      );
    };

    reposition();
    window.addEventListener('resize', reposition);
    return () => window.removeEventListener('resize', reposition);
  }, [contextMenu, contextMenu?.loading, contextMenu?.admins.length, contextMenu?.mode]);

  useEffect(() => {
    if (!contextMenu) {
      setMenuPosition(null);
    }
  }, [contextMenu]);

  useEffect(() => {
    if (communicationsModal && !communicationsModal.loading) {
      communicationsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [communicationsModal]);

  const openCommunicationsModal = async (bookingId: number, candidateName: string) => {
    setCommunicationsModal({
      bookingId,
      candidateName,
      loading: true,
      data: null,
    });

    try {
      const data = (await apiFetch(
        `bookings/${bookingId}/communications`
      )) as BookingCommunicationsResponse;
      setCommunicationsModal({
        bookingId,
        candidateName,
        loading: false,
        data,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load communications.');
      setCommunicationsModal(null);
    }
  };

  const totalPending = useMemo(
    () =>
      schedule.days.reduce(
        (sum, day) =>
          sum +
          day.rows.reduce(
            (rowSum, row) =>
              rowSum +
              row.pending_queue.filter(slot => slot.booking).length +
              row.hidden_pending_count,
            0
          ),
        0
      ),
    [schedule.days]
  );

  const dayBookingCount = useMemo(() => {
    return schedule.days.reduce((daySum, day) => {
      return (
        daySum +
        day.rows.reduce((sum, row) => {
          const queued =
            row.pending_queue.filter(slot => slot.booking).length + row.hidden_pending_count;
          const assigned = row.admin_cells.filter(
            cell => cell.status === 'booked' || cell.status === 'complete'
          ).length;
          return sum + queued + assigned;
        }, 0)
      );
    }, 0);
  }, [schedule.days]);

  type PeriodAppointment = {
    key: string;
    dayDate: string;
    dayLabel: string;
    timeLabel: string;
    startTime: string;
    candidateName: string;
    kind: 'pending' | 'booked' | 'complete';
    adminName?: string | null;
    bookingId?: number | null;
    leadId?: number | null;
    notes?: string | null;
    queuePosition?: number;
  };

  const periodAppointments = useMemo(() => {
    const items: PeriodAppointment[] = [];
    for (const day of schedule.days) {
      const adminNameById = new Map(day.admins.map(admin => [admin.id, admin.name]));
      for (const row of day.rows) {
        for (const slot of row.pending_queue) {
          if (!slot.booking) continue;
          items.push({
            key: `pending-${slot.booking.id}`,
            dayDate: day.date,
            dayLabel: day.label,
            timeLabel: row.time_label,
            startTime: row.start_time,
            candidateName: slot.booking.candidate_name,
            kind: 'pending',
            bookingId: slot.booking.id,
            leadId: slot.booking.lead_id ?? null,
            notes: slot.booking.notes,
            queuePosition: slot.queue_position,
          });
        }
        for (const cell of row.admin_cells) {
          if ((cell.status !== 'booked' && cell.status !== 'complete') || !cell.booking_id) continue;
          items.push({
            key: `${cell.status}-${cell.booking_id}`,
            dayDate: day.date,
            dayLabel: day.label,
            timeLabel: row.time_label,
            startTime: row.start_time,
            candidateName: cell.candidate_name || 'Candidate',
            kind: cell.status === 'complete' ? 'complete' : 'booked',
            adminName: cell.admin_name || adminNameById.get(cell.admin_id) || null,
            bookingId: cell.booking_id,
            leadId: cell.lead_id ?? null,
          });
        }
      }
    }
    return items.sort((a, b) => {
      const dayCmp = a.dayDate.localeCompare(b.dayDate);
      if (dayCmp !== 0) return dayCmp;
      return a.startTime.localeCompare(b.startTime);
    });
  }, [schedule.days]);

  const periodDaySummaries: PeriodDaySummary[] = useMemo(() => {
    return schedule.days.map(day => {
      const dayItems = periodAppointments.filter(item => item.dayDate === day.date);
      return {
        date: day.date,
        label: day.label,
        count: dayItems.length,
        pendingCount: dayItems.filter(item => item.kind === 'pending').length,
        bookedCount: dayItems.filter(item => item.kind === 'booked' || item.kind === 'complete')
          .length,
      };
    });
  }, [schedule.days, periodAppointments]);

  const periodAgendaStats = useMemo(() => {
    const pending = periodAppointments.filter(item => item.kind === 'pending').length;
    const booked = periodAppointments.filter(item => item.kind === 'booked').length;
    const complete = periodAppointments.filter(item => item.kind === 'complete').length;
    return [
      { label: 'Total', value: periodAppointments.length, tone: 'default' as const },
      { label: 'Assigned', value: booked, tone: 'emerald' as const },
      { label: 'Complete', value: complete, tone: 'sky' as const },
      { label: 'In queue', value: pending, tone: 'amber' as const },
    ];
  }, [periodAppointments]);

  const visiblePeriodAppointments = useMemo(() => {
    if (!periodFocusDate) return periodAppointments;
    return periodAppointments.filter(item => item.dayDate === periodFocusDate);
  }, [periodAppointments, periodFocusDate]);

  const periodAppointmentsByDay = useMemo(() => {
    const groups = new Map<string, { date: string; label: string; items: PeriodAppointment[] }>();
    for (const item of visiblePeriodAppointments) {
      const existing = groups.get(item.dayDate);
      if (existing) {
        existing.items.push(item);
      } else {
        groups.set(item.dayDate, {
          date: item.dayDate,
          label: item.dayLabel,
          items: [item],
        });
      }
    }
    return Array.from(groups.values());
  }, [visiblePeriodAppointments]);

  useEffect(() => {
    if (!isMultipleDates) {
      setPeriodFocusDate(null);
      setPeriodShowGrid(false);
    }
  }, [isMultipleDates]);

  const dateFilterLabel = useMemo(() => {
    if (isMultipleDates) {
      const startLabel = startDate.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
      const endLabel = (endDate ?? startDate).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
      return `${startLabel} → ${endLabel}`;
    }
    return startDate.toLocaleDateString(undefined, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  }, [isMultipleDates, startDate, endDate]);

  const handleDateFilterModeChange = (mode: DateFilterMode) => {
    if (mode === dateFilterMode) return;

    if (mode === 'multiple') {
      // Keep the same day visible — do not refetch / flash the grid.
      suppressScheduleLoadRef.current = true;
      setDateFilterMode('multiple');
      setEndDate(prev => prev ?? startDate);
      return;
    }

    const wasMultiDay = Boolean(endDate && toIsoDate(endDate) !== toIsoDate(startDate));
    suppressScheduleLoadRef.current = true;
    setDateFilterMode('single');
    setEndDate(null);
    if (wasMultiDay) {
      void loadSchedule(startDate, false, { mode: 'single' });
    }
  };

  const handleStartDateChange = (date: Date | null) => {
    if (!date) return;
    setStartDate(date);
    if (isMultipleDates && endDate && date > endDate) {
      setEndDate(date);
    }
    if (!isMultipleDates) {
      setEndDate(null);
    }
  };

  const handleEndDateChange = (date: Date | null) => {
    if (!isMultipleDates || !date) return;
    setEndDate(date);
    if (date < startDate) {
      setStartDate(date);
    }
  };

  const reloadScheduleQuietly = () =>
    loadSchedule(startDateRef.current, false, {
      mode: dateFilterModeRef.current,
      end: endDateRef.current,
    });

  const getFirstQueuedBooking = (row: GridRow): GridPendingBooking | null => {
    for (const slot of row.pending_queue) {
      if (slot.booking) return slot.booking;
    }
    return null;
  };

  const rowHasPending = (row: GridRow): boolean =>
    row.pending_queue.some(slot => slot.booking) || row.hidden_pending_count > 0;

  const fetchAvailableAdmins = async (
    scheduledTime: string,
    excludeBookingId?: number
  ): Promise<AvailableAdmin[]> => {
    const params = new URLSearchParams({ time: scheduledTime });
    if (excludeBookingId) {
      params.set('exclude_booking_id', String(excludeBookingId));
    }
    const data = (await apiFetch(`admins/available?${params.toString()}`)) as {
      admins: AvailableAdmin[];
    };
    return data.admins;
  };

  const openAssignMenu = async (event: React.MouseEvent, booking: GridPendingBooking) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      mode: 'assign',
      bookingId: booking.id,
      candidateName: booking.candidate_name,
      scheduledTime: booking.scheduled_time,
      leadId: booking.lead_id ?? null,
      x: event.clientX,
      y: event.clientY,
      admins: [],
      loading: true,
    });

    try {
      const admins = await fetchAvailableAdmins(booking.scheduled_time);
      setContextMenu(prev =>
        prev && prev.bookingId === booking.id
          ? { ...prev, admins, loading: false }
          : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load available admins.');
      setContextMenu(null);
    }
  };

  const openBookedMenu = async (
    event: React.MouseEvent,
    cell: GridAdminCell,
    row: GridRow
  ) => {
    if ((cell.status !== 'booked' && cell.status !== 'complete') || !cell.booking_id) return;
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      mode: 'manage',
      bookingId: cell.booking_id,
      candidateName: cell.candidate_name || 'Candidate',
      scheduledTime: row.start_time,
      leadId: cell.lead_id ?? null,
      currentAdminId: cell.admin_id,
      x: event.clientX,
      y: event.clientY,
      admins: [],
      loading: true,
    });

    try {
      const admins = await fetchAvailableAdmins(row.start_time, cell.booking_id);
      setContextMenu(prev =>
        prev && prev.bookingId === cell.booking_id
          ? { ...prev, admins, loading: false }
          : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load available admins.');
      setContextMenu(null);
    }
  };

  const handleRowContextMenu = (event: React.MouseEvent, row: GridRow) => {
    const booking = getFirstQueuedBooking(row);
    if (!booking) return;
    openAssignMenu(event, booking);
  };

  const renderPendingCell = (slot: GridPendingQueueSlot) => {
    if (!slot.booking) {
      return <span className="text-[10px] text-text-muted">—</span>;
    }

    return (
      <div
        onContextMenu={event => openAssignMenu(event, slot.booking!)}
        className="rounded-md border border-amber-200 bg-amber-50 px-1 py-1 cursor-context-menu"
        title={`Queue #${slot.queue_position} — right-click to assign admin`}
      >
        <div className="font-semibold text-amber-900 truncate text-[10px]">{slot.booking.candidate_name}</div>
        {slot.booking.notes && (
          <div className="text-[9px] text-amber-800/80 truncate">{slot.booking.notes}</div>
        )}
      </div>
    );
  };

  const renderPendingBooking = (booking: PendingPanelBooking) => (
    <div
      key={booking.id}
      onContextMenu={event => openAssignMenu(event, booking)}
      className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 cursor-context-menu"
      title="Right-click to assign an available admin"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-amber-950 truncate">{booking.candidate_name}</p>
          <p className="text-xs text-amber-900/80">
            {new Date(booking.scheduled_time).toLocaleString(undefined, {
              weekday: 'short',
              day: 'numeric',
              month: 'short',
              hour: 'numeric',
              minute: '2-digit',
            })}
          </p>
          {booking.notes && <p className="text-[11px] text-amber-900/70 truncate mt-1">{booking.notes}</p>}
        </div>
        <span className="shrink-0 rounded-full border border-amber-300 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-900">
          Pending
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={event => {
            event.stopPropagation();
            setInteractionBookingId(booking.id);
          }}
          className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-white/80 px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-white"
        >
          <MessageSquare size={12} />
          View Interaction
        </button>
        {booking.lead_id ? (
          <button
            type="button"
            onClick={event => {
              event.stopPropagation();
              setJourneyPanel({
                studentId: booking.lead_id!,
                studentName: booking.candidate_name,
              });
            }}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white/80 px-2.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-white"
          >
            <MapIcon size={12} />
            View Journey
          </button>
        ) : null}
        <button
          type="button"
          onClick={event => openAssignMenu(event, booking)}
          className="inline-flex items-center gap-1 rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-amber-950 hover:bg-amber-100"
        >
          <UserPlus size={12} />
          Assign
        </button>
      </div>
    </div>
  );

  const handleAssignAdmin = async (bookingId: number, adminId: number) => {
    try {
      setActionLoading(true);
      await apiFetch('bookings/assign', {
        method: 'POST',
        body: JSON.stringify({ booking_id: bookingId, admin_id: adminId }),
      });
      setContextMenu(null);
      await Promise.all([reloadScheduleQuietly(), loadPendingBookings()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign admin.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSwitchAdmin = async (bookingId: number, adminId: number) => {
    try {
      setActionLoading(true);
      await apiFetch('bookings/switch', {
        method: 'POST',
        body: JSON.stringify({ booking_id: bookingId, target_admin_id: adminId }),
      });
      setContextMenu(null);
      await Promise.all([reloadScheduleQuietly(), loadPendingBookings()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to switch admin.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelBooking = async (bookingId: number) => {
    if (!(await openConfirm({
      title: 'Cancel booking?',
      message: 'Cancel this booked counselling session?',
      confirmLabel: 'Cancel booking',
      variant: 'warning',
    }))) return;
    try {
      setActionLoading(true);
      await apiFetch(`bookings/cancel/${bookingId}`, { method: 'POST' });
      setContextMenu(null);
      await Promise.all([reloadScheduleQuietly(), loadPendingBookings()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel booking.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefreshAll = async () => {
    await Promise.all([
      loadSchedule(startDate, true, { mode: dateFilterMode, end: endDate }),
      loadPendingBookings(),
      loadPipelineAnalytics(),
    ]);
  };

  const handleWrapUpSubmitted = async () => {
    setContextMenu(null);
    await Promise.all([
      reloadScheduleQuietly(),
      loadPendingBookings(),
      loadPipelineAnalytics(),
    ]);
  };

  const renderDayTable = (day: DayScheduleGrid) => (
    <div key={day.date} className="space-y-3">
      <div className="overflow-x-auto rounded-xl border border-border-subtle">
        <table className="min-w-full text-xs border-collapse table-fixed">
          <colgroup>
            <col className="w-[92px]" />
            <col className="w-[72px]" />
            <col className="w-[72px]" />
            <col className="w-[72px]" />
            <col className="w-[44px]" />
            {day.admins.map(admin => (
              <col key={admin.id} className="w-[110px]" />
            ))}
          </colgroup>
          <thead>
            <tr className="bg-surface-bg border-b border-border-subtle">
              <th className="sticky left-0 z-10 bg-surface-bg px-2 py-1.5 text-left font-semibold text-text-main">
                Time
              </th>
              <th className="px-1 py-1.5 text-left font-semibold text-text-main" title="First in queue">
                Q1
              </th>
              <th className="px-1 py-1.5 text-left font-semibold text-text-main" title="Second in queue">
                Q2
              </th>
              <th className="px-1 py-1.5 text-left font-semibold text-text-main" title="Third in queue">
                Q3
              </th>
              <th className="px-1 py-1.5 text-center font-semibold text-text-main" title="Additional queued candidates">
                +
              </th>
              {day.admins.map(admin => (
                <th
                  key={admin.id}
                  className="px-1 py-1.5 text-left font-semibold text-text-main truncate"
                  title={admin.name}
                >
                  {admin.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {day.rows.map(row => {
              const hasPending = rowHasPending(row);
              return (
                <tr
                  key={row.start_time}
                  onContextMenu={event => handleRowContextMenu(event, row)}
                  className={`border-b border-border-subtle/70 ${
                    hasPending ? 'cursor-context-menu hover:bg-amber-50/40' : ''
                  }`}
                  title={hasPending ? 'Right-click to assign the first queued candidate' : undefined}
                >
                  <td className="sticky left-0 z-10 bg-card px-2 py-1.5 font-medium text-text-main whitespace-nowrap text-[11px] leading-tight">
                    {row.time_label}
                  </td>
                  {row.pending_queue.map(slot => (
                    <td
                      key={`${row.start_time}-q${slot.queue_position}`}
                      className="px-1 py-1 align-top"
                      onContextMenu={event => {
                        if (!slot.booking) return;
                        openAssignMenu(event, slot.booking);
                      }}
                    >
                      {renderPendingCell(slot)}
                    </td>
                  ))}
                  <td className="px-1 py-1 align-top text-center">
                    {row.hidden_pending_count > 0 ? (
                      <span
                        className="inline-flex items-center justify-center rounded-md border border-amber-300 bg-amber-100 px-1 py-0.5 text-[10px] font-semibold text-amber-900"
                        title={`${row.hidden_pending_count} more candidate(s) in queue (max ${schedule.max_bookings_per_slot} per slot)`}
                      >
                        +{row.hidden_pending_count}
                      </span>
                    ) : (
                      <span className="text-[10px] text-text-muted">—</span>
                    )}
                  </td>
                  {row.admin_cells.map(cell => (
                    <td key={`${row.start_time}-${cell.admin_id}`} className="px-1 py-1 align-top">
                      <div
                        onClick={event => {
                          if ((cell.status !== 'booked' && cell.status !== 'complete') || !cell.booking_id) return;
                          event.stopPropagation();
                          openCommunicationsModal(cell.booking_id, cell.candidate_name || 'Candidate');
                        }}
                        onContextMenu={event => openBookedMenu(event, cell, row)}
                        className={`rounded-md border px-1 py-1 text-[10px] leading-tight font-medium ${adminCellClass(cell.status)} ${
                          cell.status === 'booked' || cell.status === 'complete'
                            ? 'cursor-pointer hover:brightness-95 counselling-booking-blink'
                            : ''
                        }`}
                        title={
                          cell.status === 'booked' || cell.status === 'complete'
                            ? `${cell.candidate_name || cell.label} — click to view communications, right-click to manage`
                            : cell.label
                        }
                      >
                        {cell.status === 'booked' || cell.status === 'complete' ? (
                          <div className="flex flex-col gap-0.5 min-w-0">
                            <div className="flex items-center justify-between gap-1 min-w-0">
                              <span className="truncate font-semibold">{cell.candidate_name || 'Candidate'}</span>
                              <span className="shrink-0 text-[9px] uppercase tracking-wide opacity-90">
                                {cell.status === 'complete' ? 'Done' : 'Booked'}
                              </span>
                            </div>
                            <div className="truncate text-[9px] opacity-80" title={cell.admin_name || undefined}>
                              {cell.admin_name || day.admins.find(admin => admin.id === cell.admin_id)?.name || 'Counsellor'}
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="truncate">{cell.label}</div>
                            {cell.candidate_name && (
                              <div className="mt-0.5 font-semibold truncate">{cell.candidate_name}</div>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );

  const selectedDay = schedule.days[0] ?? null;
  const isRealToday = !isMultipleDates && schedule.focus_date === schedule.calendar_today;

  const computedNav = useMemo(() => {
    const past = new Date(startDate);
    past.setDate(past.getDate() - 1);
    const upcoming = new Date(startDate);
    upcoming.setDate(upcoming.getDate() + 1);
    return {
      past: toIsoDate(past),
      selected: toIsoDate(startDate),
      upcoming: toIsoDate(upcoming),
    };
  }, [startDate]);

  const navLinkClass = (targetDate: string) =>
    `inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
      !isMultipleDates && toIsoDate(startDate) === targetDate
        ? 'border-accent bg-accent/10 text-accent'
        : 'border-border-subtle bg-card text-text-main hover:bg-surface-bg'
    }`;

  const jumpToNavDate = (isoDate: string) => {
    setDateFilterMode('single');
    setEndDate(null);
    setStartDate(parseIsoDate(isoDate));
  };

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2">
            <Calendar size={24} />
            Manage Appointments
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Queue columns show the first 3 candidates per slot (FIFO). Up to{' '}
            {schedule.max_bookings_per_slot} bookings per slot — overflow appears as +N after Q3.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefreshAll}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm hover:bg-surface-bg disabled:opacity-60 self-start"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-3 text-xs">
        {Object.entries(schedule.legend).map(([status, label]) => (
          <div key={status} className="flex items-center gap-2">
            <span
              className={`inline-block w-3 h-3 rounded border ${
                legendSwatchClass[status as GridAdminCell['status']] || 'bg-surface-bg border-border-subtle'
              }`}
            />
            <span className="text-text-muted">{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded border border-amber-200 bg-amber-50" />
          <span className="text-text-muted">Queue (Q1–Q3)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block min-w-[18px] rounded border border-amber-300 bg-amber-100 text-[9px] font-semibold text-amber-900 px-1">
            +N
          </span>
          <span className="text-text-muted">Hidden queue</span>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <PipelineAnalyticsPanel analytics={pipelineAnalytics} loading={analyticsLoading} />

      <div className="rounded-2xl border border-border-subtle bg-card p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-text-main">Pending Appointments</h2>
            <p className="text-xs text-text-muted mt-1">
              Right-click a candidate to assign an available admin (conflicts excluded automatically).
            </p>
          </div>
          <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-900">
            {pendingBookings.today.length +
              pendingBookings.upcoming.reduce((sum, group) => sum + group.bookings.length, 0)}{' '}
            awaiting assignment
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">Today</h3>
            {pendingBookings.today.length === 0 ? (
              <p className="text-xs text-text-muted italic">No pending appointments today.</p>
            ) : (
              <div className="space-y-2">{pendingBookings.today.map(renderPendingBooking)}</div>
            )}
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">Upcoming</h3>
            {pendingBookings.upcoming.length === 0 ? (
              <p className="text-xs text-text-muted italic">No upcoming pending appointments.</p>
            ) : (
              <div className="space-y-3">
                {pendingBookings.upcoming.map(group => (
                  <div key={group.date}>
                    <p className="text-[11px] font-semibold text-text-main mb-1.5">{group.label}</p>
                    <div className="space-y-2">{group.bookings.map(renderPendingBooking)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border-subtle bg-card p-5 space-y-5">
        <div className="flex flex-col gap-4 pb-4 border-b border-border-subtle/70">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <h2 className="text-lg font-semibold text-text-main">Schedule Grid</h2>
            {isMultipleDates ? (
              <span className="inline-flex w-fit items-center rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent">
                Multiple dates · {dateFilterLabel}
              </span>
            ) : selectedDay && isRealToday ? (
              <span className="inline-flex w-fit items-center rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1 text-[11px] font-medium text-text-muted">
                Calendar today
              </span>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-3">
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3 min-w-[180px] flex-1 sm:flex-none">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Bookings</p>
              <p className="text-2xl font-bold text-text-main mt-1 leading-none">{dayBookingCount}</p>
              <p className="text-xs text-text-muted mt-1.5">
                {isMultipleDates
                  ? `${dayBookingCount === 1 ? 'booking' : 'bookings'} in ${dateFilterLabel}`
                  : selectedDay
                    ? `${dayBookingCount === 1 ? 'booking' : 'bookings'} on ${selectedDay.label}`
                    : 'No date selected'}
              </p>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3 min-w-[180px] flex-1 sm:flex-none">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-900/70">
                Awaiting assignment
              </p>
              <p className="text-2xl font-bold text-amber-900 mt-1 leading-none">{totalPending}</p>
              <p className="text-xs text-amber-900/70 mt-1.5">Candidates in queue</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted shrink-0">
              Date filter
            </span>
            <label className="inline-flex items-center gap-2 text-sm text-text-main cursor-pointer shrink-0">
              <input
                type="radio"
                name="counselling-date-mode"
                checked={!isMultipleDates}
                onChange={() => handleDateFilterModeChange('single')}
                className="accent-accent"
              />
              Single date
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-text-main cursor-pointer shrink-0">
              <input
                type="radio"
                name="counselling-date-mode"
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
                  className="w-[180px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-1.5 text-sm text-text-main"
                  calendarClassName="nexus-roster-datepicker"
                  popperClassName="nexus-datepicker-popper"
                  portalId="nexus-datepicker-portal"
                  withPortal
                  popperPlacement="bottom-start"
                  popperProps={{ strategy: 'fixed' }}
                />
              </div>
              <span className="text-xs text-text-muted shrink-0">to</span>
              <div className="shrink-0 [&_.react-datepicker-wrapper]:block [&_.react-datepicker__input-container]:block">
                <DatePicker
                  selected={isMultipleDates ? endDate : null}
                  onChange={handleEndDateChange}
                  selectsEnd
                  startDate={startDate}
                  endDate={endDate}
                  minDate={startDate}
                  placeholderText="End date"
                  dateFormat="EEE, d MMM yyyy"
                  className="w-[180px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-1.5 text-sm text-text-main disabled:opacity-50 disabled:cursor-not-allowed"
                  calendarClassName="nexus-roster-datepicker"
                  popperClassName="nexus-datepicker-popper"
                  portalId="nexus-datepicker-portal"
                  withPortal
                  popperPlacement="bottom-start"
                  popperProps={{ strategy: 'fixed' }}
                  disabled={!isMultipleDates}
                />
              </div>
              {!isRealToday && !isMultipleDates && (
                <button
                  type="button"
                  onClick={() => jumpToNavDate(schedule.calendar_today)}
                  className="text-xs text-accent hover:underline whitespace-nowrap shrink-0"
                >
                  Jump to today
                </button>
              )}
            </div>

            <span className="text-xs text-text-muted shrink-0">{dateFilterLabel}</span>

            <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
              <button
                type="button"
                onClick={() => jumpToNavDate(computedNav.past)}
                className={navLinkClass(computedNav.past)}
                title={schedule.navigation.past.label || computedNav.past}
                disabled={isMultipleDates}
              >
                Past Booking
              </button>
              <button
                type="button"
                onClick={() => jumpToNavDate(computedNav.selected)}
                className={navLinkClass(computedNav.selected)}
                title={schedule.navigation.selected.label || computedNav.selected}
                disabled={isMultipleDates}
              >
                Today&apos;s Booking
              </button>
              <button
                type="button"
                onClick={() => jumpToNavDate(computedNav.upcoming)}
                className={navLinkClass(computedNav.upcoming)}
                title={schedule.navigation.upcoming.label || computedNav.upcoming}
                disabled={isMultipleDates}
              >
                Upcoming Bookings
              </button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-text-muted">
            <Loader2 size={24} className="animate-spin mr-2" />
            Loading schedule...
          </div>
        ) : schedule.days.length === 0 ? (
          <p className="text-sm text-text-muted italic">
            {isMultipleDates
              ? 'No counselling schedule data for this date period.'
              : 'No counselling schedule data for this date.'}
          </p>
        ) : isMultipleDates ? (
          <div className="space-y-4">
            <PeriodAgendaShell
              periodLabel={dateFilterLabel}
              totalCount={periodAppointments.length}
              days={periodDaySummaries}
              activeDate={periodFocusDate}
              onSelectDate={date => {
                setPeriodFocusDate(date);
                setPeriodShowGrid(false);
              }}
              stats={periodAgendaStats}
              emptyMessage="No appointments found in this date period."
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-text-muted">
                  {periodFocusDate
                    ? 'Showing one day from the selected period. Switch back to All days anytime.'
                    : 'Chronological agenda for the whole period. Pick a day chip to focus.'}
                </p>
                {periodFocusDate ? (
                  <button
                    type="button"
                    onClick={() => setPeriodShowGrid(prev => !prev)}
                    className="text-xs font-semibold text-accent hover:underline"
                  >
                    {periodShowGrid ? 'Hide day grid' : 'Show day grid'}
                  </button>
                ) : null}
              </div>

              <div className="space-y-4 mt-3">
                {periodAppointmentsByDay.map(group => (
                  <section
                    key={group.date}
                    className="rounded-xl border border-border-subtle overflow-hidden"
                  >
                    <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-surface-bg border-b border-border-subtle">
                      <div>
                        <h4 className="text-sm font-semibold text-text-main">{group.label}</h4>
                        <p className="text-[11px] text-text-muted">
                          {group.items.length} appointment{group.items.length === 1 ? '' : 's'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setPeriodFocusDate(group.date);
                          setPeriodShowGrid(true);
                        }}
                        className="text-[11px] font-semibold text-accent hover:underline"
                      >
                        Open grid
                      </button>
                    </div>
                    <div className="divide-y divide-border-subtle">
                      {group.items.map(item => (
                        <div
                          key={item.key}
                          className="flex flex-col lg:flex-row lg:items-center gap-3 px-4 py-3 hover:bg-surface-bg/50"
                        >
                          <div className="w-full lg:w-36 shrink-0">
                            <p className="text-sm font-bold text-text-main">{item.timeLabel}</p>
                            <p className="text-[11px] text-text-muted mt-0.5">{item.dayLabel}</p>
                          </div>
                          <div className="min-w-0 flex-1 space-y-1">
                            <p className="text-sm font-semibold text-text-main truncate">
                              {item.candidateName}
                            </p>
                            <p className="text-xs text-text-muted truncate">
                              {item.kind === 'pending'
                                ? `Queue #${item.queuePosition ?? '—'}${
                                    item.notes ? ` · ${item.notes}` : ''
                                  }`
                                : item.adminName
                                  ? `Counsellor: ${item.adminName}`
                                  : 'Counsellor: Unassigned'}
                            </p>
                          </div>
                          <span
                            className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                              item.kind === 'pending'
                                ? 'border-amber-200 bg-amber-50 text-amber-900'
                                : item.kind === 'complete'
                                  ? 'border-sky-200 bg-sky-50 text-sky-900'
                                  : 'border-emerald-200 bg-emerald-50 text-emerald-900'
                            }`}
                          >
                            {item.kind === 'pending'
                              ? 'In queue'
                              : item.kind === 'complete'
                                ? 'Complete'
                                : 'Booked'}
                          </span>
                          <div className="flex flex-wrap items-center gap-2 shrink-0 lg:ml-auto">
                            {item.bookingId ? (
                              <button
                                type="button"
                                onClick={() => setInteractionBookingId(item.bookingId!)}
                                className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-accent/20"
                              >
                                <MessageSquare size={12} />
                                View Interaction
                              </button>
                            ) : null}
                            {item.leadId ? (
                              <button
                                type="button"
                                onClick={() =>
                                  setJourneyPanel({
                                    studentId: item.leadId!,
                                    studentName: item.candidateName,
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100"
                              >
                                <MapIcon size={12} />
                                View Journey
                              </button>
                            ) : null}
                            {item.bookingId && (item.kind === 'booked' || item.kind === 'complete') ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSessionModal({
                                      bookingId: item.bookingId!,
                                      candidateName: item.candidateName,
                                      dateLabel: item.dayLabel,
                                      timeLabel: item.timeLabel,
                                    })
                                  }
                                  className="inline-flex items-center gap-1 rounded-lg border border-violet-300 bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-900 hover:bg-violet-100"
                                >
                                  <Sparkles size={12} />
                                  Session
                                </button>
                                <button
                                  type="button"
                                  onClick={() =>
                                    openCommunicationsModal(item.bookingId!, item.candidateName)
                                  }
                                  className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-card px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg"
                                >
                                  <MessageSquare size={12} />
                                  Chat
                                </button>
                              </>
                            ) : null}
                            {item.bookingId && item.kind === 'pending' ? (
                              <button
                                type="button"
                                onClick={event =>
                                  openAssignMenu(event, {
                                    id: item.bookingId!,
                                    candidate_name: item.candidateName,
                                    scheduled_time: item.startTime,
                                    notes: item.notes,
                                    lead_id: item.leadId,
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-semibold text-amber-950 hover:bg-amber-100"
                              >
                                <UserPlus size={12} />
                                Assign
                              </button>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </PeriodAgendaShell>

            {periodShowGrid && periodFocusDate
              ? schedule.days
                  .filter(day => day.date === periodFocusDate)
                  .map(day => (
                    <div key={`grid-${day.date}`} className="space-y-2 pt-2">
                      <h3 className="text-sm font-semibold text-text-main">
                        Grid · {day.label}
                      </h3>
                      {renderDayTable(day)}
                    </div>
                  ))
              : null}
          </div>
        ) : (
          renderDayTable(schedule.days[0])
        )}
      </div>

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
                <h3 className="text-lg font-semibold text-text-main">Communication History</h3>
                <p className="text-sm text-text-muted mt-0.5">
                  {communicationsModal.data?.candidate_name || communicationsModal.candidateName}
                </p>
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
                aria-label="Close communications popup"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 custom-scrollbar bg-surface-bg/40">
              {communicationsModal.loading ? (
                <div className="flex items-center justify-center py-16 text-text-muted">
                  <Loader2 size={22} className="animate-spin mr-2" />
                  Loading communications...
                </div>
              ) : !communicationsModal.data || communicationsModal.data.messages.length === 0 ? (
                <div className="rounded-xl border border-border-subtle bg-card px-4 py-8 text-center">
                  <MessageSquare size={28} className="mx-auto text-text-muted mb-2" />
                  <p className="text-sm text-text-main font-medium">No communications found</p>
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
                    <div key={`${message.id}-${message.created_at}`} className="rounded-xl border border-border-subtle bg-card p-3">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${styles.badge}`}
                        >
                          {styles.icon}
                          {message.participant_label}
                        </span>
                        <span className="text-[11px] text-text-muted whitespace-nowrap">
                          {formatDateTime(message.created_at, { second: undefined })}
                        </span>
                      </div>
                      <div className={`rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap break-words ${styles.bubble}`}>
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

      {contextMenu && (
        <div
          ref={menuRef}
          className="fixed z-50 w-[min(100vw-2rem,320px)] max-h-[min(70vh,520px)] flex flex-col rounded-xl border border-border-subtle bg-card shadow-xl py-2"
          style={{
            top: menuPosition?.top ?? contextMenu.y,
            left: menuPosition?.left ?? contextMenu.x,
            visibility: menuPosition ? 'visible' : 'hidden',
          }}
          onContextMenu={event => event.preventDefault()}
        >
          <div className="px-3 py-2 border-b border-border-subtle text-xs font-semibold text-text-muted shrink-0">
            {contextMenu.mode === 'assign' ? (
              <span className="flex items-center gap-2">
                <UserPlus size={14} />
                Assign Admin — {contextMenu.candidateName}
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <ArrowRightLeft size={14} />
                Manage Booking — {contextMenu.candidateName}
              </span>
            )}
          </div>

          {contextMenu.mode === 'assign' && (
            <div className="shrink-0">
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => {
                  setInteractionBookingId(contextMenu.bookingId);
                  setContextMenu(null);
                }}
                className="w-full text-left px-3 py-2.5 text-sm text-text-main hover:bg-surface-bg disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
              >
                <MessageSquare size={15} />
                View Interaction
              </button>
              {contextMenu.leadId ? (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => {
                    setJourneyPanel({
                      studentId: contextMenu.leadId!,
                      studentName: contextMenu.candidateName,
                    });
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-3 py-2.5 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
                >
                  <MapIcon size={15} />
                  View Journey
                </button>
              ) : null}
            </div>
          )}

          {contextMenu.mode === 'manage' && (
            <div className="shrink-0">
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => {
                  setInteractionBookingId(contextMenu.bookingId);
                  setContextMenu(null);
                }}
                className="w-full text-left px-3 py-2.5 text-sm text-text-main hover:bg-surface-bg disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
              >
                <MessageSquare size={15} />
                View Interaction
              </button>
              {contextMenu.leadId ? (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => {
                    setJourneyPanel({
                      studentId: contextMenu.leadId!,
                      studentName: contextMenu.candidateName,
                    });
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-3 py-2.5 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
                >
                  <MapIcon size={15} />
                  View Journey
                </button>
              ) : null}
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => {
                  setSessionModal({
                    bookingId: contextMenu.bookingId,
                    candidateName: contextMenu.candidateName,
                  });
                  setContextMenu(null);
                }}
                className="w-full text-left px-3 py-2.5 text-sm text-violet-800 hover:bg-violet-50 disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
              >
                <Sparkles size={15} />
                Session
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => {
                  setWrapUpDrawer({
                    bookingId: contextMenu.bookingId,
                    candidateName: contextMenu.candidateName,
                  });
                  setContextMenu(null);
                }}
                className="w-full text-left px-3 py-2.5 text-sm text-emerald-700 hover:bg-emerald-50 disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
              >
                <CheckCircle2 size={15} />
                Mark Complete
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleCancelBooking(contextMenu.bookingId)}
                className="w-full text-left px-3 py-2.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-60 flex items-center gap-2 border-b border-border-subtle"
              >
                <XCircle size={15} />
                Cancel booking
              </button>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
          {contextMenu.loading ? (
            <div className="px-3 py-4 text-sm text-text-muted flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Loading admins...
            </div>
          ) : (
            <>
              {contextMenu.mode === 'manage' && (
                <div className="px-3 py-2 text-xs font-semibold text-text-muted uppercase tracking-wide">
                  Switch to admin
                </div>
              )}
              {contextMenu.admins.filter(
                admin =>
                  contextMenu.mode === 'assign' || admin.id !== contextMenu.currentAdminId
              ).length === 0 ? (
                <div className="px-3 py-4 text-sm text-text-muted">
                  {contextMenu.mode === 'manage'
                    ? 'No other admins available at this time.'
                    : 'No admins available at this time.'}
                </div>
              ) : (
                contextMenu.admins
                  .filter(
                    admin =>
                      contextMenu.mode === 'assign' || admin.id !== contextMenu.currentAdminId
                  )
                  .map(admin => (
                    <button
                      key={admin.id}
                      type="button"
                      disabled={actionLoading}
                      onClick={() =>
                        contextMenu.mode === 'assign'
                          ? handleAssignAdmin(contextMenu.bookingId, admin.id)
                          : handleSwitchAdmin(contextMenu.bookingId, admin.id)
                      }
                      className="w-full text-left px-3 py-2 text-sm hover:bg-surface-bg disabled:opacity-60"
                    >
                      <div className="font-medium text-text-main">{admin.name}</div>
                      <div className="text-xs text-text-muted">{admin.email}</div>
                    </button>
                  ))
              )}
            </>
          )}
          </div>
        </div>
      )}

      <SessionWrapUpDrawer
        open={wrapUpDrawer !== null}
        bookingId={wrapUpDrawer?.bookingId ?? null}
        candidateName={wrapUpDrawer?.candidateName ?? 'Candidate'}
        onClose={() => setWrapUpDrawer(null)}
        onSubmitted={handleWrapUpSubmitted}
      />

      <InteractionLogDrawer
        open={interactionBookingId !== null}
        bookingId={interactionBookingId}
        scope="schedule"
        onClose={() => setInteractionBookingId(null)}
      />

      <StudentJourneyPanel
        open={journeyPanel !== null}
        studentId={journeyPanel?.studentId ?? null}
        studentName={journeyPanel?.studentName}
        onClose={() => setJourneyPanel(null)}
      />

      <CounsellingSessionModal
        open={sessionModal !== null}
        bookingId={sessionModal?.bookingId ?? null}
        candidateName={sessionModal?.candidateName ?? ''}
        dateLabel={sessionModal?.dateLabel}
        timeLabel={sessionModal?.timeLabel}
        onClose={() => setSessionModal(null)}
        onStatusUpdated={() => {
          void Promise.all([reloadScheduleQuietly(), loadPendingBookings(), loadPipelineAnalytics()]);
        }}
      />
    </div>
  );
};

export default CounsellingDashboard;
