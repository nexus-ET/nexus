import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarPlus,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  UserPlus,
  X,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import PhoneWithCountryCodeInput from './academia/form/PhoneWithCountryCodeInput';
import { useCountries } from '../hooks/useCountries';
import {
  createStaffBooking,
  type SessionPurpose,
  type StaffBookingNotifications,
  useBookingContactCheck,
  useBookingSessionConfig,
  useCounsellorAvailabilityWeek,
  useCounsellors,
} from '../hooks/useCounsellorAvailability';
import { apiFetch } from '../utils/api';

/** Original Book Appointment purpose list (labels + short helper copy). */
const DEFAULT_SESSION_PURPOSES: SessionPurpose[] = [
  {
    label: 'General Counselling',
    description: 'Initial study-abroad guidance, goals, and overall pathway overview.',
  },
  {
    label: 'Visa Application Help',
    description: 'Help with visa forms, evidence checklist, and interview preparation.',
  },
  {
    label: 'Documentation',
    description: 'Collect, review, and organise documents needed for applications.',
  },
  {
    label: 'University Shortlisting',
    description: 'Match destinations, institutions, and programs to the candidate profile.',
  },
  {
    label: 'Test Prep Guidance',
    description: 'Plan IELTS, TOEFL, GRE, or GMAT prep and target scores.',
  },
  {
    label: 'Application Review',
    description: 'Review application drafts, essays, and submission readiness.',
  },
];

function resolveSessionPurposes(fromApi: SessionPurpose[] | undefined): SessionPurpose[] {
  if (!fromApi?.length) return DEFAULT_SESSION_PURPOSES;

  const byLabel = new Map(fromApi.map(item => [item.label.trim().toLowerCase(), item]));

  // Prefer the original category set so the dropdown stays stable and readable.
  return DEFAULT_SESSION_PURPOSES.map(defaults => {
    const match = byLabel.get(defaults.label.toLowerCase());
    return {
      label: defaults.label,
      description: (match?.description || defaults.description).trim(),
    };
  });
}

export type BookAppointmentModalProps = {
  open?: boolean;
  embedded?: boolean;
  onClose?: () => void;
  onBooked?: (bookingId: number) => void;
};

type CandidateMode = 'existing' | 'new';

type LeadHit = {
  id: number;
  full_name?: string | null;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  phone_number?: string | null;
};

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function addDays(value: Date, amount: number): Date {
  const next = startOfLocalDay(value);
  next.setDate(next.getDate() + amount);
  return next;
}

