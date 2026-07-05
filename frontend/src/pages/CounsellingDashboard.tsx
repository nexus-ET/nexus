import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Calendar, Loader2, RefreshCw, UserPlus, XCircle, ArrowRightLeft, X, Bot, UserRound, MessageSquare, CheckCircle2 } from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';
import { computeFloatingMenuPosition } from '../utils/floatingMenuPosition';
import SessionWrapUpDrawer from '../components/SessionWrapUpDrawer';
import PipelineAnalyticsPanel, { PipelineAnalyticsData } from '../components/PipelineAnalyticsPanel';

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
}

interface GridPendingQueueSlot {
  queue_position: number;
  booking: GridPendingBooking | null;
}

interface GridAdminCell {
  admin_id: number;
  status: 'available' | 'booked' | 'past' | 'complete';
  label: string;
  candidate_name?: string | null;
  booking_id?: number | null;
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

const CounsellingDashboard: React.FC = () => {
  const [focusDate, setFocusDate] = useState<Date>(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), today.getDate());
  });
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
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const communicationsEndRef = useRef<HTMLDivElement | null>(null);
  const focusDateRef = useRef(focusDate);
  focusDateRef.current = focusDate;

  const loadSchedule = useCallback(async (date: Date, showSpinner = true) => {
    if (!hasValidSession()) return;
    try {
      if (showSpinner) setLoading(true);
      setError(null);
      const params = new URLSearchParams({ date: toIsoDate(date) });
      const data = (await apiFetch(`bookings/grid?${params.toString()}`)) as ScheduleGridResponse;
      setSchedule(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load counselling schedule.');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

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
    loadSchedule(focusDate);
    loadPendingBookings();
    loadPipelineAnalytics();
  }, [focusDate, loadSchedule, loadPendingBookings, loadPipelineAnalytics]);

  useEffect(() => {
    const interval = setInterval(() => {
      loadSchedule(focusDateRef.current, false);
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
    const day = schedule.days[0];
    if (!day) return 0;

    return day.rows.reduce((sum, row) => {
      const queued =
        row.pending_queue.filter(slot => slot.booking).length + row.hidden_pending_count;
      const assigned = row.admin_cells.filter(
        cell => cell.status === 'booked' || cell.status === 'complete'
      ).length;
      return sum + queued + assigned;
    }, 0);
  }, [schedule.days]);

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
      await Promise.all([loadSchedule(focusDateRef.current, false), loadPendingBookings()]);
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
      await Promise.all([loadSchedule(focusDateRef.current, false), loadPendingBookings()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to switch admin.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelBooking = async (bookingId: number) => {
    if (!window.confirm('Cancel this booked counselling session?')) return;
    try {
      setActionLoading(true);
      await apiFetch(`bookings/cancel/${bookingId}`, { method: 'POST' });
      setContextMenu(null);
      await Promise.all([loadSchedule(focusDateRef.current, false), loadPendingBookings()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel booking.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefreshAll = async () => {
    await Promise.all([
      loadSchedule(focusDate),
      loadPendingBookings(),
      loadPipelineAnalytics(),
    ]);
  };

  const handleWrapUpSubmitted = async () => {
    setContextMenu(null);
    await Promise.all([
      loadSchedule(focusDateRef.current, false),
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
              <col key={admin.id} className="w-[72px]" />
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
                        {cell.status === 'booked' ? (
                          <div className="flex items-center justify-between gap-1 min-w-0">
                            <span className="truncate font-semibold">{cell.candidate_name || 'Candidate'}</span>
                            <span className="shrink-0 text-[9px] uppercase tracking-wide opacity-90">Booked</span>
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
  const isRealToday = schedule.focus_date === schedule.calendar_today;

  const computedNav = useMemo(() => {
    const past = new Date(focusDate);
    past.setDate(past.getDate() - 1);
    const upcoming = new Date(focusDate);
    upcoming.setDate(upcoming.getDate() + 1);
    return {
      past: toIsoDate(past),
      selected: toIsoDate(focusDate),
      upcoming: toIsoDate(upcoming),
    };
  }, [focusDate]);

  const navLinkClass = (targetDate: string) =>
    `inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
      toIsoDate(focusDate) === targetDate
        ? 'border-accent bg-accent/10 text-accent'
        : 'border-border-subtle bg-card text-text-main hover:bg-surface-bg'
    }`;

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
            {selectedDay && isRealToday && (
              <span className="inline-flex w-fit items-center rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1 text-[11px] font-medium text-text-muted">
                Calendar today
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            <div className="rounded-xl border border-border-subtle bg-surface-bg px-4 py-3 min-w-[180px] flex-1 sm:flex-none">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Bookings</p>
              <p className="text-2xl font-bold text-text-main mt-1 leading-none">{dayBookingCount}</p>
              <p className="text-xs text-text-muted mt-1.5">
                {selectedDay
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

          <div className="flex flex-col lg:flex-row lg:items-center gap-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-text-muted whitespace-nowrap">
                Select date
              </label>
              <DatePicker
                selected={focusDate}
                onChange={date => {
                  if (date) setFocusDate(date);
                }}
                dateFormat="EEE, d MMM yyyy"
                className="w-full sm:w-[200px] rounded-lg border border-border-subtle bg-surface-bg px-3 py-1.5 text-sm text-text-main"
                calendarClassName="nexus-roster-datepicker"
                popperClassName="nexus-datepicker-popper"
                portalId="nexus-datepicker-portal"
                popperPlacement="bottom-start"
                popperProps={{ strategy: 'fixed' }}
              />
              {!isRealToday && (
                <button
                  type="button"
                  onClick={() => setFocusDate(parseIsoDate(schedule.calendar_today))}
                  className="text-xs text-accent hover:underline whitespace-nowrap"
                >
                  Jump to today
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
              <button
                type="button"
                onClick={() => setFocusDate(parseIsoDate(computedNav.past))}
                className={navLinkClass(computedNav.past)}
                title={schedule.navigation.past.label || computedNav.past}
              >
                Past Booking
              </button>
              <button
                type="button"
                onClick={() => setFocusDate(parseIsoDate(computedNav.selected))}
                className={navLinkClass(computedNav.selected)}
                title={schedule.navigation.selected.label || computedNav.selected}
              >
                Today&apos;s Booking
              </button>
              <button
                type="button"
                onClick={() => setFocusDate(parseIsoDate(computedNav.upcoming))}
                className={navLinkClass(computedNav.upcoming)}
                title={schedule.navigation.upcoming.label || computedNav.upcoming}
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
        ) : !selectedDay ? (
          <p className="text-sm text-text-muted italic">No counselling schedule data for this date.</p>
        ) : (
          renderDayTable(selectedDay)
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
                          {formatCommunicationTime(message.created_at)}
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

          {contextMenu.mode === 'manage' && (
            <div className="shrink-0">
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
    </div>
  );
};

export default CounsellingDashboard;
