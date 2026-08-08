export interface QualificationProgramMajorRecord {
  id: number;
  code?: string | null;
  label: string;
}

export interface QualificationProgramRecord {
  id: string;
  code: string;
  name: string;
  label: string;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  sort_order: number;
  majors?: QualificationProgramMajorRecord[];
}
