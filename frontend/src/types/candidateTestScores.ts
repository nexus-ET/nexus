export type TestName = 'IELTS' | 'TOEFL' | 'SAT' | 'GRE' | 'PTE' | 'DUOLINGO';

export interface TestSectionConfig {
  section_name: string;
  data_type: 'float' | 'integer';
  max_length: number;
  min_score: number;
  max_score: number;
}

export interface OverallScoreConfig {
  data_type: 'float' | 'integer';
  max_length: number;
  min_score: number;
  max_score: number;
  auto_method: 'sum' | 'average' | 'none';
}

export const TEST_NAME_OPTIONS: { value: TestName; label: string }[] = [
  { value: 'IELTS', label: 'IELTS' },
  { value: 'TOEFL', label: 'TOEFL' },
  { value: 'SAT', label: 'SAT' },
  { value: 'GRE', label: 'GRE' },
  { value: 'PTE', label: 'PTE' },
  { value: 'DUOLINGO', label: 'Duolingo' },
];

export const OVERALL_SCORE_CONFIG: Record<TestName, OverallScoreConfig> = {
  IELTS: { data_type: 'float', max_length: 3, min_score: 0, max_score: 9, auto_method: 'average' },
  TOEFL: { data_type: 'integer', max_length: 3, min_score: 0, max_score: 120, auto_method: 'sum' },
  SAT: { data_type: 'integer', max_length: 4, min_score: 400, max_score: 1600, auto_method: 'sum' },
  GRE: { data_type: 'integer', max_length: 3, min_score: 260, max_score: 340, auto_method: 'sum' },
  PTE: { data_type: 'integer', max_length: 2, min_score: 10, max_score: 90, auto_method: 'average' },
  DUOLINGO: { data_type: 'integer', max_length: 3, min_score: 10, max_score: 160, auto_method: 'none' },
};

export const TEST_SECTION_CONFIG: Record<TestName, TestSectionConfig[]> = {
  IELTS: [
    { section_name: 'Reading', data_type: 'float', max_length: 3, min_score: 0, max_score: 9 },
    { section_name: 'Writing', data_type: 'float', max_length: 3, min_score: 0, max_score: 9 },
    { section_name: 'Listening', data_type: 'float', max_length: 3, min_score: 0, max_score: 9 },
    { section_name: 'Speaking', data_type: 'float', max_length: 3, min_score: 0, max_score: 9 },
  ],
  TOEFL: [
    { section_name: 'Reading', data_type: 'integer', max_length: 2, min_score: 0, max_score: 30 },
    { section_name: 'Listening', data_type: 'integer', max_length: 2, min_score: 0, max_score: 30 },
    { section_name: 'Speaking', data_type: 'integer', max_length: 2, min_score: 0, max_score: 30 },
    { section_name: 'Writing', data_type: 'integer', max_length: 2, min_score: 0, max_score: 30 },
  ],
  SAT: [
    { section_name: 'Math', data_type: 'integer', max_length: 3, min_score: 200, max_score: 800 },
    { section_name: 'Reading', data_type: 'integer', max_length: 3, min_score: 200, max_score: 800 },
  ],
  GRE: [
    { section_name: 'Quantitative', data_type: 'integer', max_length: 3, min_score: 130, max_score: 170 },
    { section_name: 'Verbal', data_type: 'integer', max_length: 3, min_score: 130, max_score: 170 },
  ],
  PTE: [
    { section_name: 'Speaking', data_type: 'integer', max_length: 2, min_score: 10, max_score: 90 },
    { section_name: 'Writing', data_type: 'integer', max_length: 2, min_score: 10, max_score: 90 },
    { section_name: 'Reading', data_type: 'integer', max_length: 2, min_score: 10, max_score: 90 },
    { section_name: 'Listening', data_type: 'integer', max_length: 2, min_score: 10, max_score: 90 },
  ],
  DUOLINGO: [
    { section_name: 'Overall', data_type: 'integer', max_length: 3, min_score: 10, max_score: 160 },
  ],
};

export interface CandidateTestScoreRecord {
  id: number;
  lead_id: number | null;
  booking_id: number | null;
  test_name: TestName;
  test_date: string | null;
  overall_score: number | null;
  section_name: string;
  score: number;
  score_report_url: string | null;
  created_at: string;
}

