import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { AlertCircle, ArrowDown, ArrowUp, ArrowUpDown, Ban, Calendar, CheckCircle2, Clock, History, Map as MapIcon, MessageSquareText, Pencil, Plus, Search, X } from 'lucide-react';
import { useCreateOfflineLead, useOfflineLeadDuplicateCheck, useOfflineLeads, useSetOfflineLeadActive, useUpdateOfflineLead } from '../hooks/useOfflineLeads';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { useCountries } from '../hooks/useCountries';
import { useLevels } from '../hooks/useLevels';
import { levelSelectOptions } from '../constants/levels';
import { findGpaCgpaScore, useGpaCgpaScores } from '../hooks/useGpaCgpaScores';
import { useFullTimeStudyYears, findFullTimeStudyYear, filterFullTimeStudyYearsByLevel } from '../hooks/useFullTimeStudyYears';
import {
  findQualificationProgram,
  useQualificationPrograms,
} from '../hooks/useQualificationPrograms';
import { useEducationMajors } from '../hooks/useEducationMajors';
import SearchableMultiSelect from '../components/academia/SearchableMultiSelect';
import { StandaloneTableOverflowMenu } from '../components/ui/DataTable';
import CounsellingSessionDrawer from '../components/CounsellingSessionDrawer';
import CounselorFollowupDrawer from '../components/CounselorFollowupDrawer';
import LeadBookingsModal from '../components/LeadBookingsModal';
import StudentJourneyPanel from '../components/StudentJourneyPanel';
import { useConfirmation } from '../context/ConfirmationContext';
import type { LeadBookingSummary } from '../hooks/useLeadBookings';
import { bookAppointmentHref } from '../utils/bookAppointmentHref';
import {
  SCHEDULED_TIME_BADGE_CLASS,
  classifyFollowupDate,
  classifyScheduledTime,
  followupCalendarDayDiff,
  formatScheduledTimeRange,
  localCalendarDayDiff,
  matchCalendarDateKeyword,
  parseScheduledWallClock,
  scheduledWeekdayShort,
  type ScheduledTimeTone,
} from '../utils/scheduledTimeBadge';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';
import {
  buildEducationPayload,
  validateEducationFields,
} from '../utils/offlineLeadEducation';
import { gpaCgpaToFormFields, validateGpaCgpaScore } from '../utils/gpaCgpaScore';
import {
  computeAgeFromDob,
  formatAgeYmd,
  formatPhoneCountryLabel,
  parseStoredPhone,
  phoneLocalToDigits,
  sanitizePhoneLocalDraft,
  validatePhoneWithCountry,
  validateDateOfBirth,
  PHONE_LOCAL_DRAFT_MAX_LENGTH,
  PHONE_LOCAL_PLACEHOLDER,
} from '../utils/phoneCountry';
import type { GpaCgpaScoreRecord } from '../types/gpaCgpaScore';
import type { QualificationProgramRecord } from '../types/qualificationProgram';
import type { CountryRecord } from '../types/country';
import {
  validateLocationFields,
  validateStudyInterestFields,
} from '../utils/offlineLeadForm';
import type {
  OfflineLeadCreatePayload,
  OfflineLeadItem,
  OfflineLeadSortDirection,
  OfflineLeadSortField,
  OfflineLeadStatusFilter,
  OfflineLeadsQuery,
} from '../types/offlineLead';
import {
  readStoredTablePageSize,
  storeTablePageSize,
  TABLE_PAGE_SIZE_OPTIONS,
  type TablePageSize,
} from '../utils/tablePageSize';
import {
  OFFLINE_LEAD_ACTIVE_REASONS,
  OFFLINE_LEAD_INACTIVE_REASONS,
} from '../constants/offlineLeadStatusReasons';

const OFFLINE_LEADS_PAGE_SIZE_KEY = 'nexus.offlineLeads.pageSize';
const OFFLINE_LEADS_COLUMNS_KEY = 'nexus.offlineLeads.visibleColumns.v9';
const OFFLINE_LEADS_ORDER_KEY = 'nexus.offlineLeads.columnOrder.v2';
const OFFLINE_LEADS_PIN_KEY = 'nexus.offlineLeads.columnPin.v2';
const OFFLINE_LEADS_WIDTH_KEY = 'nexus.offlineLeads.columnWidths.v2';
const PAGE_SIZE_OPTIONS = TABLE_PAGE_SIZE_OPTIONS;

type OfflineLeadsPageToken = number | 'ellipsis';

function offlineLeadsPageRange(from: number, to: number): number[] {
  const items: number[] = [];
  for (let i = from; i <= to; i += 1) items.push(i);
  return items;
}

/** Compact window: 1 … 8 9 10 … 42 */
function offlineLeadsPageTokens(current: number, pageCount: number, siblingCount = 1): OfflineLeadsPageToken[] {
  if (pageCount <= 1) return pageCount === 1 ? [1] : [];

  const totalSlots = siblingCount * 2 + 5;
  if (pageCount <= totalSlots) return offlineLeadsPageRange(1, pageCount);

  const leftSibling = Math.max(current - siblingCount, 1);
  const rightSibling = Math.min(current + siblingCount, pageCount);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < pageCount - 1;

  if (!showLeftEllipsis && showRightEllipsis) {
    const leftCount = 3 + 2 * siblingCount;
    return [...offlineLeadsPageRange(1, leftCount), 'ellipsis', pageCount];
  }
  if (showLeftEllipsis && !showRightEllipsis) {
    const rightCount = 3 + 2 * siblingCount;
    return [1, 'ellipsis', ...offlineLeadsPageRange(pageCount - rightCount + 1, pageCount)];
  }
  return [
    1,
    'ellipsis',
    ...offlineLeadsPageRange(leftSibling, rightSibling),
    'ellipsis',
    pageCount,
  ];
}

type OfflineLeadColumnKey =
  | 'full_name'
  | 'student_id'
  | 'source'
  | 'email'
  | 'phone_number'
  | 'date_of_birth'
  | 'program'
  | 'major'
  | 'university'
  | 'graduation_year'
  | 'gpa_cgpa'
  | 'study_interest'
  | 'city'
  | 'state'
  | 'country'
  | 'new_booking'
  | 'scheduled_time'
  | 'counselor_notes'
  | 'lead_status'
  | 'followup_status'
  | 'followup_date'
  | 'created_at';

const OFFLINE_LEAD_COLUMN_DEFS: Array<{
  key: OfflineLeadColumnKey;
  label: string;
  defaultVisible: boolean;
  required?: boolean;
}> = [
  { key: 'full_name', label: 'Name', defaultVisible: true, required: true },
  { key: 'student_id', label: 'Student ID', defaultVisible: true },
  { key: 'source', label: 'Source', defaultVisible: true },
  { key: 'email', label: 'Email', defaultVisible: true },
  { key: 'phone_number', label: 'Phone', defaultVisible: true },
  { key: 'date_of_birth', label: 'Date of Birth', defaultVisible: true },
  { key: 'program', label: 'Program', defaultVisible: false },
  { key: 'major', label: 'Major', defaultVisible: false },
  { key: 'university', label: 'University', defaultVisible: false },
  { key: 'graduation_year', label: 'Graduation Year', defaultVisible: false },
  { key: 'gpa_cgpa', label: 'GPA / CGPA', defaultVisible: false },
  { key: 'study_interest', label: 'Destination / Interest', defaultVisible: false },
  { key: 'city', label: 'City', defaultVisible: false },
  { key: 'state', label: 'State', defaultVisible: false },
  { key: 'country', label: 'Country', defaultVisible: false },
  { key: 'counselor_notes', label: 'Counselor Notes', defaultVisible: true },
  { key: 'new_booking', label: 'New Booking', defaultVisible: true },
  { key: 'scheduled_time', label: 'Booking Date & Time', defaultVisible: true },
  { key: 'lead_status', label: 'Lead Status', defaultVisible: true },
  { key: 'followup_status', label: 'Lead Follow-up Status', defaultVisible: true },
  { key: 'followup_date', label: 'Lead Follow-up Date', defaultVisible: true },
  { key: 'created_at', label: 'Date Added', defaultVisible: true },
];

const DEFAULT_PINNED_LEFT: OfflineLeadColumnKey[] = ['full_name'];
const ALL_OFFLINE_LEAD_KEYS = OFFLINE_LEAD_COLUMN_DEFS.map(column => column.key);

const REQUIRED_OFFLINE_LEAD_COLUMNS = OFFLINE_LEAD_COLUMN_DEFS.filter(column => column.required).map(
  column => column.key
);

function defaultOfflineLeadColumns(): OfflineLeadColumnKey[] {
  return OFFLINE_LEAD_COLUMN_DEFS.filter(column => column.defaultVisible).map(column => column.key);
}

function remapOfflineLeadColumnKey(key: string): string {
  return key === 'booking' ? 'scheduled_time' : key;
}

function ensureNewBookingBeforeScheduledTime(keys: OfflineLeadColumnKey[]): OfflineLeadColumnKey[] {
  const withoutNew = keys.filter(key => key !== 'new_booking');
  const scheduledIdx = withoutNew.indexOf('scheduled_time');
  if (scheduledIdx < 0 || !keys.includes('new_booking')) return keys;
  if (keys.indexOf('new_booking') === scheduledIdx) return keys;
  const next = [...withoutNew];
  next.splice(scheduledIdx, 0, 'new_booking');
  return next;
}

function ensureCounselorNotesBeforeNewBooking(keys: OfflineLeadColumnKey[]): OfflineLeadColumnKey[] {
  const bookingIdx = keys.indexOf('new_booking');
  const notesIdx = keys.indexOf('counselor_notes');
  if (bookingIdx < 0 || notesIdx < 0 || notesIdx === bookingIdx - 1) return keys;
  const next = keys.filter(key => key !== 'counselor_notes');
  next.splice(next.indexOf('new_booking'), 0, 'counselor_notes');
  return next;
}

function normalizeOfflineLeadColumns(keys: string[]): OfflineLeadColumnKey[] {
  const allowed = new Set(OFFLINE_LEAD_COLUMN_DEFS.map(column => column.key));
  const selected = new Set(
    keys
      .map(remapOfflineLeadColumnKey)
      .filter((key): key is OfflineLeadColumnKey => allowed.has(key as OfflineLeadColumnKey))
  );
  for (const key of REQUIRED_OFFLINE_LEAD_COLUMNS) {
    selected.add(key);
  }
  return OFFLINE_LEAD_COLUMN_DEFS.map(column => column.key).filter(key => selected.has(key));
}

function insertFollowupStatusColumn(keys: OfflineLeadColumnKey[]): OfflineLeadColumnKey[] {
  if (keys.includes('followup_status')) return keys;
  const next = [...keys];
  const leadStatusIdx = next.indexOf('lead_status');
  next.splice(leadStatusIdx >= 0 ? leadStatusIdx + 1 : next.length, 0, 'followup_status');
  return next;
}

function insertFollowupDateColumn(keys: OfflineLeadColumnKey[]): OfflineLeadColumnKey[] {
  if (keys.includes('followup_date')) return keys;
  const next = [...keys];
  const statusIdx = next.indexOf('followup_status');
  next.splice(statusIdx >= 0 ? statusIdx + 1 : next.length, 0, 'followup_date');
  return next;
}

