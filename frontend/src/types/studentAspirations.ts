export type WhyStudyAbroadOption =
  | 'INTERNATIONAL_REPUTATION'
  | 'BETTER_JOB_PROSPECTS'
  | 'BETTER_COURSE_QUALITY'
  | 'BETTER_RESEARCH'
  | 'LIFE_CHANGE'
  | 'OTHER';

export type InstitutionTypeOption =
  | 'PUBLIC_STATE_UNIVERSITY'
  | 'PRIVATE_UNIVERSITY'
  | 'COMMUNITY_COLLEGE_TECHNICAL'
  | 'ANY';
export type GlobalRankingOption =
  | 'TOP_100_GLOBAL_ELITE'
  | 'TOP_300_RESEARCH_INTENSIVE'
  | 'TOP_500_BROAD_ACADEMIC'
  | 'ANY_INCLUSIVE';
export type BudgetOption =
  | 'BUDGET_FRIENDLY'
  | 'MID_RANGE'
  | 'PREMIUM'
  | 'HIGH_INVESTMENT'
  | 'NEEDS_FULL_FUNDING';
export type IntakeSeasonOption =
  | 'JAN_FEB_SPRING'
  | 'APR_MAY_SUMMER'
  | 'JUL_AUG_SEP_OCT_AUTUMN'
  | 'FEB_MAR_SEM1_AUS_NZ'
  | 'JUL_AUG_SEM2_AUS_NZ'
  | 'APRIL_JAPAN'
  | 'OTHER';

/** Mirrors Academic Framework global templates (Semester / Trimester / Quarter). */
export type IntakeCalendarSystemOption = 'SEMESTER' | 'TRIMESTER' | 'QUARTER';

export type IntakeTermOption = 'FALL' | 'SPRING' | 'WINTER' | 'Q1' | 'Q2' | 'Q3' | 'Q4';
export type EnglishTestOption =
  | 'IELTS'
  | 'TOEFL'
  | 'PTE'
  | 'DUOLINGO'
  | 'CAMBRIDGE_C1_C2'
  | 'NOT_TAKEN_YET_PLANNING'
  | 'WAIVER_NOT_REQUIRED';
export type AptitudeTestOption =
  | 'GRE'
  | 'GMAT'
  | 'SAT'
  | 'ACT'
  | 'LSAT_MCAT'
  | 'NOT_TAKEN_YET_PLANNING'
  | 'NOT_REQUIRED_TEST_OPTIONAL';
export type FundingSourceOption = 'FAMILY_SPONSORED' | 'EDUCATIONAL_LOAN' | 'GRANT_SCHOLARSHIP';
export type GrantScholarshipTypeOption = 'FULL' | 'PARTIAL' | 'NOT_REQUIRED';
export type UniversityManagedAccommodationOption = 'ON_CAMPUS' | 'DORM';
export type OffCampusIndependentAccommodationOption = 'PRIVATE_ROOM' | 'PRIVATE_APARTMENT';
export type SharedLivingAccommodationOption = 'SHARED_NATIVE' | 'SHARED_INTERNATIONAL';
export type ImmersiveFamilyAccommodationOption = 'HOMESTAYS' | 'HOST_FAMILY';
export type FutureLocationOption = 'HOME_COUNTRY' | 'STUDY_COUNTRY' | 'ANOTHER_COUNTRY';

export type PostStudyGoalOption =
  | 'RETURN_HOME'
  | 'PSW_WORK_EXPERIENCE'
  | 'PATHWAY_PR'
  | 'UNDECIDED'
  | 'OTHER';

export type CountryPriorityOption = 'TOP_CHOICE' | 'ALTERNATIVE';

export interface TargetCountrySelection {
  iso2: string;
  priority: CountryPriorityOption;
}

export interface FundingSourceSelection {
  source: FundingSourceOption;
  coverage: GrantScholarshipTypeOption | '';
}

export interface StudentAspirationsFormState {
  why_study_abroad: WhyStudyAbroadOption[];
  why_study_abroad_other: string;
  post_study_goals: PostStudyGoalOption[];
  post_study_goal_other: string;
  study_countries_iso2: string[];
  study_countries_other: string;
  target_countries: TargetCountrySelection[];
  institution_type: InstitutionTypeOption[];
  global_ranking: GlobalRankingOption[];
  budget: BudgetOption[];
  /** @deprecated Replaced by intake_calendar_system + intake_terms. */
  intake_seasons: IntakeSeasonOption[];
  /** @deprecated Replaced by intake_calendar_system + intake_terms. */
  intake_season_other: string;
  /** Academic Framework calendar system (Semester / Trimester / Quarterly). */
  intake_calendar_system: IntakeCalendarSystemOption | '';
  /** Terms under the selected calendar system (e.g. Fall, Spring). */
  intake_terms: IntakeTermOption[];
  intake_years: number[];
  /** Selected level code from Levels table (radio). */
  study_level_code: string;
  /** @deprecated Kept for API compatibility; cleared when saving level selection. */
  discipline_university_college: string[];
  /** @deprecated Kept for API compatibility; cleared when saving level selection. */
  discipline_pre_college: string[];
  programs: string[];
  programs_other: string;
  academic_standing_code: string;
  academic_standing_other: string;
  /** Current education cascade for Q4 (Levels → Study Years → Program → Major). */
  current_level_id: string;
  current_full_time_study_years: string;
  current_program_code: string;
  current_major: string;
  english_tests: EnglishTestOption[];
  aptitude_tests: AptitudeTestOption[];
  funding_sources: FundingSourceSelection[];
  accommodation_university_managed: UniversityManagedAccommodationOption[];
  accommodation_off_campus_independent: OffCampusIndependentAccommodationOption[];
  accommodation_shared_living: SharedLivingAccommodationOption[];
  accommodation_immersive_family: ImmersiveFamilyAccommodationOption[];
  future_job: FutureLocationOption[];
  future_study: FutureLocationOption[];
}

