/**
 * Central schema for the Aspirations consultation intake.
 * Option catalogs that are not yet DB-backed live here so UI stays data-driven.
 * Countries, Levels, Majors, and GPA/CGPA brackets are fetched via hooks at runtime.
 */

import {
  APTITUDE_TEST_OPTIONS,
  BUDGET_OPTIONS,
  ENGLISH_TEST_OPTIONS,
  FUNDING_COVERAGE_OPTIONS,
  FUNDING_SOURCE_OPTIONS,
  GLOBAL_RANKING_OPTIONS,
  INTAKE_CALENDAR_SYSTEMS,
  INTAKE_PLANNED_OPTIONS,
  PROGRAM_OTHER_VALUE,
  STUDY_COUNTRY_OTHER_VALUE,
  WHY_STUDY_ABROAD_OPTIONS,
  type BudgetOption,
  type GlobalRankingOption,
  type StudentAspirationsFormState,
  type WhyStudyAbroadOption,
} from '../types/studentAspirations';

export type AspirationControlType =
  | 'single_select_cards'
  | 'multi_select_pills'
  | 'multi_select_checks'
  | 'cascading_select'
  | 'funding_matrix'
  | 'select'
  | 'combined_intake'
  | 'intake_calendar_terms';

export type AspirationQuestionId =
  | 'primary_motivation'
  | 'post_study_goal'
  | 'target_countries'
  | 'degree_program'
  | 'academic_standing'
  | 'budget_funding'
  | 'ranking_tier'
  | 'intake_year'
  | 'test_prep';

export type AspirationSectionId =
  | 'core_vision'
  | 'academic_profile'
  | 'financial_framework'
  | 'timeline_readiness';

export interface AspirationOptionDef {
  value: string;
  label: string;
  title?: string;
  description?: string;
  /** Extra classes for the option card (e.g. flex grow overrides in `fit` rows). */
  cardClassName?: string;
  /** Keep description on one line (default wraps). */
  descriptionNowrap?: boolean;
}

export interface AspirationQuestionDef {
  id: AspirationQuestionId;
  sectionId: AspirationSectionId;
  code: string;
  title: string;
  control: AspirationControlType;
  required: boolean;
  /** Runtime option source key resolved by the page/hooks layer. */
  optionSource:
    | 'motivations'
    | 'post_study_goals'
    | 'preferred_countries'
    | 'levels'
    | 'programs'
    | 'academic_standing'
    | 'budgets'
    | 'funding_sources'
    | 'funding_coverage'
    | 'ranking_tiers'
    | 'intake_seasons'
    | 'intake_years'
    | 'english_tests'
    | 'aptitude_tests';
}

export interface AspirationSectionDef {
  id: AspirationSectionId;
  title: string;
  description: string;
  questionIds: AspirationQuestionId[];
}

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

export type AspirationFlagSeverity = 'warning' | 'info';

export interface AspirationMismatchFlag {
  id: string;
  severity: AspirationFlagSeverity;
  title: string;
  detail: string;
}

/** Preferred destination ISO2 codes (Others always appended in UI). */
export const PREFERRED_STUDY_COUNTRY_ISO2 = [
  'AU',
  'CA',
  'FR',
  'DE',
  'HK',
  'IN',
  'IE',
  'JP',
  'MY',
  'NL',
  'NZ',
  'NO',
  'PL',
  'QA',
  'RU',
  'SG',
  'AE',
  'GB',
  'US',
] as const;

export const POST_STUDY_GOAL_OPTIONS: AspirationOptionDef[] = [
  {
    value: 'RETURN_HOME',
    label: 'Return to home country',
    description: 'Plan to return after studies.',
  },
  {
    value: 'PSW_WORK_EXPERIENCE',
    label: 'Gain international work experience (PSW)',
    description: 'Post-study work / temporary residence for experience.',
  },
  {
    value: 'PATHWAY_PR',
    label: 'Pathway to Permanent Residency (PR)',
    description: 'Study as a stepping stone toward long-term settlement.',
  },
  {
    value: 'UNDECIDED',
    label: 'Undecided',
    description: 'Still evaluating career and immigration outcomes.',
  },
  {
    value: 'OTHER',
    label: 'Others',
    description: 'Describe your desired career goals.',
  },
];

