export type OfflineLeadSortField = 'full_name' | 'created_at' | 'email' | 'phone_number';
export type OfflineLeadSortDirection = 'asc' | 'desc';
export type OfflineLeadStatusFilter = 'ALL' | 'AI_ACTIVE' | 'HANDOFF';

export interface OfflineLeadLocation {
  city: string;
  state: string;
  country_iso2: string;
}

export interface OfflineLeadEducation {
  degree_code?: string;
  degree?: string;
  degree_other?: string;
  major?: string;
  gpa_cgpa_code?: string;
  gpa_cgpa?: string;
  gpa_cgpa_other?: string;
  university?: string;
  graduation_year?: number;
}

export interface OfflineLeadItem {
  id: number;
  full_name: string;
  first_name?: string | null;
  middle_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone_number?: string | null;
  phone_country_iso2?: string | null;
  stage: string;
  status_label: string;
  source: string;
  target_destination?: string | null;
  target_destination_iso2?: string | null;
  target_program?: string | null;
  target_program_code?: string | null;
  target_course?: string | null;
  target_course_code?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  country_iso2?: string | null;
  degree?: string | null;
  degree_code?: string | null;
  major?: string | null;
  university?: string | null;
  graduation_year?: number | null;
  gpa_cgpa?: string | null;
  gpa_cgpa_code?: string | null;
  date_of_birth?: string | null;
  age?: number | null;
  created_at?: string | null;
}

export interface OfflineLeadListResponse {
  items: OfflineLeadItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface OfflineLeadCreatePayload {
  first_name: string;
  middle_name?: string;
  last_name: string;
  email?: string;
  phone_country_iso2: string;
  phone_local: string;
  date_of_birth?: string;
  education?: OfflineLeadEducation;
  target_destination_iso2: string;
  target_program_code: string;
  target_course_code: string;
  location: OfflineLeadLocation;
}

export interface OfflineLeadsQuery {
  page: number;
  pageSize: number;
  q: string;
  status: OfflineLeadStatusFilter;
  sortBy: OfflineLeadSortField;
  sortDir: OfflineLeadSortDirection;
}

export interface OfflineLeadDuplicateCheck {
  email_taken: boolean;
  phone_taken: boolean;
}