export interface CandidateTestScoresResponse {
  booking_id: number;
  lead_id: number | null;
  scores: CandidateTestScoreRecord[];
}

export interface TestScoreFormState {
  test_name: TestName | '';
  test_date: string;
  score_report_url: string;
  overall_score: string;
  overall_manual_override: boolean;
  section_scores: Record<string, string>;
}

export const emptyTestScoreForm = (): TestScoreFormState => ({
  test_name: '',
  test_date: '',
  score_report_url: '',
  overall_score: '',
  overall_manual_override: false,
  section_scores: {},
});

export interface SectionValidationResult {
  section_name: string;
  error: string | null;
  isValid: boolean;
}

export function getSectionsForTest(testName: TestName | ''): TestSectionConfig[] {
  if (!testName) return [];
  return TEST_SECTION_CONFIG[testName] ?? [];
}

export function getOverallConfig(testName: TestName | ''): OverallScoreConfig | null {
  if (!testName) return null;
  return OVERALL_SCORE_CONFIG[testName] ?? null;
}

export function showsSeparateOverallField(testName: TestName | ''): boolean {
  return Boolean(testName && testName !== 'DUOLINGO');
}

export function normalizeOverallInput(value: string, config: OverallScoreConfig): string {
  const trimmed = value.trim();
  if (!trimmed) return '';

  if (config.data_type === 'integer') {
    return trimmed.replace(/[^\d]/g, '').slice(0, config.max_length);
  }

  const cleaned = trimmed.replace(/[^\d.]/g, '');
  const parts = cleaned.split('.');
  const head = parts[0] ?? '';
  const tail = parts.slice(1).join('');
  const combined = parts.length > 1 ? `${head}.${tail.slice(0, 1)}` : head;
  return combined.slice(0, config.max_length);
}

export function normalizeScoreInput(value: string, config: TestSectionConfig): string {
  const trimmed = value.trim();
  if (!trimmed) return '';

  if (config.data_type === 'integer') {
    return trimmed.replace(/[^\d]/g, '').slice(0, config.max_length);
  }

  const cleaned = trimmed.replace(/[^\d.]/g, '');
  const parts = cleaned.split('.');
  const head = parts[0] ?? '';
  const tail = parts.slice(1).join('');
  const combined = parts.length > 1 ? `${head}.${tail.slice(0, 1)}` : head;
  return combined.slice(0, config.max_length);
}

export function calculateAutoOverallScore(
  testName: TestName,
  sectionScores: Record<string, string>
): string {
  const config = getOverallConfig(testName);
  const sections = getSectionsForTest(testName);
  if (!config || config.auto_method === 'none' || sections.length === 0) {
    return '';
  }

  const values = sections.map(section => {
    const raw = (sectionScores[section.section_name] ?? '').trim();
    if (!raw) return null;
    const numeric = Number(raw);
    return Number.isFinite(numeric) ? numeric : null;
  });

  if (values.some(value => value === null)) {
    return '';
  }

  const numericValues = values as number[];
  let result: number;
  if (config.auto_method === 'sum') {
    result = numericValues.reduce((total, value) => total + value, 0);
  } else {
    result = numericValues.reduce((total, value) => total + value, 0) / numericValues.length;
  }

  if (config.data_type === 'float') {
    return String(Math.round(result * 10) / 10);
  }
  return String(Math.round(result));
}

export function validateOverallScore(
  rawValue: string,
  testName: TestName | ''
): SectionValidationResult {
  const value = rawValue.trim();
  if (!value || !testName) {
    return { section_name: 'overall_score', error: null, isValid: true };
  }

  const config = getOverallConfig(testName);
  if (!config) {
    return { section_name: 'overall_score', error: null, isValid: true };
  }

  if (value.length > config.max_length) {
    return {
      section_name: 'overall_score',
      error: `Max ${config.max_length} characters.`,
      isValid: false,
    };
  }

  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return {
      section_name: 'overall_score',
      error: 'Enter a valid number.',
      isValid: false,
    };
  }

  if (config.data_type === 'integer' && !Number.isInteger(numeric)) {
    return {
      section_name: 'overall_score',
      error: 'Must be a whole number.',
      isValid: false,
    };
  }

  if (numeric < config.min_score || numeric > config.max_score) {
    return {
      section_name: 'overall_score',
      error: `Must be between ${config.min_score} and ${config.max_score}.`,
      isValid: false,
    };
  }

  return { section_name: 'overall_score', error: null, isValid: true };
}

