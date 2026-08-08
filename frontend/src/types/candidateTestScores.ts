export type TestName =
  | 'IELTS'
  | 'TOEFL'
  | 'SAT'
  | 'GRE'
  | 'PTE'
  | 'DUOLINGO'
  | 'GMAT'
  | 'ACT'
  | 'LSAT_MCAT';

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
  { value: 'GMAT', label: 'GMAT' },
  { value: 'ACT', label: 'ACT' },
  { value: 'LSAT_MCAT', label: 'LSAT / MCAT' },
  { value: 'PTE', label: 'PTE' },
  { value: 'DUOLINGO', label: 'Duolingo' },
];

/** Aspiration Q9 codes that should not open score capture. */
export const ASPIRATION_TESTS_SKIP_SCORE_CAPTURE = new Set([
  'NOT_TAKEN_YET_PLANNING',
  'WAIVER_NOT_REQUIRED',
  'NOT_REQUIRED_TEST_OPTIONAL',
]);

/** Map Aspirations english/aptitude option codes → Test Scores test names. */
export const ASPIRATION_OPTION_TO_TEST_NAME: Partial<Record<string, TestName>> = {
  IELTS: 'IELTS',
  TOEFL: 'TOEFL',
  PTE: 'PTE',
  DUOLINGO: 'DUOLINGO',
  GRE: 'GRE',
  GMAT: 'GMAT',
  SAT: 'SAT',
  ACT: 'ACT',
  LSAT_MCAT: 'LSAT_MCAT',
};

export function resolveAspirationTestForCapture(optionCode: string): TestName | null {
  if (ASPIRATION_TESTS_SKIP_SCORE_CAPTURE.has(optionCode)) return null;
  return ASPIRATION_OPTION_TO_TEST_NAME[optionCode] ?? null;
}

export const ENGLISH_SCORE_TEST_NAMES = new Set<TestName>([
  'IELTS',
  'TOEFL',
  'PTE',
  'DUOLINGO',
]);

export const APTITUDE_SCORE_TEST_NAMES = new Set<TestName>([
  'GRE',
  'GMAT',
  'SAT',
  'ACT',
  'LSAT_MCAT',
]);

export function aspirationOptionForTestName(
  testName: TestName
): { kind: 'english' | 'aptitude'; code: string } | null {
  if (ENGLISH_SCORE_TEST_NAMES.has(testName)) {
    return { kind: 'english', code: testName };
  }
  if (APTITUDE_SCORE_TEST_NAMES.has(testName)) {
    return { kind: 'aptitude', code: testName === 'LSAT_MCAT' ? 'LSAT_MCAT' : testName };
  }
  return null;
}

