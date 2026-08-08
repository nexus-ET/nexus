import { forwardRef, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { GripVertical, Link2 } from 'lucide-react';
import type {
  FlowxEnrollmentLink,
  FlowxEnrollmentStageMeta,
  FlowxEnrollmentTrack,
  FlowxIntakeBooking,
  FlowxStageKey,
  FlowxTask,
} from '../../types/flowx';
import {
  childTasksOfTemplate,
  delayedBrickClass,
  lifecycleBorderClass,
  lifecycleLabel,
  orderedStageTracks,
  processNumber,
  topLevelStageTasks,
  visibleJourneyStages,
  type FlowxLifecycleStatus,
} from '../../utils/flowxHierarchy';
import {
  brickLifecycle,
  intakeDelayDisplay,
  isIntakeSessionTask,
  processProgressPercentage,
  stageLifecycleFromBricks,
  subprocessLifecycle,
  subprocessProgressPercentage,
} from '../../utils/flowxIntakeSession';

type JourneyProcessFlowProps = {
  currentStageKey: FlowxStageKey;
  viewStageKey: FlowxStageKey;
  tracks: FlowxEnrollmentTrack[];
  stages?: FlowxEnrollmentStageMeta[];
  links?: FlowxEnrollmentLink[];
  /** Selected sub-process brick (Master task template title), not internal track. */
  activeTaskId?: string | null;
  pending?: boolean;
  intakeBooking?: FlowxIntakeBooking | null;
  onViewIntakeSession?: () => void;
  onSelectStage: (stageKey: FlowxStageKey) => void;
  /** Called with the clicked brick task id (top-level or nested). */
  onSelectSubprocess?: (taskId: string) => void;
  onReorderTrack?: (trackId: string, positionIndex: number) => void;
  onReorderChild?: (taskId: string, positionIndex: number) => void;
};

type StageBrick = {
  track: FlowxEnrollmentTrack;
  task: FlowxTask;
  brickIndex: number;
  children: StageBrick[];
};

type BranchOverlay = {
  parentToBus: string | null;
  bus: string | null;
  drops: string[];
  childLinks: {
    id: string;
    d: string;
    labelX: number;
    labelY: number;
    linkType: FlowxEnrollmentLink['link_type'];
    label: string;
  }[];
  height: number;
};

function FlowArrow({
  label,
  dashed,
  alignTop,
}: {
  label?: string;
  dashed?: boolean;
  alignTop?: boolean;
}) {
  return (
    <div
      className={`flex w-8 shrink-0 flex-col items-center justify-center text-text-muted ${
        alignTop ? 'self-start pt-5' : 'self-center'
      }`}
      aria-hidden
    >
      <svg width="32" height="12" viewBox="0 0 32 12">
        <line
          x1="0"
          y1="6"
          x2="22"
          y2="6"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray={dashed ? '4 3' : undefined}
        />
        <polygon points="22,2 32,6 22,10" fill="currentColor" />
      </svg>
      {label ? (
        <span className="mt-0.5 text-[8px] font-semibold uppercase tracking-wide">{label}</span>
      ) : null}
    </div>
  );
}

const StageBox = forwardRef<
  HTMLButtonElement,
  {
    processCode: string;
    label: string;
    lifecycle: FlowxLifecycleStatus;
    progressPercentage?: number | null;
    viewing: boolean;
    /** Accent blue fill when this process has nested sub-process bricks. */
    hasNestedChildren?: boolean;
    disabled?: boolean;
    onClick: () => void;
    compact?: boolean;
  }
>(function StageBox(
  { processCode, label, lifecycle, progressPercentage, viewing, hasNestedChildren, disabled, onClick, compact },
  ref
) {
  const nested = Boolean(hasNestedChildren);
  const isDelayed = lifecycle === 'delayed';
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`${compact ? 'w-[7.75rem] px-2.5 py-2' : 'w-[8.75rem] px-2.5 py-2.5'} relative shrink-0 rounded-xl border-2 text-center transition hover:brightness-[0.98] disabled:opacity-60 ${
        isDelayed
          ? delayedBrickClass()
          : nested
            ? 'border-accent bg-accent text-text-dark-bg'
            : lifecycleBorderClass(lifecycle)
      } ${viewing ? 'ring-2 ring-offset-1 ring-accent/35' : ''}`}
    >
      {isDelayed ? (
        <span className="absolute -right-1 -top-2 rounded bg-red-600 px-1.5 py-0.5 text-[8px] font-extrabold uppercase tracking-wide text-white shadow">
          Delayed
        </span>
      ) : null}
      <p
        className={`text-[9px] font-semibold uppercase tracking-wide ${
          isDelayed ? 'text-red-800/80' : nested ? 'text-text-dark-bg/75' : 'text-text-muted'
        }`}
      >
        Process {processCode}
      </p>
      <p className="mt-0.5 text-[13px] font-bold uppercase leading-snug tracking-wide">{label}</p>
      <p
        className={`mt-0.5 text-[9px] font-semibold capitalize ${
          isDelayed ? 'text-red-800' : nested ? 'text-text-dark-bg/80' : 'text-text-muted'
        }`}
      >
        {lifecycleLabel(lifecycle)}
        {typeof progressPercentage === 'number' ? ` · ${Math.round(progressPercentage)}%` : ''}
      </p>
    </button>
  );
});

