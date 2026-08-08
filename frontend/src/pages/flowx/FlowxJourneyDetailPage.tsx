import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Map, Shield } from 'lucide-react';
import CounsellingSessionDrawer from '../../components/CounsellingSessionDrawer';
import JourneyActionDrawer from '../../components/flowx/JourneyActionDrawer';
import { taskStatusLabel } from '../../components/flowx/JourneyPathNavigator';
import JourneyProcessFlow from '../../components/flowx/JourneyProcessFlow';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import { flowxCountryHubPath } from '../../config/flowxNav';
import {
  useFlowxEnrollment,
  useFlowxOverride,
  useMoveFlowxEnrollmentTrack,
  useMoveFlowxTask,
  useReorderFlowxTask,
  useUpdateFlowxTaskChecklist,
} from '../../hooks/useFlowx';
import {
  type FlowxKanbanStatus,
  type FlowxStageKey,
  type FlowxTask,
} from '../../types/flowx';
import {
  childTasksOfTemplate,
  formatHierarchyLabel,
  hierarchyCodes,
  lifecycleBorderClass,
  lifecycleLabel,
  orderedStageTasks,
  orderedStageTracks,
  processNumber,
  topLevelStageTasks,
  visibleJourneyStages,
} from '../../utils/flowxHierarchy';
import {
  brickLifecycle,
  intakeDelayDisplay,
  isIntakeSessionTask,
  processProgressPercentage,
  resolvePriorityViewStage,
  subprocessLifecycle,
  subprocessProgressPercentage,
} from '../../utils/flowxIntakeSession';

