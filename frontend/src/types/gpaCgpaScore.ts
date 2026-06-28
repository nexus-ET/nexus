export interface GpaCgpaScoreRecord {
  id: number;
  code: string;
  label: string;
  is_other: boolean;
  sort_order: number;
}

export const FALLBACK_GPA_CGPA_SCORES: GpaCgpaScoreRecord[] = [
  { id: 1, code: 'GPA_375_400', label: 'GPA 3.75 - 4.00', is_other: false, sort_order: 1 },
  { id: 2, code: 'GPA_350_374', label: 'GPA 3.50 - 3.74', is_other: false, sort_order: 2 },
  { id: 3, code: 'GPA_300_349', label: 'GPA 3.00 - 3.49', is_other: false, sort_order: 3 },
  { id: 4, code: 'GPA_250_299', label: 'GPA 2.50 - 2.99', is_other: false, sort_order: 4 },
  { id: 5, code: 'GPA_200_249', label: 'GPA 2.00 - 2.49', is_other: false, sort_order: 5 },
  { id: 6, code: 'GPA_BELOW_200', label: 'GPA Below 2.00', is_other: false, sort_order: 6 },
  { id: 7, code: 'CGPA_900_1000', label: 'CGPA 9.00 - 10.00', is_other: false, sort_order: 7 },
  { id: 8, code: 'CGPA_800_899', label: 'CGPA 8.00 - 8.99', is_other: false, sort_order: 8 },
  { id: 9, code: 'CGPA_700_799', label: 'CGPA 7.00 - 7.99', is_other: false, sort_order: 9 },
  { id: 10, code: 'CGPA_600_699', label: 'CGPA 6.00 - 6.99', is_other: false, sort_order: 10 },
  { id: 11, code: 'CGPA_500_599', label: 'CGPA 5.00 - 5.99', is_other: false, sort_order: 11 },
  { id: 12, code: 'CGPA_BELOW_500', label: 'CGPA Below 5.00', is_other: false, sort_order: 12 },
  { id: 13, code: 'PCT_90_100', label: '90% - 100%', is_other: false, sort_order: 13 },
  { id: 14, code: 'PCT_80_89', label: '80% - 89%', is_other: false, sort_order: 14 },
  { id: 15, code: 'PCT_70_79', label: '70% - 79%', is_other: false, sort_order: 15 },
  { id: 16, code: 'PCT_60_69', label: '60% - 69%', is_other: false, sort_order: 16 },
  { id: 17, code: 'PCT_50_59', label: '50% - 59%', is_other: false, sort_order: 17 },
  { id: 18, code: 'PCT_BELOW_50', label: 'Below 50%', is_other: false, sort_order: 18 },
  { id: 19, code: 'OTHER', label: 'Other', is_other: true, sort_order: 99 },
];
