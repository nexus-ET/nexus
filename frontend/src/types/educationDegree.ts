export interface EducationDegreeRecord {
  id: number;
  level_id: number;
  level_code?: string | null;
  level_name?: string | null;
  code: string;
  label: string;
  is_other: boolean;
  sort_order: number;
}

export const FALLBACK_EDUCATION_DEGREES: EducationDegreeRecord[] = [
  { id: 1, level_id: 1, level_code: 'ENTRY', level_name: 'Entry', code: 'SECONDARY_SCHOOL', label: 'Secondary (Grade 9–10)', is_other: false, sort_order: 1 },
  { id: 2, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'SENIOR_SECONDARY', label: 'Senior Secondary (Grade 11–12)', is_other: false, sort_order: 2 },
  { id: 3, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'HIGH_SCHOOL_DIPLOMA_GED', label: 'High School Diploma / GED', is_other: false, sort_order: 3 },
  { id: 4, level_id: 3, level_code: 'GRADUATE', level_name: 'Graduate', code: 'SOME_COLLEGE_NO_DEGREE', label: 'Some College (No Degree)', is_other: false, sort_order: 4 },
  { id: 5, level_id: 4, level_code: 'DOCTORAL', level_name: 'Doctoral', code: 'ASSOCIATE_DEGREE', label: 'Associate Degree (AA/AS)', is_other: false, sort_order: 5 },
  { id: 6, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'BACHELORS_3Y_INTERNATIONAL', label: "Bachelor's (3-Year International)", is_other: false, sort_order: 6 },
  { id: 7, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'BACHELORS_4Y_INTERNATIONAL', label: "Bachelor's (4-Year International)", is_other: false, sort_order: 7 },
  { id: 8, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'BACHELORS_DEGREE', label: "Bachelor's Degree (BA/BS/B.Tech)", is_other: false, sort_order: 8 },
  { id: 9, level_id: 3, level_code: 'GRADUATE', level_name: 'Graduate', code: 'INTEGRATED_MASTERS', label: "Integrated Master's", is_other: false, sort_order: 9 },
  { id: 10, level_id: 3, level_code: 'GRADUATE', level_name: 'Graduate', code: 'MASTERS_DEGREE', label: "Master's Degree (MA/MS/MBA/M.Tech)", is_other: false, sort_order: 10 },
  { id: 11, level_id: 2, level_code: 'UNDERGRAD', level_name: 'Undergraduate', code: 'POST_GRADUATE_DIPLOMA', label: 'Post-Graduate Diploma (PGD)', is_other: false, sort_order: 11 },
  { id: 12, level_id: 5, level_code: 'CERT', level_name: 'Certificate', code: 'PROFESSIONAL_DEGREE', label: 'Professional Degree (JD/MD)', is_other: false, sort_order: 12 },
  { id: 13, level_id: 5, level_code: 'CERT', level_name: 'Certificate', code: 'DOCTORATE', label: 'Doctorate (PhD/EdD)', is_other: false, sort_order: 13 },
  { id: 14, level_id: 1, level_code: 'ENTRY', level_name: 'Entry', code: 'STEM_DESIGNATED', label: 'STEM-Designated Degree', is_other: false, sort_order: 14 },
  { id: 15, level_id: 1, level_code: 'ENTRY', level_name: 'Entry', code: 'BOOTCAMP_GRADUATE', label: 'Bootcamp Graduate', is_other: false, sort_order: 15 },
  { id: 16, level_id: 1, level_code: 'ENTRY', level_name: 'Entry', code: 'PROFESSIONAL_CERTIFICATION_ONLY', label: 'Professional Certification Only', is_other: false, sort_order: 16 },
  { id: 17, level_id: 1, level_code: 'ENTRY', level_name: 'Entry', code: 'OTHER', label: 'Other', is_other: true, sort_order: 99 },
];
