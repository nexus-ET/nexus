import {
  ASPIRATION_OPTION_CATALOGS,
  ASPIRATION_QUESTIONS,
  ASPIRATION_SECTIONS,
  STUDY_COUNTRY_OTHER_VALUE,
} from '../config/aspirations.config';
import type { CountryRecord } from '../types/country';
import type { LevelRecord } from '../types/level';
import type { QualificationProgramRecord } from '../types/qualificationProgram';
import type { StudentAspirationsFormState } from '../types/studentAspirations';
import { INTAKE_CALENDAR_SYSTEMS } from '../types/studentAspirations';

export interface ProfileInstitutionOption {
  value: string;
  label: string;
  kind: string;
  name: string;
  country_id?: number | null;
  country_name?: string | null;
  state_name?: string | null;
  city_name?: string | null;
}

export interface AspirationQaItem {
  code: string;
  question: string;
  answer: string;
  sectionId: string;
  sectionTitle: string;
}

export interface AspirationQaSection {
  id: string;
  title: string;
  items: AspirationQaItem[];
}

export interface ProfileCountryGroup {
  countryKey: string;
  countryName: string;
  colleges: ProfileInstitutionOption[];
}

export interface StudentProfilePreviewModel {
  candidateName: string;
  generatedAtLabel: string;
  companyName?: string;
  companyAddressLines?: string[];
  logoDataUrl?: string | null;
  aspirationQa: AspirationQaItem[];
  aspirationSections: AspirationQaSection[];
  countryGroups: ProfileCountryGroup[];
  levelLabel: string;
  majorLabels: string[];
  programLabels: string[];
  englishLabels: string[];
  aptitudeLabels: string[];
  scholarshipLabel: string;
}

export interface BusinessProfileAddressSource {
  business_name?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  address_line3?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  zip_code?: string | null;
}

export function formatBusinessAddressLines(
  profile: BusinessProfileAddressSource | null | undefined
): string[] {
  if (!profile) return [];
  const lines: string[] = [];
  [profile.address_line1, profile.address_line2, profile.address_line3].forEach(line => {
    const cleaned = (line || '').trim();
    if (cleaned) lines.push(cleaned);
  });
  const cityStateZip = [profile.city, profile.state, profile.zip_code]
    .map(part => (part || '').trim())
    .filter(Boolean)
    .join(', ');
  if (cityStateZip) lines.push(cityStateZip);
  const country = (profile.country || '').trim();
  if (country) lines.push(country);
  return lines;
}

function labelFor(
  options: readonly { value: string; label: string }[],
  value: string
): string {
  return options.find(option => option.value === value)?.label || value;
}

export function joinLabels(values: string[]): string {
  return values.length ? values.join(', ') : '—';
}

