export type IntelCategory =
  | 'Admissions'
  | 'Visa'
  | 'Financial'
  | 'Work_Rights'
  | 'Legal';

export type IntelLifecycleStage =
  | '1_Discovery'
  | '2_Prep'
  | '3_Offer'
  | '4_Finance'
  | '5_Visa'
  | '6_Onboarding';

export type IntelSortBy =
  | 'updated'
  | 'alpha'
  | 'term'
  | 'country'
  | 'category'
  | 'lifecycle'
  | 'definition'
  | 'source';

export type IntelSortDir = 'asc' | 'desc';

export interface IntelGlossaryTerm {
  id: string;
  term_name: string;
  slug: string;
  category: string;
  country_code: string;
  lifecycle_stage: string;
  short_definition: string;
  full_explanation?: string | null;
  key_metrics?: Record<string, unknown> | null;
  tags?: string[];
  official_source_url?: string | null;
  is_student_facing: boolean;
  last_verified_at?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface IntelGlossaryListResponse {
  items: IntelGlossaryTerm[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface IntelTooltipPayload {
  slug: string;
  term_name: string;
  short_definition: string;
  last_verified_at?: string | null;
  official_source_url?: string | null;
  country_code: string;
  category: string;
}

export interface IntelTrivia {
  id: string;
  question: string;
  options: string[];
  country_code?: string | null;
  active_date: string;
  already_answered: boolean;
  selected_option_index?: number | null;
  is_correct?: boolean | null;
  explanation?: string | null;
  streak: number;
  correct_count: number;
}

export interface IntelTriviaAnswerResponse {
  is_correct: boolean;
  correct_option_index: number;
  explanation: string;
  streak: number;
  correct_count: number;
}

export interface IntelPreferences {
  enable_daily_trivia: boolean;
  enable_contextual_tips: boolean;
  preferred_countries: string[];
  trivia_streak: number;
  trivia_correct_count: number;
}

export interface IntelAcademyModule {
  id: string;
  title: string;
  slug: string;
  summary: string;
  country_code?: string | null;
  duration_minutes: number;
  quiz: {
    question: string;
    options: string[];
    correct_option_index: number;
    explanation: string;
  };
  is_active: boolean;
  sort_order: number;
}

export interface ProofOfFundsResponse {
  country_code: string;
  required_balance: number;
  currency: string;
  holding_days: number;
  breakdown: Record<string, number>;
  notes: string[];
}

export interface CountryComparisonItem {
  country_code: string;
  tuition_band: string;
  psw_rights: string;
  dependent_rules: string;
  work_limits: string;
  proof_of_funds_summary: string;
  language_requirements?: string;
}

export interface FutureInsightsEmployer {
  name: string;
  website_url: string;
  logo_url?: string | null;
  city_or_region?: string | null;
  sectors: string[];
}

export interface FutureInsightsJob {
  title: string;
  employer_name: string;
  location: string;
  apply_url: string;
  program_disciplines: string[];
  as_of: string;
}

export interface FutureInsightsRoi {
  tuition_baseline: string;
  health_fees_note: string;
  median_starting_salary: string;
  break_even_horizon: string;
  ten_year_yield_note: string;
  currency: string;
}

export interface FutureInsightsImmigration {
  psw_rights: string;
  work_limits: string;
  dependent_rules: string;
  pathway_notes: string[];
  language_requirements?: string;
  proof_of_funds_summary?: string;
}

export interface FutureInsightsCityLiving {
  shared_housing_monthly: string;
  private_rent_monthly: string;
  transit_index_note: string;
  grocery_index_note: string;
  climate_snapshot: string;
  safety_snapshot: string;
}

export interface FutureInsightsHabitatMetric {
  key: string;
  label: string;
  value: string;
  score?: number | null;
}

export interface FutureInsightsHabitatCategory {
  key: string;
  title: string;
  summary: string;
  metrics: FutureInsightsHabitatMetric[];
}

export interface FutureInsightsHabitat {
  location_label: string;
  categories: FutureInsightsHabitatCategory[];
}

export interface FutureInsightsInstitutionContext {
  institution_id: number;
  institution_name: string;
  city_name?: string | null;
  state_name?: string | null;
  country_iso2?: string | null;
  metro_key?: string | null;
  location_label: string;
  metro_matched: boolean;
  employers: FutureInsightsEmployer[];
  jobs: FutureInsightsJob[];
  city_living?: FutureInsightsCityLiving | null;
  habitat?: FutureInsightsHabitat | null;
}

export interface FutureInsightsDestinationPack {
  country_code: string;
  country_iso2: string;
  as_of: string;
  disclaimer: string;
  roi: FutureInsightsRoi;
  employers: FutureInsightsEmployer[];
  jobs: FutureInsightsJob[];
  immigration: FutureInsightsImmigration;
  city_living: FutureInsightsCityLiving;
  habitat?: FutureInsightsHabitat | null;
  institutions: FutureInsightsInstitutionContext[];
}

export interface FutureInsightsResponse {
  destinations: FutureInsightsDestinationPack[];
  unsupported_countries: string[];
}

export interface IntelScraperConfig {
  id: string;
  source_name: string;
  target_url: string;
  country_code: string;
  scrape_interval_hours: number;
  last_run_at?: string | null;
  status: string;
  last_error?: string | null;
  last_content_hash?: string | null;
  last_fetched_at?: string | null;
  last_http_status?: number | null;
  linked_glossary_id?: string | null;
  linked_glossary_term?: string | null;
}

export interface IntelScrapeRunResult {
  ran: number;
  reviews_created: number;
  unchanged?: number;
  errors?: number;
  skipped?: string | number | null;
}

export interface IntelScrapeReview {
  id: string;
  scraper_config_id: string;
  source_name?: string | null;
  glossary_id?: string | null;
  detected_at: string;
  old_text?: string | null;
  new_text: string;
  diff_summary?: string | null;
  status: string;
}

export type IntelAiSourceType = 'glossary' | 'university' | 'program' | 'level' | 'web' | string;

export interface IntelAiSource {
  type: IntelAiSourceType;
  title: string;
  url?: string | null;
  id?: string | null;
  slug?: string | null;
  summary?: string | null;
  country_code?: string | null;
  category?: string | null;
}

export interface IntelAiChatResponse {
  id: string;
  thread_id: string;
  response_text: string;
  sources: IntelAiSource[];
  retrieved_sources: IntelAiSource[];
  created_at?: string | null;
}

export interface IntelAiChatHistoryItem {
  id: string;
  thread_id?: string | null;
  prompt: string;
  response_text: string;
  sources: IntelAiSource[];
  retrieved_sources: IntelAiSource[];
  created_at?: string | null;
}

export interface IntelAiChatHistoryResponse {
  thread_id?: string | null;
  items: IntelAiChatHistoryItem[];
}

export interface IntelAiChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface IntelAiChatRequest {
  prompt: string;
  thread_id?: string | null;
  history?: IntelAiChatHistoryMessage[];
}

export interface IntelAiThreadSummary {
  thread_id: string;
  title: string;
  started_at?: string | null;
  updated_at?: string | null;
  turn_count: number;
}

export interface IntelAiThreadGroup {
  key: 'today' | 'yesterday' | 'last_7_days' | 'older';
  label: string;
  threads: IntelAiThreadSummary[];
}

export interface IntelAiThreadsResponse {
  groups: IntelAiThreadGroup[];
}

export interface IntelAiThreadMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: IntelAiSource[];
  retrieved_sources?: IntelAiSource[];
  created_at?: string | null;
}

export interface IntelAiThreadDetailResponse {
  thread_id: string;
  title?: string | null;
  messages: IntelAiThreadMessage[];
  updated_at?: string | null;
}

export const INTEL_COUNTRIES = [
  'UK',
  'CA',
  'AU',
  'DE',
  'US',
  'JP',
  'FR',
  'AE',
  'NZ',
  'SG',
  'SE',
  'CH',
  'GLOBAL',
] as const;

/** Display labels for Intel country codes (includes GLOBAL and UK≠GB). */
export const INTEL_COUNTRY_LABELS: Record<(typeof INTEL_COUNTRIES)[number] | string, string> = {
  UK: 'United Kingdom',
  CA: 'Canada',
  AU: 'Australia',
  DE: 'Germany',
  US: 'United States',
  JP: 'Japan',
  FR: 'France',
  AE: 'United Arab Emirates',
  NZ: 'New Zealand',
  SG: 'Singapore',
  SE: 'Sweden',
  CH: 'Switzerland',
  GLOBAL: 'Global',
};

export function intelCountryLabel(code: string | null | undefined): string {
  if (!code) return '—';
  const upper = code.trim().toUpperCase();
  return INTEL_COUNTRY_LABELS[upper] || upper;
}
export const INTEL_CATEGORIES = ['Admissions', 'Visa', 'Financial', 'Work_Rights', 'Legal'] as const;
export const INTEL_LIFECYCLE_STAGES = [
  { value: '1_Discovery', label: '1 · Discovery' },
  { value: '2_Prep', label: '2 · Prep' },
  { value: '3_Offer', label: '3 · Offer' },
  { value: '4_Finance', label: '4 · Finance' },
  { value: '5_Visa', label: '5 · Visa' },
  { value: '6_Onboarding', label: '6 · Onboarding' },
] as const;
