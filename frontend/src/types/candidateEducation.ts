import type { EducationMajorRecord } from './educationMajor';
import { FALLBACK_EDUCATION_MAJORS, findEducationMajor } from './educationMajor';

export const GRADUATION_MONTH_OPTIONS = [
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' },
] as const;

export interface CandidateEducationRecord {
  id: number;
  degree_code: string | null;
  degree_label: string | null;
  degree_other: string | null;
  full_time_study_years: string | null;
  full_time_study_years_label?: string | null;
  major: string | null;
  university_name: string | null;
  university_affiliation: string | null;
  graduation_month: number | null;
  graduation_year: number | null;
  gpa_cgpa_code: string | null;
  gpa_cgpa_label: string | null;
  gpa_cgpa_other: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CandidateEducationsResponse {
  booking_id: number;
  lead_id: number | null;
  educations: CandidateEducationRecord[];
  saved_at: string | null;
}

export interface CandidateEducationFormState {
  degree_code: string;
  degree_other: string;
  full_time_study_years: string;
  major: string;
  major_custom: string;
  university_name: string;
  university_affiliation: string;
  graduation_month: string;
  graduation_year: string;
  gpa_cgpa_code: string;
  gpa_cgpa_other: string;
}

export const emptyCandidateEducationForm = (): CandidateEducationFormState => ({
  degree_code: '',
  degree_other: '',
  full_time_study_years: '',
  major: '',
  major_custom: '',
  university_name: '',
  university_affiliation: '',
  graduation_month: '',
  graduation_year: '',
  gpa_cgpa_code: '',
  gpa_cgpa_other: '',
});

export function educationToForm(
  record: CandidateEducationRecord,
  majors: EducationMajorRecord[] = FALLBACK_EDUCATION_MAJORS
): CandidateEducationFormState {
  const matched = findEducationMajor(majors, record.major);
  const majorInOptions = Boolean(matched && !matched.is_other);
  return {
    degree_code: record.degree_code ?? '',
    degree_other: record.degree_other ?? '',
    full_time_study_years: record.full_time_study_years ?? '',
    major: majorInOptions ? matched!.label : record.major ? 'Other' : '',
    major_custom: majorInOptions ? '' : record.major ?? '',
    university_name: record.university_name ?? '',
    university_affiliation: record.university_affiliation ?? '',
    graduation_month: record.graduation_month != null ? String(record.graduation_month) : '',
    graduation_year: record.graduation_year != null ? String(record.graduation_year) : '',
    gpa_cgpa_code: record.gpa_cgpa_code ?? '',
    gpa_cgpa_other: record.gpa_cgpa_other ?? '',
  };
}

export function formToEducationPayload(form: CandidateEducationFormState) {
  return {
    degree_code: form.degree_code || null,
    degree_other: form.degree_other.trim() || null,
    full_time_study_years: form.full_time_study_years || null,
    major:
      form.major === 'Other'
        ? form.major_custom.trim() || null
        : form.major.trim() || null,
    university_name: form.university_name.trim() || null,
    university_affiliation: form.university_affiliation.trim() || null,
    graduation_month: form.graduation_month ? Number(form.graduation_month) : null,
    graduation_year: form.graduation_year ? Number(form.graduation_year) : null,
    gpa_cgpa_code: form.gpa_cgpa_code || null,
    gpa_cgpa_other: form.gpa_cgpa_other.trim() || null,
  };
}

export function formatGraduationPeriod(month: number | null, year: number | null): string | null {
  if (!month && !year) return null;
  const monthLabel = GRADUATION_MONTH_OPTIONS.find(option => option.value === month)?.label;
  if (monthLabel && year) return `${monthLabel} ${year}`;
  if (year) return String(year);
  return monthLabel ?? null;
}

export function sortEducationsByDegreeOrder(
  educations: CandidateEducationRecord[],
  degrees: { code: string; sort_order: number }[]
): CandidateEducationRecord[] {
  const degreeOrder = new Map(degrees.map(degree => [degree.code, degree.sort_order]));
  return [...educations].sort((a, b) => {
    const orderA = degreeOrder.get(a.degree_code ?? '') ?? 999;
    const orderB = degreeOrder.get(b.degree_code ?? '') ?? 999;
    if (orderA !== orderB) return orderA - orderB;

    const yearA = a.graduation_year ?? 0;
    const yearB = b.graduation_year ?? 0;
    if (yearA !== yearB) return yearB - yearA;

    const monthA = a.graduation_month ?? 0;
    const monthB = b.graduation_month ?? 0;
    if (monthA !== monthB) return monthB - monthA;

    return a.id - b.id;
  });
}

export function validateCandidateEducationForm(
  form: CandidateEducationFormState,
  ctx: { degreeIsOther?: boolean; gpaIsOther?: boolean } = {}
): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!form.full_time_study_years.trim()) {
    errors.full_time_study_years = 'Full-Time Study Years is required.';
  }
  if (!form.degree_code.trim()) {
    errors.degree_code = 'Current program is required.';
  }
  const majorValue = form.major === 'Other' ? form.major_custom.trim() : form.major.trim();
  if (!majorValue) {
    errors.major = 'Current major is required.';
  }
  if (!form.university_name.trim()) {
    errors.university_name = 'School / university name is required.';
  }
  if (!form.graduation_month.trim()) {
    errors.graduation_month = 'Graduation month is required.';
  } else {
    const month = Number(form.graduation_month);
    if (!Number.isInteger(month) || month < 1 || month > 12) {
      errors.graduation_month = 'Select a valid graduation month.';
    }
  }
  if (!form.graduation_year.trim()) {
    errors.graduation_year = 'Graduation year is required.';
  } else {
    const year = Number(form.graduation_year);
    if (!Number.isInteger(year) || year < 1950 || year > 2100) {
      errors.graduation_year = 'Enter a valid graduation year.';
    }
  }
  if (!form.gpa_cgpa_code.trim()) {
    errors.gpa_cgpa_code = 'GPA/CGPA score is required.';
  }
  if (ctx.degreeIsOther && !form.degree_other.trim()) {
    errors.degree_other = 'Please enter the program.';
  }
  if (ctx.gpaIsOther && !form.gpa_cgpa_other.trim()) {
    errors.gpa_cgpa_other = 'Please enter the GPA/CGPA score.';
  }

  return errors;
}
