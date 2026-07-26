export type PlatformBadge = 'FB' | 'IG' | null;

export type ProspectListItem = {
  id: number;
  full_name: string;
  name?: string;
  email?: string;
  phone?: string | null;
  phone_number?: string | null;
  stage: string;
  status?: string;
  source?: string | null;
  platform_badge: PlatformBadge;
  received_at?: string | null;
  updated_at?: string | null;
  latest_interaction_time?: string | null;
  total_messages_received?: number;
  unread_count?: number;
  has_ai_messages?: boolean;
  has_messages?: boolean;
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  target_degree?: string | null;
  target_major?: string | null;
  current_location?: string | null;
  study_interest_complete?: boolean | null;
  intake_step?: string | null;
  intake_step_label?: string | null;
  intake_complete?: boolean | null;
  wants_consultation_call?: boolean | null;
  consultation_scheduled_at?: string | null;
  consultation_session_date?: string | null;
  consultation_session_time?: string | null;
  assigned_counsellor_name?: string | null;
  appointment_status?: string | null;
  english_test_scores?: string | null;
  gre_score?: string | null;
  gmat_score?: string | null;
  test_scores?: string | null;
};

export type ProspectsListResponse = {
  items: ProspectListItem[];
  next_cursor: string | null;
  filtered_total: number;
  limit?: number;
  offset?: number;
  has_more?: boolean;
};

export type ProspectsSummary = {
  total_leads: number;
  leads_today: number;
  pending_handoff: number;
  meta_leads: number;
};

export type ProspectDetail = {
  id: number;
  full_name?: string;
  name?: string;
  email?: string;
  phone?: string;
  phone_number?: string;
  stage?: string;
  status?: string;
  source?: string | null;
  platform_badge?: PlatformBadge;
  academic_summary?: string | null;
  intake_context?: string | null;
  current_location?: string | null;
  preferred_country?: string | null;
  meta_campaign_name?: string | null;
  meta_form_id?: string | null;
  meta_ad_id?: string | null;
  additional_data?: Record<string, string> | null;
  messages?: ProspectMessage[];
  chat_history?: ProspectMessage[];
  updated_at?: string;
  created_at?: string;
  is_human_locked?: boolean;
  status_definition_id?: number | null;
  status_stage_name?: string | null;
  status_category?: string | null;
  status_description?: string | null;
};

export type ProspectMessage = {
  id?: number | string;
  sender: string;
  senderName?: string;
  text: string;
  created_at?: string;
  media_url?: string | null;
  file_name?: string | null;
};

export type ProspectsFilters = {
  q: string;
  source: string;
  dateFrom: string;
  dateTo: string;
  category: string;
  /** all | started | not_started — whether WhatsApp chat has begun. */
  contactStatus: 'all' | 'started' | 'not_started';
  /** Current page (1-based) for offset pagination. */
  page: number;
  /** Rows per page (25 | 50 | 100). */
  pageSize: 25 | 50 | 100;
};

export const DEFAULT_PROSPECTS_FILTERS: ProspectsFilters = {
  q: '',
  source: 'ALL',
  dateFrom: '',
  dateTo: '',
  category: '',
  contactStatus: 'all',
  page: 1,
  pageSize: 50,
};
