import type {
  FlowxEnrollmentStageMeta,
  FlowxEnrollmentTrack,
  FlowxIntakeBooking,
  FlowxStageKey,
  FlowxTask,
} from '../types/flowx';
import {
  childTasksOfTemplate,
  topLevelStageTasks,
  visibleJourneyStages,
  type FlowxLifecycleStatus,
} from './flowxHierarchy';

/** status_definitions ids that drive Intake Session (1.1). */
export const INTAKE_STATUS = {
  SESSION_BOOKED: 4,
  SESSION_RESCHEDULED: 5,
  SESSION_CANCELLED: 6,
  NO_ANSWER: 7,
  COUNSELLING_SCHEDULED: 12,
  COUNSELLING_FINISHED: 13,
  PROSPECT_QUALIFIED: 14,
  FOLLOW_UP: 15,
} as const;

export type IntakeSessionState = {
  lifecycle: FlowxLifecycleStatus;
  progress: number;
  isOverdue?: boolean;
  delayLabel?: string | null;
  delayDays?: number;
  delayWeeks?: number;
  delayMonths?: number;
};

const PLANNED_0: IntakeSessionState = { lifecycle: 'planned', progress: 0 };
const PLANNED_25: IntakeSessionState = { lifecycle: 'planned', progress: 25 };
const IN_PROGRESS_50: IntakeSessionState = { lifecycle: 'in_progress', progress: 50 };
const DELAYED_0: IntakeSessionState = { lifecycle: 'delayed', progress: 0 };
const COMPLETE_100: IntakeSessionState = { lifecycle: 'complete', progress: 100 };

function fromStatusId(sid: number | null | undefined): IntakeSessionState | null {
  if (sid == null) return null;
  if (
    sid === INTAKE_STATUS.COUNSELLING_FINISHED ||
    sid === INTAKE_STATUS.PROSPECT_QUALIFIED ||
    sid === INTAKE_STATUS.FOLLOW_UP
  ) {
    return COMPLETE_100;
  }
  if (sid === INTAKE_STATUS.SESSION_CANCELLED || sid === INTAKE_STATUS.NO_ANSWER) {
    return DELAYED_0;
  }
  if (sid === INTAKE_STATUS.COUNSELLING_SCHEDULED) return IN_PROGRESS_50;
  if (sid === INTAKE_STATUS.SESSION_BOOKED || sid === INTAKE_STATUS.SESSION_RESCHEDULED) {
    return PLANNED_25;
  }
  return null;
}

function fromStageName(statusStageName?: string | null): IntakeSessionState | null {
  const name = (statusStageName || '').trim().toLowerCase();
  if (!name) return null;
  if (
    name.includes('finished') ||
    name.includes('qualified') ||
    name.includes('follow-up') ||
    name.includes('follow up')
  ) {
    return COMPLETE_100;
  }
  if (name.includes('cancelled') || name.includes('no answer')) return DELAYED_0;
  if (name.includes('reschedul')) return PLANNED_25;
  if (name.includes('counselling: scheduled') || /(^|[^a-z])scheduled$/.test(name)) {
    return IN_PROGRESS_50;
  }
  if (name.includes('session booked')) return PLANNED_25;
  return null;
}

function fromBookingStatus(bookingStatus?: string | null): IntakeSessionState | null {
  const bs = (bookingStatus || '').trim().toUpperCase();
  if (!bs) return null;
  if (bs === 'COMPLETED') return COMPLETE_100;
  if (bs === 'CANCELLED') return DELAYED_0;
  if (bs === 'SCHEDULED') return IN_PROGRESS_50;
  if (bs === 'PENDING') return PLANNED_25;
  return null;
}

function mergeIntakeSignals(signals: IntakeSessionState[]): IntakeSessionState {
  if (!signals.length) return PLANNED_0;
  if (signals.some(s => s.lifecycle === 'delayed')) return DELAYED_0;
  return signals.reduce((best, s) => (s.progress > best.progress ? s : best), PLANNED_0);
}