export interface StudentAspirationsResponse {
  students_master_id: number | null;
  booking_id?: number | null;
  aspirations: StudentAspirationsFormState & {
    funding_source?: FundingSourceOption | null;
    grant_scholarship_type?: GrantScholarshipTypeOption | null;
  };
  saved_at?: string | null;
}

export const STUDY_COUNTRY_OTHER_VALUE = 'OTHER';

export const WHY_STUDY_ABROAD_OPTIONS: {
  value: WhyStudyAbroadOption;
  title?: string;
  description?: string;
  label?: string;
}[] = [
  {
    value: 'INTERNATIONAL_REPUTATION',
    title: 'Prestigious/Global Ranking',
    description: 'I want to study at an institution with an international reputation.',
  },
  {
    value: 'BETTER_JOB_PROSPECTS',
    title: 'Enhanced Career Prospects',
    description: 'I think a foreign degree will provide better job prospects.',
  },
  {
    value: 'BETTER_COURSE_QUALITY',
    title: 'Higher Academic Quality',
    description: 'I think my preferred course would be of better quality abroad.',
  },
  {
    value: 'BETTER_RESEARCH',
    title: 'Advanced Research Opportunities',
    description: 'I want to get a better research experience.',
  },
  {
    value: 'LIFE_CHANGE',
    title: 'Personal Growth & Independence',
    description: 'I need a change in my life.',
  },
  { value: 'OTHER', title: 'Others' },
];

export const INSTITUTION_TYPE_OPTIONS: { value: InstitutionTypeOption; label: string }[] = [
  { value: 'PUBLIC_STATE_UNIVERSITY', label: 'Public / State University' },
  { value: 'PRIVATE_UNIVERSITY', label: 'Private University' },
  { value: 'COMMUNITY_COLLEGE_TECHNICAL', label: 'Community College / Technical Institute' },
  { value: 'ANY', label: 'Any' },
];

const LEGACY_INSTITUTION_TYPE_MAP: Record<string, InstitutionTypeOption> = {
  PUBLIC: 'PUBLIC_STATE_UNIVERSITY',
  PRIVATE: 'PRIVATE_UNIVERSITY',
};

export function normalizeInstitutionTypes(values: string[] | undefined): InstitutionTypeOption[] {
  if (!values?.length) return [];
  return values
    .map(value => LEGACY_INSTITUTION_TYPE_MAP[value] || (value as InstitutionTypeOption))
    .filter((value): value is InstitutionTypeOption =>
      INSTITUTION_TYPE_OPTIONS.some(option => option.value === value)
    );
}

export const GLOBAL_RANKING_OPTIONS: { value: GlobalRankingOption; label: string }[] = [
  { value: 'TOP_100_GLOBAL_ELITE', label: 'Top 100 Global Elite' },
  { value: 'TOP_300_RESEARCH_INTENSIVE', label: 'Top 300 Research-Intensive' },
  { value: 'TOP_500_BROAD_ACADEMIC', label: 'Top 500 Academic Excellence' },
  { value: 'ANY_INCLUSIVE', label: 'Any (Inclusive of all)' },
];

const LEGACY_GLOBAL_RANKING_MAP: Record<string, GlobalRankingOption> = {
  TOP_100: 'TOP_100_GLOBAL_ELITE',
  TOP_300: 'TOP_300_RESEARCH_INTENSIVE',
  ANY: 'ANY_INCLUSIVE',
};

export function normalizeGlobalRanking(values: string[] | undefined): GlobalRankingOption[] {
  if (!values?.length) return [];
  return values
    .map(value => LEGACY_GLOBAL_RANKING_MAP[value] || (value as GlobalRankingOption))
    .filter((value): value is GlobalRankingOption =>
      GLOBAL_RANKING_OPTIONS.some(option => option.value === value)
    );
}

export const BUDGET_OPTIONS: { value: BudgetOption; label: string }[] = [
  { value: 'BUDGET_FRIENDLY', label: 'Budget Friendly — Up to 20 Lakhs' },
  { value: 'MID_RANGE', label: 'Mid-Range — 20 - 40 Lakhs' },
  { value: 'PREMIUM', label: 'Premium — 40 - 60 Lakhs' },
  { value: 'HIGH_INVESTMENT', label: 'High Investment — 60 Lakhs+' },
  { value: 'NEEDS_FULL_FUNDING', label: 'Needs Full Funding — 0 Lakhs (Scholarship-focused)' },
];

