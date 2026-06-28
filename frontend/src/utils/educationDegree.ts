import type { EducationDegreeRecord } from '../types/educationDegree';
import type { GpaCgpaScoreRecord } from '../types/gpaCgpaScore';

export function educationToFormFields(
  degree: string | null | undefined,
  degreeCode: string | null | undefined,
  degrees: EducationDegreeRecord[]
): { degree_code: string; degree_other: string } {
  if (degreeCode) {
    const byCode = degrees.find(item => item.code === degreeCode);
    if (byCode?.is_other) {
      return { degree_code: byCode.code, degree_other: degree || '' };
    }
    return { degree_code: degreeCode, degree_other: '' };
  }

  if (degree) {
    const byLabel = degrees.find(
      item => item.label.toLowerCase() === degree.toLowerCase() && !item.is_other
    );
    if (byLabel) {
      return { degree_code: byLabel.code, degree_other: '' };
    }
    const other = degrees.find(item => item.is_other);
    return { degree_code: other?.code || 'OTHER', degree_other: degree };
  }

  return { degree_code: '', degree_other: '' };
}

export function buildEducationPayload(
  degreeCode: string | undefined,
  degreeOther: string | undefined,
  degrees: EducationDegreeRecord[],
  options?: {
    major?: string;
    university?: string;
    graduationYear?: number;
    gpaCgpaCode?: string;
    gpaCgpaOther?: string;
    gpaCgpaScores?: GpaCgpaScoreRecord[];
  }
): {
  degree_code?: string;
  degree?: string;
  major?: string;
  gpa_cgpa_code?: string;
  gpa_cgpa?: string;
  university?: string;
  graduation_year?: number;
} | undefined {
  const code = degreeCode?.trim();
  if (!code) return undefined;

  const selected = degrees.find(item => item.code === code);
  if (!selected) return undefined;

  const payload: {
    degree_code?: string;
    degree?: string;
    major?: string;
    gpa_cgpa_code?: string;
    gpa_cgpa?: string;
    university?: string;
    graduation_year?: number;
  } = { degree_code: code };

  if (selected.is_other) {
    const custom = degreeOther?.trim();
    if (!custom) return undefined;
    payload.degree = custom;
  }

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
  degreeCode: string | undefined,
  degreeOther: string | undefined,
  major: string | undefined,
  degrees: EducationDegreeRecord[],
  university?: string,
  graduationYear?: number
): string | null {
  if (!degreeCode) return 'Degree is required.';
  const selected = degrees.find(item => item.code === degreeCode);
  if (!selected) return 'Select a valid education degree.';
  if (selected.is_other && !degreeOther?.trim()) {
    return 'Please enter the degree when Other is selected.';
  }
  if (!major?.trim()) return 'Major is required.';
  if (!university?.trim()) return 'University is required.';
  if (!graduationYear) return 'Graduation year is required.';
  return null;
}

/** @deprecated Use validateEducationFields */
export function validateEducationDegree(
  degreeCode: string | undefined,
  degreeOther: string | undefined,
  degrees: EducationDegreeRecord[]
): string | null {
  return validateEducationFields(degreeCode, degreeOther, undefined, degrees);
}