export const OVERALL_SCORE_CONFIG: Record<TestName, OverallScoreConfig> = {
  IELTS: { data_type: 'float', max_length: 3, min_score: 0, max_score: 9, auto_method: 'average' },
  TOEFL: { data_type: 'float', max_length: 6, min_score: 0, max_score: 120, auto_method: 'sum' },
  SAT: { data_type: 'integer', max_length: 4, min_score: 400, max_score: 1600, auto_method: 'sum' },
  GRE: { data_type: 'integer', max_length: 3, min_score: 260, max_score: 340, auto_method: 'sum' },
  GMAT: { data_type: 'integer', max_length: 3, min_score: 205, max_score: 805, auto_method: 'none' },
  ACT: { data_type: 'integer', max_length: 2, min_score: 1, max_score: 36, auto_method: 'average' },
  LSAT_MCAT: {
    data_type: 'integer',
    max_length: 3,
    min_score: 120,
    max_score: 528,
    auto_method: 'none',
  },
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
    { section_name: 'Reading', data_type: 'float', max_length: 4, min_score: 0, max_score: 30 },
    { section_name: 'Listening', data_type: 'float', max_length: 4, min_score: 0, max_score: 30 },
    { section_name: 'Speaking', data_type: 'float', max_length: 4, min_score: 0, max_score: 30 },
    { section_name: 'Writing', data_type: 'float', max_length: 4, min_score: 0, max_score: 30 },
  ],
  SAT: [
    { section_name: 'Math', data_type: 'integer', max_length: 3, min_score: 200, max_score: 800 },
    { section_name: 'Reading', data_type: 'integer', max_length: 3, min_score: 200, max_score: 800 },
  ],
  GRE: [
    { section_name: 'Quantitative', data_type: 'integer', max_length: 3, min_score: 130, max_score: 170 },
    { section_name: 'Verbal', data_type: 'integer', max_length: 3, min_score: 130, max_score: 170 },
  ],
  GMAT: [
    { section_name: 'Quantitative', data_type: 'integer', max_length: 2, min_score: 60, max_score: 90 },
    { section_name: 'Verbal', data_type: 'integer', max_length: 2, min_score: 60, max_score: 90 },
  ],
  ACT: [
    { section_name: 'English', data_type: 'integer', max_length: 2, min_score: 1, max_score: 36 },
    { section_name: 'Math', data_type: 'integer', max_length: 2, min_score: 1, max_score: 36 },
    { section_name: 'Reading', data_type: 'integer', max_length: 2, min_score: 1, max_score: 36 },
    { section_name: 'Science', data_type: 'integer', max_length: 2, min_score: 1, max_score: 36 },
  ],
  LSAT_MCAT: [
    { section_name: 'Overall', data_type: 'integer', max_length: 3, min_score: 120, max_score: 528 },
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

/** Only IELTS and TOEFL accept / display decimal (half-band style) scores. */
export function allowsDecimalScores(testName: TestName | '' | null | undefined): boolean {
  return testName === 'IELTS' || testName === 'TOEFL';
}

export function formatScoreNumber(
  value: number | string | null | undefined,
  testName: TestName | '' | null | undefined
): string {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return '';
  if (allowsDecimalScores(testName)) {
    const rounded = Math.round(numeric * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  }
  return String(Math.round(numeric));
}

export interface CandidateTestScoreRecord {
  id: number;
  lead_id: number | null;
  booking_id: number | null;
  test_name: TestName;
  test_date: string | null;
  overall_score: number | string | null;
  section_name: string;
  score: number | string;
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
  return Boolean(testName && testName !== 'DUOLINGO' && testName !== 'LSAT_MCAT');
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
  // Integer tests (everything except IELTS/TOEFL): never keep fractional composites.
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
  const testName = form.test_name;
  const coerceScore = (raw: string, dataType: 'float' | 'integer'): number => {
    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) return numeric;
    if (dataType === 'float' || allowsDecimalScores(testName)) {
      return Math.round(numeric * 10) / 10;
    }
    return Math.round(numeric);
  };

  const overallConfig = getOverallConfig(testName);
  return {
    test_name: testName,
    test_date: form.test_date.trim() || null,
    score_report_url: form.score_report_url.trim() || null,
    overall_score:
      showsSeparateOverallField(testName) && overallTrimmed && overallConfig
        ? coerceScore(overallTrimmed, overallConfig.data_type)
        : showsSeparateOverallField(testName) && overallTrimmed
          ? coerceScore(overallTrimmed, allowsDecimalScores(testName) ? 'float' : 'integer')
          : null,
    sections: sections.map(section => ({
      section_name: section.section_name,
      score: coerceScore(
        (form.section_scores[section.section_name] ?? '').trim(),
        section.data_type
      ),
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
  score_ids: number[];
  sections: { section_name: string; score: number }[];
}

export function groupTestScoreRecords(scores: CandidateTestScoreRecord[]): GroupedTestAttempt[] {
  const groups = new Map<string, GroupedTestAttempt>();

  const normalizeCreatedAt = (value: string) => {
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) return value;
    return new Date(parsed).toISOString().slice(0, 19);
  };

  const toNumber = (value: number | string | null | undefined): number | null => {
    if (value == null || value === '') return null;
    const numeric = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  };

  scores.forEach(record => {
    const key = [
      record.test_name,
      record.test_date ?? '',
      record.score_report_url ?? '',
      normalizeCreatedAt(record.created_at),
    ].join('|');

    const sectionScore = toNumber(record.score);
    const overallScore = toNumber(record.overall_score);

    const existing = groups.get(key);
    if (existing) {
      if (sectionScore != null) {
        existing.sections.push({ section_name: record.section_name, score: sectionScore });
      }
      if (!existing.score_ids.includes(record.id)) {
        existing.score_ids.push(record.id);
      }
      if (existing.overall_score == null && overallScore != null) {
        existing.overall_score = overallScore;
      }
      return;
    }

    groups.set(key, {
      key,
      test_name: record.test_name,
      test_date: record.test_date,
      overall_score: overallScore,
      score_report_url: record.score_report_url,
      created_at: record.created_at,
      score_ids: [record.id],
      sections:
        sectionScore != null
          ? [{ section_name: record.section_name, score: sectionScore }]
          : [],
    });
  });

  return Array.from(groups.values());
}

export function groupedAttemptToForm(attempt: GroupedTestAttempt): TestScoreFormState {
  const section_scores: Record<string, string> = {};
  getSectionsForTest(attempt.test_name).forEach(section => {
    section_scores[section.section_name] = '';
  });
  attempt.sections.forEach(section => {
    const config = getSectionsForTest(attempt.test_name).find(
      item => item.section_name.toLowerCase() === section.section_name.toLowerCase()
    );
    const formatted = formatScoreNumber(section.score, attempt.test_name);
    section_scores[config?.section_name || section.section_name] = config
      ? normalizeScoreInput(formatted, config)
      : formatted;
  });

  const overallConfig = getOverallConfig(attempt.test_name);
  const overallRaw =
    attempt.overall_score != null
      ? formatScoreNumber(attempt.overall_score, attempt.test_name)
      : '';
  const overall_score =
    overallConfig && overallRaw
      ? normalizeOverallInput(overallRaw, overallConfig)
      : overallRaw;

  return {
    test_name: attempt.test_name,
    test_date: attempt.test_date ?? '',
    score_report_url: attempt.score_report_url ?? '',
    overall_score,
    overall_manual_override: Boolean(overall_score),
    section_scores,
  };
}

/** Most recent attempt for a given test name (by created_at, then id). */
export function latestAttemptForTest(
  scores: CandidateTestScoreRecord[],
  testName: TestName
): GroupedTestAttempt | null {
  const needle = String(testName).trim().toUpperCase();
  const attempts = groupTestScoreRecords(
    scores.filter(record => String(record.test_name || '').trim().toUpperCase() === needle)
  );
  if (!attempts.length) return null;
  return [...attempts].sort((a, b) => {
    const aTime = Date.parse(a.created_at) || 0;
    const bTime = Date.parse(b.created_at) || 0;
    if (bTime !== aTime) return bTime - aTime;
    return Math.max(...b.score_ids) - Math.max(...a.score_ids);
  })[0];
}

export function uniqueTestNamesFromScores(scores: CandidateTestScoreRecord[]): TestName[] {
  const names = new Set<TestName>();
  scores.forEach(record => {
    if (TEST_NAME_OPTIONS.some(option => option.value === record.test_name)) {
      names.add(record.test_name);
    }
  });
  return Array.from(names);
}

export function formatAttemptScoreSummary(attempt: GroupedTestAttempt): string {
  const parts: string[] = [];

  let overall: number | null =
    attempt.overall_score != null && Number.isFinite(attempt.overall_score)
      ? attempt.overall_score
      : null;

  if (overall == null && showsSeparateOverallField(attempt.test_name)) {
    const sectionScores: Record<string, string> = {};
    getSectionsForTest(attempt.test_name).forEach(config => {
      const match = attempt.sections.find(
        section => section.section_name.toLowerCase() === config.section_name.toLowerCase()
      );
      if (match != null) {
        sectionScores[config.section_name] = String(match.score);
      }
    });
    const auto = calculateAutoOverallScore(attempt.test_name, sectionScores);
    if (auto) {
      const parsed = Number(auto);
      if (Number.isFinite(parsed)) overall = parsed;
    }
  }

  if (overall != null) {
    parts.push(`Overall ${formatScoreNumber(overall, attempt.test_name)}`);
  }

  attempt.sections.forEach(section => {
    // Avoid duplicating an Overall section when we already surfaced composite overall.
    if (
      overall != null &&
      section.section_name.trim().toLowerCase() === 'overall'
    ) {
      return;
    }
    parts.push(
      `${section.section_name} ${formatScoreNumber(section.score, attempt.test_name)}`
    );
  });

  return parts.join(' · ');
}

export function formatAttemptDateLabel(attempt: GroupedTestAttempt): string | null {
  if (!attempt.test_date) return null;
  const parsed = Date.parse(attempt.test_date);
  if (Number.isNaN(parsed)) return attempt.test_date;
  return new Date(parsed).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
