export interface EducationDegreeRecord {
  id: number;
  code: string;
  label: string;
  is_other: boolean;
  sort_order: number;
}

export const FALLBACK_EDUCATION_DEGREES: EducationDegreeRecord[] = [
  { id: 1, code: 'HIGH_SCHOOL_DIPLOMA_GED', label: 'High School Diploma / GED', is_other: false, sort_order: 1 },
  { id: 2, code: 'ASSOCIATE_DEGREE', label: 'Associate Degree (AA/AS)', is_other: false, sort_order: 2 },
  { id: 3, code: 'BACHELORS_DEGREE', label: "Bachelor's Degree (BA/BS/B.Tech)", is_other: false, sort_order: 3 },
  { id: 4, code: 'MASTERS_DEGREE', label: "Master's Degree (MA/MS/MBA/M.Tech)", is_other: false, sort_order: 4 },
  { id: 5, code: 'DOCTORATE', label: 'Doctorate (PhD/EdD)', is_other: false, sort_order: 5 },
  { id: 6, code: 'PROFESSIONAL_DEGREE', label: 'Professional Degree (JD/MD)', is_other: false, sort_order: 6 },
  {
    id: 7,
    code: 'BACHELORS_3Y_INTERNATIONAL',
    label: "Bachelor's (3-Year International)",
    is_other: false,
    sort_order: 7,
  },
  {
    id: 8,
    code: 'BACHELORS_4Y_INTERNATIONAL',
    label: "Bachelor's (4-Year International)",
    is_other: false,
    sort_order: 8,
  },
  { id: 9, code: 'POST_GRADUATE_DIPLOMA', label: 'Post-Graduate Diploma (PGD)', is_other: false, sort_order: 9 },
  { id: 10, code: 'INTEGRATED_MASTERS', label: "Integrated Master's", is_other: false, sort_order: 10 },
  { id: 11, code: 'STEM_DESIGNATED', label: 'STEM-Designated Degree', is_other: false, sort_order: 11 },
  { id: 12, code: 'BOOTCAMP_GRADUATE', label: 'Bootcamp Graduate', is_other: false, sort_order: 12 },
  {
    id: 13,
    code: 'PROFESSIONAL_CERTIFICATION_ONLY',
    label: 'Professional Certification Only',
    is_other: false,
    sort_order: 13,
  },
  { id: 14, code: 'SOME_COLLEGE_NO_DEGREE', label: 'Some College (No Degree)', is_other: false, sort_order: 14 },
  { id: 15, code: 'OTHER', label: 'Other', is_other: true, sort_order: 99 },
];