export const COUNTRY_PRIORITY_OPTIONS: AspirationOptionDef[] = [
  { value: 'TOP_CHOICE', label: 'Top Choice' },
  { value: 'ALTERNATIVE', label: 'Open to Alternatives' },
];

/** Level codes that prefer percentage standing brackets (PCT_*). */
export const PERCENTAGE_STANDING_LEVEL_CODES = new Set(['FOUNDATIONAL']);

export const ASPIRATION_SECTIONS: AspirationSectionDef[] = [
  {
    id: 'core_vision',
    title: 'Core Vision & Destination',
    description: 'Motivation, post-study intent, and target destinations.',
    questionIds: ['primary_motivation', 'post_study_goal', 'target_countries'],
  },
  {
    id: 'academic_profile',
    title: 'Academic Profile & Program Fit',
    description: 'Degree level, programs, and current academic standing.',
    questionIds: ['academic_standing', 'degree_program'],
  },
  {
    id: 'financial_framework',
    title: 'Financial Framework',
    description: 'Budget tier and primary funding sources.',
    questionIds: ['budget_funding'],
  },
  {
    id: 'timeline_readiness',
    title: 'Timeline & Execution Readiness',
    description: 'Ranking preference, intake timing, and test preparation.',
    questionIds: ['ranking_tier', 'intake_year', 'test_prep'],
  },
];

export const ASPIRATION_QUESTIONS: AspirationQuestionDef[] = [
  {
    id: 'primary_motivation',
    sectionId: 'core_vision',
    code: 'Q1',
    title: 'What is your primary motivation for studying abroad?',
    control: 'multi_select_checks',
    required: true,
    optionSource: 'motivations',
  },
  {
    id: 'post_study_goal',
    sectionId: 'core_vision',
    code: 'Q2',
    title: 'Post-study career & immigration goals',
    control: 'multi_select_checks',
    required: true,
    optionSource: 'post_study_goals',
  },
  {
    id: 'target_countries',
    sectionId: 'core_vision',
    code: 'Q3',
    title: 'Target countries',
    control: 'multi_select_pills',
    required: true,
    optionSource: 'preferred_countries',
  },
  {
    id: 'academic_standing',
    sectionId: 'academic_profile',
    code: 'Q4',
    title: 'Current Degree & Program',
    control: 'select',
    required: true,
    optionSource: 'academic_standing',
  },
  {
    id: 'degree_program',
    sectionId: 'academic_profile',
    code: 'Q5',
    title: 'Target Degree & Program Path',
    control: 'cascading_select',
    required: true,
    optionSource: 'levels',
  },
  {
    id: 'budget_funding',
    sectionId: 'financial_framework',
    code: 'Q6',
    title: 'Budget range & primary funding source',
    control: 'funding_matrix',
    required: true,
    optionSource: 'budgets',
  },
  {
    id: 'ranking_tier',
    sectionId: 'timeline_readiness',
    code: 'Q7',
    title: 'Preferred institution ranking tier',
    control: 'single_select_cards',
    required: true,
    optionSource: 'ranking_tiers',
  },
  {
    id: 'intake_year',
    sectionId: 'timeline_readiness',
    code: 'Q8',
    title: 'Intended intake & year',
    control: 'intake_calendar_terms',
    required: true,
    optionSource: 'intake_calendar_systems',
  },
  {
    id: 'test_prep',
    sectionId: 'timeline_readiness',
    code: 'Q9',
    title: 'Test preparation status',
    control: 'multi_select_checks',
    required: true,
    optionSource: 'english_tests',
  },
];