const FlowxJourneyDetailPage: React.FC = () => {
  const { enrollmentId } = useParams<{ enrollmentId: string }>();
  const [searchParams] = useSearchParams();
  const enrollmentQuery = useFlowxEnrollment(enrollmentId || null);
  const moveMutation = useMoveFlowxTask(enrollmentId || null);
  const checklistMutation = useUpdateFlowxTaskChecklist(enrollmentId || null);
  const reorderChildMutation = useReorderFlowxTask(enrollmentId || null);
  const moveTrackMutation = useMoveFlowxEnrollmentTrack(enrollmentId || null);
  const overrideMutation = useFlowxOverride(enrollmentId || null);

  const enrollment = enrollmentQuery.data;
  const [viewStage, setViewStage] = useState<string | null>(null);
  const [selectedSubprocessId, setSelectedSubprocessId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(true);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const hubBackIso = (
    searchParams.get('fromCountry') ||
    enrollment?.country_iso2 ||
    ''
  ).toUpperCase();

  const selectedTask = useMemo(() => {
    if (!selectedTaskId || !enrollment) return null;
    for (const track of enrollment.tracks ?? []) {
      const found = (track.tasks ?? []).find(t => t.id === selectedTaskId);
      if (found) return found;
    }
    return null;
  }, [enrollment, selectedTaskId]);

  const openIntakeSessionDrawer = () => {
    setSelectedTaskId(null);
    setSessionDrawerOpen(true);
  };

  const visibleStages = useMemo(
    () => visibleJourneyStages(enrollment?.stages),
    [enrollment?.stages]
  );

  const stageKey = (viewStage || visibleStages[0]?.key || 'counselling') as FlowxStageKey;

  // Initial view: delayed → in progress → first incomplete (not current_stage_key).
  useEffect(() => {
    if (!enrollment || visibleStages.length === 0) return;
    if (viewStage != null) {
      if (!visibleStages.some(s => s.key === viewStage)) {
        setViewStage(visibleStages[0].key);
      }
      return;
    }
    const priority = resolvePriorityViewStage(
      enrollment.tracks ?? [],
      enrollment.stages,
      enrollment.intake_booking
    );
    setViewStage(priority.stageKey);
    if (priority.subprocessId) {
      setSelectedSubprocessId(priority.subprocessId);
    }
  }, [enrollment, visibleStages, viewStage]);

  const stageTracks = useMemo(
    () => orderedStageTracks(enrollment?.tracks ?? [], stageKey),
    [enrollment, stageKey]
  );

  const topLevelBricks = useMemo(
    () => topLevelStageTasks(enrollment?.tracks ?? [], stageKey),
    [enrollment?.tracks, stageKey]
  );

  const allStageTasks = useMemo(
    () => orderedStageTasks(enrollment?.tracks ?? [], stageKey),
    [enrollment?.tracks, stageKey]
  );

  /** Selected Master sub-process brick (top-level template), resolved from click or default. */
  const activeSubprocess = useMemo(() => {
    if (!topLevelBricks.length) return null;
    if (selectedSubprocessId) {
      const direct = topLevelBricks.find(t => t.id === selectedSubprocessId);
      if (direct) return direct;
      const nested = allStageTasks.find(t => t.id === selectedSubprocessId);
      if (nested?.parent_template_id) {
        const parent = topLevelBricks.find(t => t.template_id === nested.parent_template_id);
        if (parent) return parent;
      }
    }
    return topLevelBricks[0];
  }, [topLevelBricks, selectedSubprocessId, allStageTasks]);

  useEffect(() => {
    if (!topLevelBricks.length) {
      if (selectedSubprocessId) setSelectedSubprocessId(null);
      return;
    }
    if (!selectedSubprocessId) {
      const delayed = topLevelBricks.find(t => {
        if (t.is_optional) return false;
        const nested = childTasksOfTemplate(
          enrollment?.tracks ?? [],
          stageKey,
          t.template_id
        ).filter(x => !x.is_optional);
        return brickLifecycle(t, nested, enrollment?.intake_booking) === 'delayed';
      });
      if (delayed) {
        setSelectedSubprocessId(delayed.id);
        return;
      }
      const inProgress = topLevelBricks.find(t => {
        if (t.is_optional) return false;
        const nested = childTasksOfTemplate(
          enrollment?.tracks ?? [],
          stageKey,
          t.template_id
        ).filter(x => !x.is_optional);
        return brickLifecycle(t, nested, enrollment?.intake_booking) === 'in_progress';
      });
      setSelectedSubprocessId(inProgress?.id || topLevelBricks[0].id);
      return;
    }
    const stillValid =
      topLevelBricks.some(t => t.id === selectedSubprocessId) ||
      allStageTasks.some(
        t =>
          t.id === selectedSubprocessId &&
          topLevelBricks.some(p => p.template_id === t.parent_template_id)
      );
    if (!stillValid) {
      const delayed = topLevelBricks.find(t => {
        if (t.is_optional) return false;
        const nested = childTasksOfTemplate(
          enrollment?.tracks ?? [],
          stageKey,
          t.template_id
        ).filter(x => !x.is_optional);
        return brickLifecycle(t, nested, enrollment?.intake_booking) === 'delayed';
      });
      setSelectedSubprocessId(delayed?.id || topLevelBricks[0].id);
    }
  }, [
    stageKey,
    topLevelBricks,
    selectedSubprocessId,
    allStageTasks,
    enrollment?.tracks,
    enrollment?.intake_booking,
  ]);

  /** All Master sub-process bricks under the current main process (stage). */
  const tasks = useMemo(() => topLevelBricks, [topLevelBricks]);

  const activeTrack = useMemo(() => {
    if (!activeSubprocess) return stageTracks[0] || null;
    return (
      stageTracks.find(t => (t.tasks ?? []).some(task => task.id === activeSubprocess.id)) ||
      stageTracks[0] ||
      null
    );
  }, [activeSubprocess, stageTracks]);

  const processCode = String(processNumber(stageKey, enrollment?.stages) || '');
  const stageLabel = visibleStages.find(s => s.key === stageKey)?.label || stageKey;
  const activeSubCode = activeSubprocess
    ? hierarchyCodes(
        enrollment?.tracks ?? [],
        stageKey,
        activeTrack?.id || '',
        activeSubprocess.id,
        enrollment?.stages
      )?.subProcess ||
      (topLevelBricks.findIndex(t => t.id === activeSubprocess.id) >= 0
        ? `${processCode}.${topLevelBricks.findIndex(t => t.id === activeSubprocess.id) + 1}`
        : null)
    : null;

  const taskStats = useMemo(() => {
    const required = tasks.filter(t => !t.is_optional);
    const basis = required.length > 0 ? required : tasks;
    const booking = enrollment?.intake_booking;
    const total = basis.length;
    const done = basis.filter(
      t => subprocessProgressPercentage(t, booking) >= 100
    ).length;
    const delayed = basis.filter(
      t => subprocessLifecycle(t, booking) === 'delayed'
    ).length;
    const atRisk = basis.filter(t => t.sla_status === 'amber').length;
    return {
      total,
      done,
      delayed,
      atRisk,
      pct: processProgressPercentage(tasks, booking),
    };
  }, [tasks, enrollment?.intake_booking]);

  // Map / navigator clicks only change the viewed process — never advance journey status.
  const handleSelectStage = (key: FlowxStageKey) => {
    setViewStage(key);
    setSelectedSubprocessId(null);
    setSelectedTaskId(null);
  };

  const handleSelectSubprocess = (taskId: string) => {
    setSelectedSubprocessId(taskId);
    setSelectedTaskId(taskId);
  };

  const advanceTask = (task: FlowxTask, status: FlowxKanbanStatus) => {
    void moveMutation.mutateAsync({
      task_id: task.id,
      kanban_status: status,
      position_index: task.position_index,
      updated_at: task.updated_at,
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border-subtle bg-card px-4 py-3">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-3">
            <Link
              to="/flowx/journeys"
              className="inline-flex items-center gap-1 text-sm font-semibold text-text-muted hover:text-text-main"
            >
              <ArrowLeft size={14} /> All journeys
            </Link>
            {hubBackIso ? (
              <Link
                to={flowxCountryHubPath(hubBackIso)}
                className="text-sm font-semibold text-accent hover:underline"
              >
                {hubBackIso} command center
              </Link>
            ) : null}
          </div>
          {enrollmentQuery.isLoading ? (
            <p className="text-sm text-text-muted">Loading journey…</p>
          ) : enrollment ? (
            <>
              <h2 className="text-2xl font-bold text-text-main">
                {enrollment.lead_name || `Lead #${enrollment.lead_id}`}
              </h2>
              <p className="text-sm text-text-muted">
                {enrollment.country_iso2} · {enrollment.country_name}
                {enrollment.university_name || enrollment.institution_name
                  ? ` · ${enrollment.university_name || enrollment.institution_name}`
                  : ''}
                {enrollment.college_name ? ` · ${enrollment.college_name}` : ''}
                {enrollment.program_name ? ` · ${enrollment.program_name}` : ''}
                {enrollment.pathway_name ? ` · ${enrollment.pathway_name}` : ''}
                {' · '}
                {(enrollment.application_status || enrollment.status || '').replace(/_/g, ' ')}
              </p>
            </>
          ) : (
            <p className="text-sm text-red-700">Journey not found</p>
          )}
        </div>
        {enrollment ? (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowMap(v => !v)}
              className={`inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-semibold ${
                showMap
                  ? 'border-accent/40 bg-accent/10 text-text-main'
                  : 'border-border-subtle text-text-muted'
              }`}
            >
              <Map size={13} /> {showMap ? 'Hide map' : 'Full map'}
            </button>
            <button
              type="button"
              onClick={() => setOverrideOpen(true)}
              className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-3 py-1.5 text-xs font-semibold text-text-muted"
            >
              <Shield size={13} /> Override
            </button>
          </div>
        ) : null}
      </div>

      {enrollment ? (
        <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="pb-4 pr-1 space-y-3">
          {showMap ? (
            <div className="rounded-xl border border-border-subtle bg-card p-2.5">
              <JourneyProcessFlow
                currentStageKey={enrollment.current_stage_key}
                viewStageKey={stageKey}
                tracks={enrollment.tracks ?? []}
                stages={enrollment.stages ?? []}
                links={enrollment.links ?? []}
                activeTaskId={selectedSubprocessId}
                pending={moveTrackMutation.isPending || reorderChildMutation.isPending}
                intakeBooking={enrollment.intake_booking}
                onViewIntakeSession={openIntakeSessionDrawer}
                onSelectStage={handleSelectStage}
                onSelectSubprocess={handleSelectSubprocess}
                onReorderTrack={(trackId, positionIndex) => {
                  void moveTrackMutation.mutateAsync({
                    track_id: trackId,
                    position_index: positionIndex,
                    updated_at: enrollment.updated_at,
                  });
                }}
                onReorderChild={(taskId, positionIndex) => {
                  const task = (enrollment.tracks ?? [])
                    .flatMap(t => t.tasks)
                    .find(t => t.id === taskId);
                  void reorderChildMutation.mutateAsync({
                    task_id: taskId,
                    position_index: positionIndex,
                    updated_at: task?.updated_at,
                  });
                }}
              />
            </div>
          ) : null}

          <section className="rounded-2xl border border-border-subtle bg-card">
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border-subtle px-4 py-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
                  Current sub-process tasks
                </p>
                <h3 className="text-base font-bold text-text-main">
                  {formatHierarchyLabel(processCode || '—', stageLabel)}
                </h3>
                <p className="mt-0.5 text-xs text-text-muted">
                  {tasks.length} sub-process{tasks.length === 1 ? '' : 'es'}
                  {' · '}
                  {taskStats.done}/{taskStats.total} complete
                  {taskStats.delayed ? (
                    <span className="font-bold text-red-700">
                      {` · ${taskStats.delayed} delayed`}
                    </span>
                  ) : null}
                  {taskStats.atRisk ? ` · ${taskStats.atRisk} at risk` : ''}
                </p>
              </div>
              <div className="min-w-[8rem] text-right">
                <p className="text-2xl font-extrabold tabular-nums text-text-main">
                  {Math.round(taskStats.pct)}%
                </p>
                <p className="text-[10px] font-semibold uppercase text-text-muted">Progress</p>
              </div>
            </div>

            {tasks.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-text-muted">
                No sub-processes on this process yet.
              </p>
            ) : (
              <ul className="divide-y divide-border-subtle">
                {tasks.map((task, brickIndex) => {
                  const life = subprocessLifecycle(task, enrollment.intake_booking);
                  const progressPct = subprocessProgressPercentage(
                    task,
                    enrollment.intake_booking
                  );
                  const delayDisplay = isIntakeSessionTask(task)
                    ? intakeDelayDisplay(enrollment.intake_booking, task)
                    : null;
                  const trackForTask =
                    stageTracks.find(t => (t.tasks ?? []).some(x => x.id === task.id)) ||
                    activeTrack;
                  const codes = trackForTask
                    ? hierarchyCodes(
                        enrollment.tracks ?? [],
                        stageKey,
                        trackForTask.id,
                        task.id,
                        enrollment.stages
                      )
                    : null;
                  const rowCode =
                    codes?.subProcess ||
                    (processCode ? `${processCode}.${brickIndex + 1}` : null);
                  const isActive = selectedSubprocessId === task.id;
                  const isDelayed = life === 'delayed';
                  return (
                    <li key={task.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedSubprocessId(task.id);
                          setSelectedTaskId(task.id);
                        }}
                        className={`flex w-full items-start gap-3 border-l-4 px-4 py-3 text-left transition ${
                          isDelayed
                            ? 'border-l-red-600 bg-red-50/90 hover:bg-red-50'
                            : 'border-l-transparent hover:bg-accent/5'
                        } ${
                          isActive || selectedTask?.id === task.id
                            ? isDelayed
                              ? 'bg-red-50'
                              : 'bg-accent/5'
                            : ''
                        }`}
                      >
                        <span
                          className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 ${lifecycleBorderClass(life)}`}
                          aria-hidden
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            {rowCode ? (
                              <span className="text-[10px] font-bold tabular-nums text-text-muted">
                                {rowCode}
                              </span>
                            ) : null}
                            {isDelayed ? (
                              <span className="rounded bg-red-600 px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-white">
                                Delayed
                              </span>
                            ) : null}
                            {isDelayed ? (
                              <span className="rounded border border-red-400 bg-red-100 px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-red-800">
                                Causing delay
                              </span>
                            ) : null}
                            <span
                              className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${lifecycleBorderClass(life)}`}
                            >
                              {isIntakeSessionTask(task)
                                ? `${lifecycleLabel(life)} · ${progressPct}%`
                                : `${taskStatusLabel(task)} · ${progressPct}%`}
                            </span>
                            {task.is_optional ? (
                              <span className="rounded border border-amber-300 bg-amber-50 px-1 text-[9px] font-semibold text-amber-900">
                                Optional
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-0.5 text-sm font-semibold text-text-main">{task.title}</p>
                          {isIntakeSessionTask(task) &&
                          enrollment.intake_booking?.status_stage_name ? (
                            <p
                              className={`mt-0.5 text-xs font-bold ${
                                life === 'delayed' ? 'text-red-800' : 'text-accent'
                              }`}
                            >
                              {enrollment.intake_booking.status_stage_name}
                            </p>
                          ) : null}
                          {delayDisplay ? (
                            <p className="mt-0.5 text-xs font-extrabold text-red-800">{delayDisplay}</p>
                          ) : null}
                          {task.sla_due_at ? (
                            <p className="mt-0.5 text-[11px] text-text-muted">
                              Due {new Date(task.sla_due_at).toLocaleString()}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 flex-col gap-1">
                          {(task.title || '').trim().toLowerCase() === 'intake session' ? (
                            <span
                              role="button"
                              tabIndex={0}
                              onClick={e => {
                                e.stopPropagation();
                                openIntakeSessionDrawer();
                              }}
                              onKeyDown={e => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  openIntakeSessionDrawer();
                                }
                              }}
                              className="rounded-lg border border-accent/30 bg-accent/10 px-2 py-1 text-[10px] font-bold text-accent hover:bg-accent/15"
                            >
                              View Session
                            </span>
                          ) : task.kanban_status !== 'approved' ? (
                            <span
                              role="button"
                              tabIndex={0}
                              onClick={e => {
                                e.stopPropagation();
                                advanceTask(task, 'approved');
                              }}
                              onKeyDown={e => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  advanceTask(task, 'approved');
                                }
                              }}
                              className="rounded-lg bg-accent px-2 py-1 text-[10px] font-bold text-white hover:brightness-95"
                            >
                              Complete
                            </span>
                          ) : (
                            <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-800">
                              Done
                            </span>
                          )}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </HeadlessScrollArea>
      ) : null}

      <JourneyActionDrawer
        open={Boolean(selectedTask)}
        task={selectedTask}
        code={
          selectedTask && activeTrack
            ? hierarchyCodes(
                enrollment?.tracks ?? [],
                stageKey,
                activeTrack.id,
                selectedTask.id,
                enrollment?.stages
              )?.child || activeSubCode
            : activeSubCode
        }
        processLabel={`${processCode} ${stageLabel}`}
        subProcessLabel={activeSubprocess?.title || undefined}
        pending={moveMutation.isPending}
        checklistSaving={checklistMutation.isPending}
        bookingStatusLabel={
          enrollment?.intake_booking?.status_stage_name ||
          enrollment?.intake_booking?.booking_status ||
          null
        }
        intakeBooking={enrollment?.intake_booking}
        onClose={() => setSelectedTaskId(null)}
        onViewIntakeSession={openIntakeSessionDrawer}
        onChecklistChange={payload => {
          if (!selectedTask) return;
          void checklistMutation.mutateAsync({
            task_id: selectedTask.id,
            checked: payload.checked,
            confirmed_complete: payload.confirmed_complete,
            steps: payload.steps,
            updated_at: selectedTask.updated_at,
          });
        }}
        onAdvance={status => {
          if (!selectedTask) return;
          void moveMutation
            .mutateAsync({
              task_id: selectedTask.id,
              kanban_status: status,
              position_index: selectedTask.position_index,
              updated_at: selectedTask.updated_at,
            })
            .then(() => {
              if (status === 'approved') setSelectedTaskId(null);
            });
        }}
      />

      {overrideOpen && enrollment ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-3 rounded-2xl border border-border-subtle bg-card p-4">
            <h3 className="font-bold text-text-main">Governed override</h3>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={3}
              placeholder="Reason (required)"
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOverrideOpen(false)}
                className="rounded-xl border px-3 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!reason.trim() || overrideMutation.isPending}
                onClick={() =>
                  void overrideMutation
                    .mutateAsync({
                      action_type: 'fast_forward',
                      target_entity: enrollment.current_stage_key,
                      reason: reason.trim(),
                    })
                    .then(() => {
                      setOverrideOpen(false);
                      setReason('');
                    })
                }
                className="rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Fast-forward stage
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <CounsellingSessionDrawer
        open={sessionDrawerOpen}
        bookingId={enrollment?.intake_booking?.id ?? null}
        candidateId={
          enrollment?.intake_booking?.lead_id ?? enrollment?.lead_id ?? null
        }
        candidateName={enrollment?.intake_booking?.candidate_name || enrollment?.lead_name}
        dateLabel={enrollment?.intake_booking?.date_label}
        timeLabel={enrollment?.intake_booking?.time_label}
        onClose={() => setSessionDrawerOpen(false)}
        onStatusUpdated={() => {
          void enrollmentQuery.refetch();
        }}
      />
    </div>
  );
};

export default FlowxJourneyDetailPage;