function answerForQuestion(
  questionId: string,
  form: StudentAspirationsFormState,
  ctx: {
    countryNameByIso: Map<string, string>;
    levels: LevelRecord[];
    standingLabels: Record<string, string>;
  }
): string {
  switch (questionId) {
    case 'primary_motivation': {
      const values = form.why_study_abroad.map(value =>
        labelFor(ASPIRATION_OPTION_CATALOGS.motivations, value)
      );
      if (form.why_study_abroad.includes('OTHER') && form.why_study_abroad_other.trim()) {
        values.push(`Other: ${form.why_study_abroad_other.trim()}`);
      }
      return joinLabels(values);
    }
    case 'post_study_goal': {
      const values = form.post_study_goals.map(value =>
        labelFor(ASPIRATION_OPTION_CATALOGS.post_study_goals, value)
      );
      if (form.post_study_goals.includes('OTHER') && form.post_study_goal_other.trim()) {
        values.push(`Other: ${form.post_study_goal_other.trim()}`);
      }
      return joinLabels(values);
    }
    case 'target_countries': {
      const values = form.target_countries.map(item => {
        if (item.iso2 === STUDY_COUNTRY_OTHER_VALUE) {
          return form.study_countries_other.trim() || 'Others';
        }
        const name = ctx.countryNameByIso.get(item.iso2.toUpperCase()) || item.iso2;
        const priority = labelFor(ASPIRATION_OPTION_CATALOGS.country_priorities, item.priority);
        return `${name} (${priority})`;
      });
      return joinLabels(values);
    }
    case 'degree_program': {
      const levelName =
        ctx.levels.find(level => level.code === form.study_level_code)?.name ||
        form.study_level_code ||
        '—';
      const programs = [...form.programs];
      if (form.programs_other.trim()) programs.push(form.programs_other.trim());
      return `Level: ${levelName} · Programs: ${joinLabels(programs)}`;
    }
    case 'academic_standing': {
      const score =
        ctx.standingLabels[form.academic_standing_code.trim()] ||
        form.academic_standing_code.trim() ||
        form.academic_standing_other.trim() ||
        '—';
      const parts = [
        form.current_program_code ? `Program: ${form.current_program_code}` : '',
        form.current_major ? `Major: ${form.current_major}` : '',
        form.current_full_time_study_years
          ? `Years: ${form.current_full_time_study_years}`
          : '',
        `Score: ${score}`,
      ].filter(Boolean);
      return parts.join(' · ') || '—';
    }
    case 'budget_funding': {
      const budgets = form.budget.map(value =>
        labelFor(ASPIRATION_OPTION_CATALOGS.budgets, value)
      );
      const funding = form.funding_sources
        .filter(item => item.coverage)
        .map(item => {
          const source = labelFor(ASPIRATION_OPTION_CATALOGS.funding_sources, item.source);
          const coverage = labelFor(ASPIRATION_OPTION_CATALOGS.funding_coverage, item.coverage);
          return `${source} · ${coverage}`;
        });
      return `Budget: ${joinLabels(budgets)} · Funding: ${joinLabels(funding)}`;
    }
    case 'ranking_tier':
      return joinLabels(
        form.global_ranking.map(value =>
          labelFor(ASPIRATION_OPTION_CATALOGS.ranking_tiers, value)
        )
      );
    case 'intake_year': {
      const system =
        INTAKE_CALENDAR_SYSTEMS.find(item => item.value === form.intake_calendar_system)?.label ||
        '';
      const termLabels = form.intake_terms.map(term => {
        const match = INTAKE_CALENDAR_SYSTEMS.flatMap(item => item.terms).find(
          option => option.value === term
        );
        return match?.label || term;
      });
      return `System: ${system || '—'} · Terms: ${joinLabels(termLabels)} · Years: ${joinLabels(
        form.intake_years.map(String)
      )}`;
    }
    case 'test_prep': {
      const english = form.english_tests.map(value =>
        labelFor(ASPIRATION_OPTION_CATALOGS.english_tests, value)
      );
      const aptitude = form.aptitude_tests.map(value =>
        labelFor(ASPIRATION_OPTION_CATALOGS.aptitude_tests, value)
      );
      return `English: ${joinLabels(english)} · Aptitude: ${joinLabels(aptitude)}`;
    }
    default:
      return '—';
  }
}

export function buildAspirationQa(
  form: StudentAspirationsFormState | null,
  ctx: {
    countries: CountryRecord[];
    levels: LevelRecord[];
    standingLabels?: Record<string, string>;
  }
): AspirationQaItem[] {
  if (!form) return [];
  const countryNameByIso = new Map(
    ctx.countries.map(country => [country.iso2.toUpperCase(), country.name])
  );
  const sectionTitleById = Object.fromEntries(
    ASPIRATION_SECTIONS.map(section => [section.id, section.title])
  );
  return ASPIRATION_QUESTIONS.map(question => ({
    code: question.code,
    question: question.title,
    answer: answerForQuestion(question.id, form, {
      countryNameByIso,
      levels: ctx.levels,
      standingLabels: ctx.standingLabels || {},
    }),
    sectionId: question.sectionId,
    sectionTitle: sectionTitleById[question.sectionId] || question.sectionId,
  }));
}

export function groupAspirationQa(items: AspirationQaItem[]): AspirationQaSection[] {
  const order = ASPIRATION_SECTIONS.map(section => section.id);
  const bySection = new Map<string, AspirationQaSection>();
  items.forEach(item => {
    const existing = bySection.get(item.sectionId);
    if (existing) {
      existing.items.push(item);
      return;
    }
    bySection.set(item.sectionId, {
      id: item.sectionId,
      title: item.sectionTitle,
      items: [item],
    });
  });
  return order
    .map(id => bySection.get(id))
    .filter((section): section is AspirationQaSection => Boolean(section));
}

export function buildCountryGroups(
  selectedInstitutions: ProfileInstitutionOption[],
  countries: CountryRecord[]
): ProfileCountryGroup[] {
  const countryNameById = new Map(countries.map(country => [country.id, country.name]));
  const groups = new Map<string, ProfileCountryGroup>();

  selectedInstitutions.forEach(option => {
    const countryKey =
      option.country_id != null
        ? `id:${option.country_id}`
        : option.country_name
          ? `name:${option.country_name}`
          : 'unknown';
    const countryName =
      option.country_name ||
      (option.country_id != null ? countryNameById.get(option.country_id) : null) ||
      'Unassigned country';
    const existing = groups.get(countryKey);
    if (existing) {
      existing.colleges.push(option);
      return;
    }
    groups.set(countryKey, {
      countryKey,
      countryName,
      colleges: [option],
    });
  });

  return Array.from(groups.values()).sort((a, b) =>
    a.countryName.localeCompare(b.countryName)
  );
}

