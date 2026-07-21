import { useEffect, useMemo, useState } from 'react';
import { Pencil, Search, Unlink } from 'lucide-react';

import { ACADEMIC_FRAMEWORK_LABELS } from '../../../schemas/academicFrameworkHierarchy';
import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import type { WizardCourseOfferingItem } from '../../../schemas/wizard/step4-courses';
import EmptyListMessage from '../../ui/EmptyListMessage';
import HeadlessScrollArea from '../../HeadlessScrollArea';
import WizardCollegeTabBar from './WizardCollegeTabBar';
import {
  collegeScopeKey,
  filterOfferingsForScope,
  institutionScopeKey,
  offeringScopeKey,
  type GroupedProgramLink,
  type WizardAcademicsEntityScope,
} from './wizardAcademicsScope';

export interface WizardAcademicsHierarchyTreeProps {
  institutionName: string;
  colleges: WizardCollegeItem[];
  courses: WizardCourseOfferingItem[];
  collegeOverrides: Set<string>;
  cascadeToColleges: boolean;
  activeScopeKey: string;
  panelEnriching?: boolean;
  onActiveScopeChange: (scopeKey: string) => void;
  onCascadeChange: (enabled: boolean) => void;
  onToggleCollegeOverride: (collegeLocalId: string, enabled: boolean) => void;
  onEditProgramGroup?: (scope: WizardAcademicsEntityScope, group: GroupedProgramLink) => void;
  onUnlinkProgramGroup: (scope: WizardAcademicsEntityScope, group: GroupedProgramLink) => void;
  onUnlinkAllInScope?: (scope: WizardAcademicsEntityScope) => void;
  onAddCollege?: () => void;
  onRemoveCollegeTab?: (collegeLocalId: string) => void;
  groupProgramsForScope: (
    scope: WizardAcademicsEntityScope,
    offerings: WizardCourseOfferingItem[]
  ) => GroupedProgramLink[];
  renderEntityPanel: (scope: WizardAcademicsEntityScope) => React.ReactNode;
}

function isLinkedOffering(offering: WizardCourseOfferingItem): boolean {
  return (
    Number(offering.course_id) > 0 ||
    Boolean(offering.program_id?.trim()) ||
    Number(offering.major_id) > 0
  );
}

function matchesSearch(group: GroupedProgramLink, query: string): boolean {
  if (!query) return true;
  const haystack = [
    group.levelName,
    group.programName,
    group.majorName,
    ...group.courseNames,
  ]
    .join(' ')
    .toLowerCase();
  return haystack.includes(query);
}

/**
 * Compact browse panel for large program/course mappings:
 * fixed height, search + level filter, programs grouped under level headings,
 * headless scroll for program and course panes.
 */
