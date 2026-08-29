export interface QualificationProgramMajorRecord {
  id: number;
  code?: string | null;
  label: string;
}

export interface QualificationProgramRecord {
  id: number;
  code: string;
  name: string;
  label: string;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  program_url?: string | null;
  sort_order: number;
  majors?: QualificationProgramMajorRecord[];
}
