export interface LevelRecord {
  id: number;
  code: string;
  name: string;
  description?: string | null;
}

export const FALLBACK_LEVELS: LevelRecord[] = [
  {
    id: 1,
    code: 'FOUNDATIONAL',
    name: 'Foundational',
    description: 'Secondary, Pre-university and foundational pathways.',
  },
  {
    id: 2,
    code: 'UNDERGRAD',
    name: 'Undergraduate',
    description: 'Undergraduate and bachelor-level study.',
  },
  {
    id: 3,
    code: 'GRADUATE',
    name: 'Graduate',
    description: "Master's and post-bachelor graduate study.",
  },
  {
    id: 4,
    code: 'DOCTORAL',
    name: 'Doctoral',
    description: 'Doctorate and research-intensive doctoral study.',
  },
];