function LinkedProgramsBrowser({
  groups,
  onEdit,
  onUnlink,
}: {
  groups: GroupedProgramLink[];
  onEdit?: (group: GroupedProgramLink) => void;
  onUnlink: (group: GroupedProgramLink) => void;
}) {
  const [query, setQuery] = useState('');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const normalizedQuery = query.trim().toLowerCase();

  const levels = useMemo(() => {
    const counts = new Map<string, { programs: number; courses: number }>();
    for (const group of groups) {
      const level = (group.levelName || '').trim() || 'Other';
      const current = counts.get(level) || { programs: 0, courses: 0 };
      current.programs += 1;
      current.courses += group.courseNames.length;
      counts.set(level, current);
    }
    return [...counts.entries()]
      .map(([name, stats]) => ({ name, ...stats }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [groups]);

  const filteredGroups = useMemo(() => {
    return groups
      .filter(group => {
        const level = (group.levelName || '').trim() || 'Other';
        return levelFilter === 'all' ? true : level === levelFilter;
      })
      .filter(group => matchesSearch(group, normalizedQuery))
      .sort((a, b) => {
        const levelA = (a.levelName || '').trim() || 'Other';
        const levelB = (b.levelName || '').trim() || 'Other';
        const levelCmp = levelA.localeCompare(levelB);
        if (levelCmp !== 0) return levelCmp;
        const programCmp = a.programName.localeCompare(b.programName);
        if (programCmp !== 0) return programCmp;
        return (a.majorName || '').localeCompare(b.majorName || '');
      });
  }, [groups, levelFilter, normalizedQuery]);

  const groupsByLevel = useMemo(() => {
    const sections: Array<{ levelName: string; items: GroupedProgramLink[] }> = [];
    const indexByLevel = new Map<string, number>();
    for (const group of filteredGroups) {
      const levelName = (group.levelName || '').trim() || 'Other';
      let sectionIndex = indexByLevel.get(levelName);
      if (sectionIndex === undefined) {
        sectionIndex = sections.length;
        indexByLevel.set(levelName, sectionIndex);
        sections.push({ levelName, items: [] });
      }
      sections[sectionIndex].items.push(group);
    }
    return sections;
  }, [filteredGroups]);

  useEffect(() => {
    if (filteredGroups.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!selectedKey || !filteredGroups.some(group => group.key === selectedKey)) {
      setSelectedKey(filteredGroups[0].key);
    }
  }, [filteredGroups, selectedKey]);

  const selectedGroup = filteredGroups.find(group => group.key === selectedKey) || null;
  const totalCourses = groups.reduce((sum, group) => sum + group.courseNames.length, 0);

  if (groups.length === 0) {
    return (
      <EmptyListMessage message="No linked programs yet. Use the selectors below to add academics." />
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-bg/30">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
        <p className="text-xs text-text-muted">
          <span className="font-semibold text-text-main">{groups.length}</span> program
          {groups.length === 1 ? '' : 's'}
          <span className="mx-1.5 text-border-subtle">·</span>
          <span className="font-semibold text-text-main">{totalCourses}</span> course
          {totalCourses === 1 ? '' : 's'}
          {levels.length > 0 ? (
            <>
              <span className="mx-1.5 text-border-subtle">·</span>
              <span className="font-semibold text-text-main">{levels.length}</span> level
              {levels.length === 1 ? '' : 's'}
            </>
          ) : null}
          {filteredGroups.length !== groups.length ? (
            <span className="ml-1.5">(showing {filteredGroups.length})</span>
          ) : null}
        </p>
      </div>

      <div className="space-y-2 border-b border-border-subtle px-3 py-2">
        <div className="relative">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
          />
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search programs, majors, or courses…"
            className="w-full rounded-lg border border-border-subtle bg-card py-1.5 pl-8 pr-3 text-sm outline-none focus:border-accent"
          />
        </div>
        {levels.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setLevelFilter('all')}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                levelFilter === 'all'
                  ? 'bg-accent/15 text-accent'
                  : 'bg-card text-text-muted hover:text-text-main'
              }`}
            >
              All levels
            </button>
            {levels.map(level => (
              <button
                key={level.name}
                type="button"
                onClick={() => setLevelFilter(level.name)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                  levelFilter === level.name
                    ? 'bg-accent/15 text-accent'
                    : 'bg-card text-text-muted hover:text-text-main'
                }`}
                title={`${level.programs} program${level.programs === 1 ? '' : 's'} · ${level.courses} course${level.courses === 1 ? '' : 's'}`}
              >
                {level.name}
                <span className="ml-1 opacity-70">({level.programs})</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {filteredGroups.length === 0 ? (
        <div className="px-3 py-6">
          <EmptyListMessage message="No programs match this search or level filter." />
        </div>
      ) : (
        <div className="grid h-[22rem] grid-cols-1 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <HeadlessScrollArea className="h-full border-b border-border-subtle md:border-b-0 md:border-r">
            <div className="pb-2">
              {groupsByLevel.map(section => (
                <div key={section.levelName}>
                  <div className="sticky top-0 z-10 border-b border-border-subtle bg-surface-bg/95 px-3 py-1.5 backdrop-blur-sm">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
                      {section.levelName}
                      <span className="ml-1.5 font-semibold normal-case tracking-normal text-text-muted/80">
                        {section.items.length} program{section.items.length === 1 ? '' : 's'}
                      </span>
                    </p>
                  </div>
                  <ul>
                    {section.items.map(group => {
                      const isSelected = group.key === selectedKey;
                      const courseCount = group.courseNames.length;
                      return (
                        <li key={group.key}>
                          <button
                            type="button"
                            onClick={() => setSelectedKey(group.key)}
                            className={`flex w-full items-start gap-2 px-3 py-2.5 text-left transition-colors ${
                              isSelected ? 'bg-accent/10' : 'hover:bg-card/80'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold text-text-main">
                                {group.programName}
                              </p>
                              <p className="truncate text-xs text-text-muted">
                                {group.majorName && group.majorName !== '—'
                                  ? group.majorName
                                  : 'No major'}
                                {courseCount > 0
                                  ? ` · ${courseCount} course${courseCount === 1 ? '' : 's'}`
                                  : ' · Program scope'}
                              </p>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </HeadlessScrollArea>

          <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card/40">
            {selectedGroup ? (
              <>
                <div className="flex shrink-0 items-start justify-between gap-2 border-b border-border-subtle px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-text-main">
                      {selectedGroup.programName}
                    </p>
                    <p className="truncate text-xs text-text-muted">
                      {(selectedGroup.levelName || '').trim() || 'Other'}
                      {selectedGroup.majorName && selectedGroup.majorName !== '—'
                        ? ` · ${selectedGroup.majorName}`
                        : ''}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
                    {onEdit ? (
                      <button
                        type="button"
                        onClick={() => onEdit(selectedGroup)}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => onUnlink(selectedGroup)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                    >
                      <Unlink size={12} />
                      Unlink
                    </button>
                  </div>
                </div>
                <HeadlessScrollArea className="min-h-0 flex-1">
                  <div className="px-3 py-2">
                    {selectedGroup.courseNames.length === 0 ? (
                      <p className="py-4 text-sm text-text-muted">
                        Linked at program scope — no individual courses mapped.
                      </p>
                    ) : (
                      <ul className="space-y-1">
                        {selectedGroup.courseNames.map((name, index) => (
                          <li
                            key={`${selectedGroup.key}:${index}`}
                            className="rounded-lg bg-surface-bg/60 px-2.5 py-1.5 text-sm text-text-main"
                          >
                            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                              {ACADEMIC_FRAMEWORK_LABELS.course}
                            </span>
                            <p className="mt-0.5">{name}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </HeadlessScrollArea>
              </>
            ) : (
              <p className="px-3 py-6 text-sm text-text-muted">Select a program to view courses.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const WizardAcademicsHierarchyTree: React.FC<WizardAcademicsHierarchyTreeProps> = ({
  institutionName,
  colleges,
  courses,
  collegeOverrides,
  cascadeToColleges,
  activeScopeKey,
  panelEnriching,
  onActiveScopeChange,
  onCascadeChange,
  onToggleCollegeOverride,
  onEditProgramGroup,
  onUnlinkProgramGroup,
  onUnlinkAllInScope,
  onAddCollege,
  onRemoveCollegeTab,
  groupProgramsForScope,
  renderEntityPanel,
}) => {
  const linkedCourses = useMemo(() => courses.filter(isLinkedOffering), [courses]);

  const institutionScope: WizardAcademicsEntityScope = { type: 'institution' };
  const institutionKey = institutionScopeKey();
  const knownCollegeKeys = useMemo(
    () => new Set(colleges.map(college => collegeScopeKey(college.local_id || college.name))),
    [colleges]
  );

  const institutionOfferings = useMemo(() => {
    const scoped = filterOfferingsForScope(linkedCourses, institutionScope, {
      collegeOverrides,
    });
    const orphans = linkedCourses.filter(offering => {
      const key = offeringScopeKey(offering);
      return key !== institutionScopeKey() && !knownCollegeKeys.has(key);
    });
    return [...scoped, ...orphans];
  }, [collegeOverrides, knownCollegeKeys, linkedCourses]);

  const institutionPrograms = useMemo(
    () => groupProgramsForScope(institutionScope, institutionOfferings),
    [groupProgramsForScope, institutionOfferings]
  );

  useEffect(() => {
    if (activeScopeKey === institutionKey) return;
    if (knownCollegeKeys.has(activeScopeKey)) return;
    onActiveScopeChange(institutionKey);
  }, [activeScopeKey, institutionKey, knownCollegeKeys, onActiveScopeChange]);

  const activeCollege = useMemo(() => {
    if (!activeScopeKey.startsWith('college:')) return null;
    const localId = activeScopeKey.slice('college:'.length);
    return colleges.find(college => (college.local_id || college.name) === localId) || null;
  }, [activeScopeKey, colleges]);

  const activeScope: WizardAcademicsEntityScope = activeCollege
    ? {
        type: 'college',
        collegeLocalId: activeCollege.local_id || activeCollege.name,
        collegeName: activeCollege.name,
      }
    : institutionScope;

  const activeHasOverride =
    activeScope.type === 'college' && collegeOverrides.has(activeScope.collegeLocalId);

  const activeOfferings = useMemo(() => {
    if (activeScope.type === 'institution') return institutionOfferings;
    return filterOfferingsForScope(linkedCourses, activeScope, {
      collegeOverrides,
      includeInherited: !activeHasOverride,
    });
  }, [
    activeHasOverride,
    activeScope,
    collegeOverrides,
    institutionOfferings,
    linkedCourses,
  ]);

  const activePrograms = useMemo(
    () => groupProgramsForScope(activeScope, activeOfferings),
    [activeOfferings, activeScope, groupProgramsForScope]
  );

  return (
    <div className="space-y-4">
      <WizardCollegeTabBar
        institutionLabel={institutionName || 'Institution'}
        institutionKey={institutionKey}
        colleges={colleges.map(college => {
          const collegeLocalId = college.local_id || college.name;
          const hasOverride = collegeOverrides.has(collegeLocalId);
          return {
            key: collegeScopeKey(collegeLocalId),
            label: college.name || 'Untitled school',
            title: college.name || 'Untitled school',
            badge: hasOverride ? 'Custom' : null,
            removable: Boolean(onRemoveCollegeTab),
          };
        })}
        activeKey={activeScopeKey}
        onSelect={onActiveScopeChange}
        onAdd={onAddCollege}
        onRemove={
          onRemoveCollegeTab
            ? key => {
                if (!key.startsWith('college:')) return;
                onRemoveCollegeTab(key.slice('college:'.length));
              }
            : undefined
        }
        ariaLabel="Academics scopes"
      />

      <div className="rounded-2xl border border-border-subtle bg-card p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h4 className="text-base font-bold text-text-main">
              {activeScope.type === 'institution'
                ? institutionName || 'Institution'
                : activeCollege?.name || 'School / College'}
            </h4>
            <p className="mt-1 text-sm text-text-muted">
              {activeScope.type === 'institution'
                ? `University academics · ${institutionPrograms.length} linked program${
                    institutionPrograms.length === 1 ? '' : 's'
                  }${panelEnriching ? ' · Loading…' : ''}`
                : `School / college academics · ${activePrograms.length} linked program${
                    activePrograms.length === 1 ? '' : 's'
                  }${activeHasOverride ? ' · Custom' : ''}${
                    panelEnriching ? ' · Loading…' : ''
                  }`}
            </p>
          </div>

          {activeScope.type === 'institution' ? (
            <label className="flex items-center gap-2 text-xs font-semibold text-text-main">
              <input
                type="checkbox"
                className="rounded border-border-subtle accent-accent"
                checked={cascadeToColleges}
                onChange={event => onCascadeChange(event.target.checked)}
              />
              Cascade to all schools / colleges
            </label>
          ) : (
            <label className="flex items-center gap-2 text-xs font-semibold text-text-main">
              <input
                type="checkbox"
                className="rounded border-border-subtle accent-accent"
                checked={activeHasOverride}
                onChange={event =>
                  onToggleCollegeOverride(activeScope.collegeLocalId, event.target.checked)
                }
              />
              Override university academics
            </label>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Linked programs
              </p>
              {activePrograms.length > 0 && onUnlinkAllInScope ? (
                <button
                  type="button"
                  onClick={() => onUnlinkAllInScope(activeScope)}
                  className="inline-flex items-center gap-1 rounded-lg border border-alert/30 px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                >
                  <Unlink size={12} />
                  Unlink all
                </button>
              ) : null}
            </div>
            <LinkedProgramsBrowser
              key={activeScopeKey}
              groups={activePrograms}
              onEdit={
                onEditProgramGroup
                  ? group => onEditProgramGroup(activeScope, group)
                  : undefined
              }
              onUnlink={group => onUnlinkProgramGroup(activeScope, group)}
            />
          </div>

          {renderEntityPanel(activeScope)}
        </div>
      </div>
    </div>
  );
};

export default WizardAcademicsHierarchyTree;
