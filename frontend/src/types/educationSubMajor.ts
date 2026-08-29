export interface SubMajorLevelProgramCount {
  level_id: number;
  level_name: string;
  count: number;
}

export interface EducationSubMajorRecord {
  id: number;
  name: string;
  sub_major_description?: string | null;
  major_id: number;
  major_label?: string | null;
  major_color?: string | null;
  programs_by_level?: SubMajorLevelProgramCount[];
}

export interface EducationSubMajorListResponse {
  items: EducationSubMajorRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
