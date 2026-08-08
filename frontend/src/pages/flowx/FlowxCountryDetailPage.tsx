import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { createPortal } from 'react-dom';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  GripVertical,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import ConfirmationModal from '../../components/ConfirmationModal';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import { useAlert } from '../../context/ConfirmationContext';
import BrickNestExpandToggle, {
  sortedNestChildren,
} from '../../components/flowx/BrickNestExpandToggle';
import FlowxStepsTooltip from '../../components/flowx/FlowxStepsTooltip';
import SubprocessModeControl, {
  subprocessModeFromBrick,
} from '../../components/flowx/SubprocessModeControl';
import SubprocessStepsTooltip from '../../components/flowx/SubprocessStepsTooltip';
import {
  useAddFlowxTemplate,
  useDeleteFlowxTemplate,
  useEnrollFlowxStudent,
  useFlowxCountries,
  useFlowxCountry,
  useFlowxTemplateUsage,
  useMoveFlowxTemplate,
  useOverrideFlowxTemplate,
  useRenameFlowxTemplate,
} from '../../hooks/useFlowx';
import type { FlowxTaskTemplate } from '../../types/flowx';
import { processSteps } from '../../utils/flowxProcessSteps';
import { clampSubprocessBlurb, subprocessBlurb } from '../../utils/flowxSubprocessBlurb';
import {
  actionStepsEditorValue,
  parseActionStepsText,
} from '../../utils/flowxSubprocessSteps';

function orderedStageBricks(stage: {
  bricks?: FlowxTaskTemplate[];
  tracks: { task_templates: FlowxTaskTemplate[] }[];
}): FlowxTaskTemplate[] {
  const bricks = stage.bricks ?? stage.tracks.flatMap(t => t.task_templates);
  // Top-level only — nested children live on brick.children.
  return [...bricks]
    .filter(b => !b.parent_template_id)
    .sort((a, b) => {
      if (a.position_index !== b.position_index) return a.position_index - b.position_index;
      return a.title.localeCompare(b.title);
    });
}