function formatDelayParts(days: number): {
  delayDays: number;
  delayWeeks: number;
  delayMonths: number;
  delayLabel: string;
} {
  const delayDays = Math.max(0, Math.floor(days));
  const delayWeeks = Math.floor(delayDays / 7);
  const delayMonths = Math.floor(delayDays / 30);
  const dayUnit = delayDays === 1 ? 'day' : 'days';
  const weekUnit = delayWeeks === 1 ? 'week' : 'weeks';
  const monthUnit = delayMonths === 1 ? 'month' : 'months';
  return {
    delayDays,
    delayWeeks,
    delayMonths,
    delayLabel: `${delayDays} ${dayUnit} · ${delayWeeks} ${weekUnit} · ${delayMonths} ${monthUnit}`,
  };
}

/** Client-side overdue check when API fields are present (or recomputable). */
export function computeIntakeOverdueFromBooking(
  booking?: FlowxIntakeBooking | null
): {
  isOverdue: boolean;
  delayDays: number;
  delayWeeks: number;
  delayMonths: number;
  delayLabel: string | null;
} {
  if (!booking) {
    return {
      isOverdue: false,
      delayDays: 0,
      delayWeeks: 0,
      delayMonths: 0,
      delayLabel: null,
    };
  }

  const bs = (booking.booking_status || '').trim().toUpperCase();
  const sid = booking.status_definition_id;
  if (bs === 'COMPLETED' || bs === 'CANCELLED') {
    return {
      isOverdue: false,
      delayDays: 0,
      delayWeeks: 0,
      delayMonths: 0,
      delayLabel: null,
    };
  }
  if (
    sid === INTAKE_STATUS.COUNSELLING_FINISHED ||
    sid === INTAKE_STATUS.PROSPECT_QUALIFIED ||
    sid === INTAKE_STATUS.FOLLOW_UP ||
    sid === INTAKE_STATUS.SESSION_CANCELLED ||
    sid === INTAKE_STATUS.NO_ANSWER
  ) {
    return {
      isOverdue: false,
      delayDays: 0,
      delayWeeks: 0,
      delayMonths: 0,
      delayLabel: null,
    };
  }

  if (booking.is_overdue) {
    const parts =
      typeof booking.delay_days === 'number'
        ? formatDelayParts(booking.delay_days)
        : {
            delayDays: booking.delay_days ?? 0,
            delayWeeks: booking.delay_weeks ?? 0,
            delayMonths: booking.delay_months ?? 0,
            delayLabel: booking.delay_label || null,
          };
    return {
      isOverdue: true,
      delayDays: parts.delayDays,
      delayWeeks: parts.delayWeeks,
      delayMonths: parts.delayMonths,
      delayLabel: parts.delayLabel || booking.delay_label || null,
    };
  }

  const endRaw = booking.scheduled_end_at || booking.scheduled_time;
  let slotEnd: Date | null = null;
  if (endRaw) {
    const end = new Date(endRaw);
    if (!Number.isNaN(end.getTime())) {
      slotEnd = booking.scheduled_end_at
        ? end
        : new Date(end.getTime() + 60 * 60 * 1000);
    }
  }

  // Fallback: parse My Bookings labels ("Mon, Jul 27" + "10:00 - 11:00").
  if (!slotEnd && booking.date_label) {
    const parsed = parseIntakeSlotEndFromLabels(booking.date_label, booking.time_label);
    if (parsed) slotEnd = parsed;
  }

  if (!slotEnd) {
    return {
      isOverdue: false,
      delayDays: 0,
      delayWeeks: 0,
      delayMonths: 0,
      delayLabel: null,
    };
  }

  const now = Date.now();
  if (now <= slotEnd.getTime()) {
    return {
      isOverdue: false,
      delayDays: 0,
      delayWeeks: 0,
      delayMonths: 0,
      delayLabel: null,
    };
  }

  const endDay = new Date(slotEnd);
  endDay.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let delayDays = Math.round((today.getTime() - endDay.getTime()) / 86400000);
  if (delayDays < 1) delayDays = 1;
  const parts = formatDelayParts(delayDays);
  return {
    isOverdue: true,
    ...parts,
  };
}