function toDateKey(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function parseDateKey(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function formatDayHeading(value: Date): string {
  return value.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

function formatWeekRange(start: Date): string {
  const end = addDays(start, 6);
  const startLabel = start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const endLabel = end.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  return `${startLabel} – ${endLabel}`;
}

function isValidEmail(value: string): boolean {
  if (!value.trim()) return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function slotKey(start: string): string {
  return start;
}

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary';

const BookAppointmentModal: React.FC<BookAppointmentModalProps> = ({
  open = true,
  embedded = false,
  onClose,
  onBooked,
}) => {
  const navigate = useNavigate();
  const { countries } = useCountries();
  const configQuery = useBookingSessionConfig(open);
  const counsellorsQuery = useCounsellors(open);

  const [purpose, setPurpose] = useState(DEFAULT_SESSION_PURPOSES[0].label);
  const [purposeMenuOpen, setPurposeMenuOpen] = useState(false);
  const purposeMenuRef = useRef<HTMLDivElement | null>(null);
  const [counsellorId, setCounsellorId] = useState<number | null>(null);
  const [weekStart, setWeekStart] = useState(() => startOfLocalDay(new Date()));
  const [selectedSlotStart, setSelectedSlotStart] = useState<string | null>(null);

  const [candidateMode, setCandidateMode] = useState<CandidateMode>('existing');
  const [leadId, setLeadId] = useState<number | null>(null);
  const [leadHits, setLeadHits] = useState<LeadHit[]>([]);
  const [leadSearching, setLeadSearching] = useState(false);

  const [candidateName, setCandidateName] = useState('');
  const [candidateEmail, setCandidateEmail] = useState('');
  const [candidatePhone, setCandidatePhone] = useState('');
  const [notes, setNotes] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successId, setSuccessId] = useState<number | null>(null);
  const [notificationStatus, setNotificationStatus] =
    useState<StaffBookingNotifications | null>(null);

  const weekStartKey = toDateKey(weekStart);
  const weekQuery = useCounsellorAvailabilityWeek({
    counsellorId,
    startDate: weekStartKey,
    days: 7,
    enabled: open && counsellorId != null,
  });

  const contactCheck = useBookingContactCheck({
    email: candidateEmail,
    phone: candidatePhone,
    enabled: open && candidateMode === 'new' && leadId == null,
  });

  const purposes = useMemo(
    () => resolveSessionPurposes(configQuery.data?.purposes),
    [configQuery.data?.purposes]
  );
  const selectedPurpose =
    purposes.find(item => item.label === purpose) || purposes[0] || DEFAULT_SESSION_PURPOSES[0];

  useEffect(() => {
    if (!open) return;
    if (!purposes.some(item => item.label === purpose)) {
      setPurpose(purposes[0]?.label || DEFAULT_SESSION_PURPOSES[0].label);
    }
  }, [open, purposes, purpose]);

  useEffect(() => {
    if (!purposeMenuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!purposeMenuRef.current?.contains(event.target as Node)) {
        setPurposeMenuOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPurposeMenuOpen(false);
    };
    window.addEventListener('mousedown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('mousedown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [purposeMenuOpen]);

  useEffect(() => {
    setSelectedSlotStart(null);
  }, [counsellorId, weekStartKey]);

  useEffect(() => {
    if (!open || candidateMode !== 'existing') {
      setLeadHits([]);
      return;
    }
    const query = candidateName.trim();
    if (query.length < 2 || leadId != null) {
      setLeadHits([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLeadSearching(true);
      try {
        const data = (await apiFetch(
          `leads/prospects?q=${encodeURIComponent(query)}&limit=8`
        )) as { items?: LeadHit[] } | LeadHit[];
        if (cancelled) return;
        const items = Array.isArray(data) ? data : data.items || [];
        setLeadHits(items.slice(0, 8));
      } catch {
        if (!cancelled) setLeadHits([]);
      } finally {
        if (!cancelled) setLeadSearching(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [candidateName, candidateMode, leadId, open]);

  const durationMinutes = configQuery.data?.slot_duration_minutes ?? 30;
  const bookingsAllowed = configQuery.data?.allow_bookings !== false;
  const weekDays = weekQuery.data?.days || [];

  const matrixRows = useMemo(() => {
    const labels: string[] = [];
    const seen = new Set<string>();
    for (const day of weekDays) {
      for (const slot of day.slots || []) {
        if (!seen.has(slot.label)) {
          seen.add(slot.label);
          labels.push(slot.label);
        }
      }
    }
    return labels;
  }, [weekDays]);

  const slotReasonLabel = (reason?: string | null) => {
    switch (reason) {
      case 'holiday':
        return 'Holiday';
      case 'weekend':
        return 'Non-working day';
      case 'counsellor_busy':
        return 'Booked';
      case 'slot_full':
        return 'Full';
      case 'past':
        return 'Past';
      default:
        return 'Unavailable';
    }
  };

  const duplicateBlocked =
    candidateMode === 'new' &&
    leadId == null &&
    (Boolean(contactCheck.data?.email_taken) || Boolean(contactCheck.data?.phone_taken));

  const canSubmit = useMemo(() => {
    const emailOk = isValidEmail(candidateEmail);
    const newLeadContactOk =
      candidateMode === 'existing'
        ? true
        : Boolean(candidateEmail.trim() || candidatePhone.trim());
    return (
      bookingsAllowed &&
      Boolean(purpose) &&
      counsellorId != null &&
      Boolean(selectedSlotStart) &&
      candidateName.trim().length > 1 &&
      emailOk &&
      newLeadContactOk &&
      !duplicateBlocked &&
      !submitting &&
      (candidateMode === 'existing' ? leadId != null : true)
    );
  }, [
    bookingsAllowed,
    purpose,
    counsellorId,
    selectedSlotStart,
    candidateName,
    candidateEmail,
    candidatePhone,
    candidateMode,
    leadId,
    duplicateBlocked,
    submitting,
  ]);

  const applyLead = (hit: LeadHit) => {
    setCandidateMode('existing');
    setLeadId(hit.id);
    setCandidateName((hit.full_name || hit.name || '').trim());
    setCandidateEmail((hit.email || '').trim());
    setCandidatePhone((hit.phone_number || hit.phone || '').trim());
    setLeadHits([]);
  };

  const switchMode = (mode: CandidateMode) => {
    setCandidateMode(mode);
    setLeadId(null);
    setLeadHits([]);
    setCandidateName('');
    setCandidateEmail('');
    setCandidatePhone('');
    setError(null);
  };

  const clearExistingSelection = () => {
    setLeadId(null);
    setCandidateName('');
    setCandidateEmail('');
    setCandidatePhone('');
  };

  const resetForm = () => {
    setPurpose(purposes[0]?.label || '');
    setCounsellorId(null);
    setWeekStart(startOfLocalDay(new Date()));
    setSelectedSlotStart(null);
    setCandidateMode('existing');
    setLeadId(null);
    setLeadHits([]);
    setCandidateName('');
    setCandidateEmail('');
    setCandidatePhone('');
    setNotes('');
    setError(null);
    setSuccessId(null);
    setNotificationStatus(null);
  };

  const notificationLabel = (value?: string | null) => {
    if (!value) return 'n/a';
    if (value === 'sent') return 'Sent';
    if (value === 'skipped') return 'Skipped (missing contact)';
    if (value === 'disabled') return 'Disabled in settings';
    if (value === 'failed') return 'Failed';
    return value;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || counsellorId == null || !selectedSlotStart) return;
    setSubmitting(true);
    setError(null);
    try {
      const booking = await createStaffBooking({
        scheduled_time: selectedSlotStart,
        admin_id: counsellorId,
        candidate_name: candidateName.trim(),
        candidate_email: candidateEmail.trim() || null,
        candidate_phone: candidatePhone.trim() || null,
        lead_id: candidateMode === 'existing' ? leadId : null,
        session_purpose: purpose || null,
        notes: notes.trim() || null,
        create_lead: candidateMode === 'new',
      });
      setSuccessId(booking.id);
      setNotificationStatus(booking.notifications || null);
      onBooked?.(booking.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not book appointment.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  const formBody = (
    <form onSubmit={handleSubmit} className="space-y-5">
      {!bookingsAllowed ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          New bookings are disabled in App Settings (`ALLOW_BOOKINGS`).
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="block min-w-0 space-y-1 text-sm" ref={purposeMenuRef}>
          <span className="font-semibold text-text-muted">Session purpose</span>
          <div className="relative">
            <button
              type="button"
              onClick={() => setPurposeMenuOpen(openState => !openState)}
              className={`${fieldClass} flex items-center justify-between gap-2 text-left`}
              aria-haspopup="listbox"
              aria-expanded={purposeMenuOpen}
            >
              <span className="truncate font-medium text-text-main">{selectedPurpose.label}</span>
              <ChevronDown
                size={16}
                className={`shrink-0 text-text-muted transition ${purposeMenuOpen ? 'rotate-180' : ''}`}
              />
            </button>
            {purposeMenuOpen ? (
              <ul
                role="listbox"
                className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-border-subtle bg-card py-1 shadow-lg"
              >
                {purposes.map(item => {
                  const active = item.label === purpose;
                  return (
                    <li key={item.label} role="option" aria-selected={active}>
                      <button
                        type="button"
                        onClick={() => {
                          setPurpose(item.label);
                          setPurposeMenuOpen(false);
                        }}
                        className={`flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left hover:bg-surface-bg ${
                          active ? 'bg-primary/5' : ''
                        }`}
                      >
                        <span
                          className={`text-sm font-semibold ${
                            active ? 'text-primary' : 'text-text-main'
                          }`}
                        >
                          {item.label}
                        </span>
                        <span className="text-[11px] leading-snug text-text-muted">
                          {item.description}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
          {/* Keep native required semantics for form submit without showing the messy select text */}
          <input type="hidden" name="session_purpose" value={purpose} required />
        </div>

        <label className="block min-w-0 space-y-1 text-sm">
          <span className="font-semibold text-text-muted">Counsellor</span>
          <select
            value={counsellorId ?? ''}
            onChange={e => {
              setCounsellorId(e.target.value ? Number(e.target.value) : null);
              setSelectedSlotStart(null);
            }}
            className={fieldClass}
            required
          >
            <option value="">Select counsellor…</option>
            {(counsellorsQuery.data || []).map(admin => (
              <option key={admin.id} value={admin.id}>
                {admin.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="space-y-3 rounded-xl border border-border-subtle bg-surface-bg/50 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Candidate</p>
          <div className="inline-flex rounded-lg border border-border-subtle bg-card p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => switchMode('existing')}
              className={`rounded-md px-3 py-1.5 ${
                candidateMode === 'existing' ? 'bg-primary text-white' : 'text-text-muted'
              }`}
            >
              Existing user
            </button>
            <button
              type="button"
              onClick={() => switchMode('new')}
              className={`inline-flex items-center gap-1 rounded-md px-3 py-1.5 ${
                candidateMode === 'new' ? 'bg-primary text-white' : 'text-text-muted'
              }`}
            >
              <UserPlus size={12} />
              New user
            </button>
          </div>
        </div>

        <label className="relative block space-y-1 text-sm">
          <span className="font-semibold text-text-muted">Full name</span>
          <div className="relative">
            {candidateMode === 'existing' ? (
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
              />
            ) : null}
            <input
              value={candidateName}
              onChange={e => {
                setCandidateName(e.target.value);
                if (candidateMode === 'existing' && leadId != null) {
                  setLeadId(null);
                  setCandidateEmail('');
                  setCandidatePhone('');
                }
              }}
              className={`${fieldClass} ${candidateMode === 'existing' ? 'pl-9' : ''}`}
              required
              minLength={2}
              placeholder={
                candidateMode === 'existing'
                  ? 'Type a name to find an existing Nexus lead…'
                  : 'Enter new candidate full name'
              }
              readOnly={candidateMode === 'existing' && leadId != null}
            />
            {leadSearching ? (
              <Loader2
                size={14}
                className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-text-muted"
              />
            ) : null}
          </div>
          {candidateMode === 'existing' && leadHits.length > 0 && leadId == null ? (
            <ul className="absolute z-20 mt-1 max-h-52 w-full overflow-auto rounded-xl border border-border-subtle bg-card shadow-lg">
              {leadHits.map(hit => (
                <li key={hit.id}>
                  <button
                    type="button"
                    onClick={() => applyLead(hit)}
                    className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-surface-bg"
                  >
                    <span className="font-semibold text-text-main">
                      {hit.full_name || hit.name || `Lead #${hit.id}`}
                    </span>
                    <span className="text-xs text-text-muted">
                      {[hit.email, hit.phone_number || hit.phone].filter(Boolean).join(' · ') ||
                        'No contact on file'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </label>

        <div className="grid gap-3 md:grid-cols-2">
          <PhoneWithCountryCodeInput
            label="Contact number"
            value={candidatePhone}
            onChange={setCandidatePhone}
            countries={countries}
            defaultCountryIso2="IN"
            required={candidateMode === 'new'}
            className="space-y-1 text-sm"
            hint={undefined}
          />
          <label className="block space-y-1 text-sm">
            <span className="font-semibold text-text-muted">Email</span>
            <input
              type="email"
              value={candidateEmail}
              onChange={e => setCandidateEmail(e.target.value)}
              className={fieldClass}
              required={candidateMode === 'new'}
              readOnly={candidateMode === 'existing' && leadId != null}
            />
            {!isValidEmail(candidateEmail) ? (
              <span className="text-xs text-rose-600">Enter a valid email.</span>
            ) : null}
          </label>
        </div>

        {candidateMode === 'existing' ? (
          leadId != null ? (
            <p className="text-xs text-text-muted">
              Linked to existing lead #{leadId}. Name, phone, and email are filled from Nexus.{' '}
              <button
                type="button"
                onClick={clearExistingSelection}
                className="font-semibold text-primary"
              >
                Change
              </button>
            </p>
          ) : (
            <p className="text-xs text-text-muted">
              Select a matching lead from the name suggestions to autofill phone and email.
            </p>
          )
        ) : (
          <div className="space-y-1">
            <p className="text-xs text-text-muted">
              A new Nexus lead will be created from these details when you book.
            </p>
            {contactCheck.isFetching ? (
              <p className="text-xs text-text-muted">Checking for registered email/phone…</p>
            ) : null}
            {contactCheck.data?.email_taken ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                This email is already registered
                {contactCheck.data.email_lead_id
                  ? ` (lead #${contactCheck.data.email_lead_id})`
                  : ''}
                . Switch to <strong>Existing user</strong> and select that candidate.
              </p>
            ) : null}
            {contactCheck.data?.phone_taken ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                This phone number is already registered
                {contactCheck.data.phone_lead_id
                  ? ` (lead #${contactCheck.data.phone_lead_id})`
                  : ''}
                . Switch to <strong>Existing user</strong> and select that candidate.
              </p>
            ) : null}
          </div>
        )}
      </div>

      <div className="space-y-3 rounded-xl border border-border-subtle p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
              Counsellor calendar
            </p>
            <p className="text-xs text-text-muted">
              Weekly slot matrix · {durationMinutes}-minute slots
              {configQuery.data
                ? ` · Office ${configQuery.data.office_hours_start}–${configQuery.data.office_hours_end}`
                : ''}
              · holidays &amp; non-working days from settings
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setWeekStart(prev => addDays(prev, -7));
                setSelectedSlotStart(null);
              }}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg"
            >
              <ChevronLeft size={14} />
              Previous
            </button>
            <span className="min-w-[9.5rem] text-center text-xs font-semibold text-text-main">
              {formatWeekRange(weekStart)}
            </span>
            <button
              type="button"
              onClick={() => {
                setWeekStart(prev => addDays(prev, 7));
                setSelectedSlotStart(null);
              }}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {!counsellorId ? (
          <p className="text-sm text-text-muted">Select a counsellor to load their weekly slots.</p>
        ) : weekQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading counsellor calendar…
          </div>
        ) : weekQuery.isError ? (
          <p className="text-sm text-rose-700">Could not load counsellor availability.</p>
        ) : matrixRows.length === 0 ? (
          <p className="text-sm text-text-muted">No office-hour slots configured for this week.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border-subtle">
            <table className="min-w-full border-collapse text-xs">
              <thead>
                <tr className="bg-surface-bg">
                  <th className="sticky left-0 z-10 border-b border-r border-border-subtle bg-surface-bg px-2 py-2 text-left font-semibold text-text-muted">
                    Time
                  </th>
                  {weekDays.map(day => {
                    const dayKey = day.date.slice(0, 10);
                    const dayDate = parseDateKey(dayKey);
                    const status = day.day_status || 'open';
                    return (
                      <th
                        key={dayKey}
                        className={`border-b border-border-subtle px-2 py-2 text-center font-semibold ${
                          status === 'holiday' || status === 'weekend'
                            ? 'bg-amber-50 text-amber-900'
                            : 'text-text-main'
                        }`}
                      >
                        <div>{formatDayHeading(dayDate)}</div>
                        {status === 'holiday' ? (
                          <div className="text-[10px] font-normal">Holiday</div>
                        ) : null}
                        {status === 'weekend' ? (
                          <div className="text-[10px] font-normal">Non-working</div>
                        ) : null}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {matrixRows.map(label => (
                  <tr key={label} className="odd:bg-card even:bg-surface-bg/40">
                    <td className="sticky left-0 z-10 whitespace-nowrap border-r border-border-subtle bg-inherit px-2 py-1.5 font-semibold text-text-muted">
                      {label}
                    </td>
                    {weekDays.map(day => {
                      const dayKey = day.date.slice(0, 10);
                      const slot = (day.slots || []).find(item => item.label === label);
                      if (!slot) {
                        return (
                          <td
                            key={`${dayKey}-${label}`}
                            className="border-b border-border-subtle px-1 py-1 text-center text-text-muted"
                          >
                            —
                          </td>
                        );
                      }
                      const selected = selectedSlotStart === slotKey(slot.start);
                      const closed =
                        slot.reason === 'holiday' || slot.reason === 'weekend';
                      const isBusy = slot.reason === 'counsellor_busy';
                      const busyName = (slot.candidate_name || '').trim();
                      const busyTitle = isBusy
                        ? busyName
                          ? `Booked for ${busyName} — click to open session`
                          : 'Booked — click to open session'
                        : slot.available
                          ? `Book ${label} on ${formatDayHeading(parseDateKey(dayKey))}`
                          : slotReasonLabel(slot.reason);
                      return (
                        <td
                          key={`${dayKey}-${label}`}
                          className="border-b border-border-subtle px-1 py-1 text-center"
                        >
                          <button
                            type="button"
                            disabled={!slot.available && !isBusy}
                            onClick={() => {
                              if (isBusy && slot.booking_id) {
                                const params = new URLSearchParams();
                                if (busyName) params.set('name', busyName);
                                if (slot.lead_id) params.set('leadId', String(slot.lead_id));
                                const qs = params.toString();
                                navigate(
                                  `/my-bookings/session/${slot.booking_id}${qs ? `?${qs}` : ''}`
                                );
                                return;
                              }
                              setSelectedSlotStart(slot.start);
                            }}
                            title={busyTitle}
                            className={`w-full rounded-md px-1.5 py-1.5 text-[11px] font-semibold transition ${
                              selected
                                ? 'bg-primary text-white'
                                : slot.available
                                  ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                                  : isBusy
                                    ? 'cursor-pointer bg-slate-200 text-slate-700 hover:bg-slate-300'
                                    : closed
                                      ? 'cursor-not-allowed bg-amber-50/80 text-amber-800/80'
                                      : 'cursor-not-allowed bg-slate-100 text-slate-500'
                            }`}
                          >
                            {slot.available
                              ? 'Open'
                              : isBusy
                                ? 'Booked'
                                : slot.reason === 'holiday'
                                  ? 'Holiday'
                                  : slot.reason === 'weekend'
                                    ? 'Off'
                                    : slot.reason === 'past'
                                      ? 'Past'
                                      : slot.reason === 'slot_full'
                                        ? 'Full'
                                        : 'N/A'}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedSlotStart ? (
          <p className="text-xs text-text-muted">
            Selected slot:{' '}
            <span className="font-semibold text-text-main">
              {new Date(selectedSlotStart).toLocaleString(undefined, {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </span>
          </p>
        ) : null}

        <div className="flex flex-wrap gap-3 text-[10px] text-text-muted">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-50 ring-1 ring-emerald-200" /> Open
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-200 ring-1 ring-slate-300" /> Booked (hover name · click session)
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-100 ring-1 ring-slate-200" /> Past / full
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-50 ring-1 ring-amber-200" /> Holiday / non-working
          </span>
        </div>
      </div>

      <label className="block space-y-1 text-sm">
        <span className="font-semibold text-text-muted">Internal notes (optional)</span>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={2}
          className={fieldClass}
          placeholder="Visible on the booking record for counsellors"
        />
      </label>

      {error ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {successId != null ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-900">
          <p className="font-semibold">Appointment booked (#{successId}).</p>
          <p className="mt-1 text-xs">
            Candidate and counsellor communications were attempted separately by email and WhatsApp.
          </p>
          {notificationStatus ? (
            <ul className="mt-2 space-y-0.5 text-xs text-emerald-950/90">
              <li>Candidate WhatsApp: {notificationLabel(notificationStatus.whatsapp)}</li>
              <li>Candidate email: {notificationLabel(notificationStatus.email)}</li>
              <li>Counsellor WhatsApp: {notificationLabel(notificationStatus.whatsapp_admin)}</li>
              <li>Counsellor email: {notificationLabel(notificationStatus.email_admin)}</li>
            </ul>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-3">
            <Link
              to={`/my-bookings/session/${successId}`}
              className="font-semibold text-primary hover:underline"
            >
              Open session
            </Link>
            <Link to="/counselling" className="font-semibold text-primary hover:underline">
              Open Manage Appointments
            </Link>
            <Link to="/my-bookings" className="font-semibold text-primary hover:underline">
              Open My Appointments
            </Link>
            <button
              type="button"
              onClick={resetForm}
              className="font-semibold text-text-muted hover:text-text-main"
            >
              Book another
            </button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border-subtle pt-4">
        {onClose && !embedded ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted hover:bg-surface-bg"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="submit"
          disabled={!canSubmit || successId != null}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarPlus size={16} />}
          Book Appointment
        </button>
      </div>
    </form>
  );

  if (embedded) {
    return (
      <section className="rounded-2xl border border-border-subtle bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-start gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary">
            <CalendarPlus size={20} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-text-main">Book Appointment</h1>
            <p className="text-sm text-text-muted">
              Schedule a counselling session with live counsellor availability, then notify both
              parties.
            </p>
          </div>
        </div>
        {formBody}
      </section>
    );
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="book-appointment-title"
      onMouseDown={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg px-5 py-4">
          <div>
            <h2 id="book-appointment-title" className="text-lg font-semibold text-text-main">
              Book Appointment
            </h2>
            <p className="text-sm text-text-muted">Staff scheduling for counselling sessions</p>
          </div>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"
              aria-label="Close book appointment"
            >
              <X size={16} />
            </button>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 custom-scrollbar">{formBody}</div>
      </div>
    </div>
  );
};

export default BookAppointmentModal;