export function validateSectionScore(
  rawValue: string,
  config: TestSectionConfig
): SectionValidationResult {
  const value = rawValue.trim();
  if (!value) {
    return {
      section_name: config.section_name,
      error: `${config.section_name} is required.`,
      isValid: false,
    };
  }

  if (value.length > config.max_length) {
    return {
      section_name: config.section_name,
      error: `Max ${config.max_length} characters.`,
      isValid: false,
    };
  }

  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return {
      section_name: config.section_name,
      error: 'Enter a valid number.',
      isValid: false,
    };
  }

  if (config.data_type === 'integer' && !Number.isInteger(numeric)) {
    return {
      section_name: config.section_name,
      error: 'Must be a whole number.',
      isValid: false,
    };
  }

  if (numeric < config.min_score || numeric > config.max_score) {
    return {
      section_name: config.section_name,
      error: `Must be between ${config.min_score} and ${config.max_score}.`,
      isValid: false,
    };
  }

  return {
    section_name: config.section_name,
    error: null,
    isValid: true,
  };
}

export function validateTestScoreForm(form: TestScoreFormState): {
  sectionErrors: Record<string, string>;
  isValid: boolean;
} {
  if (!form.test_name) {
    return { sectionErrors: { test_name: 'Select a test.' }, isValid: false };
  }

  const sections = getSectionsForTest(form.test_name);
  const sectionErrors: Record<string, string> = {};

  sections.forEach(section => {
    const result = validateSectionScore(form.section_scores[section.section_name] ?? '', section);
    if (!result.isValid && result.error) {
      sectionErrors[section.section_name] = result.error;
    }
  });

  if (showsSeparateOverallField(form.test_name)) {
    const overallResult = validateOverallScore(form.overall_score, form.test_name);
    if (!overallResult.isValid && overallResult.error) {
      sectionErrors.overall_score = overallResult.error;
    }
  }

  return {
    sectionErrors,
    isValid: Object.keys(sectionErrors).length === 0,
  };
}

export function testScoreFormToSavePayload(form: TestScoreFormState) {
  const sections = getSectionsForTest(form.test_name);
  const overallTrimmed = form.overall_score.trim();
  return {
    test_name: form.test_name,
    test_date: form.test_date.trim() || null,
    score_report_url: form.score_report_url.trim() || null,
    overall_score:
      showsSeparateOverallField(form.test_name) && overallTrimmed
        ? Number(overallTrimmed)
        : null,
    sections: sections.map(section => ({
      section_name: section.section_name,
      score: Number((form.section_scores[section.section_name] ?? '').trim()),
    })),
  };
}

export interface GroupedTestAttempt {
  key: string;
  test_name: TestName;
  test_date: string | null;
  overall_score: number | null;
  score_report_url: string | null;
  created_at: string;
  sections: { section_name: string; score: number }[];
}

export function groupTestScoreRecords(scores: CandidateTestScoreRecord[]): GroupedTestAttempt[] {
  const groups = new Map<string, GroupedTestAttempt>();

  scores.forEach(record => {
    const key = [
      record.test_name,
      record.test_date ?? '',
      record.score_report_url ?? '',
      record.created_at,
    ].join('|');

    const existing = groups.get(key);
    if (existing) {
      existing.sections.push({ section_name: record.section_name, score: record.score });
      if (existing.overall_score == null && record.overall_score != null) {
        existing.overall_score = record.overall_score;
      }
      return;
    }

    groups.set(key, {
      key,
      test_name: record.test_name,
      test_date: record.test_date,
      overall_score: record.overall_score,
      score_report_url: record.score_report_url,
      created_at: record.created_at,
      sections: [{ section_name: record.section_name, score: record.score }],
    });
  });

  return Array.from(groups.values());
}
