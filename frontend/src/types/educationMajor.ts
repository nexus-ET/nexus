export interface MajorLevelProgramCount {
  level_id: number;
  level_name: string;
  program_count: number;
}

export interface EducationMajorRecord {
  id: number;
  code?: string | null;
  label: string;
  major_description?: string | null;
  sub_majors_key_fields?: string | null;
  program_id?: number | null;
  program_name?: string | null;
  super_major_id?: number | null;
  super_major_name?: string | null;
  level_id?: number | null;
  level_name?: string | null;
  is_other: boolean;
  sort_order: number;
  is_active: boolean;
  color?: string | null;
  level_ids?: number[];
  level_names?: string[];
  level_program_counts?: MajorLevelProgramCount[];
  sub_major_count?: number;
}

export function educationMajorOptionLabel(major: EducationMajorRecord): string {
  const count = major.sub_major_count ?? 0;
  return `${major.label} (${count})`;
}

export interface EducationMajorListResponse {
  items: EducationMajorRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface EducationMajorBulkAssignResponse {
  assigned: number;
  overwritten: number;
  skipped: number;
  program_ids: number[];
}

export interface ProgramMajorMappingRecord {
  id: number;
  program_id: number;
  education_major_id: number;
  major_label: string;
  major_code?: string | null;
  major_color?: string | null;
  program_name?: string | null;
  level_id?: number | null;
  level_name?: string | null;
}

export interface ProgramMajorMappingListResponse {
  items: ProgramMajorMappingRecord[];
}

export const FALLBACK_EDUCATION_MAJORS: EducationMajorRecord[] = [
  { id: 1, code: 'COMPUTER_SCIENCE', label: 'Computer Science', is_other: false, sort_order: 1, is_active: true },
  {
    id: 2,
    code: 'BUSINESS_ADMINISTRATION',
    label: 'Business Administration',
    is_other: false,
    sort_order: 2,
    is_active: true,
  },
  { id: 3, code: 'ENGINEERING', label: 'Engineering', is_other: false, sort_order: 3, is_active: true },
  { id: 4, code: 'MEDICINE', label: 'Medicine', is_other: false, sort_order: 4, is_active: true },
  { id: 5, code: 'DATA_SCIENCE', label: 'Data Science', is_other: false, sort_order: 5, is_active: true },
  { id: 6, code: 'FINANCE', label: 'Finance', is_other: false, sort_order: 6, is_active: true },
  { id: 7, code: 'LAW', label: 'Law', is_other: false, sort_order: 7, is_active: true },
  { id: 8, code: 'ARCHITECTURE', label: 'Architecture', is_other: false, sort_order: 8, is_active: true },
  { id: 9, code: 'PSYCHOLOGY', label: 'Psychology', is_other: false, sort_order: 9, is_active: true },
  { id: 10, code: 'BIOTECHNOLOGY', label: 'Biotechnology', is_other: false, sort_order: 10, is_active: true },
  { id: 11, code: 'OTHER', label: 'Other', is_other: true, sort_order: 99, is_active: true },
];

export function findEducationMajor(
  majors: EducationMajorRecord[],
  value: string | null | undefined
): EducationMajorRecord | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  const upper = trimmed.toUpperCase();
  return majors.find(
    major => major.code === upper || major.label.toLowerCase() === trimmed.toLowerCase()
  );
}

export function isKnownEducationMajor(
  majors: EducationMajorRecord[],
  value: string | null | undefined
): boolean {
  const match = findEducationMajor(majors, value);
  return Boolean(match && !match.is_other);
}