const LEGACY_BUDGET_MAP: Record<string, BudgetOption> = {
  UPTO_30L: 'BUDGET_FRIENDLY',
  BETWEEN_30_50L: 'MID_RANGE',
  ABOVE_50L: 'HIGH_INVESTMENT',
  NO_FUNDING: 'NEEDS_FULL_FUNDING',
};

export function normalizeBudgetOptions(values: string[] | undefined): BudgetOption[] {
  if (!values?.length) return [];
  return values
    .map(value => LEGACY_BUDGET_MAP[value] || (value as BudgetOption))
    .filter((value): value is BudgetOption =>
      BUDGET_OPTIONS.some(option => option.value === value)
    );
}

export const INTAKE_PLANNED_OPTIONS: { value: IntakeSeasonOption; label: string }[] = [
  { value: 'JAN_FEB_SPRING', label: 'Jan/Feb Intake (Spring)' },
  { value: 'APR_MAY_SUMMER', label: 'Apr/May Intake (Summer)' },
  { value: 'JUL_AUG_SEP_OCT_AUTUMN', label: 'Jul/Aug/Sep/Oct Intake (Autumn)' },
  { value: 'FEB_MAR_SEM1_AUS_NZ', label: 'Feb/Mar (Semester 1 - AUS/NZ)' },
  { value: 'JUL_AUG_SEM2_AUS_NZ', label: 'Jul/Aug (Semester 2 - AUS/NZ)' },
  { value: 'APRIL_JAPAN', label: 'April Intake (Japan)' },
  { value: 'OTHER', label: 'Others' },
];

/** @deprecated use INTAKE_PLANNED_OPTIONS */
export const INTAKE_SEASON_OPTIONS = INTAKE_PLANNED_OPTIONS;

/**
 * Academic Framework → Global academic templates used for Q8.
 * Rolling Admissions is intentionally omitted (Semester / Trimester / Quarterly only).
 */
export const INTAKE_CALENDAR_SYSTEMS: {
  value: IntakeCalendarSystemOption;
  label: string;
  frameworkName: string;
  terms: { value: IntakeTermOption; label: string }[];
}[] = [
  {
    value: 'SEMESTER',
    label: 'Semester',
    frameworkName: 'Semester System',
    terms: [
      { value: 'FALL', label: 'Fall' },
      { value: 'SPRING', label: 'Spring' },
    ],
  },
  {
    value: 'TRIMESTER',
    label: 'Trimester',
    frameworkName: 'Trimester System',
    terms: [
      { value: 'FALL', label: 'Fall' },
      { value: 'WINTER', label: 'Winter' },
      { value: 'SPRING', label: 'Spring' },
    ],
  },
  {
    value: 'QUARTER',
    label: 'Quarterly',
    frameworkName: 'Quarter System',
    terms: [
      { value: 'Q1', label: 'Q1' },
      { value: 'Q2', label: 'Q2' },
      { value: 'Q3', label: 'Q3' },
      { value: 'Q4', label: 'Q4' },
    ],
  },
];

export function termsForCalendarSystem(
  system: IntakeCalendarSystemOption | '' | null | undefined
): { value: IntakeTermOption; label: string }[] {
  if (!system) return [];
  return INTAKE_CALENDAR_SYSTEMS.find(item => item.value === system)?.terms ?? [];
}

export function normalizeIntakeCalendarSystem(
  value: string | null | undefined
): IntakeCalendarSystemOption | '' {
  const token = (value || '').trim().toUpperCase();
  if (token === 'QUARTERLY') return 'QUARTER';
  if (INTAKE_CALENDAR_SYSTEMS.some(item => item.value === token)) {
    return token as IntakeCalendarSystemOption;
  }
  return '';
}

export function normalizeIntakeTerms(
  values: string[] | undefined,
  system?: IntakeCalendarSystemOption | '' | null
): IntakeTermOption[] {
  if (!values?.length) return [];
  const allowed = new Set(
    (system ? termsForCalendarSystem(system) : INTAKE_CALENDAR_SYSTEMS.flatMap(item => item.terms)).map(
      term => term.value
    )
  );
  const normalized: IntakeTermOption[] = [];
  values.forEach(raw => {
    const token = String(raw || '')
      .trim()
      .toUpperCase()
      .replace(/\s+/g, '_') as IntakeTermOption;
    if (allowed.has(token) && !normalized.includes(token)) {
      normalized.push(token);
    }
  });
  return normalized;
}

const LEGACY_INTAKE_MAP: Record<string, IntakeSeasonOption> = {
  FALL: 'JUL_AUG_SEP_OCT_AUTUMN',
  SUMMER: 'APR_MAY_SUMMER',
  WINTER: 'JAN_FEB_SPRING',
};