export const ASPIRATION_OPTION_CATALOGS = {
  motivations: WHY_STUDY_ABROAD_OPTIONS.map(option => ({
    value: option.value,
    label: option.title || option.label || option.value,
    title: option.title,
    description: option.description,
  })),
  post_study_goals: POST_STUDY_GOAL_OPTIONS,
  budgets: BUDGET_OPTIONS,
  funding_sources: FUNDING_SOURCE_OPTIONS,
  funding_coverage: FUNDING_COVERAGE_OPTIONS,
  ranking_tiers: [
    {
      value: 'TOP_100_GLOBAL_ELITE',
      label: 'Top 100 Global Elite',
      title: 'Top 100',
      description: 'Global Elite',
      descriptionNowrap: true,
    },
    {
      value: 'TOP_300_RESEARCH_INTENSIVE',
      label: 'Top 300 Research-Intensive',
      title: 'Top 300',
      description: 'Research-Intensive',
      descriptionNowrap: true,
    },
    {
      value: 'TOP_500_BROAD_ACADEMIC',
      label: 'Top 500 Academic Excellence',
      title: 'Top 500',
      description: 'Academic Excellence',
      cardClassName: 'flex-[1.45] min-w-[9.5rem]',
      descriptionNowrap: true,
    },
    {
      value: 'ANY_INCLUSIVE',
      label: 'Any',
      title: 'Any',
      cardClassName: 'flex-[0.55] min-w-[4.5rem] max-w-[6.5rem]',
    },
  ],
  intake_seasons: INTAKE_PLANNED_OPTIONS,
  english_tests: ENGLISH_TEST_OPTIONS,
  aptitude_tests: APTITUDE_TEST_OPTIONS,
  country_priorities: COUNTRY_PRIORITY_OPTIONS,
} as const;

export function getAspirationQuestion(id: AspirationQuestionId): AspirationQuestionDef {
  const question = ASPIRATION_QUESTIONS.find(item => item.id === id);
  if (!question) throw new Error(`Unknown aspiration question: ${id}`);
  return question;
}

export function getAspirationSection(id: AspirationSectionId): AspirationSectionDef {
  const section = ASPIRATION_SECTIONS.find(item => item.id === id);
  if (!section) throw new Error(`Unknown aspiration section: ${id}`);
  return section;
}

export function isQuestionComplete(
  questionId: AspirationQuestionId,
  form: StudentAspirationsFormState
): boolean {
  switch (questionId) {
    case 'primary_motivation':
      return (
        form.why_study_abroad.length > 0 &&
        (!form.why_study_abroad.includes('OTHER') || Boolean(form.why_study_abroad_other.trim()))
      );
    case 'post_study_goal':
      return (
        form.post_study_goals.length > 0 &&
        (!form.post_study_goals.includes('OTHER') || Boolean(form.post_study_goal_other.trim()))
      );
    case 'target_countries':
      return (
        form.target_countries.length > 0 &&
        (!form.target_countries.some(item => item.iso2 === STUDY_COUNTRY_OTHER_VALUE) ||
          Boolean(form.study_countries_other.trim()))
      );
    case 'degree_program':
      return (
        Boolean(form.study_level_code.trim()) &&
        form.programs.length > 0 &&
        (!form.programs.includes(PROGRAM_OTHER_VALUE) || Boolean(form.programs_other.trim()))
      );
    case 'academic_standing':
      return (
        Boolean(form.current_level_id.trim()) &&
        Boolean(form.current_full_time_study_years.trim()) &&
        Boolean(form.current_program_code.trim()) &&
        Boolean(form.current_major.trim()) &&
        Boolean(form.academic_standing_code.trim())
      );
    case 'budget_funding':
      return (
        form.budget.length > 0 &&
        form.funding_sources.some(item => Boolean(item.coverage))
      );
    case 'ranking_tier':
      return form.global_ranking.length > 0;
    case 'intake_year':
      return (
        Boolean(form.intake_calendar_system) &&
        form.intake_terms.length > 0 &&
        form.intake_years.length > 0
      );
    case 'test_prep':
      return form.english_tests.length > 0 && form.aptitude_tests.length > 0;
    default:
      return false;
  }
}

