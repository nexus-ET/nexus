import { FLOWX_JOURNEY_STAGES } from '../config/flowxNav';
import type {
  FlowxEnrollmentStageMeta,
  FlowxEnrollmentTrack,
  FlowxStageKey,
  FlowxTask,
  FlowxTrackStatus,
} from '../types/flowx';

/** Visual lifecycle for process / sub-process boxes. */
export type FlowxLifecycleStatus = 'planned' | 'in_progress' | 'delayed' | 'complete';

export type VisibleStage = { key: FlowxStageKey; label: string };

/** Visible (non-hidden) stages from enrollment, else global FlowX defaults. */
export function visibleJourneyStages(
  stages?: FlowxEnrollmentStageMeta[] | null
): VisibleStage[] {
  if (stages && stages.length > 0) {
    return stages
      .filter(s => !s.is_hidden)
      .slice()
      .sort((a, b) => a.position_index - b.position_index)
      .map(s => ({ key: s.stage_key, label: s.label }));
  }
  return FLOWX_JOURNEY_STAGES.map(s => ({ key: s.key, label: s.label }));
}

/** 1-based process (stage) index among visible stages, or 0 if unknown. */
export function processNumber(
  stageKey: FlowxStageKey | string,
  stages?: FlowxEnrollmentStageMeta[] | null
): number {
  const visible = visibleJourneyStages(stages);
  const idx = visible.findIndex(s => s.key === stageKey);
  return idx >= 0 ? idx + 1 : 0;
}

/** Tracks for a stage in display order. */
export function orderedStageTracks(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string
): FlowxEnrollmentTrack[] {
  return tracks
    .filter(t => t.stage_key === stageKey)
    .sort((a, b) => {
      const pa = a.position_index ?? 0;
      const pb = b.position_index ?? 0;
      if (pa !== pb) return pa - pb;
      return a.track_name.localeCompare(b.track_name);
    });
}

export function orderedTrackTasks(track: FlowxEnrollmentTrack): FlowxTask[] {
  return [...(track.tasks ?? [])].sort((a, b) => a.position_index - b.position_index);
}

/** Flat ordered tasks for a stage across tracks. */
export function orderedStageTasks(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string
): FlowxTask[] {
  const out: FlowxTask[] = [];
  for (const track of orderedStageTracks(tracks, stageKey)) {
    out.push(...orderedTrackTasks(track));
  }
  return out;
}

/** Top-level bricks only (no parent_template_id) — matches country board. */
export function topLevelStageTasks(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string
): FlowxTask[] {
  return orderedStageTasks(tracks, stageKey).filter(t => !t.parent_template_id);
}

/** Nested children of a parent template on this stage. */
export function childTasksOfTemplate(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string,
  parentTemplateId: string | null | undefined
): FlowxTask[] {
  if (!parentTemplateId) return [];
  return orderedStageTasks(tracks, stageKey).filter(
    t => t.parent_template_id === parentTemplateId
  );
}

/** Hierarchical codes: process `1`, sub-process `1.1`, child `1.1.1`. */
export function hierarchyCodes(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string,
  trackId: string,
  taskId?: string,
  stages?: FlowxEnrollmentStageMeta[] | null
): { process: string; subProcess: string; child?: string } | null {
  const p = processNumber(stageKey, stages);
  if (!p) return null;
  const stageTracks = orderedStageTracks(tracks, stageKey);
  const trackIdx = stageTracks.findIndex(t => t.id === trackId);
  if (trackIdx < 0) return null;

  const allTasks = orderedStageTasks(tracks, stageKey);
  const topLevel = allTasks.filter(t => !t.parent_template_id);

  if (!taskId) {
    return { process: String(p), subProcess: `${p}.${trackIdx + 1}` };
  }

  const task = allTasks.find(t => t.id === taskId);
  if (!task) {
    return { process: String(p), subProcess: `${p}.${trackIdx + 1}` };
  }

  if (!task.parent_template_id) {
    const topIdx = topLevel.findIndex(t => t.id === taskId);
    const sub = `${p}.${topIdx >= 0 ? topIdx + 1 : trackIdx + 1}`;
    return { process: String(p), subProcess: sub };
  }

  const parentIdx = topLevel.findIndex(t => t.template_id === task.parent_template_id);
  const siblings = allTasks.filter(t => t.parent_template_id === task.parent_template_id);
  const childIdx = siblings.findIndex(t => t.id === taskId);
  const parentNum = parentIdx >= 0 ? parentIdx + 1 : trackIdx + 1;
  const sub = `${p}.${parentNum}`;
  if (childIdx < 0) return { process: String(p), subProcess: sub };
  return { process: String(p), subProcess: sub, child: `${sub}.${childIdx + 1}` };
}

export function formatHierarchyLabel(code: string, label: string): string {
  return `${code}  ${label}`;
}

function trackHasDelay(track: FlowxEnrollmentTrack): boolean {
  if (track.track_status === 'blocked') return true;
  return (track.tasks ?? []).some(t => t.sla_status === 'breached' || t.sla_status === 'amber');
}

function trackIsActive(track: FlowxEnrollmentTrack): boolean {
  if (track.track_status === 'in_progress') return true;
  return (track.tasks ?? []).some(
    t => t.kanban_status === 'in_progress' || t.kanban_status === 'in_review'
  );
}

/** Required (non-optional) tasks — optional steps never block completion. */
export function requiredTasks(tasks: FlowxTask[]): FlowxTask[] {
  return tasks.filter(t => !t.is_optional);
}

function isIntakeSessionTitle(task: FlowxTask): boolean {
  return (task.title || '').trim().toLowerCase() === 'intake session';
}