export function normalizeIntakeSeasons(values: string[] | undefined): IntakeSeasonOption[] {
  if (!values?.length) return [];
  return values
    .map(value => LEGACY_INTAKE_MAP[value] || (value as IntakeSeasonOption))
    .filter((value): value is IntakeSeasonOption =>
      INTAKE_PLANNED_OPTIONS.some(option => option.value === value)
    );
}

export const ENGLISH_TEST_OPTIONS: { value: EnglishTestOption; label: string }[] = [
  { value: 'IELTS', label: 'IELTS' },
  { value: 'TOEFL', label: 'TOEFL' },
  { value: 'PTE', label: 'PTE' },
  { value: 'DUOLINGO', label: 'Duolingo' },
  { value: 'NOT_TAKEN_YET_PLANNING', label: 'Not Taken Yet (Planning)' },
  { value: 'WAIVER_NOT_REQUIRED', label: 'I have a Waiver / Not Required' },
];

export const APTITUDE_TEST_OPTIONS: { value: AptitudeTestOption; label: string }[] = [
  { value: 'GRE', label: 'GRE' },
  { value: 'GMAT', label: 'GMAT' },
  { value: 'SAT', label: 'SAT' },
  { value: 'ACT', label: 'ACT' },
  { value: 'LSAT_MCAT', label: 'LSAT / MCAT' },
  { value: 'NOT_TAKEN_YET_PLANNING', label: 'Not Taken Yet (Planning)' },
  { value: 'NOT_REQUIRED_TEST_OPTIONAL', label: 'Not Required / Test-Optional' },
];

export const FUNDING_SOURCE_OPTIONS: { value: FundingSourceOption; label: string }[] = [
  { value: 'FAMILY_SPONSORED', label: 'Family Sponsored' },
  { value: 'EDUCATIONAL_LOAN', label: 'Educational Loan' },
  { value: 'GRANT_SCHOLARSHIP', label: 'Grant/Scholarship' },
];

export const FUNDING_COVERAGE_OPTIONS: { value: GrantScholarshipTypeOption; label: string }[] = [
  { value: 'FULL', label: 'Full' },
  { value: 'PARTIAL', label: 'Partial' },
  { value: 'NOT_REQUIRED', label: 'Not Required' },
];

export const UNIVERSITY_MANAGED_ACCOMMODATION_OPTIONS: {
  value: UniversityManagedAccommodationOption;
  label: string;
}[] = [
  { value: 'ON_CAMPUS', label: 'On-Campus' },
  { value: 'DORM', label: 'Dorm' },
];

export const OFF_CAMPUS_INDEPENDENT_ACCOMMODATION_OPTIONS: {
  value: OffCampusIndependentAccommodationOption;
  label: string;
}[] = [
  { value: 'PRIVATE_ROOM', label: 'Private Room' },
  { value: 'PRIVATE_APARTMENT', label: 'Private Apartment/House' },
];

export const SHARED_LIVING_ACCOMMODATION_OPTIONS: {
  value: SharedLivingAccommodationOption;
  label: string;
}[] = [
  { value: 'SHARED_NATIVE', label: 'Shared with Native Students' },
  { value: 'SHARED_INTERNATIONAL', label: 'Shared with International Students' },
];

export const IMMERSIVE_FAMILY_ACCOMMODATION_OPTIONS: {
  value: ImmersiveFamilyAccommodationOption;
  label: string;
}[] = [
  { value: 'HOMESTAYS', label: 'Homestays' },
  { value: 'HOST_FAMILY', label: 'Host Family' },
];

/** @deprecated use category-specific accommodation option constants */
export const ON_CAMPUS_OPTIONS = UNIVERSITY_MANAGED_ACCOMMODATION_OPTIONS;
/** @deprecated use category-specific accommodation option constants */
export const OFF_CAMPUS_OPTIONS = [
  ...OFF_CAMPUS_INDEPENDENT_ACCOMMODATION_OPTIONS,
  ...SHARED_LIVING_ACCOMMODATION_OPTIONS,
];
/** @deprecated use category-specific accommodation option constants */
export const HOMESTAY_OPTIONS = IMMERSIVE_FAMILY_ACCOMMODATION_OPTIONS;

export const FUTURE_LOCATION_OPTIONS: { value: FutureLocationOption; label: string }[] = [
  { value: 'HOME_COUNTRY', label: 'In-Home Country' },
  { value: 'STUDY_COUNTRY', label: 'In-Country Studied' },
  { value: 'ANOTHER_COUNTRY', label: 'In-Another Country' },
];

export const PRE_COLLEGE_DEGREE_CODES = new Set([
  'SECONDARY_SCHOOL',
  'SENIOR_SECONDARY',
  'HIGH_SCHOOL_DIPLOMA_GED',
  'SOME_COLLEGE_NO_DEGREE',
  'ASSOCIATE_DEGREE',
]);

export const PROGRAM_OTHER_VALUE = 'OTHER';
export const MAX_TARGET_PROGRAMS = 4;

export const ASPIRATION_MAJOR_OPTIONS = [
  'Computer Science',
  'Business Administration',
  'Engineering',
  'Medicine',
  'Data Science',
  'Finance',
  'Law',
  'Architecture',
  'Psychology',
  'Biotechnology',
] as const;

