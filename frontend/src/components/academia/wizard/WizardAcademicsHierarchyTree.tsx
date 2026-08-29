import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Pencil, Search, Unlink } from 'lucide-react';

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
  majorGroupHeading,
  NO_MAJOR_GROUP_LABEL,
  offeringScopeKey,
  programUrlHref,
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
 * fixed height, search + optional level filter, programs grouped under major headings,
 * level shown as a badge on each program row.
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
  const [collapsedMajors, setCollapsedMajors] = useState<Set<string>>(() => new Set());

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

  const majors = useMemo(() => {
    const counts = new Map<string, { programs: number; courses: number }>();
    for (const group of groups) {
      const major = majorGroupHeading(group.majorName);
      const current = counts.get(major) || { programs: 0, courses: 0 };
      current.programs += 1;
      current.courses += group.courseNames.length;
      counts.set(major, current);
    }
    return [...counts.entries()]
      .map(([name, stats]) => ({ name, ...stats }))
      .sort((a, b) => {
        if (a.name === NO_MAJOR_GROUP_LABEL) return 1;
        if (b.name === NO_MAJOR_GROUP_LABEL) return -1;
        return a.name.localeCompare(b.name);
      });
  }, [groups]);

  const filteredGroups = useMemo(() => {
    return groups
      .filter(group => {
        const level = (group.levelName || '').trim() || 'Other';
        return levelFilter === 'all' ? true : level === levelFilter;
      })
      .filter(group => matchesSearch(group, normalizedQuery))
      .sort((a, b) => {
        const majorA = majorGroupHeading(a.majorName);
        const majorB = majorGroupHeading(b.majorName);
        if (majorA === NO_MAJOR_GROUP_LABEL && majorB !== NO_MAJOR_GROUP_LABEL) return 1;
        if (majorB === NO_MAJOR_GROUP_LABEL && majorA !== NO_MAJOR_GROUP_LABEL) return -1;
        const majorCmp = majorA.localeCompare(majorB);
        if (majorCmp !== 0) return majorCmp;
        const programCmp = a.programName.localeCompare(b.programName);
        if (programCmp !== 0) return programCmp;
        return ((a.levelName || '').trim() || 'Other').localeCompare(
          (b.levelName || '').trim() || 'Other'
        );
      });
  }, [groups, levelFilter, normalizedQuery]);

  const groupsByMajor = useMemo(() => {
    const sections: Array<{ majorName: string; items: GroupedProgramLink[] }> = [];
    const indexByMajor = new Map<string, number>();
    for (const group of filteredGroups) {
      const majorName = majorGroupHeading(group.majorName);
      let sectionIndex = indexByMajor.get(majorName);
      if (sectionIndex === undefined) {
        sectionIndex = sections.length;
        indexByMajor.set(majorName, sectionIndex);
        sections.push({ majorName, items: [] });
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
          {majors.length > 0 ? (
            <>
              <span className="mx-1.5 text-border-subtle">·</span>
              <span className="font-semibold text-text-main">{majors.length}</span> major
              {majors.length === 1 ? '' : 's'}
            </>
          ) : null}
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
              {groupsByMajor.map(section => {
                const expanded = !collapsedMajors.has(section.majorName);
                return (
                <div key={section.majorName}>
                  <div className="sticky top-0 z-10">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => {
                        setCollapsedMajors(prev => {
                          const next = new Set(prev);
                          if (next.has(section.majorName)) next.delete(section.majorName);
                          else next.add(section.majorName);
                          return next;
                        });
                      }}
                      className="flex w-full items-center gap-2 border-b border-accent/30 bg-accent px-3 py-1.5 text-left text-white"
                    >
                      <ChevronDown
                        size={16}
                        className={`shrink-0 transition-transform ${expanded ? '' : '-rotate-90'}`}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate text-base font-semibold">
                        {section.majorName}
                      </span>
                      <span className="shrink-0 text-xs font-semibold text-white/80">
                        {section.items.length} program{section.items.length === 1 ? '' : 's'}
                      </span>
                    </button>
                  </div>
                  {expanded ? (
                  <ul>
                    {section.items.map(group => {
                      const isSelected = group.key === selectedKey;
                      const courseCount = group.courseNames.length;
                      const levelLabel = (group.levelName || '').trim();
                      const programUrl = group.programUrl?.trim() || '';
                      return (
                        <li key={group.key} className="flex items-start gap-1">
                          <button
                            type="button"
                            onClick={() => setSelectedKey(group.key)}
                            className={`flex min-w-0 flex-1 items-start gap-2 px-3 py-2.5 text-left transition-colors ${
                              isSelected ? 'bg-accent/10' : 'hover:bg-card/80'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold text-text-main">
                                {group.programName}
                              </p>
                              <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                                {levelLabel && levelLabel !== '—' ? (
                                  <span className="rounded-md bg-card px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                                    {levelLabel}
                                  </span>
                                ) : null}
                                <span className="truncate text-xs text-text-muted">
                                  {courseCount > 0
                                    ? `${courseCount} course${courseCount === 1 ? '' : 's'}`
                                    : 'Program scope'}
                                </span>
                              </div>
                            </div>
                          </button>
                          {programUrl ? (
                            <a
                              href={programUrlHref(programUrl)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="shrink-0 px-2 py-2.5 text-xs font-semibold text-accent hover:underline"
                            >
                              View Program
                            </a>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                  ) : null}
                </div>
                );
              })}
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
                    {selectedGroup.programUrl?.trim() ? (
                      <a
                        href={programUrlHref(selectedGroup.programUrl)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-block text-xs font-semibold text-accent hover:underline"
                      >
                        View Program
                      </a>
                    ) : (
                      <span className="mt-1 block text-xs text-text-muted">—</span>
                    )}
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
    const knownCollegeIds = new Set(
      colleges.map(college => college.id).filter((id): id is number => Number(id) > 0)
    );
    const orphans = linkedCourses.filter(offering => {
      const key = offeringScopeKey(offering);
      if (key === institutionScopeKey()) return false;
      if (knownCollegeKeys.has(key)) return false;
      // Live DB college_id without matching draft local_id — still owned by a known college.
      if (offering.college_id && knownCollegeIds.has(offering.college_id)) return false;
      return true;
    });
    return [...scoped, ...orphans];
  }, [collegeOverrides, colleges, knownCollegeKeys, linkedCourses]);

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
        collegeId: activeCollege.id ?? null,
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