const FlowxCountryDetailPage: React.FC = () => {
  const showAlert = useAlert();
  const { countryCode } = useParams<{ countryCode: string }>();
  const iso2 = (countryCode || '').toUpperCase();
  const countryQuery = useFlowxCountry(iso2 || null);
  const countriesQuery = useFlowxCountries();
  const deleteMutation = useDeleteFlowxTemplate();
  const templateUsageMutation = useFlowxTemplateUsage();
  const moveMutation = useMoveFlowxTemplate();
  const overrideMutation = useOverrideFlowxTemplate();
  const addTemplate = useAddFlowxTemplate();
  const enrollMutation = useEnrollFlowxStudent();
  const renameTemplate = useRenameFlowxTemplate();

  const workflow = countryQuery.data;
  const catalogFromList = useMemo(
    () => (countriesQuery.data ?? []).find(c => c.country_iso2.toUpperCase() === iso2),
    [countriesQuery.data, iso2]
  );
  const institutionCount = workflow?.institution_count ?? catalogFromList?.institution_count ?? 0;
  const collegeCount = workflow?.college_count ?? catalogFromList?.college_count ?? 0;
  const studentsProcessed = workflow?.students_processed ?? catalogFromList?.students_processed ?? 0;
  const studentsInProcess = workflow?.students_in_process ?? catalogFromList?.students_in_process ?? 0;
  const [leadId, setLeadId] = useState('');
  const [newTitleByStage, setNewTitleByStage] = useState<Record<string, string>>({});
  const [newStepsByStage, setNewStepsByStage] = useState<Record<string, string>>({});
  const [addingStageId, setAddingStageId] = useState<string | null>(null);
  const [nestUnderBrickId, setNestUnderBrickId] = useState<string | null>(null);
  const [dragBrick, setDragBrick] = useState<FlowxTaskTemplate | null>(null);
  const dragBrickRef = useRef<FlowxTaskTemplate | null>(null);
  const [editBrick, setEditBrick] = useState<FlowxTaskTemplate | null>(null);
  const [editBrickTitle, setEditBrickTitle] = useState('');
  const [editBrickBlurb, setEditBrickBlurb] = useState('');
  const [editBrickSteps, setEditBrickSteps] = useState('');
  const [deleteBrick, setDeleteBrick] = useState<FlowxTaskTemplate | null>(null);
  const [deleteUsageCount, setDeleteUsageCount] = useState(0);
  const [deleteChecking, setDeleteChecking] = useState(false);
  const [expandedById, setExpandedById] = useState<Record<string, boolean>>({});
  const stages = useMemo(
    () => (workflow?.stages ?? []).filter(s => !s.is_hidden),
    [workflow?.stages]
  );

  const clearBrickDrag = () => {
    dragBrickRef.current = null;
    setDragBrick(null);
  };

  const beginBrickDrag = (brick: FlowxTaskTemplate, e: DragEvent) => {
    if (editBrick) {
      e.preventDefault();
      return;
    }
    // Required by Firefox / some Chromium builds or the drag is ignored.
    e.dataTransfer.setData('text/plain', brick.id);
    e.dataTransfer.effectAllowed = 'move';
    dragBrickRef.current = brick;
    // Close steps panels without remounting this drag source.
    window.dispatchEvent(new Event('flowx-close-steps'));
    // Defer highlight so React does not rewrite the dragged node during dragstart.
    requestAnimationFrame(() => {
      if (dragBrickRef.current?.id === brick.id) setDragBrick(brick);
    });
  };

  const endBrickDrag = () => {
    clearBrickDrag();
  };

  // Safety net: if the dragged node unmounts mid-gesture, dragend on the element
  // may never fire and the UI looks frozen until reload.
  useEffect(() => {
    const onWindowDragEnd = () => clearBrickDrag();
    window.addEventListener('dragend', onWindowDragEnd);
    return () => window.removeEventListener('dragend', onWindowDragEnd);
  }, []);

  const handleDropOnStage = (stageId: string, position_index: number) => {
    const brick = dragBrickRef.current;
    if (!brick || moveMutation.isPending) return;
    const moving = brick;
    clearBrickDrag();
    void moveMutation
      .mutateAsync({
        template_id: moving.id,
        target_stage_id: stageId,
        position_index,
        track_name: moving.track_name || undefined,
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        void showAlert({
          title: 'Move failed',
          message: message || 'Could not move sub-process.',
          variant: 'danger',
        });
      });
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="shrink-0 rounded-xl border border-border-subtle bg-card px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              to="/flowx/countries"
              className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-text-muted hover:text-text-main"
            >
              <ArrowLeft size={12} /> Countries
            </Link>
            <span className="text-text-muted">·</span>
            {countryQuery.isLoading ? (
              <span className="text-sm text-text-muted">Loading…</span>
            ) : workflow ? (
              <h2 className="truncate text-base font-bold text-text-main">
                {workflow.country_iso2} · {workflow.country_name}
              </h2>
            ) : (
              <span className="text-sm text-red-700">Country workflow not found</span>
            )}
            {workflow ? (
              <p className="w-full text-[11px] tabular-nums text-text-muted sm:w-auto">
                {institutionCount} institutions · {collegeCount} schools & colleges ·{' '}
                {studentsProcessed} processed · {studentsInProcess} in progress ·{' '}
                {workflow.enrollment_count} enrolled
              </p>
            ) : null}
          </div>
          <label className="flex shrink-0 items-center gap-1.5 text-xs">
            <input
              value={leadId}
              onChange={e => setLeadId(e.target.value)}
              placeholder="Lead ID"
              className="w-20 rounded-md border border-border-subtle bg-surface-bg px-2 py-1 text-xs"
            />
            <button
              type="button"
              disabled={!leadId || enrollMutation.isPending}
              onClick={() =>
                void enrollMutation.mutateAsync({ iso2, lead_id: Number(leadId) }).then(data => {
                  window.location.href = `/flowx/journeys/${data.id}`;
                })
              }
              className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
            >
              Enroll
            </button>
          </label>
        </div>
        <p className="mt-1.5 border-t border-border-subtle/80 pt-1.5 text-[11px] leading-snug text-text-muted">
          Names from{' '}
          <Link to="/flowx/master" className="font-semibold text-accent underline">
            Master Workflow
          </Link>{' '}
          apply globally. On this country board you can nest, drag-reorder, and mark sub-processes
          optional or dropped without changing Master.
        </p>
      </div>

      {workflow ? (
        <div className="relative flex min-h-0 flex-1 flex-col gap-2">
          <HeadlessScrollArea className="min-h-0 flex-1" axes="y" viewportClassName="pb-2 pr-1">
            <div className="flex h-full min-h-[480px] w-full gap-2">
              {stages.map((stage, stageIdx) => {
                const bricks = orderedStageBricks(stage);
                const defaultTrack = stage.tracks[0];
                const processCode = String(stageIdx + 1);
                return (
                  <div
                    key={stage.id}
                    className="flex h-full max-h-full min-w-0 flex-1 flex-col rounded-2xl border border-border-subtle bg-card"
                    onDragOver={e => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = 'move';
                    }}
                    onDrop={e => {
                      e.preventDefault();
                      handleDropOnStage(stage.id, bricks.length);
                    }}
                  >
                    <FlowxStepsTooltip
                      steps={processSteps(stage.label, stage.stage_key)}
                      disabled={Boolean(editBrick)}
                      code={processCode}
                      name={stage.label.toUpperCase()}
                      kind="Process"
                    >
                      <div className="shrink-0 border-b border-accent bg-accent px-2.5 py-2 text-white">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-white/80">
                          Process {processCode}
                        </p>
                        <h3 className="truncate text-base font-bold uppercase tracking-wide text-white">
                          <span className="mr-1.5 tabular-nums normal-case text-white/80">
                            {processCode}
                          </span>
                          {stage.label}
                        </h3>
                        <p className="text-xs text-white/75">
                          {bricks.reduce((n, b) => n + 1 + (b.children?.length ?? 0), 0)}{' '}
                          sub-processes · drag to reorder
                        </p>
                      </div>
                    </FlowxStepsTooltip>

                    <HeadlessScrollArea className="min-h-0 flex-1" axes="y" viewportClassName="p-2">
                      <div className="flex flex-col gap-2">
                        {bricks.map((brick, idx) => {
                          const currentBlurb = subprocessBlurb(brick.title, brick.description);
                          const subCode = `${processCode}.${idx + 1}`;
                          const brickMode = subprocessModeFromBrick(brick);
                          const children = sortedNestChildren(brick.children);
                          const expanded =
                            Boolean(expandedById[brick.id]) || nestUnderBrickId === brick.id;
                          const canDrag = !editBrick;
                          const nestTarget = nestUnderBrickId === brick.id;
                          return (
                            <div key={brick.id} className="space-y-1.5">
                              <SubprocessStepsTooltip
                                title={brick.title}
                                code={subCode}
                                actionSteps={brick.action_steps}
                                disabled={Boolean(editBrick)}
                              >
                                <div
                                  draggable={canDrag}
                                  onDragStart={e => beginBrickDrag(brick, e)}
                                  onDragEnd={endBrickDrag}
                                  onDragOver={e => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    e.dataTransfer.dropEffect = 'move';
                                  }}
                                  onDrop={e => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    handleDropOnStage(stage.id, idx);
                                  }}
                                  className={`cursor-grab rounded-lg border p-2.5 shadow-sm active:cursor-grabbing ${
                                    brickMode === 'dropped'
                                      ? 'border-red-400 bg-red-50/70'
                                      : brickMode === 'optional'
                                        ? 'border-amber-400 bg-amber-50/70'
                                        : nestTarget
                                          ? 'border-accent ring-2 ring-accent/25 bg-accent/5'
                                          : 'border-border-subtle bg-surface-bg/70'
                                  } ${dragBrick?.id === brick.id ? 'border-accent opacity-60' : ''}`}
                                >
                                  <div className="flex items-start gap-2">
                                    <GripVertical
                                      className="mt-0.5 h-4 w-4 shrink-0 text-text-muted"
                                      aria-hidden
                                    />
                                    <div className="min-w-0 flex-1">
                                      <p className="text-xs font-bold leading-none tabular-nums text-text-muted">
                                        Sub-process {subCode}
                                      </p>
                                      <p className="text-sm font-semibold leading-snug text-text-main">
                                        {brick.title}
                                      </p>
                                      <p className="mt-0.5 text-[13px] leading-snug text-text-muted">
                                        {currentBlurb}
                                      </p>
                                      {brick.is_country_specific ? (
                                        <div className="mt-1.5 flex flex-wrap gap-1">
                                          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs font-semibold text-violet-800">
                                            Country
                                          </span>
                                        </div>
                                      ) : null}
                                      <BrickNestExpandToggle
                                        count={children.length}
                                        expanded={expanded}
                                        onToggle={() =>
                                          setExpandedById(prev => ({
                                            ...prev,
                                            [brick.id]: !expanded,
                                          }))
                                        }
                                      />
                                    </div>
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap gap-1">
                                    <SubprocessModeControl
                                      brick={brick}
                                      compact
                                      pending={overrideMutation.isPending}
                                      onApply={payload => overrideMutation.mutateAsync(payload)}
                                    />
                                    <button
                                      type="button"
                                      title="Edit Brick"
                                      aria-label="Edit Brick"
                                      onMouseDown={e => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        setEditBrick(brick);
                                        setEditBrickTitle(brick.title);
                                        setEditBrickBlurb(
                                          subprocessBlurb(brick.title, brick.description)
                                        );
                                        setEditBrickSteps(
                                          actionStepsEditorValue(brick.title, brick.action_steps)
                                        );
                                      }}
                                      onClick={e => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                      }}
                                      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg hover:text-text-main"
                                    >
                                      <Pencil size={12} />
                                    </button>
                                    <button
                                      type="button"
                                      title="Delete Brick"
                                      aria-label="Delete Brick"
                                      onClick={e => {
                                        e.stopPropagation();
                                        setDeleteUsageCount(0);
                                        setDeleteBrick(brick);
                                        setDeleteChecking(true);
                                        void templateUsageMutation
                                          .mutateAsync(brick.id)
                                          .then(usage => {
                                            setDeleteUsageCount(usage.student_task_count || 0);
                                          })
                                          .catch(() => {
                                            setDeleteUsageCount(0);
                                          })
                                          .finally(() => setDeleteChecking(false));
                                      }}
                                      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-red-200 text-red-700 hover:bg-red-50"
                                    >
                                      <Trash2 size={12} />
                                    </button>
                                    {defaultTrack ? (
                                      <button
                                        type="button"
                                        title="Add nested sub-process"
                                        onClick={e => {
                                          e.stopPropagation();
                                          setNestUnderBrickId(brick.id);
                                          setExpandedById(prev => ({
                                            ...prev,
                                            [brick.id]: true,
                                          }));
                                          setAddingStageId(stage.id);
                                          setNewTitleByStage(prev => ({
                                            ...prev,
                                            [stage.id]: '',
                                          }));
                                          setNewStepsByStage(prev => ({
                                            ...prev,
                                            [stage.id]: '',
                                          }));
                                        }}
                                        className="rounded border border-border-subtle px-1.5 py-0.5 text-xs font-semibold text-text-muted hover:text-text-main"
                                      >
                                        <Plus size={11} className="inline" /> Nested
                                      </button>
                                    ) : null}
                                  </div>
                                </div>
                              </SubprocessStepsTooltip>

                              {expanded
                                ? children.map((child, childIdx) => {
                                    const childCode = `${subCode}.${childIdx + 1}`;
                                    const childCurrentBlurb = subprocessBlurb(
                                      child.title,
                                      child.description
                                    );
                                    const childMode = subprocessModeFromBrick(child);
                                    return (
                                      <div
                                        key={child.id}
                                        className="ml-2 border-l-2 border-orange-400 pl-1.5"
                                      >
                                        <SubprocessStepsTooltip
                                          title={child.title}
                                          code={childCode}
                                          actionSteps={child.action_steps}
                                          disabled={Boolean(editBrick)}
                                        >
                                          <div
                                            draggable={!editBrick}
                                            onDragStart={e => {
                                              e.stopPropagation();
                                              beginBrickDrag(child, e);
                                            }}
                                            onDragEnd={endBrickDrag}
                                            onDragOver={e => {
                                              e.preventDefault();
                                              e.stopPropagation();
                                              e.dataTransfer.dropEffect = 'move';
                                            }}
                                            onDrop={e => {
                                              e.preventDefault();
                                              e.stopPropagation();
                                              // Dropping on a nested row inserts at the parent index.
                                              handleDropOnStage(stage.id, idx);
                                            }}
                                            className={`cursor-grab rounded-lg border p-2.5 shadow-sm active:cursor-grabbing ${
                                              childMode === 'dropped'
                                                ? 'border-red-400 bg-red-50/70'
                                                : childMode === 'optional'
                                                  ? 'border-amber-400 bg-amber-50/70'
                                                  : 'border-border-subtle bg-orange-50/40'
                                            } ${
                                              dragBrick?.id === child.id
                                                ? 'border-accent opacity-60'
                                                : ''
                                            }`}
                                          >
                                            <div className="flex items-start gap-2">
                                              <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" />
                                              <div className="min-w-0 flex-1">
                                                <p className="text-xs font-bold leading-none tabular-nums text-orange-800">
                                                  Sub-process {childCode}
                                                </p>
                                                <p className="text-sm font-semibold leading-snug text-text-main">
                                                  {child.title}
                                                </p>
                                                <p className="mt-0.5 text-[13px] leading-snug text-text-muted">
                                                  {childCurrentBlurb}
                                                </p>
                                              </div>
                                            </div>
                                            <div className="mt-1.5 flex flex-wrap gap-1">
                                              <SubprocessModeControl
                                                brick={child}
                                                compact
                                                pending={overrideMutation.isPending}
                                                onApply={payload =>
                                                  overrideMutation.mutateAsync(payload)
                                                }
                                              />
                                              <button
                                                type="button"
                                                title="Edit Brick"
                                                aria-label="Edit Brick"
                                                onMouseDown={e => {
                                                  e.preventDefault();
                                                  e.stopPropagation();
                                                  setEditBrick(child);
                                                  setEditBrickTitle(child.title);
                                                  setEditBrickBlurb(
                                                    subprocessBlurb(
                                                      child.title,
                                                      child.description
                                                    )
                                                  );
                                                  setEditBrickSteps(
                                                    actionStepsEditorValue(
                                                      child.title,
                                                      child.action_steps
                                                    )
                                                  );
                                                }}
                                                onClick={e => {
                                                  e.preventDefault();
                                                  e.stopPropagation();
                                                }}
                                                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg hover:text-text-main"
                                              >
                                                <Pencil size={12} />
                                              </button>
                                              <button
                                                type="button"
                                                title="Delete Brick"
                                                aria-label="Delete Brick"
                                                onClick={e => {
                                                  e.stopPropagation();
                                                  setDeleteUsageCount(0);
                                                  setDeleteBrick(child);
                                                  setDeleteChecking(true);
                                                  void templateUsageMutation
                                                    .mutateAsync(child.id)
                                                    .then(usage => {
                                                      setDeleteUsageCount(
                                                        usage.student_task_count || 0
                                                      );
                                                    })
                                                    .catch(() => {
                                                      setDeleteUsageCount(0);
                                                    })
                                                    .finally(() => setDeleteChecking(false));
                                                }}
                                                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-red-200 text-red-700 hover:bg-red-50"
                                              >
                                                <Trash2 size={12} />
                                              </button>
                                            </div>
                                          </div>
                                        </SubprocessStepsTooltip>
                                      </div>
                                    );
                                  })
                                : null}
                            </div>
                          );
                        })}
                        {bricks.length === 0 ? (
                          <p className="px-1 py-6 text-center text-sm text-text-muted">
                            Drop sub-processes here
                          </p>
                        ) : null}
                      </div>
                    </HeadlessScrollArea>

                    <div className="flex shrink-0 flex-col gap-1.5 border-t border-border-subtle p-2">
                      {addingStageId === stage.id ? (
                        <>
                          {nestUnderBrickId ? (
                            <p className="text-[10px] font-semibold text-accent">
                              Nesting under selected brick (country-local)
                            </p>
                          ) : null}
                          <input
                            value={newTitleByStage[stage.id] || ''}
                            onChange={e =>
                              setNewTitleByStage(prev => ({
                                ...prev,
                                [stage.id]: e.target.value,
                              }))
                            }
                            placeholder="Brick name…"
                            autoFocus
                            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm"
                          />
                          <textarea
                            value={newStepsByStage[stage.id] || ''}
                            onChange={e =>
                              setNewStepsByStage(prev => ({
                                ...prev,
                                [stage.id]: e.target.value,
                              }))
                            }
                            placeholder={
                              'Steps to perform (required) — one step per line\n1. First action\n2. Second action\n…'
                            }
                            rows={4}
                            className="w-full resize-y rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-xs leading-relaxed text-text-main"
                            aria-label={`Steps for new brick in ${stage.label}`}
                          />
                          <div className="flex items-center justify-between gap-2">
                            <button
                              type="button"
                              disabled={addTemplate.isPending}
                              onClick={() => {
                                setAddingStageId(null);
                                setNestUnderBrickId(null);
                                setNewTitleByStage(prev => ({ ...prev, [stage.id]: '' }));
                                setNewStepsByStage(prev => ({ ...prev, [stage.id]: '' }));
                              }}
                              className="rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-50"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={
                                !defaultTrack ||
                                !(newTitleByStage[stage.id] || '').trim() ||
                                parseActionStepsText(newStepsByStage[stage.id] || '').length === 0 ||
                                addTemplate.isPending
                              }
                              onClick={() => {
                                if (!defaultTrack) return;
                                const title = (newTitleByStage[stage.id] || '').trim();
                                const action_steps = parseActionStepsText(
                                  newStepsByStage[stage.id] || ''
                                );
                                if (!title || action_steps.length === 0) return;
                                void addTemplate
                                  .mutateAsync({
                                    track_id: defaultTrack.id,
                                    title,
                                    action_steps,
                                    parent_template_id: nestUnderBrickId,
                                  })
                                  .then(() => {
                                    setAddingStageId(null);
                                    setNestUnderBrickId(null);
                                    setNewTitleByStage(prev => ({ ...prev, [stage.id]: '' }));
                                    setNewStepsByStage(prev => ({ ...prev, [stage.id]: '' }));
                                  });
                              }}
                              className="inline-flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                            >
                              <Plus size={14} />{' '}
                              {nestUnderBrickId ? 'Add nested' : 'Add brick'}
                            </button>
                          </div>
                        </>
                      ) : (
                        <button
                          type="button"
                          disabled={!defaultTrack}
                          onClick={() => {
                            setNestUnderBrickId(null);
                            setAddingStageId(stage.id);
                            setNewTitleByStage(prev => ({ ...prev, [stage.id]: '' }));
                            setNewStepsByStage(prev => ({ ...prev, [stage.id]: '' }));
                          }}
                          className="inline-flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-border-subtle px-2 py-1.5 text-xs font-semibold text-text-muted hover:border-accent hover:text-accent disabled:opacity-50"
                        >
                          <Plus size={14} /> Add brick
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </HeadlessScrollArea>
        </div>
      ) : null}

      {editBrick
        ? createPortal(
            <div
              className="fixed inset-0 z-[300] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
              role="presentation"
              onMouseDown={e => {
                if (e.target === e.currentTarget) setEditBrick(null);
              }}
            >
              <div
                role="dialog"
                aria-modal="true"
                aria-label={`Edit ${editBrick.title}`}
                className="w-full max-w-md space-y-3 rounded-2xl border border-border-subtle bg-card p-4 shadow-2xl"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold text-text-main">Edit sub-process</h3>
                  <button
                    type="button"
                    onClick={() => setEditBrick(null)}
                    className="rounded-lg p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                    aria-label="Close"
                  >
                    <X size={16} />
                  </button>
                </div>
                <label className="block space-y-1">
                  <span className="text-xs font-semibold text-text-muted">Brick name</span>
                  <input
                    value={editBrickTitle}
                    onChange={e => setEditBrickTitle(e.target.value)}
                    className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-semibold text-text-main"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-semibold text-text-muted">
                    Short definition (3–5 words)
                  </span>
                  <input
                    value={editBrickBlurb}
                    onChange={e => setEditBrickBlurb(e.target.value)}
                    onBlur={() => setEditBrickBlurb(clampSubprocessBlurb(editBrickBlurb))}
                    maxLength={80}
                    className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-semibold text-text-muted">
                    Steps to perform (one per line)
                  </span>
                  <textarea
                    value={editBrickSteps}
                    onChange={e => setEditBrickSteps(e.target.value)}
                    rows={Math.min(12, Math.max(6, editBrickSteps.split(/\r?\n/).length + 1))}
                    placeholder={'Confirm student identity\nReview study goals\n…'}
                    className="w-full resize-y rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-xs leading-relaxed text-text-main"
                  />
                </label>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setEditBrick(null)}
                    className="rounded-xl border border-border-subtle px-3 py-2 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={
                      !editBrickTitle.trim() ||
                      parseActionStepsText(editBrickSteps).length === 0 ||
                      renameTemplate.isPending
                    }
                    onClick={() => {
                      const title = editBrickTitle.trim();
                      const description = clampSubprocessBlurb(editBrickBlurb);
                      const action_steps = parseActionStepsText(editBrickSteps);
                      if (!title || action_steps.length === 0 || !editBrick) return;
                      void renameTemplate
                        .mutateAsync({
                          template_id: editBrick.id,
                          title,
                          description,
                          action_steps,
                        })
                        .then(() => setEditBrick(null));
                    }}
                    className="rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    Save changes
                  </button>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}

      <ConfirmationModal
        open={Boolean(deleteBrick)}
        variant="danger"
        title={deleteBrick ? `Delete “${deleteBrick.title}”?` : 'Delete brick?'}
        message={
          deleteChecking ? (
            <p>Checking whether candidates are mapped to this sub-process…</p>
          ) : deleteUsageCount > 0 ? (
            <p>
              <strong>{deleteUsageCount}</strong> candidate journey task
              {deleteUsageCount === 1 ? '' : 's'} already map to “{deleteBrick?.title}”
              {(deleteBrick?.children?.length ?? 0) > 0
                ? ' or its nested sub-processes'
                : ''}
              . Deleting is not advisable because those student journeys will lose this step
              {(deleteBrick?.children?.length ?? 0) > 0
                ? ' (nested bricks are deleted too)'
                : ''}
              . If you still want to delete it, confirm below.
            </p>
          ) : (deleteBrick?.children?.length ?? 0) > 0 ? (
            <p>
              This permanently removes “{deleteBrick?.title}” and its{' '}
              <strong>{deleteBrick?.children?.length}</strong> nested sub-process
              {(deleteBrick?.children?.length ?? 0) === 1 ? '' : 'es'} from this country workflow.
              No candidate journeys currently use these bricks.
            </p>
          ) : (
            <p>
              This permanently removes the sub-process from this country workflow. No candidate
              journeys currently use this brick.
            </p>
          )
        }
        confirmLabel={
          deleteMutation.isPending
            ? 'Deleting…'
            : deleteChecking
              ? 'Please wait…'
              : deleteUsageCount > 0
                ? 'Delete anyway'
                : 'Delete'
        }
        cancelLabel="Cancel"
        onCancel={() => {
          if (deleteMutation.isPending) return;
          setDeleteBrick(null);
          setDeleteUsageCount(0);
          setDeleteChecking(false);
        }}
        onConfirm={() => {
          if (!deleteBrick || deleteMutation.isPending || deleteChecking) return;
          const brick = deleteBrick;
          void deleteMutation
            .mutateAsync(brick.id)
            .then(() => {
              setDeleteBrick(null);
              setDeleteUsageCount(0);
              setDeleteChecking(false);
            })
            .catch((err: unknown) => {
              const message = err instanceof Error ? err.message : String(err);
              void showAlert({
                title: 'Delete failed',
                message: message || 'Delete failed.',
                variant: 'danger',
              });
            });
        }}
      />
    </div>
  );
};

export default FlowxCountryDetailPage;