export function normalizePrograms(values: string[] | undefined): string[] {
  if (!values?.length) return [];
  const normalized = values.map(value => (value === 'Other' ? PROGRAM_OTHER_VALUE : value));
  return normalized.slice(0, MAX_TARGET_PROGRAMS);
}

export function getIntakeYearOptions(referenceDate = new Date()): number[] {
  const currentYear = referenceDate.getFullYear();
  const startYear = referenceDate.getMonth() >= 9 ? currentYear + 1 : currentYear;
  return [startYear, startYear + 1, startYear + 2];
}

export function emptyAspirationsForm(): StudentAspirationsFormState {
  return {
    why_study_abroad: [],
    why_study_abroad_other: '',
    post_study_goals: [],
    post_study_goal_other: '',
    study_countries_iso2: [],
    study_countries_other: '',
    target_countries: [],
    institution_type: [],
    global_ranking: [],
    budget: [],
    intake_seasons: [],
    intake_season_other: '',
    intake_calendar_system: '',
    intake_terms: [],
    intake_years: [],
    study_level_code: '',
    discipline_university_college: [],
    discipline_pre_college: [],
    programs: [],
    programs_other: '',
    academic_standing_code: '',
    academic_standing_other: '',
    current_level_id: '',
    current_full_time_study_years: '',
    current_program_code: '',
    current_major: '',
    english_tests: [],
    aptitude_tests: [],
    funding_sources: [],
    accommodation_university_managed: [],
    accommodation_off_campus_independent: [],
    accommodation_shared_living: [],
    accommodation_immersive_family: [],
    future_job: [],
    future_study: [],
  };
}

function migrateLegacyFunding(raw: Record<string, unknown>): FundingSourceSelection[] {
  if (Array.isArray(raw.funding_sources) && raw.funding_sources.length > 0) {
    return raw.funding_sources as FundingSourceSelection[];
  }
  const source = raw.funding_source as FundingSourceOption | undefined;
  if (!source) return [];
  const coverage =
    (raw.grant_scholarship_type as GrantScholarshipTypeOption | undefined) || 'FULL';
  return [{ source, coverage }];
}

function filterAccommodationOptions<T extends string>(
  values: unknown,
  options: { value: T }[]
): T[] {
  if (!Array.isArray(values)) return [];
  const allowed = new Set(options.map(option => option.value));
  return values.filter((value): value is T => typeof value === 'string' && allowed.has(value as T));
}

function migrateLegacyAccommodation(raw: Record<string, unknown>): Pick<
  StudentAspirationsFormState,
  | 'accommodation_university_managed'
  | 'accommodation_off_campus_independent'
  | 'accommodation_shared_living'
  | 'accommodation_immersive_family'
> {
  if (Array.isArray(raw.accommodation_university_managed)) {
    return {
      accommodation_university_managed: filterAccommodationOptions(
        raw.accommodation_university_managed,
        UNIVERSITY_MANAGED_ACCOMMODATION_OPTIONS
      ),
      accommodation_off_campus_independent: filterAccommodationOptions(
        raw.accommodation_off_campus_independent,
        OFF_CAMPUS_INDEPENDENT_ACCOMMODATION_OPTIONS
      ),
      accommodation_shared_living: filterAccommodationOptions(
        raw.accommodation_shared_living,
        SHARED_LIVING_ACCOMMODATION_OPTIONS
      ),
      accommodation_immersive_family: filterAccommodationOptions(
        raw.accommodation_immersive_family,
        IMMERSIVE_FAMILY_ACCOMMODATION_OPTIONS
      ),
    };
  }

  const onCampus = Array.isArray(raw.accommodation_on_campus)
    ? (raw.accommodation_on_campus as string[])
    : [];
  const offCampus = Array.isArray(raw.accommodation_off_campus)
    ? (raw.accommodation_off_campus as string[])
    : [];
  const homestays = Array.isArray(raw.accommodation_homestays)
    ? (raw.accommodation_homestays as string[])
    : [];

  const accommodation_university_managed: UniversityManagedAccommodationOption[] = [];
  if (onCampus.includes('DORM')) accommodation_university_managed.push('DORM');
  if (onCampus.includes('ON_CAMPUS')) accommodation_university_managed.push('ON_CAMPUS');

  const accommodation_off_campus_independent: OffCampusIndependentAccommodationOption[] = [];
  if (onCampus.includes('PRIVATE_ROOM')) accommodation_off_campus_independent.push('PRIVATE_ROOM');
  if (offCampus.includes('PRIVATE_APARTMENT')) {
    accommodation_off_campus_independent.push('PRIVATE_APARTMENT');
  }

  const accommodation_shared_living = offCampus.filter(
    (value): value is SharedLivingAccommodationOption =>
      value === 'SHARED_NATIVE' || value === 'SHARED_INTERNATIONAL'
  );

  const accommodation_immersive_family: ImmersiveFamilyAccommodationOption[] = [];
  if (homestays.includes('HOST_FAMILY')) accommodation_immersive_family.push('HOST_FAMILY');
  if (homestays.includes('HOMESTAYS')) accommodation_immersive_family.push('HOMESTAYS');

  return {
    accommodation_university_managed,
    accommodation_off_campus_independent,
    accommodation_shared_living,
    accommodation_immersive_family,
  };
}

