/** Pipeline views under Manage Students (matches status_definitions.category). */
export const STUDENT_PIPELINE_NAV = [
  { path: '/students/counselling', label: 'Students', category: 'Counselling', slug: 'counselling' },
  { path: '/students/documentation', label: 'Documentation', category: 'Documentation', slug: 'documentation' },
  { path: '/students/admissions', label: 'Admissions', category: 'Admission', slug: 'admissions' },
  { path: '/students/visa-services', label: 'Visa Services', category: 'Visa', slug: 'visa-services' },
  { path: '/students/pre-departure', label: 'Pre-Departure', category: 'Pre-Departure', slug: 'pre-departure' },
  { path: '/students/arrivals', label: 'Arrivals', category: 'Arrival', slug: 'arrivals' },
  { path: '/students/prospects', label: 'Prospects', category: 'Prospect', slug: 'prospects' },
] as const;

export const STUDENT_PIPELINE_PATHS = STUDENT_PIPELINE_NAV.map(item => item.path);

export function studentPipelineBySlug(slug: string) {
  return STUDENT_PIPELINE_NAV.find(item => item.slug === slug);
}
