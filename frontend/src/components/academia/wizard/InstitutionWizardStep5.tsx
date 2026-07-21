import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { GraduationCap, Landmark } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import {
  hydrateWizardIntake,
  type WizardIntakeItem,
} from '../../../schemas/wizard/step5-intakes';
import type { InstitutionIntakeRecord } from '../../../types/academicCalendar';
import type {
  InstitutionIntakeHierarchy,
  IntakeHierarchyNode,
} from '../../../types/hierarchicalIntake';
import type { WizardStepHandle } from './form/wizardStepRef';
import { wizardSectionClass, wizardSectionTitleClass } from './form/wizardFormStyles';
import IntakeConfigureContent, {
  type IntakeConfigureContentHandle,
} from '../intakes/IntakeConfigureContent';
import WizardCollegeTabBar from './WizardCollegeTabBar';
import EmptyListMessage from '../../ui/EmptyListMessage';
import { useConfirmation } from '../../../context/ConfirmationContext';

interface InstitutionWizardStep5Props {
  institutionId: number | null;
  institutionName: string;
  colleges: WizardCollegeItem[];
  defaultIntakes: WizardIntakeItem[];
  onHasIntakesChange?: (hasIntakes: boolean) => void;
  onRemoveCollege?: (collegeLocalId: string) => void;
}

const INSTITUTION_TAB = 'institution';

function collegeTabKey(college: Pick<WizardCollegeItem, 'local_id' | 'name'>, index: number) {
  return college.local_id || `college-${index}-${college.name || 'untitled'}`;
}

function mapIntakeRecordToWizardItem(row: InstitutionIntakeRecord): WizardIntakeItem {
  return hydrateWizardIntake({
    name: row.display_name || row.name || row.term_name || 'Intake',
    intake_code: row.intake_code,
    start_date: row.start_date || row.class_start_date || null,
    end_date: row.end_date || null,
    application_deadline: row.application_deadline || null,
  });
}

function hierarchyHasIntakes(node: IntakeHierarchyNode | null | undefined): boolean {
  if (!node) return false;
  if ((node.intake_count || 0) > 0) return true;
  return (node.children || []).some(child => hierarchyHasIntakes(child));
}

function normalizeName(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase();
}

function collectCollegeNodes(node: IntakeHierarchyNode): IntakeHierarchyNode[] {
  const matches = node.entity_type === 'college' ? [node] : [];
  return matches.concat(...(node.children || []).flatMap(child => collectCollegeNodes(child)));
}

/**
 * Keep draft colleges under the institution with API IDs / intake counts.
 * Campus nodes are omitted — intakes are configured only for institution and colleges.
 */
function applyDraftCollegeLinksToHierarchy(
  hierarchy: InstitutionIntakeHierarchy,
  colleges: WizardCollegeItem[]
): InstitutionIntakeHierarchy {
  if (colleges.length === 0) {
    return {
      ...hierarchy,
      root: {
        ...hierarchy.root,
        children: [],
      },
    };
  }

  const draftHierarchy = buildDraftHierarchy(
    hierarchy.institution_id,
    hierarchy.institution_name,
    colleges
  );
  const apiCollegesByName = new Map(
    collectCollegeNodes(hierarchy.root).map(node => [normalizeName(node.name), node])
  );

  return {
    ...hierarchy,
    root: {
      ...hierarchy.root,
      children: draftHierarchy.root.children.map(draftCollege => {
        const apiCollege = apiCollegesByName.get(normalizeName(draftCollege.name));
        if (!apiCollege) {
          return { ...draftCollege, children: [] };
        }
        return {
          ...draftCollege,
          ...apiCollege,
          parent_entity_type: 'institution' as const,
          parent_entity_id: hierarchy.institution_id,
          children: [],
        };
      }),
    },
  };
}

function buildDraftHierarchy(
  institutionId: number,
  institutionName: string,
  colleges: WizardCollegeItem[]
): InstitutionIntakeHierarchy {
  return {
    institution_id: institutionId,
    institution_name: institutionName,
    root: {
      entity_type: 'institution',
      entity_id: institutionId,
      name: institutionName,
      is_overridden: false,
      intake_count: 0,
      children: colleges.map((college, collegeIndex): IntakeHierarchyNode => ({
        entity_type: 'college',
        entity_id: collegeIndex + 1,
        name: college.name,
        parent_entity_type: 'institution',
        parent_entity_id: institutionId,
        is_overridden: false,
        intake_count: 0,
        children: [],
      })),
    },
  };
}

