import { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Pencil, Plus, Trash2, Waypoints, X } from 'lucide-react';
import ConfirmationModal from '../../components/ConfirmationModal';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import BrickNestExpandToggle, {
  sortedNestChildren,
} from '../../components/flowx/BrickNestExpandToggle';
import FlowxStepsTooltip from '../../components/flowx/FlowxStepsTooltip';
import SubprocessStepsTooltip from '../../components/flowx/SubprocessStepsTooltip';
import {
  useFlowxMaster,
  useMasterAddTemplate,
  useMasterDeleteTemplate,
  useMasterRenameProcessLabel,
  useMasterRenameTemplate,
} from '../../hooks/useFlowx';
import type { FlowxStageKey, FlowxTaskTemplate } from '../../types/flowx';
import { isSuperAdmin } from '../../utils/adminAccess';
import { processSteps } from '../../utils/flowxProcessSteps';
import { clampSubprocessBlurb, subprocessBlurb } from '../../utils/flowxSubprocessBlurb';
import {
  actionStepsEditorValue,
  parseActionStepsText,
} from '../../utils/flowxSubprocessSteps';

interface ShellContext {
  currentUser?: {
    role?: string | null;
    admin_role?: { name?: string | null } | null;
    is_superuser?: boolean;
  } | null;
}

function orderedStageBricks(stage: {
  bricks?: FlowxTaskTemplate[];
  tracks: { task_templates: FlowxTaskTemplate[] }[];
}): FlowxTaskTemplate[] {
  const bricks = stage.bricks ?? stage.tracks.flatMap(t => t.task_templates);
  return [...bricks]
    .filter(b => !b.parent_template_id)
    .sort((a, b) => {
      if (a.position_index !== b.position_index) return a.position_index - b.position_index;
      return a.title.localeCompare(b.title);
    });
}

function walkBricks(bricks: FlowxTaskTemplate[], visit: (brick: FlowxTaskTemplate) => void) {
  for (const brick of bricks) {
    visit(brick);
    for (const child of brick.children ?? []) visit(child);
  }
}

