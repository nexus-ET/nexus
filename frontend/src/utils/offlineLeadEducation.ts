import type { GpaCgpaScoreRecord } from '../types/gpaCgpaScore';
import type { QualificationProgramRecord } from '../types/qualificationProgram';

export function buildEducationPayload(
  programCode: string | undefined,
  programs: QualificationProgramRecord[],
  options?: {
    levelId?: number | string;
    major?: string;
    university?: string;
    graduationYear?: number;
    gpaCgpaCode?: string;
    gpaCgpaOther?: string;
    gpaCgpaScores?: GpaCgpaScoreRecord[];
    fullTimeStudyYears?: string;
  }
): {
  program_code?: string;
  level_id?: number;
  full_time_study_years?: string;
  major?: string;
  gpa_cgpa_code?: string;
  gpa_cgpa?: string;
  university?: string;
  graduation_year?: number;
} | undefined {
  const code = programCode?.trim();
  if (!code) return undefined;

  const selected = programs.find(item => item.code.toUpperCase() === code.toUpperCase());
  if (!selected) return undefined;

  const payload: {
    program_code?: string;
    level_id?: number;
    full_time_study_years?: string;
    major?: string;
    gpa_cgpa_code?: string;
    gpa_cgpa?: string;
    university?: string;
    graduation_year?: number;
  } = { program_code: selected.code };

  const levelId = options?.levelId != null && options.levelId !== ''
    ? Number(options.levelId)
    : selected.level_id;
  if (Number.isFinite(levelId) && levelId > 0) {
    payload.level_id = levelId;
  }

  const studyYears = options?.fullTimeStudyYears?.trim();
  if (!studyYears) return undefined;
  payload.full_time_study_years = studyYears;

  const major = options?.major?.trim();
  if (!major) return undefined;
  payload.major = major;

  const university = options?.university?.trim();
  if (!university) return undefined;
  payload.university = university;

  if (!options?.graduationYear) return undefined;
  payload.graduation_year = options.graduationYear;

  const gpaCode = options?.gpaCgpaCode?.trim();
  const gpaScores = options?.gpaCgpaScores ?? [];
  if (!gpaCode) return undefined;
  const selectedGpa = gpaScores.find(item => item.code === gpaCode);
  if (!selectedGpa) return undefined;
  if (selectedGpa.is_other) {
    const customGpa = options?.gpaCgpaOther?.trim();
    if (!customGpa) return undefined;
    payload.gpa_cgpa_code = gpaCode;
    payload.gpa_cgpa = customGpa;
  } else {
    payload.gpa_cgpa_code = gpaCode;
  }

  return payload;
}

export function validateEducationFields(
  programCode: string | undefined,
  major: string | undefined,
  programs: QualificationProgramRecord[],
  university?: string,
  graduationYear?: number,
  fullTimeStudyYears?: string
): string | null {
  if (!fullTimeStudyYears?.trim()) return 'Full-Time Study Years is required.';
  if (!programCode) return 'Program is required.';
  const selected = programs.find(item => item.code.toUpperCase() === programCode.toUpperCase());
  if (!selected) return 'Select a valid program.';
  if (!major?.trim()) return 'Major is required.';
  if (!university?.trim()) return 'University is required.';
  if (!graduationYear) return 'Graduation year is required.';
  return null;
}