async function deleteIntakesForEntity(
  institutionId: number,
  entityType: 'college' | 'institution',
  entityId: number
): Promise<number> {
  if (!entityId || entityId < 1) return 0;
  const rows = await apiFetch<InstitutionIntakeRecord[]>(
    `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}`
  );
  let deleted = 0;
  for (const row of Array.isArray(rows) ? rows : []) {
    if (!row?.id) continue;
    await apiFetch(`academia/institutions/${institutionId}/intakes/${row.id}`, {
      method: 'DELETE',
    });
    deleted += 1;
  }
  return deleted;
}

function buildCollegeRemoveWarning(collegeName: string): string {
  return [
    `Close and remove "${collegeName}"?`,
    '',
    'This permanently deletes Step 4 and Step 5 data for this school / college:',
    '',
    '• Step 4 (Intakes): Academic calendar templates and term dates for this school / college.',
    '• Step 5 (Gallery): Gallery images linked specifically to this school / college (university images stay).',
    '',
    'The school / college will also be removed from Schools & Colleges and Academics in this wizard draft.',
    '',
    'Saved intake calendars are deleted on the server immediately and cannot be undone from here.',
  ].join('\n');
}

function EntitySummaryHeader({
  node,
  icon: Icon,
}: {
  node: IntakeHierarchyNode;
  icon: typeof Landmark;
}) {
  const entityLabel = node.entity_type === 'institution' ? 'University' : 'College';

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface-bg/40 px-4 py-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={16} className="shrink-0 text-accent" />
        <div className="min-w-0">
          <p className="truncate font-semibold text-text-main">{node.name}</p>
          <p className="text-xs text-text-muted">
            {entityLabel} · {node.intake_count} intake{node.intake_count === 1 ? '' : 's'}
            {node.is_overridden ? ' · Custom' : ''}
          </p>
        </div>
        {node.is_overridden ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
            Custom
          </span>
        ) : null}
      </div>
    </div>
  );
}

const InstitutionWizardStep5 = forwardRef<
  WizardStepHandle<WizardIntakeItem[]>,
  InstitutionWizardStep5Props