export function computeAspirationsProgress(form: StudentAspirationsFormState): {
  completed: number;
  total: number;
  percent: number;
  bySection: Record<AspirationSectionId, { completed: number; total: number }>;
} {
  const bySection = {} as Record<AspirationSectionId, { completed: number; total: number }>;
  let completed = 0;
  const total = ASPIRATION_QUESTIONS.length;

  for (const section of ASPIRATION_SECTIONS) {
    const sectionCompleted = section.questionIds.filter(id => isQuestionComplete(id, form)).length;
    bySection[section.id] = { completed: sectionCompleted, total: section.questionIds.length };
    completed += sectionCompleted;
  }

  return {
    completed,
    total,
    percent: total ? Math.round((completed / total) * 100) : 0,
    bySection,
  };
}

function labelForMotivation(value: WhyStudyAbroadOption): string {
  return (
    ASPIRATION_OPTION_CATALOGS.motivations.find(item => item.value === value)?.label || value
  );
}

function labelForBudget(value: BudgetOption): string {
  return BUDGET_OPTIONS.find(item => item.value === value)?.label || value;
}

function labelForRanking(value: GlobalRankingOption): string {
  return GLOBAL_RANKING_OPTIONS.find(item => item.value === value)?.label || value;
}

function labelForPostStudy(value: string): string {
  return POST_STUDY_GOAL_OPTIONS.find(item => item.value === value)?.label || value;
}

export interface AspirationSummaryContext {
  countryNames: Record<string, string>;
  levelNames: Record<string, string>;
  standingLabels: Record<string, string>;
}

export function generateAspirationSummary(
  form: StudentAspirationsFormState,
  ctx: AspirationSummaryContext
): string {
  const countries = form.target_countries
    .map(item => {
      const name =
        item.iso2 === STUDY_COUNTRY_OTHER_VALUE
          ? form.study_countries_other.trim() || 'Others'
          : ctx.countryNames[item.iso2] || item.iso2;
      return item.priority === 'TOP_CHOICE' ? `${name} (top)` : name;
    })
    .filter(Boolean);

  const motivation = form.why_study_abroad.length
    ? form.why_study_abroad.map(labelForMotivation).join(', ')
    : null;
  const level = form.study_level_code
    ? ctx.levelNames[form.study_level_code] || form.study_level_code
    : null;
  const programs = form.programs
    .map(item =>
      item === PROGRAM_OTHER_VALUE ? form.programs_other.trim() || 'Others' : item
    )
    .filter(Boolean);
  const intakeSystem =
    INTAKE_CALENDAR_SYSTEMS.find(item => item.value === form.intake_calendar_system)?.label || null;
  const intakeTerms = form.intake_terms
    .map(term => {
      const match = INTAKE_CALENDAR_SYSTEMS.flatMap(item => item.terms).find(
        option => option.value === term
      );
      return match?.label || term;
    })
    .filter(Boolean);
  const intakeSeason = [intakeSystem, intakeTerms.join(', ')].filter(Boolean).join(' · ') || null;
  const year = form.intake_years[0] || null;
  const budget = form.budget[0] ? labelForBudget(form.budget[0]) : null;
  const funding = form.funding_sources
    .filter(item => item.coverage)
    .map(item => {
      const source =
        FUNDING_SOURCE_OPTIONS.find(opt => opt.value === item.source)?.label || item.source;
      const coverage =
        FUNDING_COVERAGE_OPTIONS.find(opt => opt.value === item.coverage)?.label || item.coverage;
      return `${source} (${coverage})`;
    });
  const ranking = form.global_ranking.length
    ? form.global_ranking.map(value => labelForRanking(value)).join(', ')
    : null;
  const postStudy = form.post_study_goals.length
    ? form.post_study_goals
        .map(value =>
          value === 'OTHER'
            ? form.post_study_goal_other.trim() || 'Others'
            : labelForPostStudy(value)
        )
        .join(', ')
    : null;
  const standing = form.academic_standing_code
    ? ctx.standingLabels[form.academic_standing_code] || form.academic_standing_code
    : null;

  const parts: string[] = [];
  if (countries.length || programs.length || level || year) {
    const dest = countries.length ? countries.slice(0, 3).join(' & ') : 'unspecified destinations';
    const programBit = programs.length ? programs.slice(0, 2).join(', ') : 'programs TBD';
    const levelBit = level || 'degree TBD';
    const when = [intakeSeason, year].filter(Boolean).join(' ') || 'intake TBD';
    parts.push(`Targeting ${dest} for ${programBit} (${levelBit}) in ${when}.`);
  }
  if (motivation) parts.push(`Primary motivation: ${motivation}.`);
  if (postStudy) parts.push(`Post-study goal: ${postStudy}.`);
  if (standing) parts.push(`Current standing: ${standing}.`);
  if (budget || funding.length) {
    parts.push(
      [budget ? `Budget: ${budget}` : null, funding.length ? `via ${funding.join(', ')}` : null]
        .filter(Boolean)
        .join(' ')
        .concat('.')
    );
  }
  if (ranking) parts.push(`Institution preference: ${ranking}.`);

  return parts.join(' ').trim() || 'No aspirations selections yet — complete the questionnaire to generate a brief.';
}