function readStoredOfflineLeadColumns(): OfflineLeadColumnKey[] {
  try {
    const raw = localStorage.getItem(OFFLINE_LEADS_COLUMNS_KEY);
    if (!raw) return defaultOfflineLeadColumns();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return defaultOfflineLeadColumns();
    let normalized = normalizeOfflineLeadColumns(parsed.map(String));
    if (!normalized.length) return defaultOfflineLeadColumns();
    const migratedKey = `${OFFLINE_LEADS_COLUMNS_KEY}:followup-status-v1`;
    if (!localStorage.getItem(migratedKey)) {
      localStorage.setItem(migratedKey, '1');
      if (!normalized.includes('followup_status')) {
        normalized = insertFollowupStatusColumn(normalized);
        storeOfflineLeadColumns(normalized);
      }
    }
    const dateMigratedKey = `${OFFLINE_LEADS_COLUMNS_KEY}:followup-date-v1`;
    if (!localStorage.getItem(dateMigratedKey)) {
      localStorage.setItem(dateMigratedKey, '1');
      if (!normalized.includes('followup_date')) {
        normalized = insertFollowupDateColumn(normalized);
        storeOfflineLeadColumns(normalized);
      }
    }
    return normalized;
  } catch {
    return defaultOfflineLeadColumns();
  }
}

function storeOfflineLeadColumns(columns: OfflineLeadColumnKey[]) {
  try {
    localStorage.setItem(OFFLINE_LEADS_COLUMNS_KEY, JSON.stringify(columns));
  } catch {
    /* ignore quota / private mode */
  }
}

function normalizeOfflineLeadOrder(keys: string[]): OfflineLeadColumnKey[] {
  const allowed = new Set(ALL_OFFLINE_LEAD_KEYS);
  const seen = new Set<OfflineLeadColumnKey>();
  const ordered: OfflineLeadColumnKey[] = [];
  for (const key of keys.map(remapOfflineLeadColumnKey)) {
    if (!allowed.has(key as OfflineLeadColumnKey)) continue;
    const typed = key as OfflineLeadColumnKey;
    if (seen.has(typed)) continue;
    seen.add(typed);
    ordered.push(typed);
  }
  for (const key of ALL_OFFLINE_LEAD_KEYS) {
    if (!seen.has(key)) ordered.push(key);
  }
  return ensureCounselorNotesBeforeNewBooking(ensureNewBookingBeforeScheduledTime(ordered));
}

function readStoredOfflineLeadOrder(): OfflineLeadColumnKey[] {
  try {
    const raw = localStorage.getItem(OFFLINE_LEADS_ORDER_KEY);
    if (!raw) return [...ALL_OFFLINE_LEAD_KEYS];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [...ALL_OFFLINE_LEAD_KEYS];
    let keys = parsed.map(String);
    const dateMigratedKey = `${OFFLINE_LEADS_ORDER_KEY}:followup-date-v1`;
    if (!localStorage.getItem(dateMigratedKey)) {
      localStorage.setItem(dateMigratedKey, '1');
      const remapped = keys.map(remapOfflineLeadColumnKey);
      if (!remapped.includes('followup_date')) {
        const statusIdx = remapped.indexOf('followup_status');
        const next = [...keys];
        next.splice(statusIdx >= 0 ? statusIdx + 1 : next.length, 0, 'followup_date');
        keys = next;
      }
    }
    return normalizeOfflineLeadOrder(keys);
  } catch {
    return [...ALL_OFFLINE_LEAD_KEYS];
  }
}

type OfflineLeadPinState = { left: OfflineLeadColumnKey[]; right: OfflineLeadColumnKey[] };

function readStoredOfflineLeadPins(): OfflineLeadPinState {
  try {
    const raw = localStorage.getItem(OFFLINE_LEADS_PIN_KEY);
    if (!raw) return { left: [...DEFAULT_PINNED_LEFT], right: [] };
    const parsed = JSON.parse(raw) as Partial<OfflineLeadPinState>;
    const allowed = new Set(ALL_OFFLINE_LEAD_KEYS);
    const unique = (keys: string[]) => {
      const seen = new Set<OfflineLeadColumnKey>();
      return keys
        .map(key => remapOfflineLeadColumnKey(key))
        .filter((key): key is OfflineLeadColumnKey => {
          if (!allowed.has(key as OfflineLeadColumnKey) || seen.has(key as OfflineLeadColumnKey)) return false;
          seen.add(key as OfflineLeadColumnKey);
          return true;
        });
    };
    const left = unique((parsed.left ?? DEFAULT_PINNED_LEFT).map(String));
    const right = unique((parsed.right ?? []).map(String)).filter(key => !left.includes(key));
    return { left, right };
  } catch {
    return { left: [...DEFAULT_PINNED_LEFT], right: [] };
  }
}

function readStoredOfflineLeadWidths(): Partial<Record<OfflineLeadColumnKey, number>> {
  try {
    const raw = localStorage.getItem(OFFLINE_LEADS_WIDTH_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, number>;
    if (typeof parsed.scheduled_time !== 'number' && typeof parsed.booking === 'number') {
      parsed.scheduled_time = parsed.booking;
    }
    const next: Partial<Record<OfflineLeadColumnKey, number>> = {};
    for (const key of ALL_OFFLINE_LEAD_KEYS) {
      const value = parsed[key];
      if (typeof value === 'number' && value >= 72 && value <= 640) next[key] = value;
    }
    return next;
  } catch {
    return {};
  }
}

const EMPTY_FORM: OfflineLeadCreatePayload = {
  first_name: '',
  middle_name: '',
  last_name: '',
  email: '',
  phone_country_iso2: '',
  phone_local: '',
  date_of_birth: '',
  target_destination_iso2s: [],
  target_level_id: undefined,
  target_major_ids: [],
  target_program_codes: [],
  education: {
    program_code: '',
    full_time_study_years: '',
    major: '',
    gpa_cgpa_code: '',
    gpa_cgpa_other: '',
    university: '',
    graduation_year: undefined,
  },
  location: {
    address_line_1: '',
    address_line_2: '',
    city: '',
    state: '',
    country_iso2: '',
    zip_code: '',
  },
};

function serializeOfflineLeadForm(form: OfflineLeadCreatePayload): string {
  return JSON.stringify(form);
}

const UNSAVED_CLOSE_MESSAGE =
  'You have unsaved changes. Discard them and close this form?';

function leadToForm(
  lead: OfflineLeadItem,
  countries: CountryRecord[],
  programs: QualificationProgramRecord[],
  gpaCgpaScores: GpaCgpaScoreRecord[]
): OfflineLeadCreatePayload {
  const { countryIso2, localNumber } = parseStoredPhone(lead.phone_number, countries);
  const email = lead.email?.includes('@edutrust.nexus') ? '' : lead.email || '';
  const programCode = lead.program_code || lead.degree_code || '';
  const matchedProgram = findQualificationProgram(programs, programCode);
  const gpaFields = gpaCgpaToFormFields(lead.gpa_cgpa, lead.gpa_cgpa_code, gpaCgpaScores);
  const destinationIso2 =
    lead.target_destination_iso2 ||
    countries.find(
      country => country.name.toLowerCase() === (lead.target_destination || '').toLowerCase()
    )?.iso2 ||
    '';

  const destinationIso2s =
    lead.target_destination_iso2s?.length
      ? lead.target_destination_iso2s
      : destinationIso2
        ? [destinationIso2]
        : [];

  return {
    first_name: lead.first_name || '',
    middle_name: lead.middle_name || '',
    last_name: lead.last_name || '',
    email,
    phone_country_iso2: lead.phone_country_iso2 || countryIso2,
    phone_local: localNumber,
    date_of_birth: lead.date_of_birth || '',
    target_destination_iso2s: destinationIso2s,
    target_level_id: lead.target_level_id ?? undefined,
    target_major_ids: lead.target_major_ids || [],
    target_program_codes: lead.target_program_codes?.length
      ? lead.target_program_codes
      : lead.target_program_code
        ? [lead.target_program_code]
        : [],
    education: {
      program_code: matchedProgram?.code || programCode,
      full_time_study_years: lead.full_time_study_years || '',
      major: lead.major || '',
      gpa_cgpa_code: gpaFields.gpa_cgpa_code,
      gpa_cgpa_other: gpaFields.gpa_cgpa_other,
      university: lead.university || '',
      graduation_year: lead.graduation_year ?? undefined,
    },
    location: {
      address_line_1: lead.address_line_1 || '',
      address_line_2: lead.address_line_2 || '',
      city: lead.city || '',
      state: lead.state || '',
      country_iso2: lead.country_iso2 || '',
      zip_code: lead.zip_code || '',
    },
  };
}

function formatDateAdded(value?: string | null): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return value;
  }
}

