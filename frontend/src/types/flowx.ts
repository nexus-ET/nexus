/** FlowX types — country-first overseas process engine. */

export type FlowxStageKey =
  | 'counselling'
  | 'college_finding'
  | 'document_submission'
  | 'tests'
  | 'admission_processing'
  | 'visa_processing'
  | 'predeparture_travel'
  | 'landing';

export type FlowxEnrollmentStatus = 'active' | 'paused' | 'completed' | 'dormant' | 'archived';
export type FlowxKanbanStatus = 'todo' | 'in_progress' | 'in_review' | 'approved' | 'blocked';
export type FlowxSlaStatus = 'on_track' | 'amber' | 'breached';
export type FlowxTrackStatus = 'not_started' | 'in_progress' | 'completed' | 'blocked';

export interface FlowxTaskTemplate {
  id: string;
  track_id: string;
  stage_id?: string | null;
  stage_key?: FlowxStageKey | null;
  track_name?: string | null;
  track_label?: string | null;
  title: string;
  description?: string | null;
  /** Ordered checklist steps shown on hover (one action per line when edited). */
  action_steps?: string[];
  position_index: number;
  sla_days: number;
  is_country_specific: boolean;
  auto_trigger_source?: string | null;
  is_active?: boolean;
  is_optional?: boolean;
  override_action?: string | null;
  override_reason?: string | null;
  link_count?: number;
  /** When set, this brick nests under another sub-process (e.g. 3.2.1 under 3.2). */
  parent_template_id?: string | null;
  master_template_id?: string | null;
  children?: FlowxTaskTemplate[];
}

export interface FlowxSubprocessLink {
  id: string;
  workflow_id: string;
  from_template_id: string;
  to_template_id: string;
  from_title?: string | null;
  to_title?: string | null;
  link_type: 'depends_on' | 'related';
  created_at?: string | null;
}

/** Country-workflow link resolved onto enrollment tasks for journey UI. */
export interface FlowxEnrollmentLink {
  id: string;
  workflow_id: string;
  from_template_id: string;
  to_template_id: string;
  from_task_id?: string | null;
  to_task_id?: string | null;
  from_title?: string | null;
  to_title?: string | null;
  link_type: 'depends_on' | 'related';
  created_at?: string | null;
}

export interface FlowxTrackTemplate {
  id: string;
  stage_id: string;
  track_name: string;
  track_label: string;
  position_index: number;
  task_templates: FlowxTaskTemplate[];
}

export interface FlowxStage {
  id: string;
  workflow_id: string;
  stage_key: FlowxStageKey;
  label: string;
  position_index: number;
  /** When true, process column is omitted from the country board. */
  is_hidden?: boolean;
  tracks: FlowxTrackTemplate[];
  bricks?: FlowxTaskTemplate[];
}

export interface FlowxCountrySummary {
  id: string;
  country_iso2: string;
  country_name: string;
  name: string;
  status: string;
  stage_count: number;
  template_task_count: number;
  enrollment_count: number;
  institution_count?: number;
  college_count?: number;
  students_processed?: number;
  students_in_process?: number;
  updated_at?: string | null;
}

