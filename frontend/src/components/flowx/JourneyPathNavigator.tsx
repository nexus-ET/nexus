import type { ReactNode } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, CircleDashed, Clock3, AlertTriangle } from 'lucide-react';
import type { FlowxEnrollmentTrack, FlowxStageKey, FlowxTask } from '../../types/flowx';
import {
  hierarchyCodes,
  lifecycleBorderClass,
  lifecycleLabel,
  orderedStageTracks,
  processLifecycle,
  processNumber,
  subProcessLifecycle,
  type FlowxLifecycleStatus,
  type VisibleStage,
} from '../../utils/flowxHierarchy';

function StatusPill({ status }: { status: FlowxLifecycleStatus }) {
  const icon =
    status === 'complete' ? (
      <CheckCircle2 size={12} />
    ) : status === 'delayed' ? (
      <AlertTriangle size={12} />
    ) : status === 'in_progress' ? (
      <Clock3 size={12} />
    ) : (
      <CircleDashed size={12} />
    );
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${lifecycleBorderClass(status)}`}
    >
      {icon}
      {lifecycleLabel(status)}
    </span>
  );
}

function ProgressBar({ value, tone }: { value: number; tone?: FlowxLifecycleStatus }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  const fill =
    tone === 'delayed'
      ? 'bg-amber-500'
      : tone === 'complete'
        ? 'bg-emerald-500'
        : tone === 'in_progress'
          ? 'bg-sky-500'
          : 'bg-slate-400';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/10">
      <div className={`h-full rounded-full transition-all ${fill}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function trackProgress(track: FlowxEnrollmentTrack | null | undefined): number {
  if (!track) return 0;
  if (typeof track.progress_percentage === 'number' && track.progress_percentage > 0) {
    return track.progress_percentage;
  }
  const tasks = track.tasks ?? [];
  if (!tasks.length) return 0;
  const done = tasks.filter(t => t.kanban_status === 'approved').length;
  return (done / tasks.length) * 100;
}

function ContextCard({
  slot,
  code,
  title,
  status,
  progress,
  empty,
  onClick,
  active,
}: {
  slot: 'Previous' | 'Current' | 'Next';
  code?: string;
  title?: string;
  status?: FlowxLifecycleStatus;
  progress?: number;
  empty?: string;
  onClick?: () => void;
  active?: boolean;
}) {
  const isCurrent = slot === 'Current';
  const body = empty ? (
    <p className="mt-2 text-xs text-text-muted">{empty}</p>
  ) : (
    <>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {code ? (
          <span className="text-xs font-bold tabular-nums text-text-muted">{code}</span>
        ) : null}
        {status ? <StatusPill status={status} /> : null}
      </div>
      <p className={`mt-1 line-clamp-2 text-sm font-semibold leading-snug ${isCurrent ? 'text-text-main' : 'text-text-main/90'}`}>
        {title}
      </p>
      {typeof progress === 'number' ? (
        <div className="mt-2 space-y-1">
          <ProgressBar value={progress} tone={status} />
          <p className="text-[10px] font-semibold tabular-nums text-text-muted">{Math.round(progress)}%</p>
        </div>
      ) : null}
    </>
  );

  const className = `rounded-xl border px-3 py-2.5 text-left transition ${
    isCurrent
      ? 'border-accent bg-accent/5 ring-2 ring-accent/20'
      : active
        ? 'border-border-subtle bg-card hover:border-accent/40 hover:bg-accent/5'
        : 'border-dashed border-border-subtle bg-surface-bg/50'
  }`;

  if (onClick && !empty) {
    return (
      <button type="button" onClick={onClick} className={className}>
        <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">{slot}</p>
        {body}
      </button>
    );
  }
  return (
    <div className={className}>
      <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">{slot}</p>
      {body}
    </div>
  );
}

type JourneyPathNavigatorProps = {
  stages: VisibleStage[];
  tracks: FlowxEnrollmentTrack[];
  currentStageKey: FlowxStageKey;
  viewStageKey: FlowxStageKey;
  activeTrackId?: string | null;
  enrollmentStages?: { stage_key: FlowxStageKey; label: string; position_index: number; is_hidden?: boolean }[] | null;
  onSelectStage: (key: FlowxStageKey) => void;
  onSelectTrack: (trackId: string) => void;
  headerExtra?: ReactNode;
};

export default function JourneyPathNavigator({
  stages,
  tracks,
  currentStageKey,
  viewStageKey,
  activeTrackId,
  enrollmentStages,
  onSelectStage,
  onSelectTrack,
  headerExtra,
}: JourneyPathNavigatorProps) {
  const stageIdx = Math.max(
    0,
    stages.findIndex(s => s.key === viewStageKey)
  );
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;
  const currStage = stages[stageIdx] || stages[0];
  const nextStage = stageIdx < stages.length - 1 ? stages[stageIdx + 1] : null;

  const stageTracks = orderedStageTracks(tracks, viewStageKey);
  const activeTrack =
    stageTracks.find(t => t.id === activeTrackId) || stageTracks[0] || null;
  const trackIdx = activeTrack
    ? Math.max(0, stageTracks.findIndex(t => t.id === activeTrack.id))
    : 0;
  const prevTrack = trackIdx > 0 ? stageTracks[trackIdx - 1] : null;
  const nextTrack = trackIdx < stageTracks.length - 1 ? stageTracks[trackIdx + 1] : null;

  const processCode = (key: FlowxStageKey) => String(processNumber(key, enrollmentStages) || '');
  const subCode = (track: FlowxEnrollmentTrack) =>
    hierarchyCodes(tracks, viewStageKey, track.id, undefined, enrollmentStages)?.subProcess;

  const journeyDone = stages.filter(
    s => processLifecycle(tracks, s.key, currentStageKey, enrollmentStages) === 'complete'
  ).length;
  const journeyPct = stages.length ? (journeyDone / stages.length) * 100 : 0;
  const journeyTone = processLifecycle(tracks, viewStageKey, currentStageKey, enrollmentStages);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-border-subtle bg-card px-4 py-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
              Journey progress
            </p>
            <p className="text-sm font-semibold text-text-main">
              {journeyDone} of {stages.length} processes complete
            </p>
          </div>
          {headerExtra}
        </div>
        <div className="mt-2 space-y-1.5">
          <ProgressBar value={journeyPct} tone={journeyTone} />
          <div className="flex gap-1 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {stages.map((stage, i) => {
              const life = processLifecycle(tracks, stage.key, currentStageKey, enrollmentStages);
              const selected = stage.key === viewStageKey;
              return (
                <button
                  key={stage.key}
                  type="button"
                  title={stage.label}
                  onClick={() => onSelectStage(stage.key)}
                  className={`min-w-[2.25rem] flex-1 rounded-md border px-1 py-1 text-center transition ${
                    selected ? 'ring-2 ring-accent/30' : ''
                  } ${lifecycleBorderClass(life)}`}
                >
                  <span className="block text-[10px] font-bold tabular-nums">{i + 1}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border-subtle bg-card p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
            Process path · previous / current / next
          </p>
          <div className="flex gap-1">
            <button
              type="button"
              disabled={!prevStage}
              onClick={() => prevStage && onSelectStage(prevStage.key)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-muted disabled:opacity-40"
            >
              <ArrowLeft size={12} /> Prev
            </button>
            <button
              type="button"
              disabled={!nextStage}
              onClick={() => nextStage && onSelectStage(nextStage.key)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-muted disabled:opacity-40"
            >
              Next <ArrowRight size={12} />
            </button>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          <ContextCard
            slot="Previous"
            code={prevStage ? processCode(prevStage.key) : undefined}
            title={prevStage?.label}
            status={
              prevStage
                ? processLifecycle(tracks, prevStage.key, currentStageKey, enrollmentStages)
                : undefined
            }
            empty={prevStage ? undefined : 'Start of journey'}
            onClick={prevStage ? () => onSelectStage(prevStage.key) : undefined}
            active={Boolean(prevStage)}
          />
          <ContextCard
            slot="Current"
            code={currStage ? processCode(currStage.key) : undefined}
            title={currStage?.label}
            status={
              currStage
                ? processLifecycle(tracks, currStage.key, currentStageKey, enrollmentStages)
                : undefined
            }
            progress={
              currStage
                ? (() => {
                    const ts = orderedStageTracks(tracks, currStage.key);
                    if (!ts.length) return journeyTone === 'complete' ? 100 : 0;
                    return ts.reduce((s, t) => s + trackProgress(t), 0) / ts.length;
                  })()
                : 0
            }
          />
          <ContextCard
            slot="Next"
            code={nextStage ? processCode(nextStage.key) : undefined}
            title={nextStage?.label}
            status={
              nextStage
                ? processLifecycle(tracks, nextStage.key, currentStageKey, enrollmentStages)
                : undefined
            }
            empty={nextStage ? undefined : 'End of journey'}
            onClick={nextStage ? () => onSelectStage(nextStage.key) : undefined}
            active={Boolean(nextStage)}
          />
        </div>
      </div>

      <div className="rounded-2xl border border-border-subtle bg-card p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
            Sub-process path · previous / current / next
          </p>
          <div className="flex gap-1">
            <button
              type="button"
              disabled={!prevTrack}
              onClick={() => prevTrack && onSelectTrack(prevTrack.id)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-muted disabled:opacity-40"
            >
              <ArrowLeft size={12} /> Prev
            </button>
            <button
              type="button"
              disabled={!nextTrack}
              onClick={() => nextTrack && onSelectTrack(nextTrack.id)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-muted disabled:opacity-40"
            >
              Next <ArrowRight size={12} />
            </button>
          </div>
        </div>
        {stageTracks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border-subtle px-3 py-4 text-center text-xs text-text-muted">
            No sub-processes on this process yet
          </p>
        ) : (
          <div className="grid gap-2 md:grid-cols-3">
            <ContextCard
              slot="Previous"
              code={prevTrack ? subCode(prevTrack) : undefined}
              title={prevTrack?.track_label}
              status={prevTrack ? subProcessLifecycle(prevTrack) : undefined}
              progress={prevTrack ? trackProgress(prevTrack) : undefined}
              empty={prevTrack ? undefined : 'First sub-process'}
              onClick={prevTrack ? () => onSelectTrack(prevTrack.id) : undefined}
              active={Boolean(prevTrack)}
            />
            <ContextCard
              slot="Current"
              code={activeTrack ? subCode(activeTrack) : undefined}
              title={activeTrack?.track_label}
              status={activeTrack ? subProcessLifecycle(activeTrack) : undefined}
              progress={activeTrack ? trackProgress(activeTrack) : 0}
            />
            <ContextCard
              slot="Next"
              code={nextTrack ? subCode(nextTrack) : undefined}
              title={nextTrack?.track_label}
              status={nextTrack ? subProcessLifecycle(nextTrack) : undefined}
              progress={nextTrack ? trackProgress(nextTrack) : undefined}
              empty={nextTrack ? undefined : 'Last sub-process in this process'}
              onClick={nextTrack ? () => onSelectTrack(nextTrack.id) : undefined}
              active={Boolean(nextTrack)}
            />
          </div>
        )}

        {stageTracks.length > 1 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {stageTracks.map((track, i) => {
              const life = subProcessLifecycle(track);
              const selected = track.id === activeTrack?.id;
              return (
                <button
                  key={track.id}
                  type="button"
                  onClick={() => onSelectTrack(track.id)}
                  className={`inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-left text-xs font-semibold transition ${
                    selected ? 'ring-2 ring-accent/25' : ''
                  } ${lifecycleBorderClass(life)}`}
                >
                  <span className="tabular-nums opacity-70">
                    {processCode(viewStageKey)}.{i + 1}
                  </span>
                  <span className="truncate">{track.track_label}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function taskStatusLabel(task: FlowxTask): string {
  if (task.sla_status === 'breached') return 'Delayed';
  if (task.sla_status === 'amber') return 'At risk';
  if (task.kanban_status === 'approved') return 'Complete';
  if (task.kanban_status === 'in_progress' || task.kanban_status === 'in_review') return 'In progress';
  if (task.kanban_status === 'blocked') return 'Blocked';
  return 'Planned';
}