export function detectAspirationMismatches(
  form: StudentAspirationsFormState
): AspirationMismatchFlag[] {
  const flags: AspirationMismatchFlag[] = [];
  const hasElite = form.global_ranking.includes('TOP_100_GLOBAL_ELITE');
  const hasBudgetFriendly = form.budget.includes('BUDGET_FRIENDLY');
  const needsFullFunding = form.budget.includes('NEEDS_FULL_FUNDING');
  const scholarshipFunding = form.funding_sources.some(
    item => item.source === 'GRANT_SCHOLARSHIP' && item.coverage === 'FULL'
  );
  const familyOnly =
    form.funding_sources.length > 0 &&
    form.funding_sources.every(item => item.source === 'FAMILY_SPONSORED');

  if (hasElite && hasBudgetFriendly) {
    flags.push({
      id: 'elite_vs_budget',
      severity: 'warning',
      title: 'Elite ranking vs low budget',
      detail:
        'Top 100 Global Elite schools rarely fit a Budget Friendly (≤20 Lakhs) envelope without substantial aid.',
    });
  }

  if (hasElite && needsFullFunding) {
    flags.push({
      id: 'elite_vs_full_funding',
      severity: 'warning',
      title: 'Elite ranking + full funding dependency',
      detail:
        'Targeting Top 100 while needing full funding is high-risk — confirm scholarship-viable shortlists.',
    });
  }

  if (needsFullFunding && familyOnly) {
    flags.push({
      id: 'funding_mismatch',
      severity: 'warning',
      title: 'Funding source mismatch',
      detail:
        'Needs Full Funding is selected but only Family Sponsored coverage is active — add Grant/Scholarship or revise budget.',
    });
  }

  if (
    form.post_study_goals.includes('PATHWAY_PR') &&
    form.target_countries.some(item => item.iso2 === 'IN') &&
    form.target_countries.every(item => item.iso2 === 'IN' || item.iso2 === STUDY_COUNTRY_OTHER_VALUE)
  ) {
    flags.push({
      id: 'pr_vs_india_only',
      severity: 'info',
      title: 'PR pathway vs destination',
      detail:
        'Permanent residency pathways typically require destinations with post-study settlement routes — expand country targets if PR is a priority.',
    });
  }

  if (
    form.why_study_abroad.includes('INTERNATIONAL_REPUTATION') &&
    form.global_ranking.includes('ANY_INCLUSIVE') &&
    !hasElite
  ) {
    flags.push({
      id: 'prestige_vs_any_rank',
      severity: 'info',
      title: 'Prestige motivation vs open ranking',
      detail:
        'Motivation cites prestigious/global ranking but ranking preference is set to Any — consider narrowing tiers.',
    });
  }

  if (scholarshipFunding && form.budget.includes('HIGH_INVESTMENT') && !needsFullFunding) {
    flags.push({
      id: 'scholarship_high_budget',
      severity: 'info',
      title: 'High budget with full scholarship',
      detail:
        'Full Grant/Scholarship coverage with a High Investment budget may overstate cash need — verify net cost assumptions.',
    });
  }

  return flags;
}

export { STUDY_COUNTRY_OTHER_VALUE, PROGRAM_OTHER_VALUE };
