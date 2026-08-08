export interface FullTimeStudyYearRecord {
  id: number;
  code: string;
  label: string;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  sort_order: number;
}

export const FALLBACK_FULL_TIME_STUDY_YEARS: FullTimeStudyYearRecord[] = [
  {
    id: 1,
    code: '10',
    label: '10 - High School',
    level_id: 1,
    level_code: 'FOUNDATIONAL',
    level_name: 'Foundational',
    sort_order: 1,
  },
  {
    id: 2,
    code: '12',
    label: '12 - High School',
    level_id: 1,
    level_code: 'FOUNDATIONAL',
    level_name: 'Foundational',
    sort_order: 2,
  },
  {
    id: 3,
    code: '13',
    label: '13 - Foundation Year',
    level_id: 1,
    level_code: 'FOUNDATIONAL',
    level_name: 'Foundational',
    sort_order: 3,
  },
  {
    id: 4,
    code: '14',
    label: '14 - Associate / Diploma',
    level_id: 2,
    level_code: 'UNDERGRAD',
    level_name: 'Undergraduate',
    sort_order: 4,
  },
  {
    id: 5,
    code: '15',
    label: "15 - 3-Year Bachelor's",
    level_id: 2,
    level_code: 'UNDERGRAD',
    level_name: 'Undergraduate',
    sort_order: 5,
  },
  {
    id: 6,
    code: '16',
    label: "16 - 4-Year Bachelor's",
    level_id: 2,
    level_code: 'UNDERGRAD',
    level_name: 'Undergraduate',
    sort_order: 6,
  },
  {
    id: 7,
    code: '17+',
    label: "17+ - Master's / Postgraduate",
    level_id: 3,
    level_code: 'GRADUATE',
    level_name: 'Graduate',
    sort_order: 7,
  },
  {
    id: 9,
    code: '17+',
    label: "17+ - Master's / Postgraduate",
    level_id: 5,
    level_code: 'INTEGRATED',
    level_name: 'Integrated Degree',
    sort_order: 7,
  },
  {
    id: 8,
    code: '18+',
    label: '18+ - Doctoral / Research',
    level_id: 4,
    level_code: 'DOCTORAL',
    level_name: 'Doctoral',
    sort_order: 8,
  },
  {
    id: 10,
    code: '18+',
    label: '18+ - Doctoral / Research',
    level_id: 5,
    level_code: 'INTEGRATED',
    level_name: 'Integrated Degree',
    sort_order: 8,
  },
];