/** Parse "Mon, Jul 27" + "10:00 - 11:00" into a Date for the slot end (current year, or prior if future). */
function parseIntakeSlotEndFromLabels(
  dateLabel?: string | null,
  timeLabel?: string | null
): Date | null {
  const raw = (dateLabel || '').trim();
  if (!raw) return null;
  const year = new Date().getFullYear();
  // "%a, %b %d" → "Mon, Jul 27"
  const withYear = `${raw}, ${year}`;
  let start = new Date(withYear);
  if (Number.isNaN(start.getTime())) return null;

  const range = (timeLabel || '').match(
    /(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/
  );
  if (range) {
    const endH = Number(range[3]);
    const endM = Number(range[4]);
    // Labels are 12h without am/pm; counselling slots are daytime — treat as 24h if >= 1.
    start.setHours(endH, endM, 0, 0);
  } else {
    start.setHours(23, 59, 0, 0);
  }

  // If the constructed date is still in the future by > 30 days, it was likely last year.
  const now = new Date();
  if (start.getTime() - now.getTime() > 30 * 86400000) {
    start = new Date(start);
    start.setFullYear(year - 1);
  }
  return start;
}

/**
 * Sub-process 1.1 Intake Session — driven by My Bookings / status_definitions.
 *
 * | Booking / lead status                         | Lifecycle   | Progress |
 * |-----------------------------------------------|-------------|----------|
 * | Lead: Session Booked (4) / Rescheduled (5)    | Planned     | 25%      |
 * | Counselling: Scheduled (12)                   | In progress | 50%      |
 * | Lead: Session Cancelled (6) / No Answer (7)   | Delayed     | 0%       |
 * | Past appointment, status not Finished         | Delayed     | 0%       |
 * | Counselling: Finished (13) (+ 14 / 15)         | Complete    | 100%     |
 *
 * When signals disagree, Delayed wins; otherwise the furthest progress wins
 * (e.g. lead still Booked + booking SCHEDULED → In progress 50%).
 * Finished always wins over overdue.
 */
export function resolveIntakeSessionState(input: {
  statusDefinitionId?: number | null;
  bookingStatus?: string | null;
  statusStageName?: string | null;
  /** API progress already computed for this Intake Session brick. */
  progressPercentage?: number | null;
  isOverdue?: boolean;
  delayLabel?: string | null;
  delayDays?: number;
  delayWeeks?: number;
  delayMonths?: number;
}): IntakeSessionState {
  const signals: IntakeSessionState[] = [];
  const fromId = fromStatusId(input.statusDefinitionId);
  const fromName = fromStageName(input.statusStageName);
  const fromBooking = fromBookingStatus(input.bookingStatus);
  if (fromId) signals.push(fromId);
  if (fromName) signals.push(fromName);
  if (fromBooking) signals.push(fromBooking);

  const p = input.progressPercentage;
  if (typeof p === 'number' && Number.isFinite(p)) {
    if (p >= 100) signals.push(COMPLETE_100);
    else if (p >= 50) signals.push(IN_PROGRESS_50);
    else if (p >= 25) signals.push(PLANNED_25);
    else if (p <= 0 && (fromId?.lifecycle === 'delayed' || input.isOverdue)) {
      signals.push(DELAYED_0);
    }
  }

  let result = mergeIntakeSignals(signals);
  if (result.lifecycle === 'complete') {
    return result;
  }
  if (input.isOverdue) {
    result = {
      ...DELAYED_0,
      isOverdue: true,
      delayLabel: input.delayLabel ?? null,
      delayDays: input.delayDays,
      delayWeeks: input.delayWeeks,
      delayMonths: input.delayMonths,
    };
  }
  return result;
}

export function isIntakeSessionTask(task: Pick<FlowxTask, 'title'> | null | undefined): boolean {
  const title = (task?.title || '').trim().toLowerCase();
  return title === 'intake session' || title.includes('intake session');
}

export function intakeSessionStateFromBooking(
  booking?: FlowxIntakeBooking | null,
  task?: Pick<FlowxTask, 'progress_percentage' | 'title' | 'sla_status'> | null
): IntakeSessionState | null {
  if (!booking && !isIntakeSessionTask(task)) return null;
  if (!booking && !task) return null;
  const overdue = computeIntakeOverdueFromBooking(booking);
  // Synced task SLA breach must surface even when booking payload lags.
  const slaBreached =
    task?.sla_status === 'breached' &&
    (typeof task.progress_percentage !== 'number' || task.progress_percentage < 100);
  const isOverdue = overdue.isOverdue || Boolean(slaBreached);
  const state = resolveIntakeSessionState({
    statusDefinitionId: booking?.status_definition_id,
    bookingStatus: booking?.booking_status,
    statusStageName: booking?.status_stage_name,
    progressPercentage: task?.progress_percentage,
    isOverdue,
    delayLabel: overdue.delayLabel,
    delayDays: overdue.delayDays,
    delayWeeks: overdue.delayWeeks,
    delayMonths: overdue.delayMonths,
  });
  if (isOverdue && state.lifecycle === 'delayed' && !state.delayLabel && overdue.delayLabel) {
    return { ...state, isOverdue: true, delayLabel: overdue.delayLabel };
  }
  if (isOverdue && state.lifecycle === 'delayed') {
    return { ...state, isOverdue: true };
  }
  return state;
}

/** Human-readable overdue chip, e.g. "Delayed by 7 days · 1 week · 0 months". */
export function intakeDelayDisplay(
  booking?: FlowxIntakeBooking | null,
  task?: Pick<FlowxTask, 'progress_percentage' | 'title' | 'sla_status'> | null
): string | null {
  const state = intakeSessionStateFromBooking(booking, task);
  if (state?.lifecycle !== 'delayed') return null;
  if (state.isOverdue && state.delayLabel) return `Delayed by ${state.delayLabel}`;
  if (state.isOverdue) return 'Delayed · appointment overdue';
  return null;
}

/** Progress % for any sub-process brick (Intake uses booking rules). */
export function subprocessProgressPercentage(
  task: FlowxTask,
  intakeBooking?: FlowxIntakeBooking | null
): number {
  if (isIntakeSessionTask(task)) {
    return intakeSessionStateFromBooking(intakeBooking, task)?.progress ?? 0;
  }
  if (typeof task.progress_percentage === 'number') return Math.round(task.progress_percentage);
  if (task.kanban_status === 'approved') return 100;
  if (task.kanban_status === 'in_progress' || task.kanban_status === 'in_review') return 50;
  if (task.sla_status === 'breached' || task.kanban_status === 'blocked') return 0;
  return 0;
}

export function subprocessLifecycle(
  task: FlowxTask,
  intakeBooking?: FlowxIntakeBooking | null
): FlowxLifecycleStatus {
  if (isIntakeSessionTask(task)) {
    return intakeSessionStateFromBooking(intakeBooking, task)?.lifecycle ?? 'planned';
  }
  if (task.kanban_status === 'approved') return 'complete';
  if (task.sla_status === 'breached' || task.sla_status === 'amber') return 'delayed';
  if (task.kanban_status === 'in_progress' || task.kanban_status === 'in_review') {
    return 'in_progress';
  }
  return 'planned';
}

/**
 * Brick lifecycle including nested children — Delayed wins if self or any child is delayed.
 */
export function brickLifecycle(
  task: FlowxTask,
  children: FlowxTask[] = [],
  intakeBooking?: FlowxIntakeBooking | null
): FlowxLifecycleStatus {
  const self = subprocessLifecycle(task, intakeBooking);
  if (self === 'delayed') return 'delayed';
  if (children.some(child => subprocessLifecycle(child, intakeBooking) === 'delayed')) {
    return 'delayed';
  }
  if (self === 'complete' && children.length > 0) {
    const childLives = children.map(child => subprocessLifecycle(child, intakeBooking));
    if (childLives.every(l => l === 'complete')) return 'complete';
    if (childLives.some(l => l === 'in_progress')) return 'in_progress';
  }
  if (self === 'in_progress') return 'in_progress';
  if (children.some(child => subprocessLifecycle(child, intakeBooking) === 'in_progress')) {
    return 'in_progress';
  }
  if (self === 'complete') return 'complete';
  return self;
}

/**
 * Consolidated main-process progress = average of required sub-process percentages.
 * Optional sub-processes are excluded.
 */
export function processProgressPercentage(
  tasks: FlowxTask[],
  intakeBooking?: FlowxIntakeBooking | null
): number {
  const required = tasks.filter(t => !t.is_optional);
  const basis = required.length > 0 ? required : tasks;
  if (!basis.length) return 0;
  const sum = basis.reduce(
    (acc, task) => acc + subprocessProgressPercentage(task, intakeBooking),
    0
  );
  return Math.round(sum / basis.length);
}

/**
 * Main-process lifecycle from real sub-process brick state (incl. Intake booking rules).
 * Never promotes a stage to In progress from journey cursor alone.
 */
export function stageLifecycleFromBricks(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string,
  intakeBooking?: FlowxIntakeBooking | null
): FlowxLifecycleStatus {
  const tops = topLevelStageTasks(tracks, stageKey).filter(t => !t.is_optional);
  if (!tops.length) return 'planned';
  const lives = tops.map(task => {
    const nested = childTasksOfTemplate(tracks, stageKey, task.template_id).filter(
      t => !t.is_optional
    );
    return brickLifecycle(task, nested, intakeBooking);
  });
  if (lives.some(l => l === 'delayed')) return 'delayed';
  if (lives.some(l => l === 'in_progress')) return 'in_progress';
  if (lives.every(l => l === 'complete')) return 'complete';
  return 'planned';
}

/**
 * Default process to open on journey load:
 * 1. First process (in sequence) with a delayed required sub-process / nested task
 * 2. Otherwise first process (in sequence) that is currently in progress
 * 3. Otherwise first incomplete process in sequence (Process 1 when nothing has started)
 *
 * Does not use journey `current_stage_key` — that only tracks cursor and must not force
 * a later process (e.g. Process 4) open or appear In progress.
 */
export function resolvePriorityViewStage(
  tracks: FlowxEnrollmentTrack[],
  stages: FlowxEnrollmentStageMeta[] | null | undefined,
  intakeBooking?: FlowxIntakeBooking | null,
  _currentStageKey?: FlowxStageKey | string | null
): { stageKey: FlowxStageKey; subprocessId: string | null } {
  void _currentStageKey;
  const visible = visibleJourneyStages(stages);
  if (!visible.length) {
    return { stageKey: 'counselling', subprocessId: null };
  }

  const stageBrickMeta = (stageKey: string) => {
    const tops = topLevelStageTasks(tracks, stageKey);
    return tops.map(task => {
      const nested = childTasksOfTemplate(tracks, stageKey, task.template_id).filter(
        t => !t.is_optional
      );
      return {
        task,
        nested,
        life: brickLifecycle(task, nested, intakeBooking),
      };
    });
  };

  // 1) Delayed wins — earliest process in sequence that has a delayed brick.
  for (const stage of visible) {
    const bricks = stageBrickMeta(stage.key).filter(b => !b.task.is_optional);
    const delayed = bricks.find(b => b.life === 'delayed');
    if (delayed) {
      return { stageKey: stage.key, subprocessId: delayed.task.id };
    }
  }

  // 2) Otherwise the earliest process currently in progress.
  for (const stage of visible) {
    const bricks = stageBrickMeta(stage.key).filter(b => !b.task.is_optional);
    const inProgress = bricks.find(b => b.life === 'in_progress');
    if (inProgress) {
      return { stageKey: stage.key, subprocessId: inProgress.task.id };
    }
  }

  // 3) Earliest incomplete process (planned work remaining), else Process 1.
  for (const stage of visible) {
    const bricks = stageBrickMeta(stage.key).filter(b => !b.task.is_optional);
    const incomplete = bricks.find(b => b.life !== 'complete');
    if (incomplete) {
      return { stageKey: stage.key, subprocessId: incomplete.task.id };
    }
  }

  const first = visible[0];
  const firstTops = topLevelStageTasks(tracks, first.key);
  return {
    stageKey: first.key,
    subprocessId: firstTops[0]?.id ?? null,
  };
}
