import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { ArrowDown, ArrowUp, ArrowUpDown, Map as MapIcon, Pencil, Plus, Search, X } from 'lucide-react';
import { useCreateOfflineLead, useOfflineLeadDuplicateCheck, useOfflineLeads, useUpdateOfflineLead } from '../hooks/useOfflineLeads';
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
import CounsellingSessionDrawer from '../components/CounsellingSessionDrawer';
import LeadBookingsModal from '../components/LeadBookingsModal';
import StudentJourneyPanel from '../components/StudentJourneyPanel';
import { useConfirmation } from '../context/ConfirmationContext';
import type { LeadBookingSummary } from '../hooks/useLeadBookings';
import { bookAppointmentHref } from '../utils/bookAppointmentHref';
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
import './OfflineLeadsPage.css';

const OFFLINE_LEADS_PAGE_SIZE_KEY = 'nexus.offlineLeads.pageSize';
const OFFLINE_LEADS_COLUMNS_KEY = 'nexus.offlineLeads.visibleColumns.v7';
const PAGE_SIZE_OPTIONS = TABLE_PAGE_SIZE_OPTIONS;

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
  | 'booking'
  | 'new_booking'
  | 'lead_status'
  | 'status'
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
  { key: 'booking', label: 'Booking', defaultVisible: true },
  { key: 'new_booking', label: 'New Booking', defaultVisible: true },
  { key: 'lead_status', label: 'Lead Status', defaultVisible: true },
  { key: 'status', label: 'Chat Status', defaultVisible: true },
  { key: 'created_at', label: 'Date Added', defaultVisible: true },
];

const OFFLINE_LEAD_COLUMN_OPTIONS = OFFLINE_LEAD_COLUMN_DEFS.map(column => ({
  value: column.key,
  label: column.label,
}));

const REQUIRED_OFFLINE_LEAD_COLUMNS = OFFLINE_LEAD_COLUMN_DEFS.filter(column => column.required).map(
  column => column.key
);

function defaultOfflineLeadColumns(): OfflineLeadColumnKey[] {
  return OFFLINE_LEAD_COLUMN_DEFS.filter(column => column.defaultVisible).map(column => column.key);
}

function normalizeOfflineLeadColumns(keys: string[]): OfflineLeadColumnKey[] {
  const allowed = new Set(OFFLINE_LEAD_COLUMN_DEFS.map(column => column.key));
  const selected = new Set(
    keys.filter((key): key is OfflineLeadColumnKey => allowed.has(key as OfflineLeadColumnKey))
  );
  for (const key of REQUIRED_OFFLINE_LEAD_COLUMNS) {
    selected.add(key);
  }
  return OFFLINE_LEAD_COLUMN_DEFS.map(column => column.key).filter(key => selected.has(key));
}

function readStoredOfflineLeadColumns(): OfflineLeadColumnKey[] {
  try {
    const raw = localStorage.getItem(OFFLINE_LEADS_COLUMNS_KEY);
    if (!raw) return defaultOfflineLeadColumns();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return defaultOfflineLeadColumns();
    const normalized = normalizeOfflineLeadColumns(parsed.map(String));
    return normalized.length ? normalized : defaultOfflineLeadColumns();
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
  location: { city: '', state: '', country_iso2: '', zip_code: '' },
};

function serializeOfflineLeadForm(form: OfflineLeadCreatePayload): string {
  return JSON.stringify(form);
}

const UNSAVED_CLOSE_MESSAGE =
  'You have unsaved changes. Discard them and close this form?';

async function detectLocationFromIp(): Promise<{
  city: string;
  state: string;
  country_iso2: string;
  zip_code: string;
}> {
  try {
    const response = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('geo failed');
    const data = (await response.json()) as {
      city?: string;
      region?: string;
      country_code?: string;
      postal?: string;
    };
    return {
      city: data.city || '',
      state: data.region || '',
      country_iso2: (data.country_code || '').toUpperCase(),
      zip_code: data.postal || '',
    };
  } catch {
    return { city: '', state: '', country_iso2: '', zip_code: '' };
  }
}

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
        {ageLabel ? <div className="offline-leads-table__age">{ageLabel}</div> : null}
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
  return String(source || '').toUpperCase() === 'EXPRESS' ? 'Express Lead' : 'Offline Lead';
}

