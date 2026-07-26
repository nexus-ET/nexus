import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Archive, Users, Calendar, CheckCircle2, Circle, Map, RotateCcw } from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';
import StudentJourneyPanel from '../components/StudentJourneyPanel';
import AiActivePulseBoard from '../components/AiActivePulseBoard';
import LeadQueueSidebarFilters from '../components/LeadQueueSidebarFilters';
import QueuePaginationControls from '../components/QueuePaginationControls';
import HeadlessScrollArea, {
  type HeadlessScrollAreaHandle,
} from '../components/HeadlessScrollArea';
import { useConfirmation } from '../context/ConfirmationContext';
import {
  AI_ACTIVE_PAGE_SIZE_KEY,
  buildLeadQueueQueryParams,
  DEFAULT_CONTACT_STATUS,
  DEFAULT_INTERACTION_DAYS,
  formatViewingRecordsLabel,
  interactionDaysEmptyLabel,
  persistLeadQueuePageSize,
  readLeadQueuePageSize,
  type ContactStatusFilter,
  type InteractionDaysFilter,
  type LeadQueuePageSize,
} from '../utils/leadQueueFilters';

interface ConsultationDateOption {
  date: string;
  label: string;
}

interface ConsultationTimeOption {
  time: string;
  label: string;
}

interface ChatMessage {
  id?: number | string;
  sender: 'candidate' | 'student' | 'advisor' | 'system' | string;
  senderName?: string;
  text: string;
  is_read?: boolean;
  created_at?: string;
  media_url?: string | null;
  file_name?: string | null;
}

interface ActiveLead {
  id: number;
  name: string;
  email: string;
  phone?: string;
  phone_number?: string;
  status: string;
  updated_at?: string;
  latest_interaction_time?: string;
  total_messages_received: number;
  unread_count: number;
  has_ai_messages?: boolean;
  has_messages?: boolean;
  messages: ChatMessage[];
  intake_step?: string;
  intake_step_label?: string;
  intake_complete?: boolean;
  current_location?: string | null;
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  target_degree?: string | null;
  target_major?: string | null;
  study_interest_complete?: boolean;
  english_test_scores?: string | null;
  gre_score?: string | null;
  gmat_score?: string | null;
  test_scores?: string | null;
  wants_consultation_call?: boolean | null;
  consultation_scheduled_at?: string | null;
  calendar_booking_id?: string | null;
  consultation_session_date?: string | null;
  consultation_session_time?: string | null;
  assigned_counsellor_name?: string | null;
  appointment_status?: string | null;
  available_consultation_dates?: ConsultationDateOption[];
  available_consultation_times?: ConsultationTimeOption[];
  selected_consultation_date?: string | null;
  status_definition_id?: number | null;
  status_stage_name?: string | null;
  status_category?: string | null;
  status_description?: string | null;
}

const PIPELINE_STATUS_MARKETING_DISABLED = 'Lead: Marketing Disabled';
const PIPELINE_STATUS_PROSPECT_CANCELLED = 'Prospect: Cancelled & Closed';
const OUTREACH_BLOCKED_STATUS_IDS = new Set([11, 44]);
const OUTREACH_BLOCKED_STATUS_NAMES = new Set([
  PIPELINE_STATUS_MARKETING_DISABLED,
  PIPELINE_STATUS_PROSPECT_CANCELLED,
]);

const isOutreachBlocked = (
  lead: Pick<ActiveLead, 'status_stage_name' | 'status_definition_id'>
): boolean => {
  if (lead.status_definition_id != null && OUTREACH_BLOCKED_STATUS_IDS.has(lead.status_definition_id)) {
    return true;
  }
  if (lead.status_stage_name && OUTREACH_BLOCKED_STATUS_NAMES.has(lead.status_stage_name)) {
    return true;
  }
  return false;
};

const OUTREACH_BLOCKED_TOOLTIP =
  'This candidate has opted out of communication. Outreach and marketing are disabled.';

const normalizeStatus = (status?: string): string => {
  const raw = (status || '').toUpperCase().replace(/-/g, '_');
  if (raw.startsWith('LEADSTAGE.')) return raw.split('.').pop() || raw;
  return raw;
};

const isAiActive = (status?: string): boolean => normalizeStatus(status) === 'AI_ACTIVE';

const getLeadPhone = (lead: ActiveLead): string => lead.phone || lead.phone_number || '';

const getStartOutreachDisabledReason = (lead: ActiveLead): string | null => {
  if (isOutreachBlocked(lead)) return OUTREACH_BLOCKED_TOOLTIP;
  if (!getLeadPhone(lead)) return 'Add a phone number to start WhatsApp outreach';
  return null;
};

const leadHasAiMessages = (lead: ActiveLead): boolean => {
  if (typeof lead.has_ai_messages === 'boolean') return lead.has_ai_messages;
  return lead.messages.some(msg => msg.sender === 'advisor' || msg.sender === 'system');
};

const normalizeMessage = (msg: Record<string, unknown>): ChatMessage => {
  const senderRaw = String(msg.sender || 'candidate');
  const sender = senderRaw === 'student' ? 'candidate' : senderRaw;
  return {
    id: msg.id as number | string | undefined,
    sender,
    senderName: String(msg.senderName || ''),
    text: String(msg.text || msg.body || ''),
    created_at: msg.created_at as string | undefined,
    media_url: (msg.media_url as string | null | undefined) ?? null,
    file_name: (msg.file_name as string | null | undefined) ?? null,
    is_read: Boolean(msg.is_read),
  };
};

const INTAKE_STEPS = [
  { key: 'FULL_NAME', label: 'Full name' },
  { key: 'TARGET_DEGREE', label: 'Program' },
  { key: 'TARGET_MAJOR', label: 'Major' },
  { key: 'TARGET_COUNTRY', label: 'Country' },
  { key: 'CALL_CONSENT', label: 'Advisor call' },
  { key: 'PICK_DATE', label: 'Pick date' },
  { key: 'PICK_TIME', label: 'Pick time' },
  { key: 'COMPLETE', label: 'Complete' },
] as const;