export interface FlowxCountryDetail {
  id: string;
  country_iso2: string;
  country_name: string;
  name: string;
  status: string;
  stages: FlowxStage[];
  links?: FlowxSubprocessLink[];
  unlinked_bricks?: FlowxTaskTemplate[];
  enrollment_count: number;
  institution_count?: number;
  college_count?: number;
  students_processed?: number;
  students_in_process?: number;
  is_master?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface FlowxTask {
  id: string;
  enrollment_track_id: string;
  title: string;
  description?: string | null;
  kanban_status: FlowxKanbanStatus;
  position_index: number;
  sla_due_at?: string | null;
  sla_status: FlowxSlaStatus;
  /** Brick progress — Intake Session is driven by counselling booking status. */
  progress_percentage?: number;
  is_auto_added?: boolean;
  /** Optional child processes appear on the journey but do not block progress. */
  is_optional?: boolean;
  auto_trigger_source?: string | null;
  assigned_to?: number | null;
  /** Checklist steps from the country/master workflow brick. */
  action_steps?: string[];
  /** Persisted activity checklist progress for this journey task. */
  checklist_state?: {
    checked?: boolean[];
    confirmed_complete?: boolean;
    steps?: string[];
    updated_by?: number | null;
    updated_at?: string | null;
  } | null;
  /** Country-workflow template id (for nesting under parent bricks). */
  template_id?: string | null;
  parent_template_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Country-workflow stage mirrored onto a student journey. */
export interface FlowxEnrollmentStageMeta {
  stage_key: FlowxStageKey;
  label: string;
  position_index: number;
  is_hidden?: boolean;
}

export interface FlowxEnrollmentTrack {
  id: string;
  enrollment_id: string;
  stage_key: FlowxStageKey;
  track_name: string;
  track_label: string;
  position_index?: number;
  track_status: FlowxTrackStatus;
  progress_percentage: number;
  tasks: FlowxTask[];
}

export interface FlowxEnrollment {
  id: string;
  lead_id: number;
  lead_name?: string | null;
  lead_phone?: string | null;
  preferred_country?: string | null;
  country_iso2: string;
  country_name: string;
  country_workflow_id: string;
  institution_id?: number | null;
  institution_name?: string | null;
  college_id?: number | null;
  college_name?: string | null;
  university_name?: string | null;
  campus_id?: number | null;
  campus_name?: string | null;
  level_id?: number | null;
  level_name?: string | null;
  qualification_program_id?: string | null;
  program_name?: string | null;
  intake_id?: number | null;
  intake_name?: string | null;
  pathway_type?: string | null;
  pathway_name?: string | null;
  portal_url?: string | null;
  portal_username?: string | null;
  portal_password_hint?: string | null;
  institutional_app_id?: string | null;
  application_status?: string;
  fee_status?: string;
  fee_amount?: number | null;
  fee_currency?: string;
  internal_target_date?: string | null;
  official_deadline?: string | null;
  submitted_at?: string | null;
  current_stage_key: FlowxStageKey;
  status: FlowxEnrollmentStatus;
  sla_health: FlowxSlaStatus;
  /** Country-workflow stages (labels + visibility) — drives journey process map. */
  stages?: FlowxEnrollmentStageMeta[];
  tracks: FlowxEnrollmentTrack[];
  /** Sub-process links from the country workflow, mapped to journey tasks when possible. */
  links?: FlowxEnrollmentLink[];
  /** Latest counselling booking for Intake Session (1.1). */
  intake_booking?: FlowxIntakeBooking | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface FlowxIntakeBooking {
  id?: number | null;
  lead_id?: number | null;
  candidate_name: string;
  status_definition_id?: number | null;
  status_stage_name?: string | null;
  status_category?: string | null;
  booking_status?: string | null;
  date_label?: string | null;
  time_label?: string | null;
  /** ISO start of counselling slot. */
  scheduled_time?: string | null;
  /** ISO end of counselling slot (start + slot duration). */
  scheduled_end_at?: string | null;
  /** Appointment ended without Finished/Cancelled. */
  is_overdue?: boolean;
  delay_days?: number;
  delay_weeks?: number;
  delay_months?: number;
  /** e.g. "7 days · 1 week · 0 months" */
  delay_label?: string | null;
}

export interface FlowxEnrollmentListItem {
  id: string;
  lead_id: number;
  lead_name: string;
  country_iso2: string;
  country_name: string;
  institution_id?: number | null;
  institution_name?: string | null;
  college_id?: number | null;
  college_name?: string | null;
  university_name?: string | null;
  campus_name?: string | null;
  program_name?: string | null;
  intake_name?: string | null;
  pathway_name?: string | null;
  application_status?: string;
  current_stage_key: FlowxStageKey;
  status: FlowxEnrollmentStatus;
  sla_health: FlowxSlaStatus;
  /** Intake Session (1.1) past appointment without Finished update. */
  intake_overdue?: boolean;
  intake_delay_label?: string | null;
  updated_at?: string | null;
}

export interface FlowxDestinationCollege {
  id: number;
  name: string;
  institution_id: number;
}

export interface FlowxDestinationInstitution {
  id: number;
  name: string;
  state_id?: number | null;
  city_id?: number | null;
  colleges: FlowxDestinationCollege[];
}

export interface FlowxCountryDestinations {
  country_iso2: string;
  institutions: FlowxDestinationInstitution[];
}

export interface FlowxGeographyItem {
  id: number;
  name: string;
  state_id?: number | null;
}

export interface FlowxCountryGeography {
  country_iso2: string;
  country_id: number;
  states: FlowxGeographyItem[];
  cities: FlowxGeographyItem[];
}

export interface FlowxLookupItem {
  id: number | string;
  name: string;
  code?: string | null;
  extra?: Record<string, unknown> | null;
}

export interface FlowxApplicationLookups {
  campuses: FlowxLookupItem[];
  colleges: FlowxLookupItem[];
  levels: FlowxLookupItem[];
  programs: FlowxLookupItem[];
  intakes: FlowxLookupItem[];
}

export interface FlowxPathway {
  id: string;
  pathway_type: string;
  pathway_name: string;
  is_custom: boolean;
}

export interface FlowxBoardCard {
  enrollment_id: string;
  lead_id: number;
  lead_name: string;
  country_iso2: string;
  country_name: string;
  institution_name?: string | null;
  college_name?: string | null;
  current_stage_key: FlowxStageKey;
  status: FlowxEnrollmentStatus;
  sla_health: FlowxSlaStatus;
}

export interface FlowxBoardColumn {
  stage_key: FlowxStageKey;
  label: string;
  cards: FlowxBoardCard[];
}

export interface FlowxBoardResponse {
  country_iso2?: string | null;
  columns: FlowxBoardColumn[];
}

export interface FlowxOpsBottleneck {
  country_iso2: string;
  country_name: string;
  stage_key: FlowxStageKey;
  stage_label: string;
  delayed_count: number;
  at_risk_count?: number;
}

export interface FlowxOpsCountryCard {
  country_iso2: string;
  country_name: string;
  active_applications: number;
  delayed_count: number;
  at_risk_count: number;
  on_track_count: number;
  students_processed: number;
  students_in_process: number;
  institution_count: number;
  college_count: number;
  top_stage_key?: FlowxStageKey | null;
  top_stage_label?: string | null;
}

export interface FlowxOpsOverview {
  total_active: number;
  total_delayed: number;
  total_at_risk: number;
  total_on_track: number;
  visas_in_process: number;
  landed_candidates: number;
  countries: FlowxOpsCountryCard[];
  bottlenecks: FlowxOpsBottleneck[];
}

export const FLOWX_KANBAN_COLUMNS: { key: FlowxKanbanStatus; label: string }[] = [
  { key: 'todo', label: 'To Do' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'in_review', label: 'In Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'blocked', label: 'Blocked' },
];

export function slaChipClass(health: FlowxSlaStatus) {
  if (health === 'breached') return 'bg-red-100 text-red-800 border-red-200';
  if (health === 'amber') return 'bg-amber-100 text-amber-800 border-amber-200';
  return 'bg-emerald-100 text-emerald-800 border-emerald-200';
}

export function slaLabel(health: FlowxSlaStatus) {
  if (health === 'breached') return 'SLA Breach';
  if (health === 'amber') return 'At Risk';
  return 'On Track';
}