function formatFollowupDate(value?: string | null): string {
  const raw = (value || '').trim();
  if (!raw) return '';
  try {
    const parsed = new Date(`${raw.slice(0, 10)}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return '';
    const dateLabel = parsed.toLocaleDateString([], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
    return `${scheduledWeekdayShort(parsed)}, ${dateLabel}`;
  } catch {
    return '';
  }
}

function formatDateOfBirthCell(dob?: string | null): ReactNode {
  if (!dob) return '—';
  try {
    const birth = new Date(`${dob}T00:00:00`);
    if (Number.isNaN(birth.getTime())) return dob;
    const dobLabel = birth.toLocaleDateString([], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
    const ageLabel = formatAgeYmd(dob);
    return (
      <>
        <div>{dobLabel}</div>
        {ageLabel ? <div className="mt-0.5 text-xs text-slate-500">{ageLabel}</div> : null}
      </>
    );
  } catch {
    return dob;
  }
}

function formatStudyInterestCell(lead: OfflineLeadItem): string {
  const destinations =
    lead.target_destinations?.length
      ? lead.target_destinations.join(', ')
      : lead.target_destination || '';
  const programs =
    lead.target_programs?.length
      ? lead.target_programs.join(', ')
      : lead.target_program || lead.target_course || '';
  const majors = lead.target_majors?.length ? lead.target_majors.join(', ') : '';
  return [destinations, lead.target_level_name, majors, programs].filter(Boolean).join(' · ') || '—';
}

function formatLeadSourceLabel(source?: string | null): string {
  const s = String(source || '').toUpperCase();
  if (s === 'EXPRESS') return 'Express Lead';
  if (s === 'FACEBOOK_LEAD' || s === 'INSTAGRAM_LEAD') return 'Meta Lead';
  return 'Offline Lead';
}

function offlineLeadPipelineStatus(lead: OfflineLeadItem): string {
  return (lead.lead_status || lead.status_stage_name || '').trim();
}

function isManualOfflineLead(lead: Pick<OfflineLeadItem, 'source'>): boolean {
  const s = String(lead.source || '').toUpperCase();
  return s === 'OFFLINE' || s === 'EXPRESS' || s === '';
}

function columnHeaderClass(key: OfflineLeadColumnKey): string | undefined {
  if (key === 'date_of_birth') return 'max-w-56 min-w-40 break-words whitespace-normal leading-snug text-slate-700 [overflow-wrap:anywhere]';
  if (key === 'scheduled_time' || key === 'followup_date') return 'whitespace-nowrap text-center';
  return undefined;
}

const SCHEDULED_TIME_BADGE_ICON: Record<
  ScheduledTimeTone,
  typeof Clock
> = {
  'today-upcoming': Clock,
  'today-overdue': AlertCircle,
  tomorrow: CheckCircle2,
  'day-after-tomorrow': Calendar,
  upcoming: Calendar,
  past: History,
};

const SCHEDULED_TIME_STATUS_LABEL: Record<ScheduledTimeTone, string> = {
  'today-upcoming': 'Today',
  'today-overdue': 'Overdue',
  tomorrow: 'Tomorrow',
  'day-after-tomorrow': 'Day After Tomorrow',
  upcoming: 'Upcoming',
  past: 'Date Passed',
};

function scheduledTimeFilterText(lead: OfflineLeadItem): string {
  const start = parseScheduledWallClock(lead.scheduled_time);
  if (!start) return '';
  const end = parseScheduledWallClock(lead.scheduled_end_at) ?? start;
  const status = SCHEDULED_TIME_STATUS_LABEL[classifyScheduledTime(start, new Date())];
  return `${formatScheduledTimeRange(start, end)} ${status}`;
}

function offlineLeadColumnFilterText(lead: OfflineLeadItem, key: OfflineLeadColumnKey): string {
  switch (key) {
    case 'full_name':
      return lead.full_name || '';
    case 'student_id':
      return String(lead.id);
    case 'source':
      return formatLeadSourceLabel(lead.source);
    case 'email':
      return lead.email || '';
    case 'phone_number':
      return lead.phone_number || '';
    case 'date_of_birth':
      return lead.date_of_birth || '';
    case 'program':
      return lead.program || lead.degree || '';
    case 'major':
      return lead.major || '';
    case 'university':
      return lead.university || '';
    case 'graduation_year':
      return String(lead.graduation_year ?? '');
    case 'gpa_cgpa':
      return lead.gpa_cgpa || '';
    case 'study_interest':
      return [
        ...(lead.target_destinations ?? []),
        lead.target_destination,
        lead.target_level_name,
        ...(lead.target_majors ?? []),
        ...(lead.target_programs ?? []),
        lead.target_program,
        lead.target_course,
      ]
        .filter(Boolean)
        .join(' ');
    case 'city':
      return lead.city || '';
    case 'state':
      return lead.state || '';
    case 'country':
      return lead.country || '';
    case 'scheduled_time':
      return scheduledTimeFilterText(lead);
    case 'new_booking':
      return 'book';
    case 'counselor_notes':
      return String(lead.followup_count ?? 0);
    case 'lead_status':
      return offlineLeadPipelineStatus(lead);
    case 'followup_status':
      return lead.followup_status_label || '';
    case 'followup_date': {
      const label = formatFollowupDate(lead.followup_date);
      if (!label) return '';
      const tone = classifyFollowupDate(lead.followup_date, new Date());
      return tone ? `${label} ${SCHEDULED_TIME_STATUS_LABEL[tone]}` : label;
    }
    case 'created_at':
      return lead.created_at || '';
    default:
      return '';
  }
}

function renderOfflineLeadCell(
  lead: OfflineLeadItem,
  key: OfflineLeadColumnKey,
  handlers?: {
    onOpenBookings?: (lead: OfflineLeadItem) => void;
    onOpenCounselorNotes?: (lead: OfflineLeadItem) => void;
    onEditLead?: (lead: OfflineLeadItem) => void;
    bookAppointmentReturnTo?: string;
  }
): ReactNode {
  switch (key) {
    case 'full_name':
      return handlers?.onEditLead ? (
        <button
          type="button"
          className="offline-journey inline-flex cursor-pointer items-center gap-1 whitespace-nowrap border-0 bg-transparent p-0 text-[13px] font-semibold text-accent hover:underline"
          onClick={() => handlers.onEditLead?.(lead)}
          title={`Edit ${lead.full_name || `lead #${lead.id}`}`}
        >
          {lead.full_name || '—'}
        </button>
      ) : (
        lead.full_name || '—'
      );
    case 'student_id':
      return handlers?.onEditLead ? (
        <button
          type="button"
          className="offline-journey inline-flex cursor-pointer items-center gap-1 whitespace-nowrap border-0 bg-transparent p-0 text-[13px] font-semibold text-accent hover:underline"
          onClick={() => handlers.onEditLead?.(lead)}
          title={`Edit ${lead.full_name || `lead #${lead.id}`}`}
        >
          {lead.id}
        </button>
      ) : (
        lead.id
      );
    case 'source':
      return formatLeadSourceLabel(lead.source);
    case 'email':
      return lead.email?.includes('@edutrust.nexus') ? '—' : lead.email || '—';
    case 'phone_number':
      return lead.phone_number || '—';
    case 'date_of_birth':
      return formatDateOfBirthCell(lead.date_of_birth);
    case 'program':
      return lead.program || lead.degree || '—';
    case 'major':
      return lead.major || '—';
    case 'university':
      return lead.university || '—';
    case 'graduation_year':
      return lead.graduation_year ?? '—';
    case 'gpa_cgpa':
      return lead.gpa_cgpa || '—';
    case 'study_interest':
      return formatStudyInterestCell(lead);
    case 'city':
      return lead.city || '—';
    case 'state':
      return lead.state || '—';
    case 'country':
      return lead.country || '—';
    case 'scheduled_time': {
      const start = parseScheduledWallClock(lead.scheduled_time);
      if (!start) return null;
      const end = parseScheduledWallClock(lead.scheduled_end_at) ?? start;
      const label = formatScheduledTimeRange(start, end);
      const tone = classifyScheduledTime(start, new Date());
      const Icon = SCHEDULED_TIME_BADGE_ICON[tone];
      const className = `inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-1 text-xs font-semibold ${SCHEDULED_TIME_BADGE_CLASS[tone]}`;
      const content = (
        <>
          <Icon size={13} aria-hidden />
          <span className="flex flex-col items-center text-center leading-tight">
            <span className="whitespace-nowrap">{label}</span>
            <span className="whitespace-nowrap">{SCHEDULED_TIME_STATUS_LABEL[tone]}</span>
          </span>
        </>
      );
      if (!handlers?.onOpenBookings) {
        return (
          <div className="flex justify-center">
            <span className={className}>{content}</span>
          </div>
        );
      }
      return (
        <div className="flex justify-center">
          <button
            type="button"
            className={`${className} cursor-pointer`}
            onClick={() => handlers.onOpenBookings?.(lead)}
            title="View counselling bookings"
          >
            {content}
          </button>
        </div>
      );
    }
    case 'new_booking':
      return (
        <Link
          to={bookAppointmentHref(
            {
              id: lead.id,
              full_name: lead.full_name || '',
              email: lead.email,
              phone_number: lead.phone_number,
            },
            { returnTo: handlers?.bookAppointmentReturnTo }
          )}
          className="offline-journey inline-flex cursor-pointer items-center gap-1 whitespace-nowrap border-0 bg-transparent p-0 text-[13px] font-semibold text-accent hover:underline"
          title={`Book appointment for ${lead.full_name || `lead #${lead.id}`}`}
        >
          Book Now
        </Link>
      );
    case 'counselor_notes': {
      const count = lead.followup_count ?? 0;
      return (
        <button
          type="button"
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-semibold text-slate-900 hover:border-slate-300 hover:bg-slate-100"
          onClick={() => handlers?.onOpenCounselorNotes?.(lead)}
          title="Open counselor notes"
        >
          <MessageSquareText size={13} />
          Notes
          <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-slate-900 px-[5px] text-[11px] font-bold leading-none text-white">{count}</span>
        </button>
      );
    }
    case 'lead_status': {
      const label = offlineLeadPipelineStatus(lead);
      return label || '—';
    }
    case 'followup_status':
      return lead.followup_status_label?.trim() ? lead.followup_status_label : '—';
    case 'followup_date': {
      const label = formatFollowupDate(lead.followup_date);
      const tone = classifyFollowupDate(lead.followup_date, new Date());
      if (!label || !tone) return null;
      const Icon = SCHEDULED_TIME_BADGE_ICON[tone];
      const className = `inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-1 text-xs font-semibold ${SCHEDULED_TIME_BADGE_CLASS[tone]}`;
      return (
        <div className="flex justify-center">
          <span className={className}>
            <Icon size={13} aria-hidden />
            <span className="flex flex-col items-center text-center leading-tight">
              <span className="whitespace-nowrap">{label}</span>
              <span className="whitespace-nowrap">{SCHEDULED_TIME_STATUS_LABEL[tone]}</span>
            </span>
          </span>
        </div>
      );
    }
    case 'created_at':
      return formatDateAdded(lead.created_at);
    default:
      return '—';
  }
}

function SortIcon({
  field,
  sortBy,
  sortDir,
}: {
  field: OfflineLeadSortField;
  sortBy: OfflineLeadSortField;
  sortDir: OfflineLeadSortDirection;
}) {
  if (sortBy !== field) return <ArrowUpDown size={12} />;
  return sortDir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
}

const BOOKING_FILTER_TITLE =
  'Filter by: Today, Tomorrow, Day after tomorrow, Upcoming, Overdue, Completed';
const FOLLOWUP_FILTER_TITLE =
  'Filter by: Today, Tomorrow, Day after tomorrow, Upcoming, Completed';

function dateColumnFilterTitle(key: string): string | undefined {
  if (key === 'scheduled_time') return BOOKING_FILTER_TITLE;
  if (key === 'followup_date') return FOLLOWUP_FILTER_TITLE;
  return undefined;
}

function DateColumnFilterInput({
  title,
  value,
  ariaLabel,
  onChange,
}: {
  title?: string;
  value: string;
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  const [anchor, setAnchor] = useState<{ left: number; top: number } | null>(null);
  return (
    <>
      <input
        type="search"
        className="mt-1.5 block w-full rounded-md border border-slate-200 bg-white px-1.5 py-1 text-left text-xs font-normal normal-case tracking-normal text-slate-900"
        placeholder="Filter…"
        title={title}
        value={value}
        aria-label={ariaLabel}
        onClick={e => e.stopPropagation()}
        onChange={e => onChange(e.target.value)}
        onMouseEnter={e => {
          if (!title) return;
          const rect = e.currentTarget.getBoundingClientRect();
          setAnchor({ left: rect.left, top: rect.bottom + 6 });
        }}
        onMouseLeave={() => setAnchor(null)}
        onBlur={() => setAnchor(null)}
      />
      {title && anchor
        ? createPortal(
            <div
              role="tooltip"
              className="pointer-events-none fixed z-[80] max-w-sm rounded-md bg-slate-900 px-2.5 py-1.5 text-left text-xs font-medium normal-case tracking-normal text-white shadow-lg"
              style={{ left: anchor.left, top: anchor.top }}
            >
              {title}
            </div>,
            document.body
          )
        : null}
    </>
  );
}

function formatClientCivilStamp(now = new Date()): { date: string; time: string } {
  const pad = (value: number) => String(value).padStart(2, '0');
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:00`;
  return { date, time };
}

export default function OfflineLeadsPage() {
  const openConfirm = useConfirmation();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const consumedEditRef = useRef<string | null>(null);
  const skipPageResetRef = useRef(true);
  const [page, setPage] = useState(() => {
    const raw = Number(searchParams.get('page'));
    return Number.isFinite(raw) && raw >= 1 ? Math.floor(raw) : 1;
  });
  const [pageSize, setPageSize] = useState<TablePageSize>(() =>
    readStoredTablePageSize(OFFLINE_LEADS_PAGE_SIZE_KEY)
  );
  const [search, setSearch] = useState(() => searchParams.get('q') || '');
  const [status, setStatus] = useState<OfflineLeadStatusFilter>('ALL');
  const [sortBy, setSortBy] = useState<OfflineLeadSortField>('scheduled_time');
  const [sortDir, setSortDir] = useState<OfflineLeadSortDirection>('asc');
  const [visibleColumns, setVisibleColumns] = useState<OfflineLeadColumnKey[]>(readStoredOfflineLeadColumns);
  const [columnOrder, setColumnOrder] = useState<OfflineLeadColumnKey[]>(readStoredOfflineLeadOrder);
  const [columnPins, setColumnPins] = useState<OfflineLeadPinState>(readStoredOfflineLeadPins);
  const [columnWidths, setColumnWidths] = useState<Partial<Record<OfflineLeadColumnKey, number>>>(
    readStoredOfflineLeadWidths
  );
  const [selectedRowIds, setSelectedRowIds] = useState<Set<number>>(() => new Set());
  const [columnFilters, setColumnFilters] = useState<Partial<Record<OfflineLeadColumnKey, string>>>({});
  const [journeyModal, setJourneyModal] = useState<{
    studentId: number;
    studentName: string;
  } | null>(null);
  const [bookingsModal, setBookingsModal] = useState<{
    leadId: number;
    leadName: string;
  } | null>(null);
  const [followupDrawer, setFollowupDrawer] = useState<{
    leadId: number;
    leadName: string;
  } | null>(null);
  const [sessionDrawer, setSessionDrawer] = useState<{
    bookingId: number;
    leadId: number;
    candidateName: string;
    dateLabel?: string | null;
    timeLabel?: string | null;
  } | null>(null);
  const [statusModal, setStatusModal] = useState<{
    lead: OfflineLeadItem;
    nextActive: boolean;
  } | null>(null);
  const [statusReasons, setStatusReasons] = useState<string[]>([]);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLead, setEditingLead] = useState<OfflineLeadItem | null>(null);
  const [form, setForm] = useState<OfflineLeadCreatePayload>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [formBaseline, setFormBaseline] = useState('');
  const formIsDirty =
    modalOpen && Boolean(formBaseline) && serializeOfflineLeadForm(form) !== formBaseline;
  useUnsavedChanges(formIsDirty, '');
  const [educationLevelId, setEducationLevelId] = useState('');


  const debouncedSearch = useDebouncedValue(search, 350);
  const debouncedNameFilter = useDebouncedValue((columnFilters.full_name || '').trim(), 350);
  const debouncedStudentIdFilter = useDebouncedValue((columnFilters.student_id || '').trim(), 350);
  const debouncedBookingDate = useDebouncedValue((columnFilters.scheduled_time || '').trim(), 200);
  const debouncedFollowupDate = useDebouncedValue((columnFilters.followup_date || '').trim(), 200);
  const clientStamp = formatClientCivilStamp();

  const query: OfflineLeadsQuery = useMemo(
    () => ({
      page,
      pageSize,
      q: debouncedSearch,
      name: debouncedNameFilter,
      studentId: debouncedStudentIdFilter,
      status,
      sortBy,
      sortDir,
      clientDate: clientStamp.date,
      clientTime: clientStamp.time,
      bookingDateQ: debouncedBookingDate,
      followupDateQ: debouncedFollowupDate,
    }),
    [
      page,
      pageSize,
      debouncedSearch,
      debouncedNameFilter,
      debouncedStudentIdFilter,
      debouncedBookingDate,
      debouncedFollowupDate,
      status,
      sortBy,
      sortDir,
      clientStamp.date,
      clientStamp.time,
    ]
  );

  const listQuery = useOfflineLeads(query);
  const createMutation = useCreateOfflineLead();
  const updateMutation = useUpdateOfflineLead();
  const setActiveMutation = useSetOfflineLeadActive();
  const { countries } = useCountries();
  const { programs: qualificationPrograms } = useQualificationPrograms();
  const { levels } = useLevels();
  const sortedCountries = useMemo(
    () =>
      [...countries].sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
      ),
    [countries]
  );
  const sortedLevelOptions = useMemo(
    () =>
      levelSelectOptions(levels).sort((a, b) =>
        a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
      ),
    [levels]
  );
  const filteredPrograms = useMemo(() => {
    if (!educationLevelId) return [];
    return qualificationPrograms
      .filter(program => program.level_id === Number(educationLevelId))
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [qualificationPrograms, educationLevelId]);
  const { majors } = useEducationMajors();
  const selectedEducationProgram = useMemo(
    () => findQualificationProgram(qualificationPrograms, form.education?.program_code),
    [qualificationPrograms, form.education?.program_code]
  );
  const mappedProgramMajors = selectedEducationProgram?.majors ?? [];
  const filteredMajors = useMemo(() => {
    if (!form.education?.program_code || !mappedProgramMajors.length) {
      return [];
    }
    const labels = new Set(
      mappedProgramMajors.map(major => major.label.trim().toLowerCase())
    );
    const codes = new Set(
      mappedProgramMajors
        .map(major => (major.code || '').trim().toUpperCase())
        .filter(Boolean)
    );
    const matched = majors.filter(
      major =>
        !major.is_other &&
        (labels.has(major.label.trim().toLowerCase()) ||
          Boolean(major.code && codes.has(major.code.trim().toUpperCase())))
    );
    const list = matched.length
      ? matched
      : mappedProgramMajors.map(major => ({
          id: major.id,
          code: major.code,
          label: major.label,
          is_other: false,
          sort_order: 0,
          is_active: true,
        }));
    return [...list].sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
    );
  }, [form.education?.program_code, majors, mappedProgramMajors]);
  const majorSelectValue = useMemo(() => {
    const current = form.education?.major || '';
    if (!current) return '';
    if (filteredMajors.some(major => major.label === current)) return current;
    return current;
  }, [filteredMajors, form.education?.major]);
  const { scores: gpaCgpaScores } = useGpaCgpaScores();
  const { options: studyYearOptions } = useFullTimeStudyYears();
  const filteredStudyYears = useMemo(
    () =>
      [...filterFullTimeStudyYearsByLevel(studyYearOptions, educationLevelId)].sort((a, b) =>
        a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
      ),
    [studyYearOptions, educationLevelId]
  );
  const targetLevelId = form.target_level_id ? String(form.target_level_id) : '';
  const studyInterestMajors = useMemo(() => {
    if (!form.target_level_id) return [];
    const byId = new Map<number, { id: number; code?: string | null; label: string }>();
    for (const program of qualificationPrograms) {
      if (program.level_id !== form.target_level_id) continue;
      for (const major of program.majors ?? []) {
        byId.set(major.id, major);
      }
    }
    return Array.from(byId.values()).sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
    );
  }, [form.target_level_id, qualificationPrograms]);
  const studyInterestPrograms = useMemo(() => {
    if (!form.target_level_id || !form.target_major_ids?.length) return [];
    const majorIds = new Set(form.target_major_ids);
    return qualificationPrograms
      .filter(
        program =>
          program.level_id === form.target_level_id &&
          (program.majors ?? []).some(major => majorIds.has(major.id))
      )
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [form.target_level_id, form.target_major_ids, qualificationPrograms]);
  const targetDestinationOptions = useMemo(
    () =>
      sortedCountries.map(country => ({
        value: country.iso2,
        label: country.name,
      })),
    [sortedCountries]
  );
  const computedAge = useMemo(() => computeAgeFromDob(form.date_of_birth), [form.date_of_birth]);
  const dobError = useMemo(() => {
    if (!form.date_of_birth) return null;
    return validateDateOfBirth(form.date_of_birth);
  }, [form.date_of_birth]);
  const maxDateOfBirth = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const selectedGpaCgpa = useMemo(
    () => findGpaCgpaScore(gpaCgpaScores, form.education?.gpa_cgpa_code),
    [gpaCgpaScores, form.education?.gpa_cgpa_code]
  );
  const { emailTaken, phoneTaken } = useOfflineLeadDuplicateCheck(
    form.email || '',
    form.phone_country_iso2,
    form.phone_local,
    editingLead?.id,
    modalOpen
  );

  useEffect(() => {
    storeTablePageSize(OFFLINE_LEADS_PAGE_SIZE_KEY, pageSize);
  }, [pageSize]);

  useEffect(() => {
    storeOfflineLeadColumns(visibleColumns);
  }, [visibleColumns]);

  useEffect(() => {
    try {
      localStorage.setItem(OFFLINE_LEADS_ORDER_KEY, JSON.stringify(columnOrder));
    } catch {
      /* ignore */
    }
  }, [columnOrder]);

  useEffect(() => {
    try {
      localStorage.setItem(OFFLINE_LEADS_PIN_KEY, JSON.stringify(columnPins));
    } catch {
      /* ignore */
    }
  }, [columnPins]);

  useEffect(() => {
    try {
      localStorage.setItem(OFFLINE_LEADS_WIDTH_KEY, JSON.stringify(columnWidths));
    } catch {
      /* ignore */
    }
  }, [columnWidths]);

  const visibleColumnDefs = useMemo(() => {
    const byKey = new Map(OFFLINE_LEAD_COLUMN_DEFS.map(column => [column.key, column]));
    const order = columnOrder.length ? columnOrder : ALL_OFFLINE_LEAD_KEYS;
    const left = columnPins.left.filter(key => visibleColumns.includes(key));
    const right = columnPins.right.filter(key => visibleColumns.includes(key));
    const middle = order.filter(
      key =>
        visibleColumns.includes(key) && !left.includes(key) && !right.includes(key)
    );
    return [...left, ...middle, ...right]
      .map(key => byKey.get(key))
      .filter((column): column is (typeof OFFLINE_LEAD_COLUMN_DEFS)[number] => Boolean(column));
  }, [visibleColumns, columnOrder, columnPins]);

  const overflowColumns = useMemo(
    () =>
      columnOrder.map(key => {
        const def = OFFLINE_LEAD_COLUMN_DEFS.find(column => column.key === key)!;
        const pinned = columnPins.left.includes(key)
          ? ('left' as const)
          : columnPins.right.includes(key)
            ? ('right' as const)
            : false;
        return {
          id: key,
          label: def.label,
          visible: visibleColumns.includes(key),
          required: Boolean(def.required),
          pinned,
        };
      }),
    [columnOrder, visibleColumns, columnPins]
  );

  const handleToggleColumnVisibility = (id: string) => {
    const key = id as OfflineLeadColumnKey;
    setVisibleColumns(prev => {
      if (prev.includes(key)) {
        if (REQUIRED_OFFLINE_LEAD_COLUMNS.includes(key)) return prev;
        return prev.filter(item => item !== key);
      }
      return normalizeOfflineLeadColumns([...prev, key]);
    });
  };

  const handleMoveColumn = (id: string, direction: -1 | 1) => {
    const key = id as OfflineLeadColumnKey;
    setColumnOrder(prev => {
      const order = normalizeOfflineLeadOrder(prev);
      const index = order.indexOf(key);
      if (index < 0) return order;
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= order.length) return order;
      const next = [...order];
      const [item] = next.splice(index, 1);
      next.splice(nextIndex, 0, item);
      return next;
    });
  };

  const handlePinColumn = (id: string, side: 'left' | 'right' | false) => {
    const key = id as OfflineLeadColumnKey;
    setColumnPins(prev => {
      const left = prev.left.filter(item => item !== key);
      const right = prev.right.filter(item => item !== key);
      if (side === 'left') left.push(key);
      if (side === 'right') right.push(key);
      return { left, right };
    });
  };

  const resetTableView = () => {
    setVisibleColumns(defaultOfflineLeadColumns());
    setColumnOrder([...ALL_OFFLINE_LEAD_KEYS]);
    setColumnPins({ left: [...DEFAULT_PINNED_LEFT], right: [] });
    setColumnWidths({});
    setColumnFilters({});
    setSortBy('scheduled_time');
    setSortDir('asc');
    setSelectedRowIds(new Set());
  };

  const startColumnResize = (key: OfflineLeadColumnKey, startX: number, startWidth: number) => {
    const onMove = (event: MouseEvent) => {
      const next = Math.min(640, Math.max(72, startWidth + (event.clientX - startX)));
      setColumnWidths(prev => ({ ...prev, [key]: next }));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const pinOffsetLeft = (key: OfflineLeadColumnKey): number | undefined => {
    const index = columnPins.left.indexOf(key);
    if (index < 0) return undefined;
    let offset = 40; // selection column
    for (let i = 0; i < index; i += 1) {
      const prevKey = columnPins.left[i];
      if (!visibleColumns.includes(prevKey)) continue;
      offset += columnWidths[prevKey] ?? 140;
    }
    return offset;
  };

  const pinOffsetRight = (key: OfflineLeadColumnKey): number | undefined => {
    const index = columnPins.right.indexOf(key);
    if (index < 0) return undefined;
    let offset = 72; // actions
    for (let i = columnPins.right.length - 1; i > index; i -= 1) {
      const nextKey = columnPins.right[i];
      if (!visibleColumns.includes(nextKey)) continue;
      offset += columnWidths[nextKey] ?? 140;
    }
    return offset;
  };

  useEffect(() => {
    if (skipPageResetRef.current) {
      skipPageResetRef.current = false;
      return;
    }
    setPage(1);
  }, [debouncedSearch, debouncedNameFilter, debouncedStudentIdFilter, debouncedBookingDate, debouncedFollowupDate, status, pageSize, sortBy, sortDir]);

  useEffect(() => {
    setSearchParams(
      prev => {
        const current = prev.get('page');
        const desired = page <= 1 ? null : String(page);
        if ((current || null) === desired) return prev;
        const next = new URLSearchParams(prev);
        if (desired === null) next.delete('page');
        else next.set('page', desired);
        return next;
      },
      { replace: true }
    );
  }, [page, setSearchParams]);

  const toggleSort = (field: OfflineLeadSortField) => {
    if (sortBy === field) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortDir(field === 'created_at' ? 'desc' : 'asc');
    }
  };

  const openEditModal = (lead: OfflineLeadItem) => {
    const nextForm = leadToForm(lead, countries, qualificationPrograms, gpaCgpaScores);
    const program = findQualificationProgram(
      qualificationPrograms,
      nextForm.education?.program_code
    );
    const studyYear = findFullTimeStudyYear(
      studyYearOptions,
      nextForm.education?.full_time_study_years,
      lead.level_id ?? program?.level_id
    );
    const levelFromLead =
      studyYear?.level_id != null
        ? String(studyYear.level_id)
        : lead.level_id != null
          ? String(lead.level_id)
          : program
            ? String(program.level_id)
            : '';
    setEducationLevelId(levelFromLead);
    setEditingLead(lead);
    setForm(nextForm);
    setFormError(null);
    setGeoLoading(false);
    setFormBaseline(serializeOfflineLeadForm(nextForm));
    setModalOpen(true);
  };

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditingLead(null);
    setFormError(null);
    setFormBaseline('');
    setEducationLevelId('');
  }, []);

  const requestCloseModal = useCallback(async () => {
    if (formBaseline && serializeOfflineLeadForm(form) !== formBaseline) {
      if (!(await openConfirm({
        title: 'Leave without saving?',
        message: UNSAVED_CLOSE_MESSAGE,
        confirmLabel: 'Leave without saving',
        variant: 'warning',
      }))) {
        return;
      }
    }
    closeModal();
  }, [closeModal, form, formBaseline, openConfirm]);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      requestCloseModal();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modalOpen, requestCloseModal]);

  const updateForm = (patch: Partial<OfflineLeadCreatePayload>) => {
    setForm(prev => ({ ...prev, ...patch }));
  };

  const updateLocation = (patch: Partial<NonNullable<OfflineLeadCreatePayload['location']>>) => {
    setForm(prev => ({
      ...prev,
      location: { ...prev.location, ...patch },
    }));
  };

  const updateEducation = (patch: Partial<NonNullable<OfflineLeadCreatePayload['education']>>) => {
    setForm(prev => ({
      ...prev,
      education: { ...prev.education, ...patch },
    }));
  };

  const handleToggleActive = (lead: OfflineLeadItem) => {
    const currentlyActive = lead.is_active !== false;
    setStatusError(null);
    setStatusReasons([]);
    setStatusModal({
      lead,
      nextActive: !currentlyActive,
    });
  };

  const closeStatusModal = () => {
    if (setActiveMutation.isPending) return;
    setStatusModal(null);
    setStatusReasons([]);
    setStatusError(null);
  };

  const toggleStatusReason = (reason: string) => {
    setStatusReasons(prev =>
      prev.includes(reason) ? prev.filter(item => item !== reason) : [...prev, reason]
    );
    setStatusError(null);
  };

  const confirmStatusChange = async () => {
    if (!statusModal) return;
    if (!statusReasons.length) {
      setStatusError('Select at least one reason.');
      return;
    }
    try {
      await setActiveMutation.mutateAsync({
        id: statusModal.lead.id,
        isActive: statusModal.nextActive,
        reasons: statusReasons,
      });
      setStatusModal(null);
      setStatusReasons([]);
      setStatusError(null);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update lead active status.';
      setStatusError(message);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (!form.first_name.trim()) {
      setFormError('First name is required.');
      return;
    }
    if (!form.email?.trim()) {
      setFormError('Email is required.');
      return;
    }
    if (emailTaken) {
      setFormError('This email is already registered.');
      return;
    }
    if (phoneTaken) {
      setFormError('This phone number is already registered.');
      return;
    }

    const phoneError = validatePhoneWithCountry(
      form.phone_country_iso2,
      form.phone_local,
      countries
    );
    if (phoneError) {
      setFormError(phoneError);
      return;
    }

    if (form.date_of_birth) {
      const dobValidationError = validateDateOfBirth(form.date_of_birth);
      if (dobValidationError) {
        setFormError(dobValidationError);
        return;
      }
    }

    const educationError = validateEducationFields(
      form.education?.program_code,
      form.education?.major,
      qualificationPrograms,
      form.education?.university,
      form.education?.graduation_year,
      form.education?.full_time_study_years
    );
    if (educationError) {
      setFormError(educationError);
      return;
    }

    const hasEducationInput = Boolean(
      form.education?.program_code ||
        form.education?.major ||
        form.education?.university ||
        form.education?.graduation_year ||
        form.education?.full_time_study_years ||
        form.education?.gpa_cgpa_code
    );
    if (hasEducationInput && !educationLevelId) {
      setFormError('Level is required when education is provided.');
      return;
    }

    if (hasEducationInput) {
      const gpaError = validateGpaCgpaScore(
        form.education?.gpa_cgpa_code,
        form.education?.gpa_cgpa_other,
        gpaCgpaScores
      );
      if (gpaError) {
        setFormError(gpaError);
        return;
      }
    }

    const locationError = validateLocationFields(form.location);
    if (locationError) {
      setFormError(locationError);
      return;
    }

    const studyInterestError = validateStudyInterestFields({
      targetDestinationIso2s: form.target_destination_iso2s,
      targetLevelId: form.target_level_id,
      targetMajorIds: form.target_major_ids,
      targetProgramCodes: form.target_program_codes,
    });
    if (studyInterestError) {
      setFormError(studyInterestError);
      return;
    }

    const educationPayload = buildEducationPayload(
      form.education?.program_code,
      qualificationPrograms,
      {
        levelId: educationLevelId,
        major: form.education?.major,
        university: form.education?.university,
        graduationYear: form.education?.graduation_year,
        gpaCgpaCode: form.education?.gpa_cgpa_code,
        gpaCgpaOther: form.education?.gpa_cgpa_other,
        gpaCgpaScores,
        fullTimeStudyYears: form.education?.full_time_study_years,
      }
    );

    const payload: OfflineLeadCreatePayload = {
      first_name: form.first_name.trim(),
      middle_name: form.middle_name?.trim() || undefined,
      last_name: form.last_name?.trim() || "",
      phone_country_iso2: form.phone_country_iso2,
      phone_local: phoneLocalToDigits(form.phone_local),
      email: form.email.trim(),
      date_of_birth: form.date_of_birth?.trim() || undefined,
      target_destination_iso2s: form.target_destination_iso2s,
      target_level_id: form.target_level_id,
      target_major_ids: form.target_major_ids,
      target_program_codes: form.target_program_codes,
      location: {
        address_line_1: form.location?.address_line_1?.trim() || '',
        address_line_2: form.location?.address_line_2?.trim() || '',
        city: form.location?.city?.trim() || '',
        state: form.location?.state?.trim() || '',
        country_iso2: form.location?.country_iso2 || '',
        zip_code: form.location?.zip_code?.trim() || undefined,
      },
      education: educationPayload,
    };

    try {
      if (editingLead) {
        await updateMutation.mutateAsync({ id: editingLead.id, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      closeModal();
    } catch (error: unknown) {
      const message =
        error instanceof Error
          ? error.message
          : editingLead
            ? 'Failed to update lead.'
            : 'Failed to create lead.';
      setFormError(message);
    }
  };

  const pageItems = listQuery.data?.items ?? [];
  const items = pageItems;
  const filterSource = pageItems;
  const filteredItems = useMemo(() => {
    const active = (Object.entries(columnFilters) as Array<[OfflineLeadColumnKey, string]>).filter(
      ([key, value]) => value?.trim() && key !== 'full_name' && key !== 'student_id'
    );
    if (!active.length) return filterSource;
    const now = new Date();
    return filterSource.filter(lead =>
      active.every(([key, value]) => {
        const needle = value.trim().toLowerCase();
        if (key === 'scheduled_time' || key === 'followup_date') {
          const start = key === 'scheduled_time' ? parseScheduledWallClock(lead.scheduled_time) : null;
          const diffDays =
            key === 'scheduled_time'
              ? start
                ? localCalendarDayDiff(start, now)
                : null
              : followupCalendarDayDiff(lead.followup_date, now);
          const keyword = matchCalendarDateKeyword(value, diffDays, {
            column: key === 'scheduled_time' ? 'booking' : 'followup',
            startHasPassed: start ? start.getTime() < now.getTime() : false,
          });
          if (keyword !== null) return keyword;
        }
        const text = offlineLeadColumnFilterText(lead, key);
        return text.toLowerCase().includes(needle);
      })
    );
  }, [filterSource, columnFilters]);
  const total = listQuery.data?.total ?? 0;
  const totalPages = listQuery.data?.total_pages ?? 1;
  const currentPage = listQuery.data?.page ?? page;
  const pageTokens = useMemo(
    () => offlineLeadsPageTokens(currentPage, Math.max(1, totalPages)),
    [currentPage, totalPages]
  );
  const paginationBusy = listQuery.isFetching;
  const renderPaginationControls = () => (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-col gap-1 text-[13px] text-slate-500 [&_select]:min-w-[140px] [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:bg-white [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm">
        <select
          value={pageSize}
          aria-label="Rows per page"
          onChange={e => setPageSize(Number(e.target.value) as (typeof PAGE_SIZE_OPTIONS)[number])}
        >
          {PAGE_SIZE_OPTIONS.map(size => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>
      <button
        type="button"
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700"
        disabled={currentPage <= 1 || paginationBusy}
        onClick={() => setPage(p => Math.max(1, p - 1))}
      >
        Previous
      </button>
      <div className="inline-flex items-center gap-1" role="navigation" aria-label="Pagination">
        {pageTokens.map((token, index) =>
          token === 'ellipsis' ? (
            <span key={`ellipsis-${index}`} className="min-w-5 select-none text-center text-[13px] font-semibold text-slate-400" aria-hidden>
              …
            </span>
          ) : (
            <button
              key={token}
              type="button"
              className={`h-[34px] min-w-8 cursor-pointer rounded-lg border border-slate-200 bg-white px-2 text-[13px] font-semibold text-slate-600 hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-45${
                token === currentPage ? ' cursor-default border-accent bg-accent text-white' : ''
              }`}
              aria-current={token === currentPage ? 'page' : undefined}
              aria-label={`Page ${token}`}
              disabled={paginationBusy}
              onClick={() => setPage(token)}
            >
              {token}
            </button>
          )
        )}
      </div>
      <button
        type="button"
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700"
        disabled={currentPage >= totalPages || paginationBusy}
        onClick={() => setPage(p => p + 1)}
      >
        Next
      </button>
    </div>
  );
  const allFilteredSelected =
    filteredItems.length > 0 && filteredItems.every(lead => selectedRowIds.has(lead.id));
  const someFilteredSelected =
    filteredItems.some(lead => selectedRowIds.has(lead.id)) && !allFilteredSelected;

  useEffect(() => {
    const editRaw = searchParams.get('edit');
    if (!editRaw || consumedEditRef.current === editRaw || modalOpen) return;
    const editId = Number(editRaw);
    if (!Number.isFinite(editId) || editId < 1) return;
    const lead = items.find(row => row.id === editId);
    if (!lead) return;
    consumedEditRef.current = editRaw;
    openEditModal(lead);
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        next.delete('edit');
        return next;
      },
      { replace: true }
    );
  }, [items, modalOpen, openEditModal, searchParams, setSearchParams]);

  return (
    <>
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-slate-50">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-[18px] py-3.5">
        <div className="min-w-0 [&_h2]:m-0 [&_h2]:text-lg [&_h2]:text-slate-900">
          <h2>All Leads</h2>
          <p className="m-0 mt-1 text-sm text-slate-500">
            Offline, Express, and Meta leads · Source shows Offline Lead, Express Lead, or Meta Lead
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex min-w-[260px] items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 [&_input]:w-full [&_input]:border-0 [&_input]:bg-transparent [&_input]:text-sm [&_input]:outline-none">
            <Search size={15} color="#64748b" />
            <input
              type="search"
              placeholder="Search name, email, or phone…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search offline leads"
            />
          </div>

          <div className="flex flex-col gap-1 text-[13px] text-slate-500 [&_select]:min-w-[140px] [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:bg-white [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm">
            <select
              value={status}
              aria-label="Status"
              onChange={e => setStatus(e.target.value as OfflineLeadStatusFilter)}
            >
              <option value="ALL">All Prospects</option>
              <option value="ACTIVE_LEAD">Active Lead</option>
              <option value="OFFLINE">Offline Leads</option>
              <option value="AI_ACTIVE">AI Active</option>
              <option value="HANDOFF">Handoff</option>
            </select>
          </div>

          <button
            type="button"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700 px-2 py-1.5"
            onClick={() =>
              setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
            }
            title={`Sort ${sortDir === 'asc' ? 'descending' : 'ascending'}`}
            aria-label="Toggle sort direction"
          >
            {sortDir === 'asc' ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
          </button>

          <StandaloneTableOverflowMenu
            columns={overflowColumns}
            onToggleVisibility={handleToggleColumnVisibility}
            onMoveColumn={handleMoveColumn}
            onPinColumn={handlePinColumn}
            onRefresh={() => {
              void listQuery.refetch();
            }}
            refreshing={listQuery.isFetching}
            onResetView={resetTableView}
            className="self-end"
          />

          <button
            type="button"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-accent text-white disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => {
              const params = new URLSearchParams(location.search);
              if (page > 1) params.set('page', String(page));
              else params.delete('page');
              const qs = params.toString();
              const returnTo = `${location.pathname}${qs ? `?${qs}` : ''}`;
              navigate(`/express-leads?returnTo=${encodeURIComponent(returnTo)}`);
            }}
          >
            <Plus size={16} />
            Add New Lead
          </button>

          {renderPaginationControls()}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-[18px] py-4 max-md:p-2">
        {listQuery.isLoading && !listQuery.data ? (
          <div className="px-6 py-12 text-center text-slate-500">Loading offline leads…</div>
        ) : listQuery.isError ? (
          <div className="px-6 py-12 text-center text-slate-500">Failed to load offline leads.</div>
        ) : pageItems.length === 0 ? (
          <div className="px-6 py-12 text-center text-slate-500">No offline leads match your filters.</div>
        ) : (
          <table className="w-full min-w-[720px] border-collapse overflow-hidden rounded-[10px] border border-slate-200 bg-white text-sm max-md:text-xs [&_tbody_tr.is-selected]:bg-blue-50 [&_tbody_tr:hover]:bg-slate-50 [&_td]:border-b [&_td]:border-slate-100 [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-left [&_th]:relative [&_th]:border-b [&_th]:border-slate-100 [&_th]:bg-slate-50 [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:align-top [&_th]:text-[13px] [&_th]:uppercase [&_th]:tracking-wide [&_th]:whitespace-nowrap [&_th]:text-slate-600 [&_th]:select-none [&_tr:last-child_td]:border-b-0">
            <thead>
              <tr>
                <th className="w-10 text-center" style={{ width: 40 }}>
                  <input
                    type="checkbox"
                    aria-label="Select all visible rows"
                    checked={allFilteredSelected}
                    ref={el => {
                      if (el) el.indeterminate = someFilteredSelected;
                    }}
                    onChange={() => {
                      setSelectedRowIds(prev => {
                        const next = new Set(prev);
                        if (allFilteredSelected) {
                          filteredItems.forEach(lead => next.delete(lead.id));
                        } else {
                          filteredItems.forEach(lead => next.add(lead.id));
                        }
                        return next;
                      });
                    }}
                  />
                </th>
                {visibleColumnDefs.map(column => {
                  const sortable =
                    column.key === 'full_name' ||
                    column.key === 'email' ||
                    column.key === 'phone_number' ||
                    column.key === 'created_at' ||
                    column.key === 'scheduled_time';
                  const pinnedLeft = columnPins.left.includes(column.key);
                  const pinnedRight = columnPins.right.includes(column.key);
                  const width = columnWidths[column.key];
                  const style: CSSProperties = {
                    width: width ?? undefined,
                    minWidth: width ?? undefined,
                    position: pinnedLeft || pinnedRight ? 'sticky' : undefined,
                    left: pinnedLeft ? pinOffsetLeft(column.key) : undefined,
                    right: pinnedRight ? pinOffsetRight(column.key) : undefined,
                    zIndex: pinnedLeft || pinnedRight ? 3 : undefined,
                    background: pinnedLeft || pinnedRight ? '#f8fafc' : undefined,
                  };
                  const filterTitle =
                    column.key === 'scheduled_time'
                      ? 'Filter by: Today, Tomorrow, Day after tomorrow, Upcoming, Overdue, Completed'
                      : column.key === 'followup_date'
                        ? 'Filter by: Today, Tomorrow, Day after tomorrow, Upcoming, Completed'
                        : undefined;
                  const filterInput = (
                    <DateColumnFilterInput
                      title={filterTitle}
                      value={columnFilters[column.key] ?? ''}
                      ariaLabel={`Filter ${column.label}`}
                      onChange={next =>
                        setColumnFilters(prev => ({ ...prev, [column.key]: next }))
                      }
                    />
                  );
                  const resizeHandle = (
                    <span
                      className="absolute top-0 right-0 h-full w-1 cursor-col-resize hover:bg-slate-400"
                      onMouseDown={e => {
                        e.preventDefault();
                        e.stopPropagation();
                        const th = (e.target as HTMLElement).parentElement;
                        startColumnResize(column.key, e.clientX, th?.offsetWidth ?? 140);
                      }}
                    />
                  );
                  if (sortable) {
                    const sortField = column.key as OfflineLeadSortField;
                    return (
                      <th
                        key={column.key}
                        className={`cursor-pointer hover:bg-slate-100 ${columnHeaderClass(column.key) || ''}`.trim()}
                        style={style}
                        onClick={() => toggleSort(sortField)}
                      >
                        <span
                          className={`inline-flex items-center gap-1 ${column.key === 'scheduled_time' || column.key === 'followup_date' ? 'w-full justify-center' : ''}`}
                        >
                          {column.label}{' '}
                          <SortIcon field={sortField} sortBy={sortBy} sortDir={sortDir} />
                        </span>
                        {filterInput}
                        {resizeHandle}
                      </th>
                    );
                  }
                  return (
                    <th key={column.key} className={columnHeaderClass(column.key)} style={style}>
                      <span
                        className={`inline-flex items-center gap-1 ${column.key === 'scheduled_time' || column.key === 'followup_date' ? 'w-full justify-center' : ''}`}
                      >
                        {column.label}
                      </span>
                      {filterInput}
                      {resizeHandle}
                    </th>
                  );
                })}
                <th className="w-[7.5rem] text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={visibleColumnDefs.length + 2} className="px-3 py-8 text-center text-slate-500">
                    No leads match this filter.
                  </td>
                </tr>
              ) : (
                filteredItems.map((lead: OfflineLeadItem) => (
                <tr
                  key={lead.id}
                  className={[
                    selectedRowIds.has(lead.id) ? 'is-selected' : '',
                    lead.is_active === false ? '[&_td]:bg-slate-100 [&_td]:text-slate-400 hover:[&_td]:bg-slate-200 [&.is-selected_td]:bg-slate-200 [&_.offline-journey]:text-slate-500' : '',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined}
                >
                  <td className="w-10 text-center">
                    <input
                      type="checkbox"
                      aria-label={`Select ${lead.full_name}`}
                      checked={selectedRowIds.has(lead.id)}
                      onChange={() => {
                        setSelectedRowIds(prev => {
                          const next = new Set(prev);
                          if (next.has(lead.id)) next.delete(lead.id);
                          else next.add(lead.id);
                          return next;
                        });
                      }}
                    />
                  </td>
                  {visibleColumnDefs.map(column => {
                    const pinnedLeft = columnPins.left.includes(column.key);
                    const pinnedRight = columnPins.right.includes(column.key);
                    const width = columnWidths[column.key];
                    const style: CSSProperties = {
                      width: width ?? undefined,
                      minWidth: width ?? undefined,
                      position: pinnedLeft || pinnedRight ? 'sticky' : undefined,
                      left: pinnedLeft ? pinOffsetLeft(column.key) : undefined,
                      right: pinnedRight ? pinOffsetRight(column.key) : undefined,
                      zIndex: pinnedLeft || pinnedRight ? 2 : undefined,
                      background: pinnedLeft || pinnedRight ? '#fff' : undefined,
                    };
                    return (
                      <td key={column.key} className={columnHeaderClass(column.key)} style={style}>
                        {renderOfflineLeadCell(lead, column.key, {
                          onOpenBookings: next =>
                            setBookingsModal({
                              leadId: next.id,
                              leadName: next.full_name,
                            }),
                          onOpenCounselorNotes: next =>
                            setFollowupDrawer({
                              leadId: next.id,
                              leadName: next.full_name,
                            }),
                          onEditLead: openEditModal,
                          bookAppointmentReturnTo: (() => {
                            const params = new URLSearchParams(location.search);
                            if (page > 1) params.set('page', String(page));
                            else params.delete('page');
                            const qs = params.toString();
                            return `${location.pathname}${qs ? `?${qs}` : ''}`;
                          })(),
                        })}
                      </td>
                    );
                  })}
                  <td className="w-[7.5rem] text-right">
                    <div className="inline-flex items-center justify-end gap-1">
                      <button
                        type="button"
                        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700 px-2 py-1.5"
                        onClick={() =>
                          setJourneyModal({
                            studentId: lead.id,
                            studentName: lead.full_name,
                          })
                        }
                        aria-label="View Journey"
                        title="View Journey"
                      >
                        <MapIcon size={14} />
                      </button>
                      <button
                        type="button"
                        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700 px-2 py-1.5"
                        onClick={() => openEditModal(lead)}
                        aria-label={`Edit ${lead.full_name}`}
                        title="Edit lead"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700 px-2 py-1.5"
                        onClick={() => handleToggleActive(lead)}
                        disabled={setActiveMutation.isPending}
                        aria-label={
                          lead.is_active === false
                            ? `Activate ${lead.full_name}`
                            : `Deactivate ${lead.full_name}`
                        }
                        title={lead.is_active === false ? 'Set Active' : 'Set Inactive'}
                      >
                        {lead.is_active === false ? (
                          <CheckCircle2 size={14} />
                        ) : (
                          <Ban size={14} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white px-[18px] py-3">
        <div className="text-[13px] text-slate-500">
          Showing {items.length} of {total} leads
        </div>
        {renderPaginationControls()}
      </div>

      {modalOpen &&
        createPortal(
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/45 p-4 max-md:items-stretch max-md:p-0">
          <div
            className="flex max-h-[96vh] w-[min(1360px,calc(100vw-24px))] flex-col overflow-hidden rounded-xl bg-white shadow-[0_20px_50px_rgba(15,23,42,0.2)] max-md:max-h-screen max-md:w-full max-md:max-w-full max-md:rounded-none max-[900px]:w-[min(960px,calc(100vw-20px))] [&_form]:flex [&_form]:min-h-0 [&_form]:flex-1 [&_form]:flex-col [&_form]:overflow-hidden"
            role="dialog"
            aria-modal="true"
            aria-labelledby="offline-lead-modal-title"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-6 py-4 [&_h3]:m-0 [&_h3]:text-[17px] [&_h3]:text-slate-900">
              <h3 id="offline-lead-modal-title">{editingLead ? 'Edit Lead' : 'Add Offline Lead'}</h3>
              <button type="button" className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700" onClick={requestCloseModal}>
                <X size={16} />
              </button>
            </div>

            <form
              onSubmit={handleSubmit}
              onKeyDown={event => {
                if (event.key !== 'Enter' || event.target instanceof HTMLTextAreaElement) {
                  return;
                }
                event.preventDefault();
              }}
            >
              <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-x-hidden overflow-y-auto px-6 py-5">
                <section className="flex min-w-0 flex-col gap-3 overflow-visible rounded-[10px] border border-slate-200 px-4 py-3.5">
                  <h4 className="m-0 text-sm font-bold uppercase tracking-wide text-slate-700">Personal Profile</h4>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-3 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-first-name">First Name *</label>
                      <input
                        id="ol-first-name"
                        value={form.first_name}
                        onChange={e => updateForm({ first_name: e.target.value })}
                        required
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-middle-name">Middle Name</label>
                      <input
                        id="ol-middle-name"
                        value={form.middle_name || ''}
                        onChange={e => updateForm({ middle_name: e.target.value })}
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-last-name">Last Name</label>
                      <input
                        id="ol-last-name"
                        value={form.last_name}
                        onChange={e => updateForm({ last_name: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 min-[769px]:grid-cols-2 min-[901px]:grid-cols-4 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-dob">Date of Birth</label>
                      <input
                        id="ol-dob"
                        type="date"
                        value={form.date_of_birth || ''}
                        onChange={e => updateForm({ date_of_birth: e.target.value })}
                        max={maxDateOfBirth}
                      />
                      {dobError ? (
                        <span className="text-[13px] font-semibold leading-snug text-amber-700">{dobError}</span>
                      ) : (
                        computedAge !== null && (
                          <span className="text-[13px] font-semibold text-emerald-600">Age: {computedAge} years</span>
                        )
                      )}
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-email">Email *</label>
                      <input
                        id="ol-email"
                        type="email"
                        value={form.email || ''}
                        onChange={e => updateForm({ email: e.target.value })}
                        required
                      />
                      {emailTaken && (
                        <span className="text-[13px] font-semibold leading-snug text-amber-700">
                          This email is already registered.
                        </span>
                      )}
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-phone-country">Phone Country *</label>
                      <select
                        id="ol-phone-country"
                        value={form.phone_country_iso2}
                        onChange={e => updateForm({ phone_country_iso2: e.target.value })}
                        required
                      >
                        <option value="">Country code</option>
                        {sortedCountries.map(country => (
                          <option key={country.iso2} value={country.iso2}>
                            {formatPhoneCountryLabel(country)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-phone-local">Phone Number *</label>
                      <input
                        id="ol-phone-local"
                        type="tel"
                        inputMode="text"
                        autoCapitalize="characters"
                        spellCheck={false}
                        value={form.phone_local}
                        onChange={e =>
                          updateForm({ phone_local: sanitizePhoneLocalDraft(e.target.value) })
                        }
                        placeholder={PHONE_LOCAL_PLACEHOLDER}
                        maxLength={PHONE_LOCAL_DRAFT_MAX_LENGTH}
                        required
                      />
                      {phoneTaken && (
                        <span className="text-[13px] font-semibold leading-snug text-amber-700">
                          This phone number is already registered.
                        </span>
                      )}
                    </div>
                  </div>
                </section>

                <section className="flex min-w-0 flex-col gap-3 overflow-visible rounded-[10px] border border-slate-200 px-4 py-3.5">
                  <h4 className="m-0 text-sm font-bold uppercase tracking-wide text-slate-700">
                    Current Location{geoLoading && !editingLead ? ' (detecting…)' : ''}
                  </h4>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-address-1">Address Line 1</label>
                      <input
                        id="ol-address-1"
                        value={form.location?.address_line_1 || ''}
                        onChange={e => updateLocation({ address_line_1: e.target.value })}
                        placeholder="Street address, P.O. box, company name"
                        autoComplete="address-line1"
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-address-2">Address Line 2</label>
                      <input
                        id="ol-address-2"
                        value={form.location?.address_line_2 || ''}
                        onChange={e => updateLocation({ address_line_2: e.target.value })}
                        placeholder="Apartment, suite, unit, building, floor"
                        autoComplete="address-line2"
                      />
                    </div>
                  </div>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 min-[769px]:grid-cols-2 min-[901px]:grid-cols-4 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-country">Country</label>
                      <select
                        id="ol-country"
                        value={form.location?.country_iso2 || ''}
                        onChange={e => updateLocation({ country_iso2: e.target.value })}
                      >
                        <option value="">Select country</option>
                        {sortedCountries.map(country => (
                          <option key={country.iso2} value={country.iso2}>
                            {country.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-state">State</label>
                      <input
                        id="ol-state"
                        value={form.location?.state || ''}
                        onChange={e => updateLocation({ state: e.target.value })}
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-city">City</label>
                      <input
                        id="ol-city"
                        value={form.location?.city || ''}
                        onChange={e => updateLocation({ city: e.target.value })}
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-zip">Zip code</label>
                      <input
                        id="ol-zip"
                        value={form.location?.zip_code || ''}
                        onChange={e => updateLocation({ zip_code: e.target.value })}
                        placeholder="e.g. 560001"
                      />
                    </div>
                  </div>
                </section>

                <section className="flex min-w-0 flex-col gap-3 overflow-visible rounded-[10px] border border-slate-200 px-4 py-3.5">
                  <h4 className="m-0 text-sm font-bold uppercase tracking-wide text-slate-700">Education</h4>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 min-[769px]:grid-cols-2 min-[901px]:grid-cols-4 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-course-level">Levels</label>
                      <select
                        id="ol-course-level"
                        value={educationLevelId}
                        onChange={e => {
                          const nextLevelId = e.target.value;
                          setEducationLevelId(nextLevelId);
                          updateEducation({
                            full_time_study_years: '',
                            program_code: '',
                            major: '',
                          });
                        }}
                      >
                        <option value="">Select level</option>
                        {sortedLevelOptions.map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-study-years">Full-Time Study Years</label>
                      <select
                        id="ol-study-years"
                        value={form.education?.full_time_study_years || ''}
                        disabled={!educationLevelId}
                        onChange={e =>
                          updateEducation({ full_time_study_years: e.target.value })
                        }
                      >
                        <option value="">
                          {educationLevelId
                            ? filteredStudyYears.length
                              ? 'Select study years'
                              : 'No study years for this level'
                            : 'Select level first'}
                        </option>
                        {filteredStudyYears.map(option => (
                          <option key={option.code} value={option.code}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-program">Programs</label>
                      <select
                        id="ol-program"
                        value={form.education?.program_code || ''}
                        disabled={!educationLevelId}
                        onChange={e => {
                          const nextCode = e.target.value;
                          const program = findQualificationProgram(
                            qualificationPrograms,
                            nextCode
                          );
                          const mapped = program?.majors ?? [];
                          const autoMajor = mapped.length === 1 ? mapped[0].label : '';
                          updateEducation({
                            program_code: nextCode,
                            major: autoMajor,
                          });
                        }}
                      >
                        <option value="">
                          {educationLevelId
                            ? filteredPrograms.length
                              ? 'Select program'
                              : 'No programs for this level'
                            : 'Select level first'}
                        </option>
                        {filteredPrograms.map(program => (
                          <option key={program.code} value={program.code}>
                            {program.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-major">Major</label>
                      <select
                        id="ol-major"
                        value={
                          filteredMajors.some(major => major.label === majorSelectValue)
                            ? majorSelectValue
                            : ''
                        }
                        disabled={!form.education?.program_code}
                        onChange={e => updateEducation({ major: e.target.value })}
                      >
                        <option value="">
                          {form.education?.program_code
                            ? filteredMajors.length
                              ? 'Select major'
                              : 'No majors for this program'
                            : 'Select program first'}
                        </option>
                        {filteredMajors.map(major => (
                          <option key={major.code || major.id} value={major.label}>
                            {major.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-3 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-university">University</label>
                      <input
                        id="ol-university"
                        value={form.education?.university || ''}
                        onChange={e => updateEducation({ university: e.target.value })}
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-grad-year">Graduation Year</label>
                      <input
                        id="ol-grad-year"
                        type="number"
                        min={1950}
                        max={2100}
                        value={form.education?.graduation_year ?? ''}
                        onChange={e =>
                          updateEducation({
                            graduation_year: e.target.value ? Number(e.target.value) : undefined,
                          })
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-gpa-cgpa">GPA / CGPA</label>
                      <select
                        id="ol-gpa-cgpa"
                        value={form.education?.gpa_cgpa_code || ''}
                        onChange={e => {
                          const nextCode = e.target.value;
                          const nextScore = findGpaCgpaScore(gpaCgpaScores, nextCode);
                          updateEducation({
                            gpa_cgpa_code: nextCode,
                            gpa_cgpa_other: nextScore?.is_other
                              ? form.education?.gpa_cgpa_other || ''
                              : '',
                          });
                        }}
                      >
                        <option value="">Select GPA / CGPA</option>
                        {gpaCgpaScores.map(score => (
                          <option key={score.code} value={score.code}>
                            {score.label}
                          </option>
                        ))}
                      </select>
                      {selectedGpaCgpa?.is_other && (
                        <input
                          id="ol-gpa-cgpa-other"
                          className="mt-1.5"
                          value={form.education?.gpa_cgpa_other || ''}
                          onChange={e => updateEducation({ gpa_cgpa_other: e.target.value })}
                          placeholder="Enter GPA / CGPA"
                        />
                      )}
                    </div>
                  </div>
                </section>

                <section className="flex min-w-0 flex-col gap-3 overflow-visible rounded-[10px] border border-slate-200 px-4 py-3.5">
                  <h4 className="m-0 text-sm font-bold uppercase tracking-wide text-slate-700">Study Interest</h4>
                  <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0 grid min-w-0 grid-cols-1 gap-3 min-[769px]:grid-cols-2 min-[901px]:grid-cols-4 [&>*]:min-w-0">
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-target-destination">Target Destination</label>
                      <SearchableMultiSelect
                        id="ol-target-destination"
                        compact
                        preferDropUp
                        values={form.target_destination_iso2s || []}
                        options={targetDestinationOptions}
                        onChange={values =>
                          updateForm({
                            target_destination_iso2s: values.slice(0, 6),
                            ...(values.length
                              ? {}
                              : {
                                  target_level_id: undefined,
                                  target_major_ids: [],
                                  target_program_codes: [],
                                }),
                          })
                        }
                        maxSelections={6}
                        placeholder="Select up to 6 countries"
                        hint="Max 6 countries"
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-target-level">Target Levels</label>
                      <select
                        id="ol-target-level"
                        value={targetLevelId}
                        disabled={!form.target_destination_iso2s?.length}
                        onChange={e => {
                          const nextLevelId = e.target.value
                            ? Number(e.target.value)
                            : undefined;
                          updateForm({
                            target_level_id: nextLevelId,
                            target_major_ids: [],
                            target_program_codes: [],
                          });
                        }}
                      >
                        <option value="">
                          {form.target_destination_iso2s?.length
                            ? 'Select level'
                            : 'Select destination first'}
                        </option>
                        {sortedLevelOptions.map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-target-majors">Target Majors</label>
                      <SearchableMultiSelect
                        id="ol-target-majors"
                        compact
                        preferDropUp
                        values={(form.target_major_ids || []).map(String)}
                        options={studyInterestMajors.map(major => ({
                          value: String(major.id),
                          label: major.label,
                        }))}
                        onChange={values => {
                          const nextMajorIds = values
                            .map(Number)
                            .filter(id => Number.isFinite(id) && id > 0)
                            .slice(0, 3);
                          const majorIdSet = new Set(nextMajorIds);
                          const nextProgramCodes = (form.target_program_codes || []).filter(
                            code => {
                              const program = findQualificationProgram(
                                qualificationPrograms,
                                code
                              );
                              return (program?.majors ?? []).some(major =>
                                majorIdSet.has(major.id)
                              );
                            }
                          );
                          updateForm({
                            target_major_ids: nextMajorIds,
                            target_program_codes: nextProgramCodes,
                          });
                        }}
                        maxSelections={3}
                        disabled={!form.target_level_id}
                        placeholder={
                          form.target_level_id
                            ? studyInterestMajors.length
                              ? 'Select up to 3 majors'
                              : 'No majors for this level'
                            : 'Select level first'
                        }
                        hint="Max 3 majors"
                        emptyMessage="No majors for this level"
                      />
                    </div>
                    <div className="flex flex-col gap-1 [&_input]:box-border [&_input]:w-full [&_input]:max-w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-slate-200 [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-sm [&_input]:focus:border-accent [&_input]:focus:outline-2 [&_input]:focus:outline-accent/35 [&_label]:text-[13px] [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-wide [&_label]:text-slate-500 [&_select]:box-border [&_select]:w-full [&_select]:max-w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-slate-200 [&_select]:px-2.5 [&_select]:py-2 [&_select]:text-sm [&_select]:focus:border-accent [&_select]:focus:outline-2 [&_select]:focus:outline-accent/35">
                      <label htmlFor="ol-target-programs">Target Programs</label>
                      <SearchableMultiSelect
                        id="ol-target-programs"
                        compact
                        preferDropUp
                        values={form.target_program_codes || []}
                        options={studyInterestPrograms.map(program => ({
                          value: program.code,
                          label: program.name,
                        }))}
                        onChange={values =>
                          updateForm({
                            target_program_codes: values,
                          })
                        }
                        disabled={!form.target_major_ids?.length}
                        placeholder={
                          form.target_major_ids?.length
                            ? studyInterestPrograms.length
                              ? 'Select programs'
                              : 'No programs for selected majors'
                            : 'Select majors first'
                        }
                        emptyMessage="No programs for selected majors"
                      />
                    </div>
                  </div>
                </section>

                {formError && <p className="m-0 text-[13px] text-red-700">{formError}</p>}
              </div>

              <div className="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-6 py-4">
                <button type="button" className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700" onClick={requestCloseModal}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-accent text-white disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSaving || emailTaken || phoneTaken}
                >
                  {isSaving ? 'Saving…' : editingLead ? 'Update Lead' : 'Save Lead'}
                </button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}
    </div>
    {statusModal &&
      createPortal(
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/45 p-4 max-md:items-stretch max-md:p-0" onMouseDown={closeStatusModal}>
          <div
            className="max-h-[90vh] w-[min(480px,calc(100vw-32px))] overflow-auto rounded-xl bg-white shadow-[0_20px_50px_rgba(15,23,42,0.25)]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="offline-lead-status-title"
            onMouseDown={event => event.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-6 py-4 [&_h3]:m-0 [&_h3]:text-[17px] [&_h3]:text-slate-900">
              <h3 id="offline-lead-status-title">
                {statusModal.nextActive ? 'Set lead Active' : 'Set lead Inactive'}
              </h3>
              <button
                type="button"
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700"
                onClick={closeStatusModal}
                aria-label="Close status change dialog"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex flex-col gap-3.5 px-[18px] py-4">
              <p className="m-0 text-sm leading-snug text-slate-700">
                You are about to mark{' '}
                <strong>
                  {statusModal.lead.full_name || `lead #${statusModal.lead.id}`}
                </strong>{' '}
                as <strong>{statusModal.nextActive ? 'Active' : 'Inactive'}</strong>. Select at
                least one reason. The lead is not deleted.
              </p>
              <fieldset className="m-0 flex flex-col gap-2 rounded-[10px] border border-slate-200 p-3 [&_legend]:px-1 [&_legend]:text-xs [&_legend]:font-bold [&_legend]:text-slate-500">
                <legend>Reasons</legend>
                {(statusModal.nextActive
                  ? OFFLINE_LEAD_ACTIVE_REASONS
                  : OFFLINE_LEAD_INACTIVE_REASONS
                ).map(reason => {
                  const checked = statusReasons.includes(reason);
                  const inputId = `status-reason-${reason.replace(/[^a-zA-Z0-9]+/g, '-')}`;
                  return (
                    <label key={reason} htmlFor={inputId} className="flex cursor-pointer items-start gap-2 text-sm text-slate-900 [&_input]:mt-0.5">
                      <input
                        id={inputId}
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleStatusReason(reason)}
                      />
                      <span>{reason}</span>
                    </label>
                  );
                })}
              </fieldset>
              {statusError ? (
                <p className="text-[13px] font-semibold leading-snug text-amber-700" role="alert">
                  {statusError}
                </p>
              ) : null}
            </div>
            <div className="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-6 py-4">
              <button
                type="button"
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-slate-100 text-slate-700"
                onClick={closeStatusModal}
                disabled={setActiveMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold border-0 bg-accent text-white disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void confirmStatusChange()}
                disabled={setActiveMutation.isPending || statusReasons.length === 0}
              >
                {setActiveMutation.isPending ? 'Saving…' : 'Confirm Status Change'}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    <StudentJourneyPanel
      open={journeyModal !== null}
      studentId={journeyModal?.studentId ?? null}
      studentName={journeyModal?.studentName}
      onClose={() => setJourneyModal(null)}
    />
    <CounselorFollowupDrawer
      open={followupDrawer !== null}
      leadId={followupDrawer?.leadId ?? null}
      leadName={followupDrawer?.leadName}
      onClose={() => setFollowupDrawer(null)}
    />
    <LeadBookingsModal
      open={bookingsModal !== null}
      leadId={bookingsModal?.leadId ?? null}
      leadName={bookingsModal?.leadName}
      onClose={() => setBookingsModal(null)}
      onSelectBooking={(booking: LeadBookingSummary) => {
        if (!bookingsModal) return;
        setSessionDrawer({
          bookingId: booking.id,
          leadId: bookingsModal.leadId,
          candidateName: booking.candidate_name || bookingsModal.leadName,
          dateLabel: booking.date_label,
          timeLabel: booking.time_label,
        });
        setBookingsModal(null);
      }}
    />
    <CounsellingSessionDrawer
      open={sessionDrawer !== null}
      bookingId={sessionDrawer?.bookingId}
      candidateId={sessionDrawer?.leadId}
      candidateName={sessionDrawer?.candidateName}
      dateLabel={sessionDrawer?.dateLabel}
      timeLabel={sessionDrawer?.timeLabel}
      onClose={() => setSessionDrawer(null)}
      onStatusUpdated={() => {
        void listQuery.refetch();
      }}
    />
    </>
  );
}
