export interface TargetProgramRecord {
  id: number;
  code: string;
  label: string;
  sort_order: number;
}

export interface TargetCourseRecord {
  id: number;
  code: string;
  label: string;
  program_code: string;
  sort_order: number;
}

export const FALLBACK_TARGET_PROGRAMS: TargetProgramRecord[] = [
  { id: 1, code: 'BUSINESS_MANAGEMENT', label: 'Business & Management', sort_order: 1 },
  { id: 2, code: 'COMPUTER_SCIENCE_IT', label: 'Computer Science & IT', sort_order: 7 },
];

export const FALLBACK_TARGET_COURSES: TargetCourseRecord[] = [
  { id: 1, code: 'MBA', label: 'MBA', program_code: 'BUSINESS_MANAGEMENT', sort_order: 1 },
  {
    id: 2,
    code: 'MSC_DATA_SCIENCE',
    label: 'MSc Data Science',
    program_code: 'COMPUTER_SCIENCE_IT',
    sort_order: 2,
  },
];
