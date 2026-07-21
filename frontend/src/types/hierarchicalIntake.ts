export type IntakeEntityType = 'institution' | 'campus' | 'college';

export interface IntakeHierarchyNode {
  entity_type: IntakeEntityType;
  entity_id: number;
  name: string;
  parent_entity_type?: IntakeEntityType | null;
  parent_entity_id?: number | null;
  is_overridden: boolean;
  intake_count: number;
  children: IntakeHierarchyNode[];
}

export interface InstitutionIntakeHierarchy {
  institution_id: number;
  institution_name: string;
  root: IntakeHierarchyNode;
}

export interface CalendarIntakeAlert {
  id: number;
  institution_id: number;
  institution_name: string;
  entity_type: IntakeEntityType;
  entity_id: number;
  entity_name: string;
  term_name: string;
  year: number;
  class_start_date?: string | null;
  days_until_start?: number | null;
  alert_type: string;
  alerted_at?: string | null;
  link_path?: string | null;
}

export interface IntakeConfigurePayload {
  entity_type: IntakeEntityType;
  entity_id: number;
  template_id: number;
  level_ids: number[];
  term_names?: string[];
  year?: number;
  cascade_to_children: boolean;
}

export interface IntakeDateFormValues {
  id: number;
  name: string;
  template_id?: number | null;
  term_name?: string | null;
  year?: number | null;
  application_deadline: string;
  check_in_date: string;
  orientation_date: string;
  class_start_date: string;
  is_overridden: boolean;
  parent_intake_id?: number | null;
  /** Local preview row from a template; not yet persisted. */
  is_pending?: boolean;
  /** Levels this calendar row applies to (shared multi-select or a single level). */
  level_ids: number[];
}

export type IntakeTimelineDateField =
  | 'application_deadline'
  | 'check_in_date'
  | 'orientation_date'
  | 'class_start_date';

export interface IntakeDateValidationResult {
  messages: string[];
  conflictingFields: IntakeTimelineDateField[];
}

export function validateIntakeTimeline(values: {
  application_deadline: string;
  check_in_date?: string;
  orientation_date?: string;
  class_start_date: string;
}): IntakeDateValidationResult {
  const messages: string[] = [];
  const conflictingFields = new Set<IntakeTimelineDateField>();
  const required: Array<[IntakeTimelineDateField, string]> = [
    ['application_deadline', 'Application Deadline'],
    ['orientation_date', 'Orientation Date'],
    ['check_in_date', 'Check-in Date'],
    ['class_start_date', 'Class Start Date'],
  ];

  for (const [field, label] of required) {
    if (!values[field]) {
      messages.push(`${label} is required.`);
      conflictingFields.add(field);
    }
  }

  if (messages.length > 0) {
    return { messages, conflictingFields: [...conflictingFields] };
  }

  const deadline = new Date(values.application_deadline).getTime();
  const orientation = new Date(values.orientation_date!).getTime();
  const checkIn = new Date(values.check_in_date!).getTime();
  const classStart = new Date(values.class_start_date).getTime();

  if ([deadline, orientation, checkIn, classStart].some(Number.isNaN)) {
    return {
      messages: ['Enter valid dates for the academic timeline.'],
      conflictingFields: required.map(([field]) => field),
    };
  }

  // Chronological order:
  // Application Deadline < Orientation Date <= Check-in Date <= Class Start Date
  if (deadline >= orientation) {
    messages.push('Application Deadline must be earlier than Orientation Date.');
    conflictingFields.add('application_deadline');
    conflictingFields.add('orientation_date');
  }
  if (orientation > checkIn) {
    messages.push('Check-in Date cannot be earlier than Orientation Date.');
    conflictingFields.add('orientation_date');
    conflictingFields.add('check_in_date');
  }
  if (checkIn > classStart) {
    messages.push('Check-in Date cannot be later than Class Start Date.');
    conflictingFields.add('check_in_date');
    conflictingFields.add('class_start_date');
  }

  return { messages, conflictingFields: [...conflictingFields] };
}

export function validateIntakeDates(values: {
  application_deadline: string;
  check_in_date?: string;
  orientation_date?: string;
  class_start_date: string;
}): string | null {
  return validateIntakeTimeline(values).messages[0] || null;
}
