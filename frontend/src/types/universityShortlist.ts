export type FitBand = 'safe' | 'target' | 'reach';
export type ShortlistRunStatus = 'completed' | 'failed' | 'insufficient_data';

export interface MatchingWeightProfile {
  id: number;
  code: string;
  name: string;
  description?: string | null;
  weight_academic: number | string;
  weight_profile: number | string;
  weight_aspirations: number | string;
  weight_safety: number | string;
  is_default: boolean;
  is_active: boolean;
}

export interface MatchedAcademicPathway {
  offering_id?: number | null;
  program_code?: string | null;
  program_name?: string | null;
  major_code?: string | null;
  major_name?: string | null;
  course_id?: number | null;
  course_code?: string | null;
  course_label?: string | null;
  course_level?: string | null;
  match_score?: number | null;
  match_reason?: string | null;
}

export interface LabeledCatalogRef {
  code?: string | null;
  name?: string | null;
}

export interface DerivedAcademicSummary {
  student_preferences?: {
    programs?: string[];
    programs_other?: string | null;
    discipline_university_college?: string[];
    discipline_pre_college?: string[];
  };
  matched_programs?: LabeledCatalogRef[];
  matched_majors?: LabeledCatalogRef[];
  matched_courses?: LabeledCatalogRef[];
  source?: string | null;
}

export interface UniversityShortlistItem {
  id: number;
  institution_id: number;
  institution_name?: string | null;
  institution_country_iso2?: string | null;
  ranking_tier_global?: string | null;
  institution_type?: string | null;
  offering_id?: number | null;
  program_code?: string | null;
  program_name?: string | null;
  major_code?: string | null;
  major_name?: string | null;
  course_code?: string | null;
  course_label?: string | null;
  course_level?: string | null;
  matched_pathways?: MatchedAcademicPathway[];
  rank: number;
  consolidated_score: number | string;
  s_academic: number | string;
  s_profile: number | string;
  s_aspirations: number | string;
  s_safety: number | string;
  fit_band: FitBand;
  explanation?: {
    algorithm_version?: string;
    classification_mode?: string;
    disclaimer?: string;
    academic?: { reasons?: string[]; gpa_band_code?: string | null };
    profile?: {
      reasons?: string[];
      work_years?: number;
      research_count?: number;
      digital_presence_count?: number;
    };
    aspirations?: { reasons?: string[] };
    safety?: { reasons?: string[]; mode?: string };
    primary_pathway?: MatchedAcademicPathway | null;
    matched_pathways?: MatchedAcademicPathway[];
    data_completeness?: number;
  } | null;
}

export interface UniversityShortlistRun {
  id: number;
  lead_id?: number | null;
  booking_id?: number | null;
  students_master_id?: number | null;
  algorithm_version: string;
  status: ShortlistRunStatus;
  classification_mode: string;
  item_count: number;
  weight_profile?: MatchingWeightProfile | null;
  notes?: string | null;
  disclaimer: string;
  created_at: string;
  derived_academic?: DerivedAcademicSummary | null;
  items: UniversityShortlistItem[];
}

export interface UniversityShortlistResponse {
  booking_id: number;
  run: UniversityShortlistRun | null;
}

export const FIT_BAND_META: Record<
  FitBand,
  { label: string; badgeClass: string; barClass: string }
> = {
  safe: {
    label: 'Safe',
    badgeClass: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    barClass: 'bg-emerald-500',
  },
  target: {
    label: 'Target',
    badgeClass: 'border-sky-200 bg-sky-50 text-sky-900',
    barClass: 'bg-sky-500',
  },
  reach: {
    label: 'Reach',
    badgeClass: 'border-amber-200 bg-amber-50 text-amber-950',
    barClass: 'bg-amber-500',
  },
};

export function scoreNumber(value: number | string | null | undefined): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatScore(value: number | string | null | undefined): string {
  return scoreNumber(value).toFixed(1);
}

export function formatCatalogRef(ref: LabeledCatalogRef): string {
  if (ref.name && ref.code) return `${ref.name} (${ref.code})`;
  return ref.name || ref.code || '';
}

export function formatPathwayLine(pathway: MatchedAcademicPathway): string {
  const parts = [
    pathway.program_name || pathway.program_code,
    pathway.major_name || pathway.major_code,
    pathway.course_label || pathway.course_code,
  ].filter(Boolean);
  return parts.join(' → ');
}