function columnHeaderClass(key: OfflineLeadColumnKey): string | undefined {
  if (key === 'date_of_birth') return 'offline-leads-table__dob';
  return undefined;
}

function renderOfflineLeadCell(
  lead: OfflineLeadItem,
  key: OfflineLeadColumnKey,
  handlers?: {
    onViewJourney?: (lead: OfflineLeadItem) => void;
    onOpenBookings?: (lead: OfflineLeadItem) => void;
    onEditLead?: (lead: OfflineLeadItem) => void;
  }
): ReactNode {
  switch (key) {
    case 'full_name':
      return lead.full_name || '—';
    case 'student_id':
      return (
        <button
          type="button"
          className="offline-leads-journey-link"
          onClick={() => handlers?.onEditLead?.(lead)}
          title={`Edit ${lead.full_name || `lead #${lead.id}`}`}
        >
          {lead.id}
        </button>
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
    case 'booking': {
      const count = lead.booking_count ?? 0;
      if (count <= 0) {
        return <span className="text-text-muted">0</span>;
      }
      return (
        <button
          type="button"
          className="offline-leads-journey-link"
          onClick={() => handlers?.onOpenBookings?.(lead)}
          title="View counselling bookings"
        >
          {count}
        </button>
      );
    }
    case 'new_booking':
      return (
        <Link
          to={bookAppointmentHref({
            id: lead.id,
            full_name: lead.full_name || '',
            email: lead.email,
            phone_number: lead.phone_number,
          })}
          className="offline-leads-journey-link"
          title={`Book appointment for ${lead.full_name || `lead #${lead.id}`}`}
        >
          Book Now
        </Link>
      );
    case 'lead_status':
      return (
        <button
          type="button"
          className="offline-leads-journey-link"
          onClick={() => handlers?.onViewJourney?.(lead)}
          title="View student journey timeline"
        >
          <MapIcon size={13} />
          View Journey
        </button>
      );
    case 'status':
      return <span className={statusClass(lead.status_label)}>{lead.status_label}</span>;
    case 'created_at':
      return formatDateAdded(lead.created_at);
    default:
      return '—';
  }
}

function statusClass(label: string): string {
  if (label === 'Handoff') return 'offline-leads-status offline-leads-status--handoff';
  if (label === 'Archive') return 'offline-leads-status offline-leads-status--archive';
  return 'offline-leads-status offline-leads-status--ai';
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

export default function OfflineLeadsPage() {
  const openConfirm = useConfirmation();
  const [searchParams, setSearchParams] = useSearchParams();
  const consumedEditRef = useRef<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<TablePageSize>(() =>
    readStoredTablePageSize(OFFLINE_LEADS_PAGE_SIZE_KEY)
  );
  const [search, setSearch] = useState(() => searchParams.get('q') || '');
  const [status, setStatus] = useState<OfflineLeadStatusFilter>('ALL');
  const [sortBy, setSortBy] = useState<OfflineLeadSortField>('created_at');
  const [sortDir, setSortDir] = useState<OfflineLeadSortDirection>('desc');
  const [visibleColumns, setVisibleColumns] = useState<OfflineLeadColumnKey[]>(readStoredOfflineLeadColumns);
  const [journeyModal, setJourneyModal] = useState<{
    studentId: number;
    studentName: string;
  } | null>(null);
  const [bookingsModal, setBookingsModal] = useState<{
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
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLead, setEditingLead] = useState<OfflineLeadItem | null>(null);
  const [form, setForm] = useState<OfflineLeadCreatePayload>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [formBaseline, setFormBaseline] = useState('');
  const formIsDirty =
    modalOpen && Boolean(formBaseline) && serializeOfflineLeadForm(form) !== formBaseline;
  useUnsavedChanges(formIsDirty, 'offline-leads-form');
  const [educationLevelId, setEducationLevelId] = useState('');


  const debouncedSearch = useDebouncedValue(search, 350);

  const query: OfflineLeadsQuery = useMemo(
    () => ({
      page,
      pageSize,
      q: debouncedSearch,
      status,
      sortBy,
      sortDir,
    }),
    [page, pageSize, debouncedSearch, status, sortBy, sortDir]
  );

  const listQuery = useOfflineLeads(query);
  const createMutation = useCreateOfflineLead();
  const updateMutation = useUpdateOfflineLead();
  const { countries } = useCountries();
  const { programs: qualificationPrograms } = useQualificationPrograms();
  const { levels } = useLevels();
  const filteredPrograms = useMemo(() => {
    if (!educationLevelId) return [];
    return qualificationPrograms.filter(
      program => program.level_id === Number(educationLevelId)
    );
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
    if (matched.length) {
      return matched;
    }
    return mappedProgramMajors.map(major => ({
      id: major.id,
      code: major.code,
      label: major.label,
      is_other: false,
      sort_order: 0,
      is_active: true,
    }));
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
    () => filterFullTimeStudyYearsByLevel(studyYearOptions, educationLevelId),
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
    return Array.from(byId.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [form.target_level_id, qualificationPrograms]);
  const studyInterestPrograms = useMemo(() => {
    if (!form.target_level_id || !form.target_major_ids?.length) return [];
    const majorIds = new Set(form.target_major_ids);
    return qualificationPrograms.filter(
      program =>
        program.level_id === form.target_level_id &&
        (program.majors ?? []).some(major => majorIds.has(major.id))
    );
  }, [form.target_level_id, form.target_major_ids, qualificationPrograms]);
  const computedAge = useMemo(() => computeAgeFromDob(form.date_of_birth), [form.date_of_birth]);
  const dobError = useMemo(() => validateDateOfBirth(form.date_of_birth), [form.date_of_birth]);
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

  const visibleColumnDefs = useMemo(
    () => OFFLINE_LEAD_COLUMN_DEFS.filter(column => visibleColumns.includes(column.key)),
    [visibleColumns]
  );

  const handleVisibleColumnsChange = (values: string[]) => {
    setVisibleColumns(normalizeOfflineLeadColumns(values));
  };

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, status, pageSize, sortBy, sortDir]);

  const toggleSort = (field: OfflineLeadSortField) => {
    if (sortBy === field) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortDir(field === 'created_at' ? 'desc' : 'asc');
    }
  };

  const openCreateModal = async () => {
    setEditingLead(null);
    setEducationLevelId('');
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormBaseline(serializeOfflineLeadForm(EMPTY_FORM));
    setModalOpen(true);
    setGeoLoading(true);
    const detected = await detectLocationFromIp();
    const withLocation: OfflineLeadCreatePayload = {
      ...EMPTY_FORM,
      location: {
        city: detected.city,
        state: detected.state,
        country_iso2: detected.country_iso2,
        zip_code: detected.zip_code,
      },
    };
    setForm(withLocation);
    setFormBaseline(serializeOfflineLeadForm(withLocation));
    setGeoLoading(false);
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

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (!form.first_name.trim()) {
      setFormError('First name is required.');
      return;
    }
    if (!form.last_name.trim()) {
      setFormError('Last name is required.');
      return;
    }
    if (!form.date_of_birth) {
      setFormError('Date of birth is required.');
      return;
    }
    const dobValidationError = validateDateOfBirth(form.date_of_birth);
    if (dobValidationError) {
      setFormError(dobValidationError);
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

    if (!educationLevelId) {
      setFormError('Level is required.');
      return;
    }

    const gpaError = validateGpaCgpaScore(
      form.education?.gpa_cgpa_code,
      form.education?.gpa_cgpa_other,
      gpaCgpaScores
    );
    if (gpaError) {
      setFormError(gpaError);
      return;
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
      last_name: form.last_name.trim(),
      phone_country_iso2: form.phone_country_iso2,
      phone_local: phoneLocalToDigits(form.phone_local),
      email: form.email.trim(),
      date_of_birth: form.date_of_birth,
      target_destination_iso2s: form.target_destination_iso2s,
      target_level_id: form.target_level_id,
      target_major_ids: form.target_major_ids,
      target_program_codes: form.target_program_codes,
      location: {
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

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? 0;
  const totalPages = listQuery.data?.total_pages ?? 1;
  const currentPage = listQuery.data?.page ?? page;

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
    <div className="offline-leads-page">
      <div className="offline-leads-toolbar">
        <div className="offline-leads-toolbar__title">
          <h2>Offline Leads</h2>
          <p className="offline-leads-toolbar__subtitle">
            Manually entered walk-in and event leads · source defaults to Offline · status AI Active
          </p>
        </div>

        <div className="offline-leads-toolbar__controls">
          <div className="offline-leads-toolbar__search">
            <Search size={15} color="#64748b" />
            <input
              type="search"
              placeholder="Search name, email, or phone…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search offline leads"
            />
          </div>

          <div className="offline-leads-toolbar__field offline-leads-toolbar__columns">
            <span>Columns</span>
            <SearchableMultiSelect
              id="offline-leads-columns"
              values={visibleColumns}
              options={OFFLINE_LEAD_COLUMN_OPTIONS}
              onChange={handleVisibleColumnsChange}
              placeholder="Choose columns…"
              selectedDisplay={`${visibleColumns.length} columns`}
              compact
              className="offline-leads-columns-select"
            />
          </div>

          <div className="offline-leads-toolbar__field">
            <span>Status</span>
            <select
              value={status}
              onChange={e => setStatus(e.target.value as OfflineLeadStatusFilter)}
            >
              <option value="ALL">All Prospects</option>
              <option value="AI_ACTIVE">AI Active</option>
              <option value="HANDOFF">Handoff</option>
            </select>
          </div>

          <button type="button" className="offline-leads-btn offline-leads-btn--primary" onClick={openCreateModal}>
            <Plus size={16} />
            Add New Lead
          </button>
        </div>
      </div>

      <div className="offline-leads-table-wrap">
        {listQuery.isLoading && !listQuery.data ? (
          <div className="offline-leads-empty">Loading offline leads…</div>
        ) : listQuery.isError ? (
          <div className="offline-leads-empty">Failed to load offline leads.</div>
        ) : items.length === 0 ? (
          <div className="offline-leads-empty">No offline leads match your filters.</div>
        ) : (
          <table className="offline-leads-table">
            <thead>
              <tr>
                {visibleColumnDefs.map(column => {
                  const sortable =
                    column.key === 'full_name' ||
                    column.key === 'email' ||
                    column.key === 'phone_number' ||
                    column.key === 'created_at';
                  if (sortable) {
                    const sortField = column.key as OfflineLeadSortField;
                    return (
                      <th
                        key={column.key}
                        className={`sortable ${columnHeaderClass(column.key) || ''}`.trim()}
                        onClick={() => toggleSort(sortField)}
                      >
                        {column.label}{' '}
                        <SortIcon field={sortField} sortBy={sortBy} sortDir={sortDir} />
                      </th>
                    );
                  }
                  return (
                    <th key={column.key} className={columnHeaderClass(column.key)}>
                      {column.label}
                    </th>
                  );
                })}
                <th className="offline-leads-table__actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((lead: OfflineLeadItem) => (
                <tr key={lead.id}>
                  {visibleColumnDefs.map(column => (
                    <td key={column.key} className={columnHeaderClass(column.key)}>
                      {renderOfflineLeadCell(lead, column.key, {
                        onViewJourney: next =>
                          setJourneyModal({
                            studentId: next.id,
                            studentName: next.full_name,
                          }),
                        onOpenBookings: next =>
                          setBookingsModal({
                            leadId: next.id,
                            leadName: next.full_name,
                          }),
                        onEditLead: openEditModal,
                      })}
                    </td>
                  ))}
                  <td className="offline-leads-table__actions">
                    <button
                      type="button"
                      className="offline-leads-btn offline-leads-btn--ghost offline-leads-btn--icon"
                      onClick={() => openEditModal(lead)}
                      aria-label={`Edit ${lead.full_name}`}
                      title="Edit lead"
                    >
                      <Pencil size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="offline-leads-pagination">
        <div className="offline-leads-pagination__info">
          Showing {items.length} of {total} offline leads
        </div>
        <div className="offline-leads-pagination__controls">
          <div className="offline-leads-toolbar__field">
            <span>Rows</span>
            <select
              value={pageSize}
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
            className="offline-leads-btn offline-leads-btn--ghost"
            disabled={currentPage <= 1 || listQuery.isFetching}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span className="offline-leads-pagination__info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            className="offline-leads-btn offline-leads-btn--ghost"
            disabled={currentPage >= totalPages || listQuery.isFetching}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </button>
        </div>
      </div>

      {modalOpen &&
        createPortal(
        <div className="offline-leads-modal-backdrop">
          <div
            className="offline-leads-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="offline-lead-modal-title"
          >
            <div className="offline-leads-modal__header">
              <h3 id="offline-lead-modal-title">{editingLead ? 'Edit Offline Lead' : 'Add Offline Lead'}</h3>
              <button type="button" className="offline-leads-btn offline-leads-btn--ghost" onClick={requestCloseModal}>
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
              <div className="offline-leads-modal__body">
                <section className="offline-leads-panel">
                  <h4 className="offline-leads-panel__title">Personal Profile</h4>
                  <div className="offline-leads-form-grid offline-leads-form-grid--3">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-first-name">First Name *</label>
                      <input
                        id="ol-first-name"
                        value={form.first_name}
                        onChange={e => updateForm({ first_name: e.target.value })}
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-middle-name">Middle Name</label>
                      <input
                        id="ol-middle-name"
                        value={form.middle_name || ''}
                        onChange={e => updateForm({ middle_name: e.target.value })}
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-last-name">Last Name *</label>
                      <input
                        id="ol-last-name"
                        value={form.last_name}
                        onChange={e => updateForm({ last_name: e.target.value })}
                        required
                      />
                    </div>
                  </div>

                  <div className="offline-leads-form-grid offline-leads-form-grid--4">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-dob">Date of Birth *</label>
                      <input
                        id="ol-dob"
                        type="date"
                        value={form.date_of_birth || ''}
                        onChange={e => updateForm({ date_of_birth: e.target.value })}
                        max={maxDateOfBirth}
                        required
                      />
                      {dobError ? (
                        <span className="offline-leads-field-warning">{dobError}</span>
                      ) : (
                        computedAge !== null && (
                          <span className="offline-leads-age">Age: {computedAge} years</span>
                        )
                      )}
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-email">Email *</label>
                      <input
                        id="ol-email"
                        type="email"
                        value={form.email || ''}
                        onChange={e => updateForm({ email: e.target.value })}
                        required
                      />
                      {emailTaken && (
                        <span className="offline-leads-field-warning">
                          This email is already registered.
                        </span>
                      )}
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-phone-country">Phone Country *</label>
                      <select
                        id="ol-phone-country"
                        value={form.phone_country_iso2}
                        onChange={e => updateForm({ phone_country_iso2: e.target.value })}
                        required
                      >
                        <option value="">Country code</option>
                        {countries.map(country => (
                          <option key={country.iso2} value={country.iso2}>
                            {formatPhoneCountryLabel(country)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="offline-leads-field">
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
                        <span className="offline-leads-field-warning">
                          This phone number is already registered.
                        </span>
                      )}
                    </div>
                  </div>
                </section>

                <section className="offline-leads-panel">
                  <h4 className="offline-leads-panel__title">
                    Current Location{geoLoading && !editingLead ? ' (detecting…)' : ''}
                  </h4>
                  <div className="offline-leads-form-grid offline-leads-form-grid--4">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-country">Country *</label>
                      <select
                        id="ol-country"
                        value={form.location?.country_iso2 || ''}
                        onChange={e => updateLocation({ country_iso2: e.target.value })}
                        required
                      >
                        <option value="">Select country</option>
                        {countries.map(country => (
                          <option key={country.iso2} value={country.iso2}>
                            {country.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-state">State *</label>
                      <input
                        id="ol-state"
                        value={form.location?.state || ''}
                        onChange={e => updateLocation({ state: e.target.value })}
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-city">City *</label>
                      <input
                        id="ol-city"
                        value={form.location?.city || ''}
                        onChange={e => updateLocation({ city: e.target.value })}
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
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

                <section className="offline-leads-panel">
                  <h4 className="offline-leads-panel__title">Education</h4>
                  <div className="offline-leads-form-grid offline-leads-form-grid--4">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-course-level">Levels *</label>
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
                        required
                      >
                        <option value="">Select level</option>
                        {levelSelectOptions(levels).map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-study-years">Full-Time Study Years *</label>
                      <select
                        id="ol-study-years"
                        value={form.education?.full_time_study_years || ''}
                        disabled={!educationLevelId}
                        onChange={e =>
                          updateEducation({ full_time_study_years: e.target.value })
                        }
                        required
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
                    <div className="offline-leads-field">
                      <label htmlFor="ol-program">Programs *</label>
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
                        required
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
                    <div className="offline-leads-field">
                      <label htmlFor="ol-major">Major *</label>
                      <select
                        id="ol-major"
                        value={
                          filteredMajors.some(major => major.label === majorSelectValue)
                            ? majorSelectValue
                            : ''
                        }
                        disabled={!form.education?.program_code}
                        onChange={e => updateEducation({ major: e.target.value })}
                        required={Boolean(form.education?.program_code)}
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
                  <div className="offline-leads-form-grid offline-leads-form-grid--3">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-university">University *</label>
                      <input
                        id="ol-university"
                        value={form.education?.university || ''}
                        onChange={e => updateEducation({ university: e.target.value })}
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-grad-year">Graduation Year *</label>
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
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-gpa-cgpa">GPA / CGPA *</label>
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
                        required
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
                          className="offline-leads-degree-other"
                          value={form.education?.gpa_cgpa_other || ''}
                          onChange={e => updateEducation({ gpa_cgpa_other: e.target.value })}
                          placeholder="Enter GPA / CGPA"
                          required
                        />
                      )}
                    </div>
                  </div>
                </section>

                <section className="offline-leads-panel">
                  <h4 className="offline-leads-panel__title">Study Interest</h4>
                  <div className="offline-leads-form-grid offline-leads-form-grid--4">
                    <div className="offline-leads-field">
                      <label htmlFor="ol-target-destination">Target Destination *</label>
                      <SearchableMultiSelect
                        id="ol-target-destination"
                        compact
                        preferDropUp
                        values={form.target_destination_iso2s || []}
                        options={countries.map(country => ({
                          value: country.iso2,
                          label: country.name,
                        }))}
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
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-target-level">Target Levels *</label>
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
                        required
                      >
                        <option value="">
                          {form.target_destination_iso2s?.length
                            ? 'Select level'
                            : 'Select destination first'}
                        </option>
                        {levelSelectOptions(levels).map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-target-majors">Target Majors *</label>
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
                        required
                      />
                    </div>
                    <div className="offline-leads-field">
                      <label htmlFor="ol-target-programs">Target Programs *</label>
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
                        required
                      />
                    </div>
                  </div>
                </section>

                {formError && <p className="offline-leads-error">{formError}</p>}
              </div>

              <div className="offline-leads-modal__footer">
                <button type="button" className="offline-leads-btn offline-leads-btn--ghost" onClick={requestCloseModal}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="offline-leads-btn offline-leads-btn--primary"
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
    <StudentJourneyPanel
      open={journeyModal !== null}
      studentId={journeyModal?.studentId ?? null}
      studentName={journeyModal?.studentName}
      onClose={() => setJourneyModal(null)}
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
