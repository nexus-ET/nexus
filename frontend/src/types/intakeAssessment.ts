/** Sub-Process 1.1 Intake Session counselor assessment workspace. */

export type IntakeTaskStatus = 'planned' | 'in_progress' | 'complete';

export interface IntakeAcademicAssessment {
  grading_scale_code: string | null;
  notes: string;
  status: IntakeTaskStatus;
}

export interface IntakeEnglishAssessment {
  selected_test_id: number | null;
  test_name: string | null;
  reading: string | null;
  writing: string | null;
  listening: string | null;
  speaking: string | null;
  overall: string | null;
  language_waiver_eligible: boolean;
}

export interface IntakeGapAssessment {
  reason: string | null;
  notes: string;
}

export interface IntakeGoalsAssessment {
  countries: string[];
  colleges: string[];
  intake_season: string | null;
  intake_year: number | null;
}

export interface IntakeFinancialAssessment {
  funding_source: string | null;
  budget_min: number;
  budget_max: number;
  currency: string;
  notes: string;
}

export interface IntakeAssessmentPayload {
  academic: IntakeAcademicAssessment;
  english: IntakeEnglishAssessment;
  gap: IntakeGapAssessment;
  goals: IntakeGoalsAssessment;
  financial: IntakeFinancialAssessment;
}

export interface IntakeEducationSnapshot {
  id: number;
  degree_label?: string | null;
  university_name?: string | null;
  graduation_year?: number | null;
  graduation_month?: number | null;
  gpa_cgpa_label?: string | null;
  gpa_cgpa_code?: string | null;
  major?: string | null;
}

export interface IntakeTestScoreSnapshot {
  id: number;
  test_name?: string | null;
  overall_score?: string | number | null;
  exam_date?: string | null;
  sections?: { section_name: string; score: string | number | null }[];
}

export interface IntakeWorkSnapshot {
  id: number;
  company_name?: string | null;
  job_title?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
}

export interface IntakeProfileSnapshot {
  educations: IntakeEducationSnapshot[];
  test_scores: IntakeTestScoreSnapshot[];
  work_experiences: IntakeWorkSnapshot[];
  aspirations?: Record<string, unknown> | null;
  preferred_country?: string | null;
  course_interest?: string | null;
  candidate_name?: string | null;
}

export interface IntakeAssessmentResponse {
  booking_id: number;
  lead_id: number | null;
  assessment: IntakeAssessmentPayload;
  profile_snapshot: IntakeProfileSnapshot;
}

export const GAP_REASON_OPTIONS = [
  'Employment',
  'Military Service',
  'Medical',
  'Personal',
  'Family Care',
  'Travel / Gap Year',
  'Other',
] as const;

export const FUNDING_SOURCE_OPTIONS = [
  'Self-Funded',
  'Educational Loan',
  'Family Sponsor',
  'Scholarship',
  'Employer Sponsored',
  'Mixed',
] as const;

export const INTAKE_SEASON_OPTIONS = ['Fall', 'Spring', 'Summer', 'Winter'] as const;

export const INTAKE_TASK_STATUS_OPTIONS: { value: IntakeTaskStatus; label: string }[] = [
  { value: 'planned', label: 'Planned' },
  { value: 'in_progress', label: 'In-Progress' },
  { value: 'complete', label: 'Complete' },
];

export function emptyIntakeAssessment(year = new Date().getFullYear() + 1): IntakeAssessmentPayload {
  return {
    academic: { grading_scale_code: null, notes: '', status: 'planned' },
    english: {
      selected_test_id: null,
      test_name: 'IELTS',
      reading: null,
      writing: null,
      listening: null,
      speaking: null,
      overall: null,
      language_waiver_eligible: false,
    },
    gap: { reason: null, notes: '' },
    goals: {
      countries: [],
      colleges: [],
      intake_season: 'Fall',
      intake_year: year,
    },
    financial: {
      funding_source: null,
      budget_min: 10000,
      budget_max: 45000,
      currency: 'USD',
      notes: '',
    },
  };
}