const FlowxMasterWorkflowPage: React.FC = () => {
  const context = useOutletContext<ShellContext>();
  const canEdit = isSuperAdmin(context?.currentUser);
  const masterQuery = useFlowxMaster();
  const renameProcess = useMasterRenameProcessLabel();
  const addTemplate = useMasterAddTemplate();
  const renameTemplate = useMasterRenameTemplate();
  const deleteTemplate = useMasterDeleteTemplate();

  const [editMode, setEditMode] = useState(false);
  const [draftStageLabels, setDraftStageLabels] = useState<Record<string, string>>({});
  const [draftBrickTitles, setDraftBrickTitles] = useState<Record<string, string>>({});
  const [draftBrickBlurbs, setDraftBrickBlurbs] = useState<Record<string, string>>({});
  const [touchedBrickBlurbs, setTouchedBrickBlurbs] = useState<Record<string, boolean>>({});
  const [addingStageId, setAddingStageId] = useState<string | null>(null);
  const [newTitleByStage, setNewTitleByStage] = useState<Record<string, string>>({});
  const [newStepsByStage, setNewStepsByStage] = useState<Record<string, string>>({});
  const [nestUnderBrickId, setNestUnderBrickId] = useState<string | null>(null);
  const [expandedById, setExpandedById] = useState<Record<string, boolean>>({});

  const [editBrick, setEditBrick] = useState<FlowxTaskTemplate | null>(null);
  const [editBrickTitle, setEditBrickTitle] = useState('');
  const [editBrickBlurb, setEditBrickBlurb] = useState('');
  const [editBrickSteps, setEditBrickSteps] = useState('');
  const [deleteBrick, setDeleteBrick] = useState<FlowxTaskTemplate | null>(null);
  const [savingBatch, setSavingBatch] = useState(false);

  const workflow = masterQuery.data;

  const stages = useMemo(
    () =>
      [...(workflow?.stages ?? [])]
        .filter(s => !s.is_hidden)
        .sort((a, b) => a.position_index - b.position_index),
    [workflow?.stages]
  );

  const seedDrafts = () => {
    if (!workflow) return;
    const labels: Record<string, string> = {};
    const titles: Record<string, string> = {};
    const blurbs: Record<string, string> = {};
    for (const stage of workflow.stages ?? []) {
      labels[stage.id] = stage.label;
      walkBricks(orderedStageBricks(stage), brick => {
        titles[brick.id] = brick.title;
        blurbs[brick.id] = subprocessBlurb(brick.title, brick.description);
      });
    }
    setDraftStageLabels(labels);
    setDraftBrickTitles(titles);
    setDraftBrickBlurbs(blurbs);
    setTouchedBrickBlurbs({});
  };

  const pending =
    renameProcess.isPending ||
    addTemplate.isPending ||
    renameTemplate.isPending ||
    deleteTemplate.isPending ||
    savingBatch;

  const saveBatchEdits = async () => {
    if (!workflow || savingBatch) return;
    setSavingBatch(true);
    try {
      for (const stage of stages) {
        const nextLabel = (draftStageLabels[stage.id] ?? stage.label).trim();
        if (nextLabel && nextLabel !== stage.label.trim()) {
          await renameProcess.mutateAsync({
            stage_key: stage.stage_key as FlowxStageKey,
            label: nextLabel,
          });
        }
        const bricks: FlowxTaskTemplate[] = [];
        walkBricks(orderedStageBricks(stage), b => bricks.push(b));
        for (const brick of bricks) {
          const nextTitle = (draftBrickTitles[brick.id] ?? brick.title).trim();
          const currentBlurb = subprocessBlurb(brick.title, brick.description);
          const nextBlurb = clampSubprocessBlurb(
            draftBrickBlurbs[brick.id] ?? currentBlurb
          );
          const titleChanged = Boolean(nextTitle) && nextTitle !== brick.title.trim();
          const blurbChanged =
            Boolean(touchedBrickBlurbs[brick.id]) && nextBlurb !== currentBlurb;
          if (titleChanged || blurbChanged) {
            await renameTemplate.mutateAsync({
              template_id: brick.id,
              title: titleChanged ? nextTitle : undefined,
              description: blurbChanged ? nextBlurb : undefined,
            });
          }
        }
      }
      setEditMode(false);
      setTouchedBrickBlurbs({});
      await masterQuery.refetch();
      seedDrafts();
    } finally {
      setSavingBatch(false);
    }
  };

  const toggleEditMode = () => {
    if (pending) return;
    if (!editMode) {
      seedDrafts();
      setAddingStageId(null);
      setNestUnderBrickId(null);
      setEditMode(true);
      return;
    }
    void saveBatchEdits();
  };

  const openBrickEditor = (brick: FlowxTaskTemplate) => {
    setEditBrick(brick);
    setEditBrickTitle(brick.title);
    setEditBrickBlurb(subprocessBlurb(brick.title, brick.description));
    setEditBrickSteps(actionStepsEditorValue(brick.title, brick.action_steps));
  };

  if (!canEdit) {
    return (
      <div className="rounded-2xl border border-border-subtle bg-card p-8 text-center">
        <p className="text-sm font-semibold text-text-main">Super Admin access required</p>
        <p className="mt-1 text-sm text-text-muted">
          Only Super Admins can view and edit the Master Workflow.
        </p>
      </div>
    );
  }

  if (masterQuery.isLoading) {
    return <p className="text-sm text-text-muted">Loading Master Workflow…</p>;
  }

  if (masterQuery.isError || !workflow) {
    return (
      <p className="text-sm text-rose-700">
        Could not load Master Workflow. {(masterQuery.error as Error)?.message || ''}
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="shrink-0 rounded-xl border border-border-subtle bg-card px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-text-muted">
              <Waypoints size={12} /> Canonical
            </span>
            <span className="text-text-muted">·</span>
            <h2 className="truncate text-base font-bold text-text-main">Master Workflow</h2>
            <p className="w-full text-[11px] text-text-muted sm:w-auto">
              {editMode
                ? 'Edit mode · renames sync to every country'
                : 'Numbered process board · same layout as country workflows · edits apply globally'}
            </p>
          </div>
          <button
            type="button"
            disabled={pending}
            onClick={toggleEditMode}
            className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-semibold disabled:opacity-50 ${
              editMode
                ? 'bg-accent text-white'
                : 'border border-border-subtle text-text-muted hover:text-text-main'
            }`}
          >
            {editMode ? (savingBatch ? 'Saving…' : 'Save & done') : 'Edit names'}
          </button>
        </div>
        <p className="mt-1.5 border-t border-border-subtle/80 pt-1.5 text-[11px] leading-snug text-text-muted">
          Changes here apply to <strong className="text-text-main">all countries</strong>. Country
          boards may still mark a sub-process optional or dropped without changing Master.
          {editMode ? (
            <>
              {' '}
              <span className="font-semibold text-amber-800">
                Editing names &amp; definitions — click Save &amp; done when finished.
              </span>
            </>
          ) : null}
        </p>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col gap-2">
        <HeadlessScrollArea className="min-h-0 flex-1" axes="y" viewportClassName="pb-2 pr-1">
          <div className="flex h-full min-h-[480px] w-full gap-2">
            {stages.map((stage, stageIdx) => {
              const bricks = orderedStageBricks(stage);
              const defaultTrack = stage.tracks[0];
              const draftLabel = draftStageLabels[stage.id] ?? stage.label;
              const processLabelDirty = draftLabel.trim() !== stage.label.trim();
              const processCode = String(stageIdx + 1);
              return (
                <div
                  key={stage.id}
                  className="flex h-full max-h-full min-w-0 flex-1 flex-col rounded-2xl border border-border-subtle bg-card"
                >
                  <FlowxStepsTooltip
                    steps={processSteps(stage.label, stage.stage_key)}
                    disabled={editMode || Boolean(editBrick)}
                    code={processCode}
                    name={stage.label.toUpperCase()}
                    kind="Process"
                  >
                    <div className="shrink-0 border-b border-accent bg-accent px-2.5 py-2 text-white">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-white/80">
                          Process {processCode}
                        </p>
                        {editMode ? (
                          <span className="rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                            Global name
                          </span>
                        ) : null}
                      </div>
                      {editMode ? (
                        <div className="mt-1.5 space-y-1">
                          <input
                            value={draftLabel}
                            onChange={e =>
                              setDraftStageLabels(prev => ({
                                ...prev,
                                [stage.id]: e.target.value,
                              }))
                            }
                            className="w-full rounded-lg border border-white/30 bg-white px-2 py-1 text-sm font-bold text-text-main"
                          />
                          {processLabelDirty ? (
                            <p className="text-[10px] font-semibold text-amber-100">Unsaved</p>
                          ) : null}
                        </div>
                      ) : (
                        <h3 className="truncate text-base font-bold uppercase tracking-wide text-white">
                          <span className="mr-1.5 tabular-nums normal-case text-white/80">
                            {processCode}
                          </span>
                          {stage.label}
                        </h3>
                      )}
                      <p className="text-xs text-white/75">
                        {bricks.reduce((n, b) => n + 1 + (b.children?.length ?? 0), 0)}{' '}
                        sub-processes
                      </p>
                    </div>
                  </FlowxStepsTooltip>

                  <HeadlessScrollArea className="min-h-0 flex-1" axes="y" viewportClassName="p-2">
                    <div className="flex flex-col gap-2">
                      {bricks.map((brick, idx) => {
                        const draftTitle = draftBrickTitles[brick.id] ?? brick.title;
                        const currentBlurb = subprocessBlurb(brick.title, brick.description);
                        const draftBlurb = draftBrickBlurbs[brick.id] ?? currentBlurb;
                        const brickTitleDirty = draftTitle.trim() !== brick.title.trim();
                        const brickBlurbDirty =
                          Boolean(touchedBrickBlurbs[brick.id]) &&
                          clampSubprocessBlurb(draftBlurb) !== currentBlurb;
                        const subCode = `${processCode}.${idx + 1}`;
                        const children = sortedNestChildren(brick.children);
                        const expanded = Boolean(expandedById[brick.id]);
                        const nestTarget = nestUnderBrickId === brick.id;
                        return (
                          <div key={brick.id} className="space-y-1.5">
                            <SubprocessStepsTooltip
                              title={brick.title}
                              code={subCode}
                              actionSteps={brick.action_steps}
                              disabled={editMode || Boolean(editBrick)}
                            >
                              <div
                                className={`rounded-lg border p-2.5 shadow-sm ${
                                  nestTarget
                                    ? 'border-accent ring-2 ring-accent/25 bg-accent/5'
                                    : 'border-border-subtle bg-surface-bg/70'
                                }`}
                              >
                                <div className="flex items-start gap-2">
                                  {editMode ? (
                                    <Pencil className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                                  ) : null}
                                  <div className="min-w-0 flex-1">
                                    <p className="text-xs font-bold leading-none tabular-nums text-text-muted">
                                      Sub-process {subCode}
                                    </p>
                                    {editMode ? (
                                      <div className="mt-1 space-y-1.5">
                                        <input
                                          value={draftTitle}
                                          onChange={e =>
                                            setDraftBrickTitles(prev => ({
                                              ...prev,
                                              [brick.id]: e.target.value,
                                            }))
                                          }
                                          placeholder="Sub-process name"
                                          className="w-full rounded-lg border border-border-subtle bg-card px-2 py-0.5 text-sm font-semibold leading-snug text-text-main"
                                        />
                                        <input
                                          value={draftBlurb}
                                          onChange={e => {
                                            setDraftBrickBlurbs(prev => ({
                                              ...prev,
                                              [brick.id]: e.target.value,
                                            }));
                                            setTouchedBrickBlurbs(prev => ({
                                              ...prev,
                                              [brick.id]: true,
                                            }));
                                          }}
                                          onBlur={() =>
                                            setDraftBrickBlurbs(prev => ({
                                              ...prev,
                                              [brick.id]: clampSubprocessBlurb(
                                                prev[brick.id] ?? draftBlurb
                                              ),
                                            }))
                                          }
                                          placeholder="Short definition (3–5 words)"
                                          maxLength={80}
                                          className="w-full rounded-lg border border-border-subtle bg-card px-2 py-1 text-xs text-text-muted"
                                        />
                                        {(brickTitleDirty || brickBlurbDirty) && (
                                          <p className="text-[10px] font-semibold text-amber-800">
                                            Unsaved
                                          </p>
                                        )}
                                      </div>
                                    ) : (
                                      <>
                                        <p className="text-sm font-semibold leading-snug text-text-main">
                                          {brick.title}
                                        </p>
                                        <p className="mt-0.5 text-[13px] leading-snug text-text-muted">
                                          {currentBlurb}
                                        </p>
                                      </>
                                    )}
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
                                {editMode ? null : (
                                  <div className="mt-1.5 flex flex-wrap gap-1">
                                    <button
                                      type="button"
                                      title="Edit Brick"
                                      aria-label="Edit Brick"
                                      onClick={() => openBrickEditor(brick)}
                                      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg hover:text-text-main"
                                    >
                                      <Pencil size={12} />
                                    </button>
                                    <button
                                      type="button"
                                      title="Delete Brick"
                                      aria-label="Delete Brick"
                                      onClick={() => setDeleteBrick(brick)}
                                      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-red-200 text-red-700 hover:bg-red-50"
                                    >
                                      <Trash2 size={12} />
                                    </button>
                                    {defaultTrack ? (
                                      <button
                                        type="button"
                                        title="Add nested sub-process"
                                        onClick={() => {
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
                                )}
                              </div>
                            </SubprocessStepsTooltip>

                            {expanded
                              ? children.map((child, childIdx) => {
                                  const childCode = `${subCode}.${childIdx + 1}`;
                                  const childDraftTitle =
                                    draftBrickTitles[child.id] ?? child.title;
                                  const childCurrentBlurb = subprocessBlurb(
                                    child.title,
                                    child.description
                                  );
                                  const childDraftBlurb =
                                    draftBrickBlurbs[child.id] ?? childCurrentBlurb;
                                  const childTitleDirty =
                                    childDraftTitle.trim() !== child.title.trim();
                                  const childBlurbDirty =
                                    Boolean(touchedBrickBlurbs[child.id]) &&
                                    clampSubprocessBlurb(childDraftBlurb) !==
                                      childCurrentBlurb;
                                  return (
                                    <div key={child.id} className="ml-2 border-l-2 border-orange-400 pl-1.5">
                                      <SubprocessStepsTooltip
                                        title={child.title}
                                        code={childCode}
                                        actionSteps={child.action_steps}
                                        disabled={editMode || Boolean(editBrick)}
                                      >
                                        <div className="rounded-lg border border-border-subtle bg-orange-50/40 p-2.5 shadow-sm">
                                          <div className="min-w-0">
                                            <p className="text-xs font-bold leading-none tabular-nums text-orange-800">
                                              Sub-process {childCode}
                                            </p>
                                            {editMode ? (
                                              <div className="mt-1 space-y-1.5">
                                                <input
                                                  value={childDraftTitle}
                                                  onChange={e =>
                                                    setDraftBrickTitles(prev => ({
                                                      ...prev,
                                                      [child.id]: e.target.value,
                                                    }))
                                                  }
                                                  className="w-full rounded-lg border border-border-subtle bg-card px-2 py-1 text-sm font-semibold text-text-main"
                                                />
                                                <input
                                                  value={childDraftBlurb}
                                                  onChange={e => {
                                                    setDraftBrickBlurbs(prev => ({
                                                      ...prev,
                                                      [child.id]: e.target.value,
                                                    }));
                                                    setTouchedBrickBlurbs(prev => ({
                                                      ...prev,
                                                      [child.id]: true,
                                                    }));
                                                  }}
                                                  onBlur={() =>
                                                    setDraftBrickBlurbs(prev => ({
                                                      ...prev,
                                                      [child.id]: clampSubprocessBlurb(
                                                        prev[child.id] ?? childDraftBlurb
                                                      ),
                                                    }))
                                                  }
                                                  className="w-full rounded-lg border border-border-subtle bg-card px-2 py-1 text-xs text-text-muted"
                                                />
                                                {(childTitleDirty || childBlurbDirty) && (
                                                  <p className="text-[10px] font-semibold text-amber-800">
                                                    Unsaved
                                                  </p>
                                                )}
                                              </div>
                                            ) : (
                                              <>
                                                <p className="text-sm font-semibold leading-snug text-text-main">
                                                  {child.title}
                                                </p>
                                                <p className="mt-0.5 text-[13px] leading-snug text-text-muted">
                                                  {childCurrentBlurb}
                                                </p>
                                              </>
                                            )}
                                          </div>
                                          {editMode ? null : (
                                            <div className="mt-1.5 flex flex-wrap gap-1">
                                              <button
                                                type="button"
                                                title="Edit Brick"
                                                aria-label="Edit Brick"
                                                onClick={() => openBrickEditor(child)}
                                                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle text-text-muted hover:bg-surface-bg hover:text-text-main"
                                              >
                                                <Pencil size={12} />
                                              </button>
                                              <button
                                                type="button"
                                                title="Delete Brick"
                                                aria-label="Delete Brick"
                                                onClick={() => setDeleteBrick(child)}
                                                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-red-200 text-red-700 hover:bg-red-50"
                                              >
                                                <Trash2 size={12} />
                                              </button>
                                            </div>
                                          )}
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
                          No sub-processes yet
                        </p>
                      ) : null}
                    </div>
                  </HeadlessScrollArea>

                  <div className="flex shrink-0 flex-col gap-1.5 border-t border-border-subtle p-2">
                    {addingStageId === stage.id ? (
                      <>
                        {nestUnderBrickId ? (
                          <p className="text-[10px] font-semibold text-accent">
                            Nesting under selected brick
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
                          disabled={editMode}
                          autoFocus
                          className="w-full rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm disabled:opacity-50"
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
                          disabled={editMode}
                          rows={4}
                          className="w-full resize-y rounded-lg border border-border-subtle bg-surface-bg px-2 py-1.5 text-xs leading-relaxed text-text-main disabled:opacity-50"
                        />
                        <div className="flex items-center justify-between gap-2">
                          <button
                            type="button"
                            disabled={editMode || addTemplate.isPending}
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
                              editMode ||
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
                            <Plus size={12} /> Add to all countries
                          </button>
                        </div>
                      </>
                    ) : (
                      <button
                        type="button"
                        disabled={editMode || !defaultTrack || pending}
                        onClick={() => {
                          setNestUnderBrickId(null);
                          setAddingStageId(stage.id);
                          setNewTitleByStage(prev => ({ ...prev, [stage.id]: '' }));
                          setNewStepsByStage(prev => ({ ...prev, [stage.id]: '' }));
                        }}
                        className="inline-flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-border-subtle px-2 py-2 text-xs font-semibold text-text-muted hover:border-accent/40 hover:text-text-main disabled:opacity-50"
                      >
                        <Plus size={13} /> Add Brick
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </HeadlessScrollArea>
      </div>

      {editBrick ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-3 rounded-2xl border border-border-subtle bg-card p-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-text-main">Edit sub-process</h3>
              <button
                type="button"
                onClick={() => setEditBrick(null)}
                className="rounded-lg p-1 text-text-muted hover:bg-surface-bg"
              >
                <X size={16} />
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-xs font-semibold text-text-muted">Name</span>
              <input
                value={editBrickTitle}
                onChange={e => setEditBrickTitle(e.target.value)}
                className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-semibold"
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
                className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-semibold text-text-muted">
                Steps to perform (one per line)
              </span>
              <textarea
                value={editBrickSteps}
                onChange={e => setEditBrickSteps(e.target.value)}
                rows={6}
                className="w-full resize-y rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-xs"
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
                  pending ||
                  !editBrickTitle.trim() ||
                  parseActionStepsText(editBrickSteps).length === 0
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
                Save for all countries
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmationModal
        open={Boolean(deleteBrick)}
        variant="danger"
        title={deleteBrick ? `Delete “${deleteBrick.title}”?` : 'Delete?'}
        message={
          (deleteBrick?.children?.length ?? 0) > 0 ? (
            <p>
              This removes “{deleteBrick?.title}” and its{' '}
              <strong>{deleteBrick?.children?.length}</strong> nested sub-process
              {(deleteBrick?.children?.length ?? 0) === 1 ? '' : 'es'} from Master and from every
              country board (including student journey tasks that mapped to them).
            </p>
          ) : (
            <p>
              This removes the sub-process from Master and from every country board (including
              student journey tasks that mapped to it).
            </p>
          )
        }
        confirmLabel={deleteTemplate.isPending ? 'Deleting…' : 'Delete everywhere'}
        cancelLabel="Cancel"
        onCancel={() => {
          if (!deleteTemplate.isPending) setDeleteBrick(null);
        }}
        onConfirm={() => {
          if (!deleteBrick || deleteTemplate.isPending) return;
          const id = deleteBrick.id;
          void deleteTemplate.mutateAsync(id).then(() => setDeleteBrick(null));
        }}
      />
    </div>
  );
};

export default FlowxMasterWorkflowPage;