function SubprocessCard({
  brick,
  processCode,
  selected,
  linked,
  canReorder,
  dragChildId,
  linkedTaskIds,
  intakeBooking,
  onViewSession,
  onSelectSubprocess,
  onReorderChild,
  setDragChildId,
  cardRef,
}: {
  brick: StageBrick;
  processCode: string;
  selected: boolean;
  linked: boolean;
  canReorder: boolean;
  dragChildId: string | null;
  linkedTaskIds: Set<string>;
  intakeBooking?: FlowxIntakeBooking | null;
  onViewSession?: () => void;
  onSelectSubprocess?: (taskId: string) => void;
  onReorderChild?: (taskId: string, positionIndex: number) => void;
  setDragChildId: (id: string | null) => void;
  cardRef?: (el: HTMLDivElement | null) => void;
}) {
  const { task, brickIndex, children } = brick;
  const subCode = `${processCode}.${brickIndex + 1}`;
  const isIntakeSession = isIntakeSessionTask(task);
  const childTasks = children.map(c => c.task);
  const life = brickLifecycle(task, childTasks, intakeBooking);
  const progressPct = subprocessProgressPercentage(task, intakeBooking);
  const bookingStatusLabel =
    intakeBooking?.status_stage_name || intakeBooking?.booking_status || null;
  const delayDisplay = isIntakeSession ? intakeDelayDisplay(intakeBooking, task) : null;
  const hasNested = children.length > 0;
  const isDelayed = life === 'delayed';
  const selfDelayed = subprocessLifecycle(task, intakeBooking) === 'delayed';
  // Delayed always wins visually — never hide behind nested accent fill.
  const modeClass = isDelayed
    ? delayedBrickClass()
    : hasNested
      ? 'border-accent bg-accent text-text-dark-bg'
      : isIntakeSession
        ? lifecycleBorderClass(life)
        : task.is_optional
          ? 'border-amber-400 bg-amber-50/80'
          : linked
            ? 'border-emerald-500 bg-emerald-50/70'
            : 'border-border-subtle bg-card';

  return (
    <div
      ref={cardRef}
      role="button"
      tabIndex={0}
      draggable={canReorder}
      onDragStart={e => {
        if (!canReorder) return;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', task.id);
        setDragChildId(task.id);
      }}
      onDragEnd={() => setDragChildId(null)}
      onDragOver={e => {
        if (!canReorder || !dragChildId || dragChildId === task.id) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      }}
      onDrop={e => {
        e.preventDefault();
        if (!onReorderChild || !dragChildId || dragChildId === task.id) {
          setDragChildId(null);
          return;
        }
        onReorderChild(dragChildId, task.position_index);
        setDragChildId(null);
      }}
      onClick={() => onSelectSubprocess?.(task.id)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelectSubprocess?.(task.id);
        }
      }}
      className={`relative w-[9rem] shrink-0 rounded-xl border-2 px-2.5 py-2 text-center shadow-sm transition ${modeClass} ${
        selected ? 'ring-2 ring-offset-1 ring-accent/40' : ''
      } ${canReorder ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'} ${
        dragChildId === task.id ? 'opacity-50' : ''
      }`}
    >
      {isDelayed ? (
        <span className="absolute -right-1 -top-2 rounded bg-red-600 px-1.5 py-0.5 text-[8px] font-extrabold uppercase tracking-wide text-white shadow">
          Delayed
        </span>
      ) : null}
      <div className="mb-0.5 flex items-center justify-center gap-1">
        {canReorder ? (
          <GripVertical
            className={`h-3.5 w-3.5 shrink-0 ${
              isDelayed
                ? 'text-red-700/70'
                : hasNested
                  ? 'text-text-dark-bg/70'
                  : 'text-text-muted'
            }`}
            aria-hidden
          />
        ) : null}
        <p
          className={`text-[9px] font-semibold uppercase tracking-wide ${
            isDelayed
              ? 'text-red-800/80'
              : hasNested
                ? 'text-text-dark-bg/75'
                : 'text-text-muted'
          }`}
        >
          Sub-process {subCode}
        </p>
      </div>
      <p
        className={`text-[13px] font-bold leading-snug ${
          isDelayed ? 'text-red-950' : hasNested ? '' : 'text-text-main'
        }`}
      >
        {task.title}
      </p>
      {selfDelayed ? (
        <p className="mt-0.5 text-[8px] font-extrabold uppercase tracking-wide text-red-700">
          Causing delay
        </p>
      ) : null}
      {isIntakeSession && bookingStatusLabel ? (
        <p
          className={`mt-1 text-[10px] font-bold leading-snug ${
            isDelayed ? 'text-red-800' : hasNested ? 'text-sky-100' : 'text-accent'
          }`}
        >
          {bookingStatusLabel}
        </p>
      ) : null}
      {delayDisplay ? (
        <p className="mt-0.5 text-[9px] font-extrabold leading-snug text-red-800">{delayDisplay}</p>
      ) : isDelayed ? (
        <p className="mt-0.5 text-[9px] font-extrabold leading-snug text-red-800">Action overdue</p>
      ) : null}
      <div className="mt-1 flex flex-wrap items-center justify-center gap-1">
        {task.is_optional ? (
          <span className="rounded border border-amber-300 bg-amber-100 px-1 text-[8px] font-bold text-amber-900">
            Optional
          </span>
        ) : (
          <span
            className={`rounded border px-1 text-[8px] font-bold ${
              isDelayed
                ? 'border-red-300 bg-red-100 text-red-900'
                : hasNested
                  ? 'border-white/30 bg-white/15 text-text-dark-bg'
                  : 'border-border-subtle bg-surface-bg text-text-muted'
            }`}
          >
            Required
          </span>
        )}
        {linked ? (
          <span className="inline-flex items-center gap-0.5 rounded border border-emerald-300 bg-emerald-100 px-1 text-[8px] font-bold text-emerald-800">
            <Link2 size={10} /> Linked
          </span>
        ) : null}
        <span
          className={`text-[9px] font-bold capitalize ${
            isDelayed
              ? 'text-red-800'
              : hasNested
                ? 'text-text-dark-bg/80'
                : 'text-text-muted'
          }`}
        >
          {lifecycleLabel(life)}
          {` · ${Math.round(progressPct)}%`}
        </span>
      </div>
      {isIntakeSession && onViewSession ? (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            onViewSession();
          }}
          className={`mt-1.5 w-full rounded-md border px-1.5 py-1 text-[9px] font-bold transition ${
            isDelayed
              ? 'border-red-400 bg-red-600 text-white hover:bg-red-700'
              : hasNested
                ? 'border-white/35 bg-white/15 text-text-dark-bg hover:bg-white/25'
                : 'border-accent/30 bg-accent/10 text-accent hover:bg-accent/15'
          }`}
        >
          View Session
        </button>
      ) : null}
      {children.length > 0 ? (
        <div
          className={`mt-1.5 space-y-1 border-t pt-1.5 ${
            isDelayed ? 'border-red-300/70' : 'border-white/25'
          }`}
        >
          <p
            className={`text-[8px] font-bold uppercase tracking-wide ${
              isDelayed ? 'text-red-800/80' : 'text-text-dark-bg/75'
            }`}
          >
            Nested ({children.length})
          </p>
          {children.map(child => {
            const childLife = subprocessLifecycle(child.task, intakeBooking);
            const childDelayed = childLife === 'delayed';
            const childCode = `${subCode}.${child.brickIndex + 1}`;
            const childDelay = isIntakeSessionTask(child.task)
              ? intakeDelayDisplay(intakeBooking, child.task)
              : null;
            return (
              <button
                key={child.task.id}
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  onSelectSubprocess?.(child.task.id);
                }}
                className={`relative w-full rounded-lg border px-1.5 py-1 text-center transition hover:brightness-[0.98] ${
                  childDelayed
                    ? delayedBrickClass()
                    : linkedTaskIds.has(child.task.id)
                      ? 'border-emerald-300 bg-emerald-50/90 text-text-main'
                      : isDelayed
                        ? 'border-red-300 bg-white/70 text-red-950'
                        : 'border-white/30 bg-white/15'
                }`}
              >
                {childDelayed ? (
                  <span className="absolute -right-1 -top-1.5 rounded bg-red-600 px-1 py-0.5 text-[7px] font-extrabold uppercase tracking-wide text-white shadow">
                    Delayed
                  </span>
                ) : null}
                <p className="text-[8px] font-semibold uppercase tracking-wide opacity-80">
                  {childCode}
                </p>
                <p className="text-xs font-bold leading-snug">{child.task.title}</p>
                {childDelayed ? (
                  <p className="mt-0.5 text-[7px] font-extrabold uppercase tracking-wide text-red-700">
                    Causing delay
                  </p>
                ) : null}
                {childDelay ? (
                  <p className="mt-0.5 text-[7px] font-bold leading-snug text-red-800">{childDelay}</p>
                ) : null}
                <p
                  className={`mt-0.5 text-[8px] font-semibold capitalize ${
                    childDelayed ? 'text-red-800' : 'opacity-80'
                  }`}
                >
                  {lifecycleLabel(childLife)}
                  {` · ${subprocessProgressPercentage(child.task, intakeBooking)}%`}
                </p>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Centered process-flow map: main processes on a centered rail, then a dedicated
 * branch from the active process into its sub-processes with tree + sibling arrows.
 */
export default function JourneyProcessFlow({
  currentStageKey: _currentStageKey,
  viewStageKey,
  tracks,
  stages,
  links = [],
  activeTaskId,
  pending,
  intakeBooking,
  onViewIntakeSession,
  onSelectStage,
  onSelectSubprocess,
  onReorderTrack: _onReorderTrack,
  onReorderChild,
}: JourneyProcessFlowProps) {
  const visibleStages = useMemo(() => visibleJourneyStages(stages), [stages]);
  const stageTracks = useMemo(
    () => orderedStageTracks(tracks, viewStageKey),
    [tracks, viewStageKey]
  );
  const trackByTaskId = useMemo(() => {
    const map = new Map<string, FlowxEnrollmentTrack>();
    for (const track of stageTracks) {
      for (const task of track.tasks ?? []) map.set(task.id, track);
    }
    return map;
  }, [stageTracks]);

  const stageBricks = useMemo(() => {
    const tops = topLevelStageTasks(tracks, viewStageKey);
    const out: StageBrick[] = [];
    tops.forEach((task, brickIndex) => {
      const track = trackByTaskId.get(task.id);
      if (!track) return;
      const nested = childTasksOfTemplate(tracks, viewStageKey, task.template_id)
        .map((child, childIdx) => {
          const childTrack = trackByTaskId.get(child.id);
          if (!childTrack) return null;
          return {
            track: childTrack,
            task: child,
            brickIndex: childIdx,
            children: [] as StageBrick[],
          };
        })
        .filter((b): b is StageBrick => Boolean(b));
      out.push({ track, task, brickIndex, children: nested });
    });
    if (out.length === 0) {
      let i = 0;
      for (const track of stageTracks) {
        for (const task of [...(track.tasks ?? [])].sort(
          (a, b) => a.position_index - b.position_index
        )) {
          out.push({ track, task, brickIndex: i, children: [] });
          i += 1;
        }
      }
    }
    return out;
  }, [tracks, viewStageKey, trackByTaskId, stageTracks]);

  const brickByTaskId = useMemo(() => {
    const map = new Map<string, StageBrick>();
    for (const brick of stageBricks) {
      map.set(brick.task.id, brick);
      for (const child of brick.children) map.set(child.task.id, child);
    }
    return map;
  }, [stageBricks]);

  const stageLocalLinks = useMemo(
    () =>
      links.filter(
        link =>
          Boolean(link.from_task_id && brickByTaskId.has(link.from_task_id)) &&
          Boolean(link.to_task_id && brickByTaskId.has(link.to_task_id))
      ),
    [links, brickByTaskId]
  );

  const linkedTaskIds = useMemo(() => {
    const set = new Set<string>();
    for (const link of links) {
      if (link.from_task_id && brickByTaskId.has(link.from_task_id)) set.add(link.from_task_id);
      if (link.to_task_id && brickByTaskId.has(link.to_task_id)) set.add(link.to_task_id);
    }
    return set;
  }, [links, brickByTaskId]);

  const processCode = String(processNumber(viewStageKey, stages) || '');
  const stageMeta = visibleStages.find(s => s.key === viewStageKey);
  const viewLifecycle = useMemo(
    () => stageLifecycleFromBricks(tracks, viewStageKey, intakeBooking),
    [tracks, viewStageKey, intakeBooking]
  );
  const stagesWithNested = useMemo(() => {
    const set = new Set<string>();
    for (const stage of visibleStages) {
      const hasNested =
        topLevelStageTasks(tracks, stage.key).length > 0 ||
        orderedStageTracks(tracks, stage.key).length > 0;
      if (hasNested) set.add(stage.key);
    }
    return set;
  }, [visibleStages, tracks]);
  const nextStage = (() => {
    const idx = visibleStages.findIndex(s => s.key === viewStageKey);
    return idx >= 0 && idx < visibleStages.length - 1 ? visibleStages[idx + 1] : null;
  })();

  const [dragChildId, setDragChildId] = useState<string | null>(null);
  const canReorderChildren = Boolean(onReorderChild) && stageBricks.length > 1;

  const branchRef = useRef<HTMLDivElement>(null);
  const parentRef = useRef<HTMLButtonElement>(null);
  const childrenRowRef = useRef<HTMLDivElement>(null);
  const brickElRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [overlay, setOverlay] = useState<BranchOverlay>({
    parentToBus: null,
    bus: null,
    drops: [],
    childLinks: [],
    height: 0,
  });

  useLayoutEffect(() => {
    const branch = branchRef.current;
    const parent = parentRef.current;
    if (!branch || !parent) {
      setOverlay({
        parentToBus: null,
        bus: null,
        drops: [],
        childLinks: [],
        height: 0,
      });
      return;
    }

    const measure = () => {
      const root = branch.getBoundingClientRect();
      const parentRect = parent.getBoundingClientRect();
      const parentX = parentRect.left + parentRect.width / 2 - root.left;
      const parentBottom = parentRect.bottom - root.top;

      const childCenters: {
        id: string;
        x: number;
        top: number;
        bottom: number;
      }[] = [];
      for (const brick of stageBricks) {
        const el = brickElRefs.current.get(brick.task.id);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        childCenters.push({
          id: brick.task.id,
          x: r.left + r.width / 2 - root.left,
          top: r.top - root.top,
          bottom: r.bottom - root.top,
        });
      }

      let parentToBus: string | null = null;
      let bus: string | null = null;
      const drops: string[] = [];

      if (childCenters.length === 1) {
        const c = childCenters[0];
        parentToBus = `M ${parentX} ${parentBottom} L ${parentX} ${(parentBottom + c.top) / 2} L ${c.x} ${(parentBottom + c.top) / 2} L ${c.x} ${c.top}`;
      } else if (childCenters.length > 1) {
        const minX = Math.min(...childCenters.map(c => c.x));
        const maxX = Math.max(...childCenters.map(c => c.x));
        const childTop = Math.min(...childCenters.map(c => c.top));
        const busY = Math.max(parentBottom + 18, childTop - 22);
        parentToBus = `M ${parentX} ${parentBottom} L ${parentX} ${busY}`;
        bus = `M ${minX} ${busY} L ${maxX} ${busY}`;
        for (const child of childCenters) {
          drops.push(`M ${child.x} ${busY} L ${child.x} ${child.top}`);
        }
      }

      // Explicit depends_on / related links only — avoid drawing when adjacent
      // siblings already share the horizontal sequence arrow in the row.
      const adjacentPairs = new Set<string>();
      for (let i = 0; i < stageBricks.length - 1; i += 1) {
        adjacentPairs.add(`${stageBricks[i].task.id}->${stageBricks[i + 1].task.id}`);
        adjacentPairs.add(`${stageBricks[i + 1].task.id}->${stageBricks[i].task.id}`);
      }

      const childLinks: BranchOverlay['childLinks'] = [];
      let linkDepth = 0;
      for (const link of stageLocalLinks) {
        if (
          link.from_task_id &&
          link.to_task_id &&
          adjacentPairs.has(`${link.from_task_id}->${link.to_task_id}`)
        ) {
          continue;
        }
        const from = childCenters.find(c => c.id === link.from_task_id);
        const to = childCenters.find(c => c.id === link.to_task_id);
        if (!from || !to) continue;
        linkDepth += 1;
        const yBase = Math.max(from.bottom, to.bottom) + 10;
        const yCurve = yBase + 14 + linkDepth * 16;
        childLinks.push({
          id: link.id,
          d: `M ${from.x} ${from.bottom} C ${from.x} ${yCurve}, ${to.x} ${yCurve}, ${to.x} ${to.bottom}`,
          labelX: (from.x + to.x) / 2,
          labelY: yCurve - 5,
          linkType: link.link_type,
          label: link.link_type === 'depends_on' ? 'depends on' : 'related',
        });
      }

      const childrenRow = childrenRowRef.current;
      const contentBottom = Math.max(
        parentBottom,
        ...childCenters.map(c => c.bottom),
        ...childLinks.map(l => l.labelY + 16),
        childrenRow ? childrenRow.getBoundingClientRect().bottom - root.top : 0
      );

      setOverlay({
        parentToBus,
        bus,
        drops,
        childLinks,
        height: contentBottom + 12,
      });
    };

    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => measure()) : null;
    ro?.observe(branch);
    if (childrenRowRef.current) ro?.observe(childrenRowRef.current);
    window.addEventListener('resize', measure);
    // Remeasure after fonts/layout settle
    const t = window.setTimeout(measure, 50);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', measure);
      window.clearTimeout(t);
    };
  }, [stageBricks, stageLocalLinks, viewStageKey, nextStage]);

  return (
    <div className="space-y-3 rounded-xl border border-border-subtle bg-card p-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Process flow map
          </p>
          <p className="text-xs text-text-muted">
            Select a process to see its sub-processes linked underneath
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5 text-[9px] font-semibold text-text-muted">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm border-2 border-slate-300 bg-card" /> Planned
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm border-2 border-sky-500 bg-sky-50" /> In progress
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm border-2 border-red-600 bg-red-50" /> Delayed
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm border-2 border-emerald-500 bg-emerald-50" /> Complete
          </span>
        </div>
      </div>

      {/* Centered main process rail */}
      <div className="overflow-x-auto rounded-lg border border-dashed border-border-subtle bg-surface-bg/40 p-2.5">
        <div className="mx-auto flex w-max min-w-full items-stretch justify-center gap-0 px-0.5 py-1.5">
          <div className="flex w-12 shrink-0 flex-col items-center justify-center self-center">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-emerald-400 bg-emerald-50 text-[9px] font-bold text-emerald-800">
              Start
            </div>
          </div>
          <FlowArrow />
          {visibleStages.map((stage, idx) => {
            const lifecycle = stageLifecycleFromBricks(tracks, stage.key, intakeBooking);
            const code = String(idx + 1);
            const viewing = viewStageKey === stage.key;
            const stageProgress = processProgressPercentage(
              topLevelStageTasks(tracks, stage.key),
              intakeBooking
            );
            return (
              <div key={stage.key} className="flex items-stretch">
                <StageBox
                  processCode={code}
                  label={stage.label}
                  lifecycle={lifecycle}
                  progressPercentage={stageProgress}
                  viewing={viewing}
                  hasNestedChildren={stagesWithNested.has(stage.key)}
                  disabled={pending}
                  onClick={() => onSelectStage(stage.key)}
                  compact
                />
                {idx < visibleStages.length - 1 ? <FlowArrow label="next" /> : null}
              </div>
            );
          })}
          <FlowArrow />
          <div className="flex w-12 shrink-0 flex-col items-center justify-center self-center">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-border-subtle bg-surface-bg text-[9px] font-bold text-text-muted">
              End
            </div>
          </div>
        </div>
      </div>

      {/* Branch: parent process centered on screen; sub-processes + Next adjacent in one centered row */}
      <div className="overflow-x-auto rounded-lg border border-border-subtle bg-surface-bg/30 p-2.5">
        <div
          ref={branchRef}
          className="relative flex w-full flex-col items-center"
          style={{ minHeight: overlay.height || undefined }}
        >
          <svg
            className="pointer-events-none absolute inset-0 overflow-visible"
            width="100%"
            height="100%"
            aria-hidden
          >
            <defs>
              <marker
                id="flowx-branch-arrow"
                markerWidth="7"
                markerHeight="7"
                refX="5.5"
                refY="2.75"
                orient="auto"
              >
                <path d="M0,0 L5.5,2.75 L0,5.5 Z" fill="#322f86" />
              </marker>
              <marker
                id="flowx-branch-arrow-link"
                markerWidth="7"
                markerHeight="7"
                refX="5.5"
                refY="2.75"
                orient="auto"
              >
                <path d="M0,0 L5.5,2.75 L0,5.5 Z" fill="#059669" />
              </marker>
            </defs>

            {overlay.parentToBus ? (
              <path
                d={overlay.parentToBus}
                fill="none"
                stroke="#322f86"
                strokeWidth="2.15"
                markerEnd={stageBricks.length === 1 ? 'url(#flowx-branch-arrow)' : undefined}
              />
            ) : null}
            {overlay.bus ? (
              <path d={overlay.bus} fill="none" stroke="#322f86" strokeWidth="2.15" />
            ) : null}
            {overlay.drops.map((d, idx) => (
              <path
                key={`drop-${idx}`}
                d={d}
                fill="none"
                stroke="#322f86"
                strokeWidth="2.15"
                markerEnd="url(#flowx-branch-arrow)"
              />
            ))}
            {overlay.childLinks.map(path => (
              <g key={path.id}>
                <path
                  d={path.d}
                  fill="none"
                  stroke={path.linkType === 'depends_on' ? '#059669' : '#0d9488'}
                  strokeWidth="1.85"
                  strokeDasharray={path.linkType === 'related' ? '5 4' : '6 3'}
                  markerEnd="url(#flowx-branch-arrow-link)"
                />
                <foreignObject x={path.labelX - 36} y={path.labelY - 9} width="72" height="16">
                  <div className="flex justify-center">
                    <span className="rounded-full border border-emerald-300 bg-emerald-50 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-emerald-800 shadow-sm">
                      {path.label}
                    </span>
                  </div>
                </foreignObject>
              </g>
            ))}
          </svg>

          <p className="mb-1.5 w-full text-center text-[10px] font-semibold text-text-muted">
            Branching from Process {processCode}
            {stageMeta?.label ? ` · ${stageMeta.label}` : ''}
          </p>

          <div className="flex w-full justify-center">
            <StageBox
              ref={parentRef}
              processCode={processCode || '—'}
              label={stageMeta?.label || viewStageKey}
              lifecycle={viewLifecycle}
              progressPercentage={processProgressPercentage(
                topLevelStageTasks(tracks, viewStageKey),
                intakeBooking
              )}
              viewing
              hasNestedChildren={stageBricks.length > 0}
              disabled={pending}
              onClick={() => onSelectStage(viewStageKey)}
            />
          </div>

          <div
            ref={childrenRowRef}
            className="mx-auto mt-9 flex w-max max-w-none items-start justify-center gap-0 px-1"
            style={{
              paddingBottom: stageLocalLinks.length > 0 ? 22 + stageLocalLinks.length * 14 : 8,
            }}
          >
            {stageBricks.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border-subtle bg-card px-3 py-4 text-center text-xs text-text-muted">
                No sub-processes on this process yet.
              </p>
            ) : (
              stageBricks.map((brick, i) => (
                <div key={brick.task.id} className="flex items-start gap-0">
                  <SubprocessCard
                    brick={brick}
                    processCode={processCode}
                    selected={
                      activeTaskId === brick.task.id ||
                      brick.children.some(c => c.task.id === activeTaskId)
                    }
                    linked={linkedTaskIds.has(brick.task.id)}
                    canReorder={canReorderChildren}
                    dragChildId={dragChildId}
                    linkedTaskIds={linkedTaskIds}
                    intakeBooking={intakeBooking}
                    onViewSession={
                      isIntakeSessionTask(brick.task) ? onViewIntakeSession : undefined
                    }
                    onSelectSubprocess={onSelectSubprocess}
                    onReorderChild={onReorderChild}
                    setDragChildId={setDragChildId}
                    cardRef={el => {
                      if (el) brickElRefs.current.set(brick.task.id, el);
                      else brickElRefs.current.delete(brick.task.id);
                    }}
                  />
                  {i < stageBricks.length - 1 ? (
                    <FlowArrow label="next" alignTop />
                  ) : null}
                </div>
              ))
            )}

            {/* Next process sits immediately after the last sub-process; top-aligned dashed connector */}
            <div className="flex items-start gap-0">
              {stageBricks.length > 0 ? <FlowArrow label="next" dashed alignTop /> : null}
              {nextStage ? (
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => onSelectStage(nextStage.key)}
                  className="w-[9.25rem] shrink-0 self-start rounded-xl border-2 border-accent bg-accent px-2.5 py-2 text-center text-text-dark-bg transition hover:brightness-95 disabled:opacity-60"
                >
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-text-dark-bg/75">
                    Next process
                  </p>
                  <p className="text-[13px] font-bold uppercase tracking-wide">
                    {visibleStages.findIndex(s => s.key === nextStage.key) + 1} {nextStage.label}
                  </p>
                </button>
              ) : stageBricks.length > 0 ? (
                <div className="w-[9.25rem] shrink-0 self-start rounded-xl border-2 border-accent bg-accent px-2.5 py-2 text-center text-text-dark-bg">
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-text-dark-bg/75">
                    Journey
                  </p>
                  <p className="text-[13px] font-bold uppercase tracking-wide">Complete</p>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
