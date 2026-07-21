export * from './shared';
export * from './step1-institution';
export * from './step2-campus';
export * from './step3-colleges';
export * from './step4-courses';
export * from './step5-intakes';
export * from './step6-pictures';
export * from './wizardUiSteps';
export { WIZARD_STEP_LABELS, WIZARD_UI_STEP_COUNT, normalizePublishReportSteps } from './wizardUiSteps';

export interface WizardDraft {
  id: number;
  created_by_user_id: number;
  institution_id: number | null;
  title: string;
  status: string;
  current_step: number;
  completed_steps: number[];
  payload: {
    institution?: import('./step1-institution').WizardInstitutionFormValues | null;
    campus?: import('./step2-campus').WizardCampusItem | null;
    campuses?: import('./step2-campus').WizardCampusItem[];
    colleges?: import('./step3-colleges').WizardCollegeItem[];
    courses?: import('./step4-courses').WizardCourseOfferingItem[];
    /** College local_ids that opted out of inheriting university academics. */
    college_academic_overrides?: string[];
    intakes?: import('./step5-intakes').WizardIntakeItem[];
    pictures?: import('./step6-pictures').WizardPictureItem[];
    /** College local_ids that opted out of inheriting university gallery images. */
    college_picture_overrides?: string[];
  };
  created_at: string;
  updated_at: string;
}

export interface AcademiaAuditEntry {
  id: number;
  user_id: number | null;
  entity_type: string;
  entity_id: number;
  action: string;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  rollback_of_id: number | null;
  created_at: string;
}

export interface PublishReportCheck {
  name: string;
  status: 'passed' | 'failed' | 'warning';
  details: string;
}

export interface PublishReportDiscrepancy {
  description: string;
  resolution: string;
  status: 'fixed' | 'unresolved';
}

export interface PublishReportStep {
  step: number;
  label: string;
  status: 'success' | 'failure' | 'warning';
  started_at: string;
  completed_at: string;
  checks: PublishReportCheck[];
  discrepancies: PublishReportDiscrepancy[];
  result: Record<string, unknown>;
}

export interface InstitutionPublishReport {
  version: number;
  attempt_id: string;
  draft_id: number;
  institution_id: number;
  actor_user_id: number | null;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  outcome: 'success' | 'failure';
  summary: {
    steps_total: number;
    steps_passed: number;
    checks_passed: number;
    discrepancies_found: number;
    discrepancies_fixed: number;
  };
  steps: PublishReportStep[];
}
