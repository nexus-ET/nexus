export interface DegreeRecord {
  /** Framework qualification program — table: programs */
  id: number;
  code: string;
  name: string;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  description?: string | null;
  program_url?: string | null;
  is_active: boolean;
  sort_order: number;
  major_count?: number;
  major_ids?: number[];
  major_names?: string[];
  sub_major_ids?: number[];
  sub_major_names?: string[];
  institution_id?: number | null;
  institution_ids?: number[];
  institution_names?: string[];
  country_id?: number | null;
  college_id?: number | null;
  intake_ids?: number[];
}

export interface ProgramRecord {
  /** Legacy target_programs discipline row */
  id: number;
  program_id: number;
  degree_id: number;
  code: string;
  label: string;
  name: string;
  description?: string | null;
  degree_name?: string | null;
  level_id?: number | null;
  level_code?: string | null;
  level_name?: string | null;
  is_active: boolean;
  sort_order: number;
  course_count?: number;
}

export interface CourseRecord {
  /** Academic framework course — table: education_courses */
  id: number;
  program_id: number;
  major_id?: number | null;
  major_ids?: number[];
  degree_id?: number | null;
  level_id?: number | null;
  code?: string | null;
  description?: string | null;
  label: string;
  name: string;
  level?: string | null;
  is_active: boolean;
  sort_order: number;
  program_code?: string | null;
  program_label?: string | null;
  program_name?: string | null;
  major_name?: string | null;
  major_names?: string[];
  degree_name?: string | null;
  hierarchy_breadcrumb?: string | null;
}

export interface HierarchyCourseNode {
  id: number;
  name: string;
  code?: string | null;
}

export interface HierarchyMajorNode {
  id: number;
  name: string;
  courses: HierarchyCourseNode[];
}

export interface HierarchyProgramNode {
  id: number;
  name: string;
  majors: HierarchyMajorNode[];
  sub_major_count?: number;
  sub_major_ids?: number[];
}

export interface HierarchyLevelNode {
  id: number;
  name: string;
  programs: HierarchyProgramNode[];
  /** Distinct catalog majors mapped to programs at this level. */
  major_count?: number;
  /** Distinct catalog sub-majors mapped to programs at this level. */
  sub_major_count?: number;
}

export interface FrameworkCoveragePair {
  mapped: number;
  unmapped: number;
  total: number;
  mapped_pct?: number;
  unmapped_pct?: number;
}

export interface FrameworkInstitutionCoverage {
  institution_id: number;
  institution_name: string;
  country_id?: number | null;
  country_name?: string | null;
  program_count: number;
  without_major: number;
  without_sub_major: number;
  without_course: number;
  without_level: number;
  without_url?: number;
  without_major_pct?: number;
  without_sub_major_pct?: number;
  without_course_pct?: number;
  without_level_pct?: number;
  without_url_pct?: number;
}

export interface FrameworkCountryCoverage {
  country_id?: number | null;
  country_name?: string | null;
  institution_count: number;
  campus_count: number;
  college_count: number;
  program_count: number;
  major_count: number;
  sub_major_count: number;
  level_count: number;
  programs_with_no_major?: number;
  programs_with_no_sub_major?: number;
  major_mapping: FrameworkCoveragePair;
  sub_major_mapping: FrameworkCoveragePair;
  course_link: FrameworkCoveragePair;
  level_assignment: FrameworkCoveragePair;
  program_url?: FrameworkCoveragePair;
  by_institution: FrameworkInstitutionCoverage[];
  program_ids?: number[];
}

export interface FrameworkCoverageMetrics {
  institution_count: number;
  campus_count: number;
  college_count: number;
  program_count: number;
  major_count: number;
  sub_major_count: number;
  level_count: number;
  course_count: number;
  programs_with_no_major?: number;
  programs_with_no_sub_major?: number;
  major_mapping: FrameworkCoveragePair;
  sub_major_mapping: FrameworkCoveragePair;
  course_link: FrameworkCoveragePair;
  level_assignment: FrameworkCoveragePair;
  program_url?: FrameworkCoveragePair;
  by_institution: FrameworkInstitutionCoverage[];
  by_institution_truncated?: boolean;
  by_country?: FrameworkCountryCoverage[];
}

export interface AcademicHierarchySummary {
  levels: HierarchyLevelNode[];
  coverage?: FrameworkCoverageMetrics;
}

export interface CourseListResponse {
  items: CourseRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface DegreeListResponse {
  items: DegreeRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export const FRAMEWORK_SECTION_PATH = '/academia/framework';
export const LEVELS_PATH = `${FRAMEWORK_SECTION_PATH}/levels`;
export const PROGRAMS_PATH = `${FRAMEWORK_SECTION_PATH}/programs`;
export const SUPER_MAJORS_PATH = `${FRAMEWORK_SECTION_PATH}/super-majors`;
export const MAJORS_PATH = `${FRAMEWORK_SECTION_PATH}/majors`;
export const SUB_MAJORS_PATH = `${FRAMEWORK_SECTION_PATH}/sub-majors`;
/** @deprecated Use PROGRAMS_PATH */
export const DEGREES_PATH = PROGRAMS_PATH;
export const COURSES_PATH = `${FRAMEWORK_SECTION_PATH}/courses`;
export const SUMMARY_PATH = `${FRAMEWORK_SECTION_PATH}/summary`;