function migrateTargetCountries(raw: Record<string, unknown>): TargetCountrySelection[] {
  if (Array.isArray(raw.target_countries) && raw.target_countries.length > 0) {
    return (raw.target_countries as TargetCountrySelection[])
      .filter(item => item && typeof item.iso2 === 'string' && item.iso2.trim())
      .map(item => ({
        iso2: item.iso2.trim().toUpperCase(),
        priority: item.priority === 'TOP_CHOICE' ? 'TOP_CHOICE' : 'ALTERNATIVE',
      }))
      .slice(0, 6);
  }
  const isoList = Array.isArray(raw.study_countries_iso2)
    ? (raw.study_countries_iso2 as string[])
    : [];
  return isoList
    .map(iso2 => iso2.trim().toUpperCase())
    .filter(Boolean)
    .map((iso2, index) => ({
      iso2,
      priority: (index === 0 ? 'TOP_CHOICE' : 'ALTERNATIVE') as CountryPriorityOption,
    }))
    .slice(0, 6);
}

const POST_STUDY_GOAL_VALUES = new Set<PostStudyGoalOption>([
  'RETURN_HOME',
  'PSW_WORK_EXPERIENCE',
  'PATHWAY_PR',
  'UNDECIDED',
  'OTHER',
]);

function migratePostStudyGoals(raw: Record<string, unknown>): PostStudyGoalOption[] {
  if (Array.isArray(raw.post_study_goals) && raw.post_study_goals.length > 0) {
    return (raw.post_study_goals as string[])
      .map(item => String(item || '').trim().toUpperCase())
      .filter((item): item is PostStudyGoalOption =>
        POST_STUDY_GOAL_VALUES.has(item as PostStudyGoalOption)
      );
  }
  const legacy = typeof raw.post_study_goal === 'string' ? raw.post_study_goal.trim().toUpperCase() : '';
  if (legacy && POST_STUDY_GOAL_VALUES.has(legacy as PostStudyGoalOption)) {
    return [legacy as PostStudyGoalOption];
  }
  return [];
}

export function aspirationsToForm(
  raw: Partial<StudentAspirationsFormState> & {
    funding_source?: FundingSourceOption | null;
    grant_scholarship_type?: GrantScholarshipTypeOption | null;
  } | null | undefined
): StudentAspirationsFormState {
  const base = emptyAspirationsForm();
  if (!raw) return base;
  const {
    funding_source: _legacySource,
    grant_scholarship_type: _legacyType,
    accommodation_on_campus: _legacyOnCampus,
    accommodation_off_campus: _legacyOffCampus,
    accommodation_homestays: _legacyHomestays,
    post_study_goal: _legacyPostStudyGoal,
    ...rest
  } = raw as Partial<StudentAspirationsFormState> & {
    funding_source?: FundingSourceOption | null;
    grant_scholarship_type?: GrantScholarshipTypeOption | null;
    accommodation_on_campus?: string[];
    accommodation_off_campus?: string[];
    accommodation_homestays?: string[];
    post_study_goal?: PostStudyGoalOption | null;
  };
  const target_countries = migrateTargetCountries(raw as Record<string, unknown>);
  const whyList = Array.isArray(raw.why_study_abroad)
    ? (raw.why_study_abroad as WhyStudyAbroadOption[])
    : [];
  return {
    ...base,
    ...rest,
    why_study_abroad: whyList,
    budget: normalizeBudgetOptions(raw.budget as string[] | undefined).slice(0, 1),
    institution_type: normalizeInstitutionTypes(raw.institution_type as string[] | undefined),
    global_ranking: normalizeGlobalRanking(raw.global_ranking as string[] | undefined),
    intake_seasons: normalizeIntakeSeasons(raw.intake_seasons as string[] | undefined),
    intake_season_other: raw.intake_season_other || '',
    intake_calendar_system: normalizeIntakeCalendarSystem(
      (raw as { intake_calendar_system?: string | null }).intake_calendar_system
    ),
    intake_terms: normalizeIntakeTerms(
      (raw as { intake_terms?: string[] }).intake_terms,
      normalizeIntakeCalendarSystem(
        (raw as { intake_calendar_system?: string | null }).intake_calendar_system
      )
    ),
    why_study_abroad_other: raw.why_study_abroad_other || '',
    study_countries_other: raw.study_countries_other || '',
    programs: normalizePrograms(raw.programs as string[] | undefined),
    programs_other: raw.programs_other || '',
    english_tests: (Array.isArray(raw.english_tests) ? raw.english_tests : []).filter(
      (value): value is EnglishTestOption =>
        ENGLISH_TEST_OPTIONS.some(option => option.value === value)
    ),
    study_level_code:
      typeof raw.study_level_code === 'string' ? raw.study_level_code.trim().toUpperCase() : '',
    post_study_goals: migratePostStudyGoals(raw as Record<string, unknown>),
    post_study_goal_other:
      typeof (raw as { post_study_goal_other?: string | null }).post_study_goal_other === 'string'
        ? ((raw as { post_study_goal_other?: string | null }).post_study_goal_other || '').trim()
        : '',
    academic_standing_code:
      typeof raw.academic_standing_code === 'string'
        ? raw.academic_standing_code.trim().toUpperCase()
        : '',
    academic_standing_other:
      typeof raw.academic_standing_other === 'string' ? raw.academic_standing_other : '',
    current_level_id:
      raw.current_level_id != null && String(raw.current_level_id).trim()
        ? String(raw.current_level_id).trim()
        : '',
    current_full_time_study_years:
      typeof (raw as { current_full_time_study_years?: string }).current_full_time_study_years ===
      'string'
        ? (raw as { current_full_time_study_years?: string }).current_full_time_study_years!.trim()
        : '',
    current_program_code:
      typeof (raw as { current_program_code?: string }).current_program_code === 'string'
        ? (raw as { current_program_code?: string }).current_program_code!.trim().toUpperCase()
        : '',
    current_major:
      typeof (raw as { current_major?: string }).current_major === 'string'
        ? (raw as { current_major?: string }).current_major!.trim()
        : '',
    target_countries,
    study_countries_iso2: target_countries.map(item => item.iso2),
    funding_sources: migrateLegacyFunding(raw as Record<string, unknown>),
    ...migrateLegacyAccommodation(raw as Record<string, unknown>),
  };
}

