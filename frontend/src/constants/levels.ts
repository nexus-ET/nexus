import type { LevelRecord } from '../types/level';

/** Legacy target-course level strings stored on framework courses. */
export const TARGET_COURSE_LEVELS = [
  'Undergraduate',
  'Graduate',
  'PhD',
  'Certificate',
] as const;

export type TargetCourseLevel = (typeof TARGET_COURSE_LEVELS)[number];

export const TARGET_COURSE_LEVEL_OPTIONS = TARGET_COURSE_LEVELS.map(level => ({
  value: level,
  label: level,
}));

const LEVEL_ID_TO_TARGET_COURSE_LEVEL: Record<number, TargetCourseLevel> = {
  1: 'Certificate',
  2: 'Undergraduate',
  3: 'Graduate',
  4: 'PhD',
};

export function targetCourseLevelForLevelId(levelId: number | null | undefined): TargetCourseLevel | '' {
  if (!levelId) return '';
  return LEVEL_ID_TO_TARGET_COURSE_LEVEL[levelId] ?? '';
}

export function levelSelectOptions(levels: LevelRecord[]) {
  return levels.map(level => ({
    value: String(level.id),
    label: level.name,
  }));
}
