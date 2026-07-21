export type IntakeType = 'Fixed' | 'Rolling';
export type IntakeStatus = 'Draft' | 'Open' | 'Closed';

export interface TemplateIntakeConfig {
  term_name: string;
  intake_type: IntakeType;
  expected_duration_months: number;
}

export interface GlobalAcademicTemplate {
  id: number;
  name: string;
  description?: string | null;
  default_intake_configs: TemplateIntakeConfig[];
  is_active: boolean;
  sort_order: number;
}

export interface InstitutionIntakeRecord {
  id: number;
  institution_id: number;
  campus_id?: number | null;
  template_id?: number | null;
  parent_intake_id?: number | null;
  name: string;
  term_name?: string | null;
  year?: number | null;
  intake_type: IntakeType;
  status: IntakeStatus;
  intake_code?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  application_deadline?: string | null;
  check_in_date?: string | null;
  orientation_date?: string | null;
  class_start_date?: string | null;
  level_ids?: number[];
  entity_type?: 'institution' | 'campus' | 'college' | null;
  entity_id?: number | null;
  is_overridden?: boolean;
  cascade_to_children?: boolean;
  is_active: boolean;
  sort_order: number;
  display_name?: string | null;
}

export interface InstitutionIntakeCalendar {
  institution_id: number;
  years: number[];
  intakes_by_year: Record<number, InstitutionIntakeRecord[]>;
}

export const INTAKE_STATUS_LABELS: Record<IntakeStatus, string> = {
  Draft: 'Draft',
  Open: 'Open',
  Closed: 'Closed',
};

export const INTAKE_TYPE_LABELS: Record<IntakeType, string> = {
  Fixed: 'Fixed Term',
  Rolling: 'Rolling Admissions',
};

export function intakeDisplayName(intake: InstitutionIntakeRecord): string {
  if (intake.display_name) return intake.display_name;
  const term = intake.term_name || intake.name || 'Term';
  return intake.year ? `${term} ${intake.year}` : term;
}

/** JSON object keys are strings — normalize year lookup for intakes_by_year. */
export function getIntakesForYear(
  calendar: InstitutionIntakeCalendar | null,
  year: number | null
): InstitutionIntakeRecord[] {
  if (!calendar || year == null) return [];
  const grouped = calendar.intakes_by_year as Record<string, InstitutionIntakeRecord[]>;
  return grouped[String(year)] ?? [];
}

export function normalizeCalendarYears(calendar: InstitutionIntakeCalendar | null): number[] {
  if (!calendar?.years?.length) return [];
  return calendar.years.map(year => Number(year)).filter(year => !Number.isNaN(year));
}

export const institutionIntakesPath = (institutionId: number | string) =>
  `/academia/institutions/${institutionId}/intakes`;