const formatConsultationDateTime = (iso?: string | null): string => {
  if (!iso) return '';
  try {
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return iso;
    return parsed.toLocaleString([], {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

const getIntakeStepIndex = (step?: string): number => {
  const normalized = (step || 'WELCOME').toUpperCase();
  if (normalized === 'WELCOME') return -1;
  if (normalized === 'CURRENT_LOCATION') {
    return INTAKE_STEPS.findIndex(item => item.key === 'TARGET_DEGREE');
  }
  if (normalized === 'ENGLISH_SCORES' || normalized === 'GRE_SCORE' || normalized === 'GMAT_SCORE') {
    return INTAKE_STEPS.findIndex(item => item.key === 'CALL_CONSENT');
  }
  return INTAKE_STEPS.findIndex(item => item.key === normalized);
};

const mapLeadFromApi = (lead: Record<string, unknown>): ActiveLead => {
  const rawMessages = (lead.messages || lead.chat_history || lead.history || []) as Record<
    string,
    unknown
  >[];

  return {
    id: lead.id as number,
    name: (lead.name || lead.full_name || 'Unknown Lead') as string,
    email: (lead.email || '') as string,
    phone: lead.phone as string | undefined,
    phone_number: lead.phone_number as string | undefined,
    status: (lead.status || lead.stage || 'AI_ACTIVE') as string,
    updated_at: lead.updated_at as string | undefined,
    latest_interaction_time: lead.latest_interaction_time as string | undefined,
    total_messages_received: Number(lead.total_messages_received ?? 0),
    unread_count: Number(lead.unread_count ?? 0),
    has_ai_messages:
      typeof lead.has_ai_messages === 'boolean'
        ? Boolean(lead.has_ai_messages)
        : rawMessages.some(
            msg => msg.sender === 'advisor' || msg.sender === 'system'
          ),
    has_messages:
      typeof lead.has_messages === 'boolean'
        ? Boolean(lead.has_messages)
        : rawMessages.length > 0 ||
          Boolean(lead.has_ai_messages) ||
          Number(lead.total_messages_received ?? 0) > 0,
    messages: rawMessages.map(normalizeMessage),
    intake_step: lead.intake_step as string | undefined,
    intake_step_label: lead.intake_step_label as string | undefined,
    intake_complete: Boolean(lead.intake_complete),
    current_location: (lead.current_location as string | null | undefined) ?? null,
    preferred_country: (lead.preferred_country as string | null | undefined) ?? null,
    preferred_course: (lead.preferred_course as string | null | undefined) ?? null,
    target_program: (lead.target_program as string | null | undefined) ?? null,
    target_degree: (lead.target_degree as string | null | undefined) ?? null,
    target_major: (lead.target_major as string | null | undefined) ?? null,
    study_interest_complete: Boolean(lead.study_interest_complete),
    english_test_scores: (lead.english_test_scores as string | null | undefined) ?? null,
    gre_score: (lead.gre_score as string | null | undefined) ?? null,
    gmat_score: (lead.gmat_score as string | null | undefined) ?? null,
    test_scores: (lead.test_scores as string | null | undefined) ?? null,
    wants_consultation_call: (lead.wants_consultation_call as boolean | null | undefined) ?? null,
    consultation_scheduled_at: (lead.consultation_scheduled_at as string | null | undefined) ?? null,
    calendar_booking_id: (lead.calendar_booking_id as string | null | undefined) ?? null,
    consultation_session_date: (lead.consultation_session_date as string | null | undefined) ?? null,
    consultation_session_time: (lead.consultation_session_time as string | null | undefined) ?? null,
    assigned_counsellor_name: (lead.assigned_counsellor_name as string | null | undefined) ?? null,
    appointment_status: (lead.appointment_status as string | null | undefined) ?? null,
    available_consultation_dates: (lead.available_consultation_dates as ConsultationDateOption[] | undefined) ?? [],
    available_consultation_times: (lead.available_consultation_times as ConsultationTimeOption[] | undefined) ?? [],
    selected_consultation_date: (lead.selected_consultation_date as string | null | undefined) ?? null,
    status_definition_id: (lead.status_definition_id as number | null | undefined) ?? null,
    status_stage_name: (lead.status_stage_name as string | null | undefined) ?? null,
    status_category: (lead.status_category as string | null | undefined) ?? null,
    status_description: (lead.status_description as string | null | undefined) ?? null,
  };
};

const getUnreadCount = (lead: ActiveLead): number => {
  if (typeof lead.unread_count === 'number' && !Number.isNaN(lead.unread_count)) {
    return lead.unread_count;
  }
  return lead.messages.filter(
    msg => (msg.sender === 'candidate' || msg.sender === 'student') && !msg.is_read
  ).length;
};

const getLeadActivityTime = (lead: ActiveLead): number => {
  const latestFromMessages = lead.messages.reduce((max, msg) => {
    const time = new Date(msg.created_at || 0).getTime();
    return time > max ? time : max;
  }, 0);

  if (latestFromMessages > 0) return latestFromMessages;
  if (lead.latest_interaction_time) return new Date(lead.latest_interaction_time).getTime();
  return new Date(lead.updated_at || 0).getTime();
};

const sortActiveLeads = (a: ActiveLead, b: ActiveLead): number => {
  const aContacted = Number(
    Boolean(a.has_messages ?? a.has_ai_messages ?? (a.messages?.length ?? 0) > 0)
  );
  const bContacted = Number(
    Boolean(b.has_messages ?? b.has_ai_messages ?? (b.messages?.length ?? 0) > 0)
  );
  if (bContacted !== aContacted) return bContacted - aContacted;

  const unreadDiff = getUnreadCount(b) - getUnreadCount(a);
  if (unreadDiff !== 0) return unreadDiff;
  return getLeadActivityTime(b) - getLeadActivityTime(a);
};

const mergeLeadSnapshot = (
  previous: ActiveLead,
  incoming: ActiveLead,
  options?: { replaceMessages?: boolean }
): ActiveLead => {
  if (previous.id !== incoming.id) {
    return incoming;
  }

  const incomingMessages = incoming.messages ?? [];
  const previousMessages = previous.messages ?? [];

  // Queue list payloads intentionally ship `messages: []`. Never treat that as a
  // wipe — only replace when the caller explicitly asks (Reset chat).
  let messages: ChatMessage[];
  if (options?.replaceMessages) {
    messages = incomingMessages;
  } else if (incomingMessages.length > 0) {
    messages =
      incomingMessages.length >= previousMessages.length ? incomingMessages : previousMessages;
  } else {
    messages = previousMessages;
  }

  const hasAiMessages = messages.some(
    msg => msg.sender === 'advisor' || msg.sender === 'system'
  );

  // Intake/session fields are always present on queue + detail payloads.
  // Prefer incoming (including null) so Reset chat / cancelled bookings clear the UI.
  return {
    ...previous,
    ...incoming,
    name: incoming.name || previous.name,
    messages,
    has_ai_messages: options?.replaceMessages
      ? Boolean(incoming.has_ai_messages) || hasAiMessages
      : hasAiMessages || Boolean(incoming.has_ai_messages) || Boolean(previous.has_ai_messages),
    has_messages:
      Boolean(incoming.has_messages) ||
      Boolean(previous.has_messages) ||
      Boolean(incoming.has_ai_messages) ||
      Boolean(previous.has_ai_messages) ||
      messages.length > 0,
    total_messages_received:
      options?.replaceMessages && messages.length === 0
        ? 0
        : incoming.total_messages_received ?? previous.total_messages_received,
    unread_count:
      options?.replaceMessages && messages.length === 0
        ? 0
        : incoming.unread_count ?? previous.unread_count,
    current_location: incoming.current_location ?? null,
    preferred_country: incoming.preferred_country ?? null,
    preferred_course: incoming.preferred_course ?? null,
    target_program: incoming.target_program ?? null,
    target_degree: incoming.target_degree ?? null,
    target_major: incoming.target_major ?? null,
    study_interest_complete: Boolean(incoming.study_interest_complete),
    english_test_scores: incoming.english_test_scores ?? null,
    gre_score: incoming.gre_score ?? null,
    gmat_score: incoming.gmat_score ?? null,
    test_scores: incoming.test_scores ?? null,
    wants_consultation_call: incoming.wants_consultation_call ?? null,
    consultation_scheduled_at: incoming.consultation_scheduled_at ?? null,
    calendar_booking_id: incoming.calendar_booking_id ?? null,
    consultation_session_date: incoming.consultation_session_date ?? null,
    consultation_session_time: incoming.consultation_session_time ?? null,
    assigned_counsellor_name: incoming.assigned_counsellor_name ?? null,
    appointment_status: incoming.appointment_status ?? null,
    status_definition_id: incoming.status_definition_id,
    status_stage_name: incoming.status_stage_name,
    status_category: incoming.status_category,
    status_description: incoming.status_description,
    intake_step: incoming.intake_step,
    intake_step_label: incoming.intake_step_label,
    intake_complete: Boolean(incoming.intake_complete),
    available_consultation_dates: incoming.available_consultation_dates ?? [],
    available_consultation_times: incoming.available_consultation_times ?? [],
    selected_consultation_date: incoming.selected_consultation_date ?? null,
  };
};

const formatTime = (dateStr?: string): string => {
  if (!dateStr) return '';
  try {
    const parsed = new Date(dateStr);
    if (Number.isNaN(parsed.getTime())) return '';
    return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const REPLY_EXAMPLE_HINT =
  /\n*\s*Example:\s*reply\s*\*?1\*?\s*for the first option\.?\s*$/i;

const formatCandidateMessageText = (text: string, lead: ActiveLead | null): string => {
  const trimmed = (text || '').trim();
  const dateMatch = trimmed.match(/^date:(\d{4}-\d{2}-\d{2})$/i);
  if (dateMatch) {
    const parsed = new Date(`${dateMatch[1]}T12:00:00`);
    if (!Number.isNaN(parsed.getTime())) {
      return `Selected ${parsed.toLocaleDateString([], {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })}`;
    }
  }

  const timeMatch = trimmed.match(/^time:(\d+)$/i);
  if (timeMatch) {
    if (lead?.consultation_scheduled_at) {
      const formatted = formatConsultationDateTime(lead.consultation_scheduled_at);
      const timePart = formatted.split(',').slice(-1)[0]?.trim();
      if (timePart) return `Selected ${timePart}`;
    }
    return 'Selected consultation time';
  }

  return text;
};

const formatAdvisorMessageText = (text: string): string =>
  (text || '').replace(REPLY_EXAMPLE_HINT, '').trimEnd();

const getDateGroupLabel = (dateStr?: string): string => {
  if (!dateStr) return 'Earlier';
  try {
    const parsed = new Date(dateStr);
    if (Number.isNaN(parsed.getTime())) return 'Earlier';

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const target = new Date(parsed);
    target.setHours(0, 0, 0, 0);
    const diffDays = Math.round((today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays > 1 && diffDays < 7) {
      return target.toLocaleDateString('en-US', { weekday: 'long' });
    }
    return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Earlier';
  }
};

const TRANSITION_OPTIONS = [
  { key: 'handoff', label: 'HANDOFF', icon: Users },
  { key: 'archive', label: 'ARCHIVE', icon: Archive },
] as const;

const getTargetProgramValue = (
  lead: Pick<ActiveLead, 'target_degree' | 'target_program'>
): string => (lead.target_degree || lead.target_program || '').trim();

const getTargetMajorValue = (
  lead: Pick<ActiveLead, 'target_major' | 'preferred_course' | 'target_degree' | 'target_program'>
): string => {
  const major = (lead.target_major || '').trim();
  if (major) return major;
  const program = getTargetProgramValue(lead);
  const preferredCourse = (lead.preferred_course || '').trim();
  if (program && preferredCourse === program) return '';
  return preferredCourse;
};

function IntakeProfilePanel({ lead }: { lead: ActiveLead }) {
  const currentStepIndex = getIntakeStepIndex(lead.intake_step);
  const targetProgram = getTargetProgramValue(lead);
  const targetMajor = getTargetMajorValue(lead);
  const studyPrefilled = Boolean(
    lead.study_interest_complete ||
      (lead.preferred_country && (targetProgram || targetMajor))
  );
  const showCalendar =
    lead.intake_step === 'PICK_DATE' && (lead.available_consultation_dates?.length ?? 0) > 0;
  const showTimes =
    lead.intake_step === 'PICK_TIME' && (lead.available_consultation_times?.length ?? 0) > 0;
  const hasProfileData =
    lead.preferred_country ||
    targetProgram ||
    targetMajor ||
    lead.english_test_scores ||
    lead.gre_score ||
    lead.gmat_score ||
    lead.consultation_scheduled_at ||
    lead.consultation_session_date ||
    lead.assigned_counsellor_name;

  if (lead.intake_complete && !hasProfileData && !lead.status_stage_name) return null;

  const pipelineStatusLabel = (lead.status_stage_name || '').trim() || 'Status pending';
  const pipelineStatusDescription = (lead.status_description || '').trim();
  const outreachBlocked = isOutreachBlocked(lead);

  return (
    <div style={styles.intakeProfilePanel}>
      <div style={styles.intakeProfileHeader}>
        <div style={styles.intakeProfileHeaderMainRow}>
          <div>
            <span style={styles.intakeProfileTitle}>Admissions intake</span>
            <span style={styles.intakeStepBadge}>
              {lead.intake_complete ? 'Complete' : lead.intake_step_label || 'In progress'}
            </span>
          </div>
          <div style={styles.intakePipelineStatusBlock}>
            <span
              style={{
                ...styles.intakePipelineStatus,
                color: outreachBlocked ? '#b91c1c' : '#0f172a',
              }}
            >
              {pipelineStatusLabel}
            </span>
            {pipelineStatusDescription ? (
              <span
                style={{
                  ...styles.intakePipelineStatusDescription,
                  color: outreachBlocked ? '#dc2626' : '#64748b',
                }}
              >
                {pipelineStatusDescription}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {!lead.intake_complete && (
        <div style={styles.intakeProgressRow}>
          {INTAKE_STEPS.map((step, index) => {
            const isDone =
              currentStepIndex > index ||
              (step.key === 'TARGET_COUNTRY' && studyPrefilled);
            const isCurrent =
              currentStepIndex === index && !(step.key === 'TARGET_COUNTRY' && studyPrefilled);
            return (
              <div
                key={step.key}
                title={step.label}
                style={{
                  ...styles.intakeProgressChip,
                  backgroundColor: isCurrent ? '#ecfdf5' : isDone ? '#f0fdf4' : '#f8fafc',
                  borderColor: isCurrent ? '#059669' : isDone ? '#86efac' : '#e2e8f0',
                  color: isCurrent ? '#047857' : isDone ? '#15803d' : '#64748b',
                }}
              >
                {isDone ? <CheckCircle2 size={11} /> : <Circle size={11} />}
                <span>{step.label}</span>
              </div>
            );
          })}
        </div>
      )}

      <div style={styles.intakeFieldGrid}>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Full name</span>
          <span style={styles.intakeFieldValue}>{lead.name || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Target program</span>
          <span style={styles.intakeFieldValue}>{targetProgram || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>TARGET MAJOR</span>
          <span style={styles.intakeFieldValue}>{targetMajor || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>TARGET COUNTRY</span>
          <span style={styles.intakeFieldValue}>{lead.preferred_country || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Advisor call</span>
          <span style={styles.intakeFieldValue}>
            {lead.wants_consultation_call === true
              ? 'Yes'
              : lead.wants_consultation_call === false
                ? 'No'
                : '—'}
          </span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Session date</span>
          <span style={styles.intakeFieldValue}>{lead.consultation_session_date || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Session time</span>
          <span style={styles.intakeFieldValue}>{lead.consultation_session_time || '—'}</span>
        </div>
        <div style={styles.intakeFieldCell}>
          <span style={styles.intakeFieldLabel}>Assigned counsellor</span>
          <span style={styles.intakeFieldValue}>
            {lead.assigned_counsellor_name?.trim() || 'Not assigned'}
          </span>
        </div>
      </div>

      {showCalendar && (
        <div style={styles.consultationCalendarSection}>
          <div style={styles.consultationCalendarTitle}>
            <Calendar size={14} />
            Candidate is choosing a consultation date (WhatsApp numbered list)
          </div>
          <div style={styles.consultationDateGrid}>
            {lead.available_consultation_dates?.map((slot, index) => (
              <div key={slot.date} style={styles.consultationDateCard}>
                <span style={styles.consultationDateNumber}>{index + 1}</span>
                <span style={styles.consultationDateLabel}>{slot.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {showTimes && (
        <div style={styles.consultationCalendarSection}>
          <div style={styles.consultationCalendarTitle}>
            <Calendar size={14} />
            Candidate is choosing a time
            {lead.selected_consultation_date
              ? ` on ${formatConsultationDateTime(`${lead.selected_consultation_date}T12:00:00`).split(',')[0]}`
              : ''}
          </div>
          <div style={styles.consultationTimeGrid}>
            {lead.available_consultation_times?.map((slot, index) => (
              <div key={slot.time} style={styles.consultationTimeCard}>
                <span style={styles.consultationDateNumber}>{index + 1}</span>
                <span>{slot.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AiActiveView() {
  const openConfirm = useConfirmation();
  const [queue, setQueue] = useState<ActiveLead[]>([]);
  const [selectedLead, setSelectedLead] = useState<ActiveLead | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [interactionDays, setInteractionDays] = useState<InteractionDaysFilter>(DEFAULT_INTERACTION_DAYS);
  const [contactStatus, setContactStatus] = useState<ContactStatusFilter>(DEFAULT_CONTACT_STATUS);
  const [pageSize, setPageSize] = useState<LeadQueuePageSize>(() =>
    readLeadQueuePageSize(AI_ACTIVE_PAGE_SIZE_KEY)
  );
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMorePages, setHasMorePages] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatingRowId, setUpdatingRowId] = useState<number | null>(null);
  const [startingOutreachId, setStartingOutreachId] = useState<number | null>(null);
  const [resettingConversationId, setResettingConversationId] = useState<number | null>(null);
  const [outreachSuccess, setOutreachSuccess] = useState<string | null>(null);
  const [whatsappConfig, setWhatsappConfig] = useState<{
    business_phone_number?: string | null;
    outreach_template?: string | null;
    ready?: boolean;
  } | null>(null);
  const [journeyModal, setJourneyModal] = useState<{
    studentId: number;
    studentName: string;
  } | null>(null);

  const chatContainerRef = useRef<HeadlessScrollAreaHandle | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const conversationAbortRef = useRef<AbortController | null>(null);
  const selectedLeadIdRef = useRef<number | null>(null);
  const queuePollInFlightRef = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    setPage(1);
    // Drop the previous page immediately so a stale Contact status list
    // cannot remain visible while the next fetch is in flight.
    setQueue([]);
    setTotalCount(0);
  }, [pageSize, interactionDays, contactStatus, debouncedSearch]);

  useEffect(() => {
    selectedLeadIdRef.current = selectedLead?.id ?? null;
  }, [selectedLead?.id]);

  const handlePageSizeChange = useCallback((next: LeadQueuePageSize) => {
    persistLeadQueuePageSize(AI_ACTIVE_PAGE_SIZE_KEY, next);
    setPageSize(next);
  }, []);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize) || 1);
  const rangeStart = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, totalCount);

  const applyLeadDetail = useCallback(
    (mapped: ActiveLead, options?: { replaceMessages?: boolean }) => {
      if (selectedLeadIdRef.current !== mapped.id) return;

      setSelectedLead(prev =>
        prev?.id === mapped.id ? mergeLeadSnapshot(prev, mapped, options) : prev
      );
      setQueue(prev =>
        prev.map(item =>
          item.id === mapped.id ? mergeLeadSnapshot(item, mapped, options) : item
        )
      );
    },
    []
  );

  const fetchLeadDetail = useCallback(async (leadId: number, signal?: AbortSignal) => {
    const data = await apiFetch(`leads/${leadId}`, { signal });
    const mapped = mapLeadFromApi(data as Record<string, unknown>);
    applyLeadDetail(mapped);
    return mapped;
  }, [applyLeadDetail]);

  const fetchActiveQueue = useCallback(async (signal?: AbortSignal) => {
    try {
      const query = new URLSearchParams(
        buildLeadQueueQueryParams(interactionDays, debouncedSearch, contactStatus)
      );
      const safePage = Math.max(1, page);
      const offset = (safePage - 1) * pageSize;
      query.set('limit', String(pageSize));
      query.set('offset', String(offset));
      const data = await apiFetch(`leads/active?${query.toString()}`, { signal });
      if (signal?.aborted) return;

      let rows: unknown[] = [];
      let nextTotal = 0;
      let nextHasMore = false;
      if (Array.isArray(data)) {
        rows = data;
        nextTotal = data.length;
        nextHasMore = false;
      } else if (data && typeof data === 'object') {
        const payload = data as {
          items?: unknown[];
          total_count?: number;
          has_more?: boolean;
        };
        rows = Array.isArray(payload.items) ? payload.items : [];
        nextTotal = Number(payload.total_count ?? rows.length) || 0;
        nextHasMore = Boolean(
          payload.has_more ?? offset + rows.length < nextTotal
        );
      }

      const activeOnly = rows
        .map(item => mapLeadFromApi(item as Record<string, unknown>))
        .filter(lead => isAiActive(lead.status))
        .sort(sortActiveLeads);

      if (signal?.aborted) return;

      setQueue(activeOnly);
      setTotalCount(nextTotal);
      setHasMorePages(nextHasMore);
      setLoadError(null);

      setSelectedLead(prev => {
        // Keep an explicit selection in sync; do not auto-select on first load
        // so the right panel can show the living pulse overview.
        if (!prev) return null;

        const updatedLead = activeOnly.find(l => l.id === prev.id);
        if (!updatedLead) return null;
        return mergeLeadSnapshot(prev, updatedLead);
      });
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Failed to fetch AI active queue:', error);
        setLoadError(error.message || 'Failed to load AI active leads.');
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, [interactionDays, contactStatus, debouncedSearch, page, pageSize]);

  const groupedMessages = useMemo(() => {
    if (!selectedLead) return {};

    const groups: Record<string, ChatMessage[]> = {};
    selectedLead.messages.forEach(msg => {
      const label = getDateGroupLabel(msg.created_at);
      if (!groups[label]) groups[label] = [];
      groups[label].push(msg);
    });
    Object.values(groups).forEach(messages =>
      messages.sort(
        (a, b) =>
          new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime()
      )
    );
    return groups;
  }, [selectedLead]);

  const hasNoMessages = useMemo(() => Object.keys(groupedMessages).length === 0, [groupedMessages]);

  const emptyQueueMessage = useMemo(() => {
    if (debouncedSearch) return 'No matching candidates found.';
    if (interactionDays === 0) return 'No leads are currently in AI Active status.';
    return `No candidates with activity in ${interactionDaysEmptyLabel(interactionDays)}.`;
  }, [debouncedSearch, interactionDays]);

  useEffect(() => {
    void apiFetch('settings/whatsapp-outreach')
      .then(data =>
        setWhatsappConfig(
          data as {
            business_phone_number?: string | null;
            outreach_template?: string | null;
            ready?: boolean;
          }
        )
      )
      .catch(() => setWhatsappConfig(null));
  }, []);

  useEffect(() => {
    let isActive = true;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    queuePollInFlightRef.current = false;
    setIsLoading(true);

    async function pollQueue() {
      if (!isActive) return;

      // Always abort any previous in-flight queue call for this effect generation.
      if (abortControllerRef.current !== controller) return;

      queuePollInFlightRef.current = true;
      try {
        await fetchActiveQueue(controller.signal);
      } finally {
        queuePollInFlightRef.current = false;
        if (isActive && abortControllerRef.current === controller) {
          pollingTimerRef.current = setTimeout(pollQueue, 10000);
        }
      }
    }

    void pollQueue();
    return () => {
      isActive = false;
      queuePollInFlightRef.current = false;
      if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);
      controller.abort();
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    };
  }, [fetchActiveQueue]);

  useEffect(() => {
    if (!selectedLead?.id) return;

    conversationAbortRef.current?.abort();
    const controller = new AbortController();
    conversationAbortRef.current = controller;

    const refreshSelectedConversation = async () => {
      if (!hasValidSession()) return;
      try {
        await fetchLeadDetail(selectedLead.id, controller.signal);
      } catch (error: unknown) {
        if (error instanceof Error && error.name !== 'AbortError') {
          console.error('Failed to refresh AI active conversation:', error);
        }
      }
    };

    void refreshSelectedConversation();
    const interval = setInterval(refreshSelectedConversation, 8000);

    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [selectedLead?.id, selectedLead?.messages.length, selectedLead?.updated_at, fetchLeadDetail]);

  useEffect(() => {
    const container = chatContainerRef.current?.getViewport();
    if (!container || !selectedLead) return;
    container.scrollTop = container.scrollHeight;
  }, [selectedLead?.id, selectedLead?.messages.length]);

  const handleSelectLead = async (lead: ActiveLead) => {
    conversationAbortRef.current?.abort();
    selectedLeadIdRef.current = lead.id;
    setSelectedLead(lead);

    if (getUnreadCount(lead) === 0) return;

    try {
      await apiFetch(`leads/${lead.id}/mark-read`, { method: 'POST' });

      const markMessagesRead = (messages: ChatMessage[]) =>
        messages.map(message =>
          message.sender === 'candidate' || message.sender === 'student'
            ? { ...message, is_read: true }
            : message
        );

      setQueue(prev =>
        prev.map(item =>
          item.id === lead.id
            ? { ...item, unread_count: 0, messages: markMessagesRead(item.messages) }
            : item
        )
      );

      setSelectedLead(prev =>
        prev?.id === lead.id
          ? { ...prev, unread_count: 0, messages: markMessagesRead(prev.messages) }
          : prev
      );
    } catch (error) {
      console.error('Failed to mark AI active messages as read:', error);
    }
  };

  const handleStartAiConversation = async (leadOverride?: ActiveLead) => {
    const target = leadOverride ?? selectedLead;
    if (!target) return;

    const disabledReason = getStartOutreachDisabledReason(target);
    if (disabledReason) {
      alert(disabledReason);
      return;
    }

    if (leadHasAiMessages(target)) {
      return;
    }

    setStartingOutreachId(target.id);
    setOutreachSuccess(null);
    if (leadOverride) setSelectedLead(target);

    try {
      await apiFetch(`leads/${target.id}/ai-outreach`, {
        method: 'POST',
      });

      const detail = await apiFetch(`leads/${target.id}`);
      const mapped = mapLeadFromApi(detail as Record<string, unknown>);
      applyLeadDetail(mapped);
      setOutreachSuccess(
        `WhatsApp message sent from ${whatsappConfig?.business_phone_number || 'business line'} to ${getLeadPhone(mapped) || 'student'}.`
      );
    } catch (error) {
      console.error('Failed to start AI conversation:', error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Could not start the AI WhatsApp conversation. Check Meta WhatsApp settings and try again.';
      alert(message);
    } finally {
      setStartingOutreachId(null);
    }
  };

  const handleResetWhatsappConversation = async () => {
    if (!selectedLead) return;

    const confirmed = await openConfirm({
      title: 'Reset WhatsApp conversation?',
      message:
        `This will permanently delete all WhatsApp messages with ${selectedLead.name}, ` +
        `remove any consultation / counselling bookings linked to this lead, ` +
        `and reset Lead Status to New. This cannot be undone. Continue?`,
      confirmLabel: 'Reset chat',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;

    setResettingConversationId(selectedLead.id);
    setOutreachSuccess(null);

    try {
      const result = (await apiFetch(`leads/${selectedLead.id}/reset-whatsapp`, {
        method: 'POST',
      })) as {
        lead?: Record<string, unknown>;
        deleted_messages?: number;
        deleted_bookings?: number;
      };

      const mapped = result.lead
        ? mapLeadFromApi(result.lead)
        : mapLeadFromApi((await apiFetch(`leads/${selectedLead.id}`)) as Record<string, unknown>);

      // Force-clear local chat + intake profile so merge cannot retain stale UI.
      const cleared: ActiveLead = {
        ...mapped,
        messages: [],
        has_ai_messages: false,
        total_messages_received: 0,
        unread_count: 0,
        current_location: null,
        preferred_country: null,
        preferred_course: null,
        target_program: null,
        target_degree: null,
        target_major: null,
        study_interest_complete: false,
        english_test_scores: null,
        gre_score: null,
        gmat_score: null,
        test_scores: null,
        wants_consultation_call: null,
        consultation_scheduled_at: null,
        calendar_booking_id: null,
        consultation_session_date: null,
        consultation_session_time: null,
        assigned_counsellor_name: null,
        appointment_status: null,
        available_consultation_dates: [],
        available_consultation_times: [],
        selected_consultation_date: null,
        intake_complete: false,
      };
      applyLeadDetail(cleared, { replaceMessages: true });
      const messagePart =
        typeof result.deleted_messages === 'number'
          ? `${result.deleted_messages} message${result.deleted_messages === 1 ? '' : 's'}`
          : 'messages';
      const bookingPart =
        typeof result.deleted_bookings === 'number'
          ? `${result.deleted_bookings} booking${result.deleted_bookings === 1 ? '' : 's'}`
          : 'bookings';
      setOutreachSuccess(
        `WhatsApp conversation with ${cleared.name} was reset (${messagePart} and ${bookingPart} removed). ` +
          'Lead Status is New — you can start a fresh AI conversation.'
      );
    } catch (error) {
      console.error('Failed to reset WhatsApp conversation:', error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Could not reset the WhatsApp conversation. Please try again.';
      alert(message);
    } finally {
      setResettingConversationId(null);
    }
  };

  const handleTransitionStatus = async (
    event: React.MouseEvent,
    leadId: number,
    targetStatus: 'handoff' | 'archive'
  ) => {
    event.stopPropagation();
    setUpdatingRowId(leadId);

    try {
      await apiFetch(`leads/${leadId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: targetStatus }),
      });

      setQueue(prev => prev.filter(l => l.id !== leadId));
      setSelectedLead(prev => (prev?.id === leadId ? null : prev));
    } catch (error) {
      console.error('AI active status update error:', error);
    } finally {
      setUpdatingRowId(null);
    }
  };

  const renderMessageContent = (msg: ChatMessage) => {
    const targetUrl =
      msg.media_url || (typeof msg.text === 'string' && msg.text.startsWith('data:') ? msg.text : null);

    if (targetUrl) {
      const isImage =
        targetUrl.includes('.png') ||
        targetUrl.includes('.jpg') ||
        targetUrl.includes('.jpeg') ||
        targetUrl.startsWith('data:image/');

      if (isImage) {
        return (
          <img
            src={targetUrl}
            alt={msg.file_name || 'Attachment'}
            style={styles.inlineImagePreview}
          />
        );
      }

      return (
        <a
          href={targetUrl}
          target="_blank"
          rel="noreferrer"
          style={styles.downloadFileActionLink}
        >
          {msg.file_name || 'View attachment'}
        </a>
      );
    }

    if (!msg.text) return null;

    const displayText =
      msg.sender === 'candidate' || msg.sender === 'student'
        ? formatCandidateMessageText(msg.text, selectedLead)
        : formatAdvisorMessageText(msg.text);

    return <p style={styles.bubbleTextString}>{displayText}</p>;
  };

  return (
    <>
    <div style={styles.pageShell}>
      {whatsappConfig?.business_phone_number ? (
        <div style={styles.whatsappLineBanner}>
          <span>
            WhatsApp business line: <strong>{whatsappConfig.business_phone_number}</strong>
            {whatsappConfig.outreach_template
              ? ` · template: ${whatsappConfig.outreach_template}`
              : ''}
          </span>
          {!whatsappConfig.ready ? (
            <span style={styles.whatsappLineWarning}>
              Meta WhatsApp is not fully configured — check backend .env and Meta console.
            </span>
          ) : null}
        </div>
      ) : null}

      <div style={styles.workspaceContainer}>
      <style>{`
        html, body, #root { overflow: hidden !important; }
        .ai-status-btn {
          display: flex;
          align-items: center;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          padding: 4px;
          border-radius: 4px;
          width: 26px;
          height: 26px;
          overflow: hidden;
          cursor: pointer;
          transition: width 0.3s ease;
          color: #334155;
        }
        .ai-status-btn:hover { width: 96px; }
        .ai-status-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .ai-status-btn-label {
          display: none;
          margin-left: 8px;
          font-size: 8px;
          font-weight: 800;
          text-transform: uppercase;
          white-space: nowrap;
        }
        .ai-status-btn:hover .ai-status-btn-label { display: block; }
      `}</style>

      <div style={styles.leftSidebarPanel}>
        <div style={styles.sidebarHeader}>
          <div style={styles.sidebarHeaderText}>
            <h2 style={styles.sidebarTitle}>AI Active</h2>
            <p
              style={styles.viewingRecordsLabel}
              title={
                totalCount > 0
                  ? formatViewingRecordsLabel(rangeStart, rangeEnd, totalCount)
                  : 'No candidates in the filtered queue'
              }
            >
              {formatViewingRecordsLabel(rangeStart, rangeEnd, totalCount)}
            </p>
          </div>
          <span style={styles.activeCounterBadge}>
            {totalCount > 0 ? `${rangeStart}–${rangeEnd}/${totalCount}` : 0}
          </span>
        </div>

        {!isLoading && !loadError && (totalCount > 0 || queue.length > 0) ? (
          <QueuePaginationControls
            page={page}
            totalPages={totalPages}
            hasMorePages={hasMorePages}
            disabled={isLoading}
            onPageChange={setPage}
            style={styles.sidebarPaginationHeader}
          />
        ) : null}

        <LeadQueueSidebarFilters
          interactionDays={interactionDays}
          onInteractionDaysChange={setInteractionDays}
          contactStatus={contactStatus}
          onContactStatusChange={setContactStatus}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          pageSize={pageSize}
          onPageSizeChange={handlePageSizeChange}
        />

        <HeadlessScrollArea
          className="flex-1 min-h-0"
          style={styles.leadScrollList}
          viewportStyle={styles.leadScrollViewport}
        >
          {isLoading ? (
            <div style={styles.emptyListPlaceholder}>Loading AI active leads...</div>
          ) : loadError ? (
            <div style={styles.emptyListPlaceholder}>{loadError}</div>
          ) : queue.length === 0 ? (
            <div style={styles.emptyListPlaceholder}>{emptyQueueMessage}</div>
          ) : (
            <>
            {queue.map(lead => {
              const isSelected = selectedLead?.id === lead.id;
              const unreadCount = getUnreadCount(lead);

              return (
                <div
                  key={lead.id}
                  onClick={() => handleSelectLead(lead)}
                  style={{
                    ...styles.leadInteractionCard,
                    backgroundColor: isSelected ? '#ecfdf5' : '#ffffff',
                    borderColor: isSelected ? '#059669' : '#e2e8f0',
                    cursor: 'pointer',
                  }}
                >
                  <div style={styles.cardTopRow}>
                    <div style={styles.leadCardNameRow}>
                      <h4 style={styles.leadCardName}>{lead.name}</h4>
                      {unreadCount > 0 && (
                        <span style={styles.receivedCountBadge} title="Unread candidate messages">
                          {unreadCount}
                        </span>
                      )}
                    </div>
                    <div style={styles.statusActionGroup}>
                      {TRANSITION_OPTIONS.map(({ key, label, icon: Icon }) => (
                        <button
                          key={key}
                          type="button"
                          className="ai-status-btn"
                          title={label}
                          disabled={updatingRowId === lead.id}
                          onClick={event => handleTransitionStatus(event, lead.id, key)}
                        >
                          <Icon size={14} />
                          <span className="ai-status-btn-label">{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <p style={styles.leadCardPhone} title={getLeadPhone(lead) || 'No phone'}>
                    📱 {getLeadPhone(lead) || 'No phone'}
                  </p>
                  <p style={styles.leadCardEmail} title={lead.email || 'No email'}>
                    📧 {lead.email || 'No email'}
                  </p>

                  <div style={styles.cardBottomRow}>
                    <span style={styles.aiActiveBadge}>
                      <Bot size={12} />
                      AI Active
                    </span>
                    {leadHasAiMessages(lead) ? (
                      <span style={styles.cardConversationActiveBadge} title="WhatsApp conversation in progress">
                        Conversation active
                      </span>
                    ) : (
                      <button
                        type="button"
                        style={{
                          ...styles.cardStartButton,
                          ...(getStartOutreachDisabledReason(lead)
                            ? { opacity: 0.55, cursor: 'not-allowed' }
                            : {}),
                        }}
                        disabled={
                          startingOutreachId === lead.id || Boolean(getStartOutreachDisabledReason(lead))
                        }
                        title={
                          getStartOutreachDisabledReason(lead) ||
                          'Send the standard AI welcome on WhatsApp'
                        }
                        onClick={event => {
                          event.stopPropagation();
                          void handleStartAiConversation(lead);
                        }}
                      >
                        {startingOutreachId === lead.id ? 'Sending...' : 'Start AI Conversation'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            </>
          )}
        </HeadlessScrollArea>

        {!isLoading && !loadError && (totalCount > 0 || queue.length > 0) ? (
          <QueuePaginationControls
            page={page}
            totalPages={totalPages}
            hasMorePages={hasMorePages}
            disabled={isLoading}
            onPageChange={setPage}
            style={styles.sidebarPagination}
          />
        ) : null}
      </div>

      <div style={styles.rightChatPanel}>
        {selectedLead ? (
          <div style={styles.activeChatInterface}>
            <div style={styles.chatHeaderBar}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3 style={styles.headerProfileName}>{selectedLead.name}</h3>
                <p style={styles.headerProfileMeta}>
                  📱 {getLeadPhone(selectedLead) || 'No phone'} | 📧 {selectedLead.email || 'No email'}
                </p>
                <button
                  type="button"
                  onClick={() =>
                    setJourneyModal({
                      studentId: selectedLead.id,
                      studentName: selectedLead.name,
                    })
                  }
                  style={styles.headerJourneyLink}
                  title="View student journey timeline"
                >
                  <Map size={13} />
                  View Journey
                </button>
              </div>
              <div style={styles.headerActionGroup}>
              <button
                type="button"
                onClick={() => {
                  selectedLeadIdRef.current = null;
                  setSelectedLead(null);
                }}
                style={styles.headerOverviewButton}
                title="Back to intake pulse overview"
              >
                Overview
              </button>
              {(selectedLead.messages.length > 0 || leadHasAiMessages(selectedLead)) && (
                <button
                  type="button"
                  onClick={() => void handleResetWhatsappConversation()}
                  disabled={resettingConversationId === selectedLead.id}
                  style={styles.headerResetButton}
                  title="Reset WhatsApp conversation — clear all messages and start fresh"
                >
                  <RotateCcw size={13} />
                  {resettingConversationId === selectedLead.id ? 'Resetting…' : 'Reset chat'}
                </button>
              )}
              {!leadHasAiMessages(selectedLead) ? (
                <button
                  type="button"
                  onClick={() => void handleStartAiConversation()}
                  disabled={
                    startingOutreachId === selectedLead.id ||
                    Boolean(getStartOutreachDisabledReason(selectedLead))
                  }
                  style={{
                    ...styles.headerStartButton,
                    ...(getStartOutreachDisabledReason(selectedLead)
                      ? { opacity: 0.55, cursor: 'not-allowed' }
                      : {}),
                  }}
                  title={
                    getStartOutreachDisabledReason(selectedLead) ||
                    'Send the standard AI welcome on WhatsApp'
                  }
                >
                  {startingOutreachId === selectedLead.id ? 'Sending...' : 'Start AI Conversation'}
                </button>
              ) : (
                <div style={styles.aiAgentBadge}>
                  <Bot size={14} />
                  AI Agent Active
                </div>
              )}
              </div>
            </div>

            <IntakeProfilePanel key={selectedLead.id} lead={selectedLead} />

            <HeadlessScrollArea
              ref={chatContainerRef}
              className="flex-1 min-h-0"
              style={styles.whatsappChatFeedShell}
              viewportStyle={styles.whatsappChatFeedSurface}
            >
              {hasNoMessages ? (
                <div style={styles.emptyConversationPrompt}>
                  <div style={{ fontSize: '32px', marginBottom: '8px' }}>🤖</div>
                  <h4 style={{ margin: '0 0 4px 0', color: '#334155', fontWeight: '600' }}>
                    No conversation yet
                  </h4>
                  <p style={{ margin: '0 0 16px 0', color: '#64748b', fontSize: '13px', lineHeight: '1.4' }}>
                    Start the AI Agent with a standard welcome message on WhatsApp, or wait for the
                    student to message first.
                  </p>
                  <button
                    type="button"
                    onClick={() => void handleStartAiConversation()}
                    disabled={
                      startingOutreachId === selectedLead.id ||
                      Boolean(getStartOutreachDisabledReason(selectedLead))
                    }
                    style={{
                      ...styles.startConversationButton,
                      ...(getStartOutreachDisabledReason(selectedLead)
                        ? { opacity: 0.55, cursor: 'not-allowed' }
                        : {}),
                    }}
                    title={getStartOutreachDisabledReason(selectedLead) || undefined}
                  >
                    {startingOutreachId === selectedLead.id ? 'Sending...' : 'Start AI Conversation'}
                  </button>
                </div>
              ) : (
                Object.entries(groupedMessages).map(([dateLabel, messages]) => (
                  <div key={dateLabel} style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
                    <div style={styles.timelineDividerCenter}>
                      <span style={styles.timelineBadgeBubble}>{dateLabel}</span>
                    </div>

                    {messages.map((msg, index) => {
                      if (msg.sender === 'system') {
                        return (
                          <div key={msg.id || index} style={styles.systemLogCentralRow}>
                            <span>{msg.text}</span>
                          </div>
                        );
                      }

                      const isAiAgent = msg.sender === 'advisor';
                      return (
                        <div
                          key={msg.id || index}
                          style={{
                            ...styles.messageStreamRow,
                            justifyContent: isAiAgent ? 'flex-end' : 'flex-start',
                          }}
                        >
                          <div
                            style={{
                              ...styles.messageBubbleCell,
                              backgroundColor: isAiAgent ? '#dcfce7' : '#ffffff',
                              borderRadius: isAiAgent ? '8px 8px 0 8px' : '8px 8px 8px 0',
                              boxShadow: '0 1px 1px rgba(0,0,0,0.12)',
                            }}
                          >
                            <span style={styles.senderLabel}>
                              {isAiAgent ? 'AI Agent' : selectedLead.name}
                            </span>
                            {renderMessageContent(msg)}
                            {msg.created_at && (
                              <span style={styles.bubbleTimestampLabel}>{formatTime(msg.created_at)}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))
              )}
              <div ref={chatEndRef} style={{ height: '1px', width: '100%' }} />
            </HeadlessScrollArea>

            <div style={styles.readOnlyFooter}>
              <Bot size={16} />
              <span style={{ flex: 1 }}>
                {outreachSuccess ? (
                  <span style={{ color: '#15803d' }}>{outreachSuccess}</span>
                ) : isOutreachBlocked(selectedLead) ? (
                  OUTREACH_BLOCKED_TOOLTIP
                ) : leadHasAiMessages(selectedLead)
                  ? 'AI Agent is active on WhatsApp. The student can continue the conversation there — outreach cannot be started again from this screen.'
                  : 'Click Start AI Conversation to send the standard welcome message to this student on WhatsApp.'}
              </span>
              {!leadHasAiMessages(selectedLead) ? (
                <button
                  type="button"
                  onClick={() => void handleStartAiConversation()}
                  disabled={
                    startingOutreachId === selectedLead.id ||
                    Boolean(getStartOutreachDisabledReason(selectedLead))
                  }
                  style={{
                    ...styles.footerActionButton,
                    ...(getStartOutreachDisabledReason(selectedLead)
                      ? { opacity: 0.55, cursor: 'not-allowed' }
                      : {}),
                  }}
                  title={getStartOutreachDisabledReason(selectedLead) || undefined}
                >
                  {startingOutreachId === selectedLead.id ? 'Sending...' : 'Start AI Conversation'}
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <AiActivePulseBoard
            leads={queue}
            isLoading={isLoading}
            onSelectLead={leadId => {
              const lead = queue.find(item => item.id === leadId);
              if (lead) void handleSelectLead(lead);
            }}
          />
        )}
      </div>
      </div>
    </div>
    <StudentJourneyPanel
      open={journeyModal !== null}
      studentId={journeyModal?.studentId ?? null}
      studentName={journeyModal?.studentName}
      onClose={() => setJourneyModal(null)}
    />
    </>
  );
}

const styles = {
  pageShell: {
    display: 'flex',
    flexDirection: 'column' as const,
    width: '100%',
    height: '100%',
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#f8fafc',
  },
  whatsappLineBanner: {
    flexShrink: 0,
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '8px',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 16px',
    backgroundColor: '#ecfdf5',
    borderBottom: '1px solid #a7f3d0',
    color: '#065f46',
    fontSize: '12px',
  },
  whatsappLineWarning: {
    color: '#b45309',
    fontWeight: 600,
  },
  workspaceContainer: {
    display: 'flex',
    flex: 1,
    minHeight: 0,
    width: '100%',
    position: 'relative' as const,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#f8fafc',
    overflow: 'hidden',
    boxSizing: 'border-box',
    fontFamily: 'system-ui, -apple-system, sans-serif',
  } as React.CSSProperties,
  leftSidebarPanel: {
    width: '28%',
    minWidth: '320px',
    maxWidth: '400px',
    height: '100%',
    borderRight: '1px solid #e2e8f0',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#ffffff',
    overflow: 'hidden',
    boxSizing: 'border-box',
    flexShrink: 0,
  } as React.CSSProperties,
  sidebarHeader: {
    padding: '16px 20px',
    borderBottom: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    flexShrink: 0,
    gap: '10px',
  } as React.CSSProperties,
  sidebarHeaderText: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    minWidth: 0,
    flex: 1,
  } as React.CSSProperties,
  sidebarTitle: { margin: 0, fontSize: '16px', fontWeight: '700', color: '#0f172a' } as React.CSSProperties,
  viewingRecordsLabel: {
    margin: 0,
    fontSize: '12px',
    fontWeight: 700,
    color: '#0f172a',
    lineHeight: 1.35,
  } as React.CSSProperties,
  activeCounterBadge: {
    backgroundColor: '#dcfce7',
    color: '#059669',
    padding: '2px 8px',
    borderRadius: '10px',
    fontSize: '11px',
    fontWeight: '700',
    flexShrink: 0,
  } as React.CSSProperties,
  sidebarLoadMoreButton: {
    margin: '8px 12px 16px',
    width: 'calc(100% - 24px)',
    boxSizing: 'border-box',
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid #bbf7d0',
    backgroundColor: '#f0fdf4',
    color: '#047857',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
  } as React.CSSProperties,
  sidebarPagination: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    margin: 0,
    padding: '10px 12px',
    borderTop: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
    flexShrink: 0,
  } as React.CSSProperties,
  sidebarPaginationHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    margin: 0,
    padding: '8px 12px',
    borderBottom: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
    flexShrink: 0,
  } as React.CSSProperties,
  searchHeaderSection: {
    padding: '12px',
    borderBottom: '1px solid #e2e8f0',
    flexShrink: 0,
  } as React.CSSProperties,
  searchBarInput: {
    width: '100%',
    boxSizing: 'border-box',
    padding: '10px 12px',
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    color: '#0f172a',
    fontSize: '13px',
    outline: 'none',
  } as React.CSSProperties,
  leadScrollList: {
    flex: 1,
    minHeight: 0,
  } as React.CSSProperties,
  leadScrollViewport: {
    padding: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  } as React.CSSProperties,
  emptyListPlaceholder: {
    textAlign: 'center',
    padding: '40px 20px',
    color: '#94a3b8',
    fontSize: '13px',
  } as React.CSSProperties,
  leadInteractionCard: {
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid',
    transition: 'all 0.2s ease',
    flexShrink: 0,
    width: '100%',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  } as React.CSSProperties,
  cardTopRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '6px',
  } as React.CSSProperties,
  cardBottomRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '6px',
    marginTop: '2px',
  } as React.CSSProperties,
  leadCardNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,
  leadCardName: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '700',
    color: '#1e3a8a',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    minWidth: 0,
  } as React.CSSProperties,
  leadCardPhone: {
    margin: 0,
    fontSize: '12px',
    color: '#475569',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  } as React.CSSProperties,
  leadCardEmail: {
    margin: 0,
    fontSize: '12px',
    color: '#64748b',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  } as React.CSSProperties,
  receivedCountBadge: {
    flexShrink: 0,
    display: 'inline-grid',
    placeItems: 'center',
    minWidth: '22px',
    height: '22px',
    padding: '0 5px',
    borderRadius: '9999px',
    fontSize: '11px',
    fontWeight: '600',
    color: '#ffffff',
    backgroundColor: '#25D366',
  } as React.CSSProperties,
  statusActionGroup: { display: 'flex', gap: '3px', flexShrink: 0 } as React.CSSProperties,
  aiActiveBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    fontWeight: '700',
    textTransform: 'uppercase',
    color: '#059669',
    backgroundColor: '#ecfdf5',
    border: '1px solid #bbf7d0',
    borderRadius: '4px',
    padding: '2px 6px',
  } as React.CSSProperties,
  cardStartButton: {
    border: 'none',
    backgroundColor: '#059669',
    color: '#ffffff',
    padding: '6px 10px',
    borderRadius: '6px',
    fontSize: '11px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  cardConversationActiveBadge: {
    flexShrink: 0,
    fontSize: '10px',
    fontWeight: '700',
    color: '#047857',
    backgroundColor: '#ecfdf5',
    border: '1px solid #bbf7d0',
    borderRadius: '6px',
    padding: '5px 8px',
  } as React.CSSProperties,
  headerActionGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexShrink: 0,
    marginLeft: '16px',
  } as React.CSSProperties,
  headerOverviewButton: {
    border: '1px solid #cbd5e1',
    backgroundColor: '#ffffff',
    color: '#03045e',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  headerResetButton: {
    border: '1px solid #fecaca',
    backgroundColor: '#fef2f2',
    color: '#b91c1c',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
  } as React.CSSProperties,
  headerJourneyLink: {
    marginTop: '6px',
    border: 'none',
    background: 'none',
    color: '#0284c7',
    padding: 0,
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
  } as React.CSSProperties,
  headerStartButton: {
    border: 'none',
    backgroundColor: '#059669',
    color: '#ffffff',
    padding: '10px 16px',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
    boxShadow: '0 2px 8px rgba(5, 150, 105, 0.25)',
  } as React.CSSProperties,
  rightChatPanel: {
    flex: '1 1 auto',
    minWidth: 0,
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#efeae2',
    overflow: 'hidden',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  activeChatInterface: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: '100%',
    overflow: 'hidden',
  } as React.CSSProperties,
  chatHeaderBar: {
    padding: '14px 24px',
    backgroundColor: '#f0f2f5',
    borderBottom: '1px solid #e3e6e9',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    flexShrink: 0,
    gap: '12px',
  } as React.CSSProperties,
  intakeProfilePanel: {
    padding: '14px 20px',
    borderBottom: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
    flexShrink: 0,
  } as React.CSSProperties,
  intakeProfileHeader: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    marginBottom: '10px',
  } as React.CSSProperties,
  intakeProfileHeaderMainRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '16px',
    width: '100%',
  } as React.CSSProperties,
  intakePipelineStatusBlock: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: '4px',
    flexShrink: 0,
    maxWidth: '52%',
  } as React.CSSProperties,
  intakePipelineStatus: {
    fontSize: '18px',
    fontWeight: '800',
    lineHeight: 1.2,
    textAlign: 'right',
  } as React.CSSProperties,
  intakePipelineStatusDescription: {
    fontSize: '12px',
    fontWeight: '500',
    lineHeight: 1.35,
    textAlign: 'right',
  } as React.CSSProperties,
  intakeProfileTitle: {
    display: 'block',
    fontSize: '12px',
    fontWeight: '700',
    color: '#0f172a',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  } as React.CSSProperties,
  intakeStepBadge: {
    display: 'inline-block',
    marginTop: '4px',
    padding: '2px 8px',
    borderRadius: '999px',
    backgroundColor: '#ecfdf5',
    color: '#047857',
    fontSize: '11px',
    fontWeight: '600',
  } as React.CSSProperties,
  scheduledCallBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 10px',
    borderRadius: '8px',
    backgroundColor: '#dcfce7',
    color: '#166534',
    fontSize: '12px',
    fontWeight: '600',
  } as React.CSSProperties,
  intakeProgressRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
    marginBottom: '12px',
  } as React.CSSProperties,
  intakeProgressChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '4px 8px',
    borderRadius: '999px',
    border: '1px solid',
    fontSize: '10px',
    fontWeight: '600',
    whiteSpace: 'nowrap',
  } as React.CSSProperties,
  intakeFieldGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: '8px',
  } as React.CSSProperties,
  intakeFieldCell: {
    padding: '8px 10px',
    borderRadius: '8px',
    backgroundColor: '#ffffff',
    border: '1px solid #e2e8f0',
  } as React.CSSProperties,
  intakeFieldLabel: {
    display: 'block',
    fontSize: '13px',
    fontWeight: '700',
    color: '#64748b',
    textTransform: 'uppercase',
    marginBottom: '4px',
  } as React.CSSProperties,
  intakeFieldValue: {
    display: 'block',
    fontSize: '14px',
    color: '#0f172a',
    fontWeight: '500',
    wordBreak: 'break-word',
  } as React.CSSProperties,
  consultationCalendarSection: {
    marginTop: '12px',
    paddingTop: '12px',
    borderTop: '1px dashed #cbd5e1',
  } as React.CSSProperties,
  consultationCalendarTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '12px',
    fontWeight: '600',
    color: '#334155',
    marginBottom: '8px',
  } as React.CSSProperties,
  consultationDateGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
    gap: '8px',
  } as React.CSSProperties,
  consultationDateCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: '8px',
    backgroundColor: '#ffffff',
    border: '1px solid #bbf7d0',
  } as React.CSSProperties,
  consultationDateNumber: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '20px',
    height: '20px',
    borderRadius: '999px',
    backgroundColor: '#059669',
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: '700',
    flexShrink: 0,
  } as React.CSSProperties,
  consultationDateLabel: {
    fontSize: '12px',
    color: '#0f172a',
    fontWeight: '500',
  } as React.CSSProperties,
  consultationTimeGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  } as React.CSSProperties,
  consultationTimeCard: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 12px',
    borderRadius: '8px',
    backgroundColor: '#ffffff',
    border: '1px solid #bbf7d0',
    fontSize: '12px',
    color: '#0f172a',
    fontWeight: '500',
  } as React.CSSProperties,
  headerProfileName: {
    margin: 0,
    fontSize: '16px',
    fontWeight: '600',
    color: '#111b21',
  } as React.CSSProperties,
  headerProfileMeta: {
    margin: '4px 0 0 0',
    fontSize: '14px',
    color: '#667781',
  } as React.CSSProperties,
  aiAgentBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '9999px',
    backgroundColor: '#dcfce7',
    color: '#166534',
    fontSize: '12px',
    fontWeight: '700',
    flexShrink: 0,
  } as React.CSSProperties,
  whatsappChatFeedShell: {
    flex: 1,
    minHeight: 0,
  } as React.CSSProperties,
  whatsappChatFeedSurface: {
    padding: '20px 4%',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    backgroundImage:
      'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")',
    backgroundColor: '#efeae2',
    backgroundRepeat: 'repeat',
  } as React.CSSProperties,
  timelineDividerCenter: {
    display: 'flex',
    justifyContent: 'center',
    width: '100%',
    margin: '14px 0',
  } as React.CSSProperties,
  timelineBadgeBubble: {
    backgroundColor: '#ffffff',
    color: '#54656f',
    fontSize: '12px',
    padding: '5px 12px',
    borderRadius: '7px',
    boxShadow: '0 1px 1px rgba(0,0,0,0.08)',
  } as React.CSSProperties,
  systemLogCentralRow: {
    display: 'flex',
    justifyContent: 'center',
    width: '100%',
    margin: '6px 0',
    fontSize: '12px',
    color: '#54656f',
    fontStyle: 'italic',
  } as React.CSSProperties,
  messageStreamRow: { display: 'flex', width: '100%', margin: '2px 0' } as React.CSSProperties,
  messageBubbleCell: {
    maxWidth: '65%',
    padding: '8px 12px 10px 12px',
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  } as React.CSSProperties,
  senderLabel: {
    fontSize: '10px',
    fontWeight: '700',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  } as React.CSSProperties,
  bubbleTextString: {
    margin: 0,
    color: '#111b21',
    whiteSpace: 'pre-wrap',
    paddingRight: '45px',
    fontSize: '14px',
    lineHeight: '1.45',
  } as React.CSSProperties,
  bubbleTimestampLabel: {
    fontSize: '10.5px',
    color: '#667781',
    position: 'absolute',
    bottom: '3px',
    right: '8px',
  } as React.CSSProperties,
  inlineImagePreview: {
    width: '100%',
    maxHeight: '240px',
    borderRadius: '6px',
    objectFit: 'cover',
  } as React.CSSProperties,
  downloadFileActionLink: {
    fontSize: '12px',
    color: '#0284c7',
    textDecoration: 'none',
    fontWeight: '600',
  } as React.CSSProperties,
  emptyConversationPrompt: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    margin: 'auto',
    padding: '32px',
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    borderRadius: '12px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
    textAlign: 'center',
    maxWidth: '420px',
  } as React.CSSProperties,
  readOnlyFooter: {
    padding: '12px 18px',
    backgroundColor: '#f0f2f5',
    borderTop: '1px solid #e3e6e9',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontSize: '12px',
    color: '#64748b',
    flexShrink: 0,
    flexWrap: 'wrap',
  } as React.CSSProperties,
  startConversationButton: {
    border: 'none',
    backgroundColor: '#059669',
    color: '#ffffff',
    padding: '10px 16px',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '700',
    cursor: 'pointer',
  } as React.CSSProperties,
  footerActionButton: {
    marginLeft: 'auto',
    border: 'none',
    backgroundColor: '#059669',
    color: '#ffffff',
    padding: '8px 14px',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  emptyWorkspaceGrid: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f8fafc',
  } as React.CSSProperties,
};