export function buildStudyFilterLabels(params: {
  levels: LevelRecord[];
  qualificationPrograms: QualificationProgramRecord[];
  selectedLevelId: string;
  selectedMajorIds: string[];
  selectedProgramIds: Array<number | string>;
}): {
  levelLabel: string;
  majorLabels: string[];
  programLabels: string[];
} {
  const { levels, qualificationPrograms, selectedLevelId, selectedMajorIds, selectedProgramIds } =
    params;

  const levelLabel = selectedLevelId
    ? levels.find(level => String(level.id) === selectedLevelId)?.name || selectedLevelId
    : '—';

  const majorLabels: string[] = [];
  if (selectedLevelId && selectedMajorIds.length) {
    const levelId = Number(selectedLevelId);
    const byId = new Map<number, string>();
    for (const program of qualificationPrograms) {
      if (program.level_id !== levelId) continue;
      for (const major of program.majors ?? []) {
        byId.set(major.id, major.label);
      }
    }
    selectedMajorIds.forEach(id => {
      const label = byId.get(Number(id));
      if (label) majorLabels.push(label);
    });
  }

  const programById = new Map(
    qualificationPrograms.map(program => [
      program.id,
      program.name || program.label || program.code,
    ])
  );
  const programLabels = selectedProgramIds
    .map(id => programById.get(id))
    .filter((label): label is string => Boolean(label));

  return { levelLabel, majorLabels, programLabels };
}

export function buildStudentProfilePreviewModel(params: {
  candidateName: string;
  generatedAtLabel: string;
  companyName?: string;
  companyAddressLines?: string[];
  logoDataUrl?: string | null;
  aspirations: StudentAspirationsFormState | null;
  countries: CountryRecord[];
  levels: LevelRecord[];
  standingLabels?: Record<string, string>;
  qualificationPrograms: QualificationProgramRecord[];
  selectedInstitutions: ProfileInstitutionOption[];
  selectedLevelId: string;
  selectedMajorIds: string[];
  selectedProgramIds: Array<number | string>;
  scholarshipInterests?: string;
}): StudentProfilePreviewModel {
  const aspirationQa = buildAspirationQa(params.aspirations, {
    countries: params.countries,
    levels: params.levels,
    standingLabels: params.standingLabels,
  });
  const aspirationSections = groupAspirationQa(aspirationQa);
  const countryGroups = buildCountryGroups(params.selectedInstitutions, params.countries);
  const study = buildStudyFilterLabels({
    levels: params.levels,
    qualificationPrograms: params.qualificationPrograms,
    selectedLevelId: params.selectedLevelId,
    selectedMajorIds: params.selectedMajorIds,
    selectedProgramIds: params.selectedProgramIds,
  });

  const englishLabels =
    params.aspirations?.english_tests.map(value =>
      labelFor(ASPIRATION_OPTION_CATALOGS.english_tests, value)
    ) || [];
  const aptitudeLabels =
    params.aspirations?.aptitude_tests.map(value =>
      labelFor(ASPIRATION_OPTION_CATALOGS.aptitude_tests, value)
    ) || [];

  const fromSession = (params.scholarshipInterests || '').trim();
  let scholarshipLabel = fromSession || '—';
  if (!fromSession && params.aspirations) {
    const grant = params.aspirations.funding_sources.find(
      item => item.source === 'GRANT_SCHOLARSHIP'
    );
    if (grant?.coverage) {
      scholarshipLabel = `Grant/Scholarship · ${labelFor(
        ASPIRATION_OPTION_CATALOGS.funding_coverage,
        grant.coverage
      )}`;
    }
  }

  return {
    candidateName: params.candidateName,
    generatedAtLabel: params.generatedAtLabel,
    companyName: (params.companyName || '').trim() || undefined,
    companyAddressLines: params.companyAddressLines?.filter(Boolean) || [],
    logoDataUrl: params.logoDataUrl || null,
    aspirationQa,
    aspirationSections,
    countryGroups,
    levelLabel: study.levelLabel,
    majorLabels: study.majorLabels,
    programLabels: study.programLabels,
    englishLabels,
    aptitudeLabels,
    scholarshipLabel,
  };
}