export function aspirationsToSavePayload(form: StudentAspirationsFormState) {
  const completeFunding = form.funding_sources.filter(
    (item): item is { source: FundingSourceOption; coverage: GrantScholarshipTypeOption } =>
      Boolean(item.coverage)
  );
  const otherWhySelected = form.why_study_abroad.includes('OTHER');
  const otherPostStudySelected = form.post_study_goals.includes('OTHER');
  const target_countries = form.target_countries.map(item => ({
    iso2: item.iso2.trim().toUpperCase(),
    priority: item.priority,
  }));
  const otherCountrySelected = target_countries.some(
    item => item.iso2 === STUDY_COUNTRY_OTHER_VALUE
  );
  const otherProgramSelected = form.programs.includes(PROGRAM_OTHER_VALUE);
  const calendarSystem = normalizeIntakeCalendarSystem(form.intake_calendar_system);
  const intakeTerms = normalizeIntakeTerms(form.intake_terms, calendarSystem);

  return {
    aspirations: {
      why_study_abroad: form.why_study_abroad,
      why_study_abroad_other: otherWhySelected ? form.why_study_abroad_other.trim() : '',
      post_study_goals: form.post_study_goals,
      post_study_goal_other: otherPostStudySelected ? form.post_study_goal_other.trim() : '',
      post_study_goal: form.post_study_goals[0] || null,
      study_countries_iso2: target_countries.map(item => item.iso2),
      study_countries_other: otherCountrySelected ? form.study_countries_other.trim() : '',
      target_countries,
      institution_type: normalizeInstitutionTypes(form.institution_type),
      global_ranking: normalizeGlobalRanking(form.global_ranking),
      budget: normalizeBudgetOptions(form.budget).slice(0, 1),
      intake_seasons: [],
      intake_season_other: '',
      intake_calendar_system: calendarSystem || null,
      intake_terms: intakeTerms,
      intake_years: form.intake_years,
      study_level_code: form.study_level_code.trim().toUpperCase() || null,
      discipline_university_college: [],
      discipline_pre_college: [],
      programs: normalizePrograms(form.programs),
      programs_other: otherProgramSelected ? form.programs_other.trim() : '',
      academic_standing_code: form.academic_standing_code.trim().toUpperCase() || null,
      academic_standing_other: form.academic_standing_other.trim() || null,
      current_level_id: (() => {
        const raw = form.current_level_id.trim();
        if (!raw) return null;
        const parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : null;
      })(),
      current_full_time_study_years: form.current_full_time_study_years.trim() || null,
      current_program_code: form.current_program_code.trim().toUpperCase() || null,
      current_major: form.current_major.trim() || null,
      english_tests: form.english_tests,
      aptitude_tests: form.aptitude_tests,
      funding_sources: completeFunding,
      accommodation_university_managed: form.accommodation_university_managed,
      accommodation_off_campus_independent: form.accommodation_off_campus_independent,
      accommodation_shared_living: form.accommodation_shared_living,
      accommodation_immersive_family: form.accommodation_immersive_family,
      future_job: form.future_job,
      future_study: form.future_study,
    },
  };
}