>(({ institutionId, institutionName, colleges, defaultIntakes, onHasIntakesChange, onRemoveCollege }, ref) => {
  const openConfirm = useConfirmation();
  const [hierarchy, setHierarchy] = useState<InstitutionIntakeHierarchy | null>(null);
  const [liveIntakes, setLiveIntakes] = useState<WizardIntakeItem[]>(defaultIntakes);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(INSTITUTION_TAB);
  const [intakePanelDirty, setIntakePanelDirty] = useState(false);
  const intakePanelMarkCleanRef = useRef<(() => void) | null>(null);
  const configureRef = useRef<IntakeConfigureContentHandle>(null);
  const lastValidationErrorRef = useRef<string | null>(null);
  const liveIntakesRef = useRef(liveIntakes);
  liveIntakesRef.current = liveIntakes;

  const draftHierarchy = useMemo(() => {
    if (!institutionId) return null;
    return buildDraftHierarchy(institutionId, institutionName, colleges);
  }, [colleges, institutionId, institutionName]);

  const loadHierarchy = useCallback(async () => {
    if (!institutionId) {
      setHierarchy(draftHierarchy);
      liveIntakesRef.current = [];
      setLiveIntakes([]);
      onHasIntakesChange?.(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [data, intakeRows] = await Promise.all([
        apiFetch<InstitutionIntakeHierarchy>(
          `academia/institutions/${institutionId}/intakes/hierarchy`
        ),
        apiFetch<InstitutionIntakeRecord[]>(
          `academia/institutions/${institutionId}/intakes`
        ),
      ]);
      const nextHierarchy =
        data?.root?.children?.length || colleges.length
          ? applyDraftCollegeLinksToHierarchy(data, colleges)
          : draftHierarchy
            ? {
                ...data,
                root: {
                  ...data.root,
                  children: draftHierarchy.root.children,
                },
              }
            : data;
      setHierarchy(nextHierarchy);
      const mapped = (Array.isArray(intakeRows) ? intakeRows : []).map(
        mapIntakeRecordToWizardItem
      );
      liveIntakesRef.current = mapped;
      setLiveIntakes(mapped);
      onHasIntakesChange?.(
        mapped.length > 0 || hierarchyHasIntakes(nextHierarchy?.root)
      );
    } catch (err) {
      setHierarchy(draftHierarchy);
      liveIntakesRef.current = defaultIntakes;
      setLiveIntakes(defaultIntakes);
      onHasIntakesChange?.(defaultIntakes.length > 0);
      setError(err instanceof Error ? err.message : 'Failed to load intake hierarchy.');
    } finally {
      setLoading(false);
    }
  }, [
    colleges,
    defaultIntakes,
    draftHierarchy,
    institutionId,
    onHasIntakesChange,
  ]);

  useEffect(() => {
    void loadHierarchy();
  }, [loadHierarchy]);

  useEffect(() => {
    if (activeTab === INSTITUTION_TAB) return;
    const stillExists = colleges.some(
      (college, index) => collegeTabKey(college, index) === activeTab
    );
    if (!stillExists) setActiveTab(INSTITUTION_TAB);
  }, [activeTab, colleges]);

  useImperativeHandle(
    ref,
    () => ({
      validate: async () => {
        if (!institutionId) {
          const message = 'Save Step 1 (Institution) first so intake calendars can be linked.';
          lastValidationErrorRef.current = message;
          setError(message);
          return false;
        }
        lastValidationErrorRef.current = null;
        setError(null);
        return true;
      },
      getValues: () => liveIntakesRef.current,
      reset: () => {
        void loadHierarchy();
      },
      isDirty: () => intakePanelDirty,
      markClean: () => {
        intakePanelMarkCleanRef.current?.();
        setIntakePanelDirty(false);
      },
      getValidationError: () => lastValidationErrorRef.current || error,
      persistPending: async () => {
        if (!institutionId) {
          const message = 'Save Step 1 (Institution) first so intake calendars can be linked.';
          lastValidationErrorRef.current = message;
          setError(message);
          return false;
        }

        if (configureRef.current) {
          const saveError = await configureRef.current.saveAll();
          if (saveError) {
            lastValidationErrorRef.current = saveError;
            setError(saveError);
            return false;
          }
        }

        await loadHierarchy();
        lastValidationErrorRef.current = null;
        setError(null);
        return true;
      },
    }),
    [error, institutionId, intakePanelDirty, loadHierarchy]
  );

  const selectTab = async (key: string) => {
    if (key === activeTab) return;
    if (intakePanelDirty) {
      const confirmed = await openConfirm({
        title: 'Discard unsaved calendar changes?',
        message:
          'You have unsaved calendar edits on this tab. Switch tabs and discard them?',
        confirmLabel: 'Discard & switch',
        variant: 'warning',
      });
      if (!confirmed) return;
      intakePanelMarkCleanRef.current?.();
      setIntakePanelDirty(false);
    }
    setActiveTab(key);
  };

  const handleRemoveCollegeTab = async (tabKey: string) => {
    const index = colleges.findIndex(
      (college, itemIndex) => collegeTabKey(college, itemIndex) === tabKey
    );
    if (index < 0) return;
    const college = colleges[index];
    const collegeLocalId = college.local_id || college.name;
    const collegeName = college.name || 'this school / college';
    const confirmed = await openConfirm({
      title: 'Close school / college tab?',
      message: buildCollegeRemoveWarning(collegeName),
      confirmLabel: 'Delete data & close',
      variant: 'danger',
    });
    if (!confirmed) return;

    setError(null);
    try {
      if (institutionId && hierarchy) {
        const collegeNode =
          (hierarchy.root.children || []).find(
            node =>
              node.entity_type === 'college' &&
              normalizeName(node.name) === normalizeName(college.name)
          ) || (hierarchy.root.children || [])[index];
        if (collegeNode) {
          await deleteIntakesForEntity(institutionId, 'college', collegeNode.entity_id);
        }
      }
      onRemoveCollege?.(collegeLocalId);
      setActiveTab(INSTITUTION_TAB);
      setIntakePanelDirty(false);
      await loadHierarchy();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to delete intake calendars for this school / college.'
      );
    }
  };

  const activeCollegeIndex = useMemo(() => {
    if (activeTab === INSTITUTION_TAB) return null;
    const index = colleges.findIndex(
      (college, itemIndex) => collegeTabKey(college, itemIndex) === activeTab
    );
    return index >= 0 ? index : null;
  }, [activeTab, colleges]);

  const activeCollegeNode = useMemo(() => {
    if (activeCollegeIndex === null || !hierarchy) return null;
    const college = colleges[activeCollegeIndex];
    if (!college) return null;
    const byName = (hierarchy.root.children || []).find(
      node =>
        node.entity_type === 'college' &&
        normalizeName(node.name) === normalizeName(college.name)
    );
    if (byName) return byName;
    return (hierarchy.root.children || [])[activeCollegeIndex] || null;
  }, [activeCollegeIndex, colleges, hierarchy]);

  return (
    <div className="space-y-6">
      <section className={wizardSectionClass}>
        <h3 className={wizardSectionTitleClass}>Intake management</h3>
        <p className="text-sm text-text-muted">
          Institution is the primary tab. Open a school / college tab to set templates and dates for
          that division — all inline on this page.
        </p>
        {!institutionId ? (
          <p className="mt-3 text-sm text-amber-700">
            Complete and save Step 1 to enable calendar configuration.
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-alert">{error}</p> : null}

        <div className="mt-4">
          <WizardCollegeTabBar
            institutionLabel={institutionName || 'Institution'}
            institutionKey={INSTITUTION_TAB}
            colleges={colleges.map((college, index) => ({
              key: collegeTabKey(college, index),
              label: college.name || 'Untitled school',
              title: college.name || 'Untitled school / college',
              removable: Boolean(onRemoveCollege),
            }))}
            activeKey={activeTab}
            onSelect={key => void selectTab(key)}
            onRemove={onRemoveCollege ? key => void handleRemoveCollegeTab(key) : undefined}
            ariaLabel="Intake scopes"
          />
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-text-muted">Loading hierarchy...</p>
        ) : hierarchy ? (
          <div className="mt-4 space-y-4">
            {activeTab === INSTITUTION_TAB ? (
              <>
                <EntitySummaryHeader node={hierarchy.root} icon={Landmark} />

                {institutionId ? (
                  <div className="rounded-2xl border border-border-subtle bg-card p-4">
                    <IntakeConfigureContent
                      key={`institution-${institutionId}`}
                      ref={configureRef}
                      institutionId={institutionId}
                      entityType="institution"
                      entityId={hierarchy.root.entity_id}
                      onUpdated={() => void loadHierarchy()}
                      onDirtyChange={setIntakePanelDirty}
                      markCleanRef={intakePanelMarkCleanRef}
                    />
                  </div>
                ) : null}

                {colleges.length === 0 ? (
                  <EmptyListMessage message="No schools or colleges yet. Add them in Step 2, then return here to set up calendars." />
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {colleges.map((college, index) => {
                      const node =
                        (hierarchy.root.children || []).find(
                          child =>
                            child.entity_type === 'college' &&
                            normalizeName(child.name) === normalizeName(college.name)
                        ) || (hierarchy.root.children || [])[index];
                      return (
                        <button
                          key={collegeTabKey(college, index)}
                          type="button"
                          onClick={() => void selectTab(collegeTabKey(college, index))}
                          className="rounded-xl border border-border-subtle bg-card p-4 text-left hover:border-accent/40 hover:bg-accent/5"
                        >
                          <div className="flex items-start gap-2">
                            <GraduationCap size={16} className="mt-0.5 shrink-0 text-accent" />
                            <div className="min-w-0">
                              <p className="font-semibold text-text-main">
                                {college.name || 'Untitled school'}
                              </p>
                              <p className="mt-1 text-xs text-text-muted">
                                {node
                                  ? `${node.intake_count} intake${
                                      node.intake_count === 1 ? '' : 's'
                                    }`
                                  : 'Open tab to configure'}
                              </p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            ) : activeCollegeNode ? (
              <>
                <EntitySummaryHeader node={activeCollegeNode} icon={GraduationCap} />

                {institutionId ? (
                  <div className="rounded-2xl border border-border-subtle bg-card p-4">
                    <IntakeConfigureContent
                      key={`college-${activeCollegeNode.entity_id}`}
                      ref={configureRef}
                      institutionId={institutionId}
                      entityType="college"
                      entityId={activeCollegeNode.entity_id}
                      onUpdated={() => void loadHierarchy()}
                      onDirtyChange={setIntakePanelDirty}
                      markCleanRef={intakePanelMarkCleanRef}
                    />
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyListMessage message="Select a school / college tab to configure intakes." />
            )}
          </div>
        ) : institutionId ? (
          <div className="mt-4">
            <EmptyListMessage message="No intake hierarchy available yet. Add schools / colleges in Step 2, then refresh this step." />
          </div>
        ) : null}
      </section>
    </div>
  );
});

InstitutionWizardStep5.displayName = 'InstitutionWizardStep5';
export default InstitutionWizardStep5;
