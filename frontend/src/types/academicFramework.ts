export interface DegreeRecord {
  /** Framework qualification program — table: programs */
  id: string;
  code: string;
  name: string;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  description?: string | null;
  is_active: boolean;
  sort_order: number;
  major_count?: number;
  major_ids?: number[];
  institution_id?: number | null;
  intake_ids?: number[];
}

export interface ProgramRecord {
  /** Legacy target_programs discipline row */
  id: number;
  program_id: string;
  degree_id: string;
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
  degree_id?: string | null;
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
  id: string;
  name: string;
  majors: HierarchyMajorNode[];
}

export interface HierarchyLevelNode {
  id: number;
  name: string;
  programs: HierarchyProgramNode[];
}

export interface AcademicHierarchySummary {
  levels: HierarchyLevelNode[];
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
export const MAJORS_PATH = `${FRAMEWORK_SECTION_PATH}/majors`;
/** @deprecated Use PROGRAMS_PATH */
export const DEGREES_PATH = PROGRAMS_PATH;
export const COURSES_PATH = `${FRAMEWORK_SECTION_PATH}/courses`;
export const SUMMARY_PATH = `${FRAMEWORK_SECTION_PATH}/summary`;
