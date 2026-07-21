import type { PaginatedListResponse } from '../utils/academiaList';

export interface InstitutionSummaryRecord {
  id: number;
  name: string;
  code?: string | null;
  country_id?: number | null;
  state_id?: number | null;
  city_id?: number | null;
  country_name?: string | null;
  state_name?: string | null;
  city_name?: string | null;
  institution_type?: string | null;
  accreditation_details?: string | null;
  is_active: boolean;
  publish_status: 'pending' | 'success' | 'failure';
  last_publish_attempt_at?: string | null;
  sort_order: number;
  level_count: number;
  program_count: number;
  major_count: number;
  course_count: number;
  campus_count: number;
  college_count: number;
  intake_count: number;
  picture_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export type InstitutionSummaryListResponse = PaginatedListResponse<InstitutionSummaryRecord> & {
  active_count: number;
  inactive_count: number;
};

export type InstitutionSummarySortBy =
  | 'name'
  | 'city'
  | 'state'
  | 'country'
  | 'created_at'
  | 'code'
  | 'institution_type'
  | 'program_count'
  | 'major_count'
  | 'course_count'
  | 'campus_count'
  | 'college_count'
  | 'intake_count'
  | 'status';

export type InstitutionSummarySortOrder = 'asc' | 'desc';

export type InstitutionSummaryColumnKey =
  | 'name'
  | 'code'
  | 'city'
  | 'state'
  | 'country'
  | 'institution_type'
  | 'level_count'
  | 'program_count'
  | 'major_count'
  | 'course_count'
  | 'campus_count'
  | 'college_count'
  | 'intake_count'
  | 'picture_count'
  | 'status'
  | 'published'
  | 'created_at';

export const INSTITUTION_SUMMARY_COLUMN_DEFS: {
  key: InstitutionSummaryColumnKey;
  label: string;
  defaultVisible: boolean;
}[] = [
  { key: 'name', label: 'Name', defaultVisible: true },
  { key: 'code', label: 'Code', defaultVisible: false },
  { key: 'city', label: 'City', defaultVisible: true },
  { key: 'state', label: 'State', defaultVisible: true },
  { key: 'country', label: 'Country', defaultVisible: true },
  { key: 'institution_type', label: 'Program Type', defaultVisible: true },
  { key: 'campus_count', label: 'Campuses', defaultVisible: true },
  { key: 'college_count', label: 'Colleges', defaultVisible: true },
  { key: 'level_count', label: 'Levels', defaultVisible: true },
  { key: 'program_count', label: 'Programs', defaultVisible: true },
  { key: 'major_count', label: 'Majors', defaultVisible: true },
  { key: 'course_count', label: 'Courses', defaultVisible: true },
  { key: 'intake_count', label: 'Intakes', defaultVisible: true },
  { key: 'picture_count', label: 'Pictures', defaultVisible: true },
  { key: 'status', label: 'Status', defaultVisible: true },
  { key: 'published', label: 'Published', defaultVisible: true },
  { key: 'created_at', label: 'Created At', defaultVisible: false },
];

export const INSTITUTION_SUMMARY_COLUMNS_STORAGE_KEY = 'nexus.institutionsSummary.visibleColumns';

/** Bump when new default-visible columns are added so saved prefs pick them up. */
export const INSTITUTION_SUMMARY_COLUMNS_VERSION = 6;

export const DEFAULT_INSTITUTION_SUMMARY_SORT: {
  sortBy: InstitutionSummarySortBy;
  sortOrder: InstitutionSummarySortOrder;
} = {
  sortBy: 'created_at',
  sortOrder: 'desc',
};