/** Intake Session completion follows booking-driven progress_percentage (100 = complete). */
function taskCountsAsComplete(task: FlowxTask): boolean {
  if (isIntakeSessionTitle(task) && typeof task.progress_percentage === 'number') {
    return task.progress_percentage >= 100;
  }
  return task.kanban_status === 'approved';
}

function taskCountsAsDelayed(task: FlowxTask): boolean {
  if (isIntakeSessionTitle(task) && typeof task.progress_percentage === 'number') {
    return task.progress_percentage === 0 && task.sla_status === 'breached';
  }
  return (
    task.kanban_status === 'blocked' ||
    task.sla_status === 'breached' ||
    task.sla_status === 'amber'
  );
}

function taskHasStarted(task: FlowxTask): boolean {
  if (isIntakeSessionTitle(task) && typeof task.progress_percentage === 'number') {
    return task.progress_percentage > 0 && task.progress_percentage < 100;
  }
  return task.kanban_status !== 'todo';
}

/**
 * Lifecycle from a flat task list (includes nested children when provided).
 * Optional tasks are ignored for completion. Returns null when there are no tasks.
 * Intake Session (1.1) uses booking-driven progress_percentage when present.
 */
export function tasksLifecycle(tasks: FlowxTask[]): FlowxLifecycleStatus | null {
  if (!tasks.length) return null;

  const basis = requiredTasks(tasks);
  // Only optional work exists — it does not block the parent from being complete.
  if (basis.length === 0) return 'complete';

  if (basis.every(taskCountsAsComplete)) return 'complete';
  if (basis.some(taskCountsAsDelayed)) return 'delayed';
  if (basis.some(t => taskCountsAsComplete(t) || taskHasStarted(t))) return 'in_progress';
  return 'planned';
}

/** Sub-process lifecycle from required tasks on the track (nested children included). */
export function subProcessLifecycle(track: FlowxEnrollmentTrack): FlowxLifecycleStatus {
  const fromTasks = tasksLifecycle(track.tasks ?? []);
  if (fromTasks) return fromTasks;

  const status: FlowxTrackStatus = track.track_status;
  if (status === 'completed') return 'complete';
  if (trackHasDelay(track)) return 'delayed';
  if (status === 'in_progress' || trackIsActive(track)) return 'in_progress';
  return 'planned';
}

/**
 * Parent process lifecycle from all required sub-processes / nested tasks under the stage.
 * A process is Complete only when every required task (any nesting depth) is approved.
 * Journey position alone must never mark a process Complete or In progress — only real
 * task state (including booking-driven Intake Session) drives lifecycle.
 */
export function processLifecycle(
  tracks: FlowxEnrollmentTrack[],
  stageKey: FlowxStageKey | string,
  _currentStageKey: FlowxStageKey | string,
  stages?: FlowxEnrollmentStageMeta[] | null
): FlowxLifecycleStatus {
  void stages;
  void _currentStageKey;

  const stageTasks = orderedStageTasks(tracks, stageKey);
  const fromTasks = tasksLifecycle(stageTasks);
  if (fromTasks) return fromTasks;

  // No tasks on the stage yet — fall back to track rollups only (no journey-position promotion).
  const stageTracks = orderedStageTracks(tracks, stageKey);
  if (stageTracks.length > 0) {
    const lives = stageTracks.map(subProcessLifecycle);
    if (lives.every(l => l === 'complete')) return 'complete';
    if (lives.some(l => l === 'delayed')) return 'delayed';
    if (lives.some(l => l === 'in_progress')) return 'in_progress';
    return 'planned';
  }

  return 'planned';
}

/** Border-focused tones for process / sub-process boxes. */
export function lifecycleBorderClass(status: FlowxLifecycleStatus): string {
  switch (status) {
    case 'complete':
      return 'border-emerald-500 bg-emerald-50 text-emerald-950';
    case 'delayed':
      return 'border-red-600 bg-red-50 text-red-950';
    case 'in_progress':
      return 'border-sky-500 bg-sky-50 text-sky-950';
    default:
      return 'border-slate-300 bg-card text-text-main';
  }
}

/** Extra emphasis for delayed bricks (map cards) — delayed always wins over nested accent fill. */
export function delayedBrickClass(): string {
  return 'border-red-600 bg-red-50 text-red-950 shadow-[0_0_0_3px_rgba(220,38,38,0.22)] ring-2 ring-red-500/50';
}

export function lifecycleLabel(status: FlowxLifecycleStatus): string {
  switch (status) {
    case 'complete':
      return 'Complete';
    case 'delayed':
      return 'Delayed';
    case 'in_progress':
      return 'In progress';
    default:
      return 'Planned';
  }
}

/** Child task lifecycle from kanban + SLA. */
export function childLifecycle(
  kanban: FlowxTask['kanban_status'] | FlowxTask,
  sla?: FlowxTask['sla_status']
): FlowxLifecycleStatus {
  const kanbanStatus = typeof kanban === 'object' ? kanban.kanban_status : kanban;
  const slaStatus = typeof kanban === 'object' ? kanban.sla_status : sla;
  if (kanbanStatus === 'approved') return 'complete';
  if (slaStatus === 'breached' || slaStatus === 'amber') return 'delayed';
  if (kanbanStatus === 'in_progress' || kanbanStatus === 'in_review') return 'in_progress';
  return 'planned';
}

/** Lifecycle for a task including its nested descendants (optional descendants ignored). */
export function taskTreeLifecycle(
  task: FlowxTask,
  descendants: FlowxTask[] = []
): FlowxLifecycleStatus {
  return tasksLifecycle([task, ...descendants]) ?? childLifecycle(task);
}