export function validateAspirationsForm(form: StudentAspirationsFormState): string[] {
  const errors: string[] = [];
  const requireList = (values: unknown[], label: string) => {
    if (!values.length) errors.push(`${label} is required.`);
  };

  requireList(form.why_study_abroad, 'Primary motivation');
  if (form.why_study_abroad.includes('OTHER')) {
    const otherText = form.why_study_abroad_other.trim();
    if (!otherText) {
      errors.push('Please enter a value for Others — primary motivation.');
    } else if (otherText.length > 100) {
      errors.push('Others — primary motivation must be 100 characters or fewer.');
    }
  }
  if (!form.post_study_goals.length) {
    errors.push('Post-study career & immigration goals is required.');
  }
  if (form.post_study_goals.includes('OTHER')) {
    const otherText = form.post_study_goal_other.trim();
    if (!otherText) {
      errors.push('Please enter your desired career goals for Others.');
    } else if (otherText.length > 200) {
      errors.push('Others — career goals must be 200 characters or fewer.');
    }
  }
  if (!form.target_countries.length) {
    errors.push('Target countries is required.');
  }
  if (form.target_countries.length > 6) {
    errors.push('Select at most 6 target countries.');
  }
  if (form.target_countries.some(item => item.iso2 === STUDY_COUNTRY_OTHER_VALUE)) {
    const otherText = form.study_countries_other.trim();
    if (!otherText) {
      errors.push('Please enter a value for Others — target countries.');
    } else if (otherText.length > 100) {
      errors.push('Others — target countries must be 100 characters or fewer.');
    }
  }
  requireList(form.global_ranking, 'Preferred institution ranking tier');
  requireList(form.budget, 'Budget range');
  if (!form.intake_calendar_system) {
    errors.push('Intended intake calendar system is required.');
  } else if (!form.intake_terms.length) {
    errors.push('Select at least one intake term.');
  }
  requireList(form.intake_years, 'Intake year');
  if (!form.study_level_code.trim()) {
    errors.push('Degree selection is required.');
  }
  requireList(form.programs, 'Program selection');
  if (form.programs.length > MAX_TARGET_PROGRAMS) {
    errors.push(`Select up to ${MAX_TARGET_PROGRAMS} programs.`);
  }
  if (form.programs.includes(PROGRAM_OTHER_VALUE)) {
    const otherText = form.programs_other.trim();
    if (!otherText) {
      errors.push('Please enter a value for Others — programs.');
    } else if (otherText.length > 50) {
      errors.push('Others — programs must be 50 characters or fewer.');
    }
  }
  if (!form.current_level_id.trim()) {
    errors.push('Current level is required.');
  }
  if (!form.current_full_time_study_years.trim()) {
    errors.push('Full-Time Study Years is required.');
  }
  if (!form.current_program_code.trim()) {
    errors.push('Current program is required.');
  }
  if (!form.current_major.trim()) {
    errors.push('Major is required.');
  }
  if (!form.academic_standing_code.trim()) {
    errors.push('Academic scores is required.');
  }
  requireList(form.english_tests, 'English language proficiency');
  requireList(form.aptitude_tests, 'Aptitude tests');

  const completeFunding = form.funding_sources.filter(item => item.coverage);
  if (!completeFunding.length) {
    if (form.funding_sources.length) {
      errors.push(
        'Select Full, Partial, or Not Required for at least one primary funding source.'
      );
    } else {
      errors.push('Primary funding source is required.');
    }
  }

  return errors;
}

export function splitDegreesByLevel(degrees: { code: string; label: string; is_other?: boolean }[]) {
  const universityCollege: { code: string; label: string }[] = [];
  const preCollege: { code: string; label: string }[] = [];
  degrees.forEach(degree => {
    if (degree.is_other) return;
    const item = { code: degree.code, label: degree.label };
    if (PRE_COLLEGE_DEGREE_CODES.has(degree.code)) {
      preCollege.push(item);
    } else {
      universityCollege.push(item);
    }
  });
  return { universityCollege, preCollege };
}

export function toggleListValue<T extends string | number>(
  current: T[],
  value: T,
  checked: boolean
): T[] {
  if (checked) {
    return current.includes(value) ? current : [...current, value];
  }
  return current.filter(item => item !== value);
}

export function getFundingCoverage(
  sources: FundingSourceSelection[],
  source: FundingSourceOption
): GrantScholarshipTypeOption | '' {
  return sources.find(item => item.source === source)?.coverage || '';
}

export function toggleFundingSource(
  sources: FundingSourceSelection[],
  source: FundingSourceOption,
  checked: boolean
): FundingSourceSelection[] {
  if (!checked) {
    return sources.filter(item => item.source !== source);
  }
  if (sources.some(item => item.source === source)) {
    return sources;
  }
  return [...sources, { source, coverage: '' }];
}

export function setFundingCoverage(
  sources: FundingSourceSelection[],
  source: FundingSourceOption,
  coverage: GrantScholarshipTypeOption
): FundingSourceSelection[] {
  const exists = sources.some(item => item.source === source);
  if (!exists) {
    return [...sources, { source, coverage }];
  }
  return sources.map(item => (item.source === source ? { ...item, coverage } : item));
}

export function isFundingSourceSelected(
  sources: FundingSourceSelection[],
  source: FundingSourceOption
): boolean {
  return sources.some(item => item.source === source);
}
