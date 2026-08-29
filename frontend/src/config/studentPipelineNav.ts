/** Pipeline views under Students (aligned with FlowX journey stages). */
export const STUDENT_PIPELINE_NAV = [
  {
    path: '/students/counselling',
    label: '1 Counselling',
    category: 'Counselling',
    slug: 'counselling',
  },
  {
    path: '/students/college-finding',
    label: '2 College Finding',
    /** No separate College Finding status exists — show counselling students ready to shortlist. */
    category: 'Counselling',
    slug: 'college-finding',
  },
  {
    path: '/students/document-readiness',
    label: '3 Document Readiness',
    /** Reuses existing Documentation status definitions until renamed in seed. */
    category: 'Documentation',
    slug: 'document-readiness',
  },
  {
    path: '/students/admission-processing',
    label: '4 Admission Processing',
    category: 'Admission',
    slug: 'admission-processing',
  },
  {
    path: '/students/visa-processing',
    label: '5 Visa Processing',
    category: 'Visa',
    slug: 'visa-processing',
  },
  {
    path: '/students/pre-departure-travel',
    label: '6 Pre-Departure & Travel',
    category: 'Pre-Departure',
    slug: 'pre-departure-travel',
  },
  {
    path: '/students/landing',
    label: '7 Landing',
    category: 'Arrival',
    slug: 'landing',
  },
] as const;

/** Walk-in / phone capture — first Students heading, before the pipeline. */
export const OFFLINE_LEADS_NAV_GROUP = {
  key: 'offline-leads',
  label: 'Offline Leads',
  items: [
    { path: '/express-leads', label: 'Express Leads' },
    { path: '/offline-leads', label: 'Offline Leads' },
  ],
} as const;

/** Students mega-menu / sidebar group headings (pipeline stages). */
export const STUDENT_PIPELINE_NAV_GROUPS = [
  {
    key: 'discover-plan',
    label: 'Discover & Plan',
    items: STUDENT_PIPELINE_NAV.slice(0, 2),
  },
  {
    key: 'application-approval',
    label: 'Application & Approval',
    items: STUDENT_PIPELINE_NAV.slice(2, 5),
  },
  {
    key: 'depart-settle',
    label: 'Depart & Settle',
    items: STUDENT_PIPELINE_NAV.slice(5),
  },
] as const;

/** Old Students pipeline paths — redirect to counselling. */
export const LEGACY_STUDENT_PIPELINE_SLUGS = [
  'documentation',
  'admissions',
  'visa-services',
  'pre-departure',
  'arrivals',
  'prospects',
] as const;

export const STUDENT_PIPELINE_PATHS = STUDENT_PIPELINE_NAV.map(item => item.path);

export function studentPipelineBySlug(slug: string) {
  return STUDENT_PIPELINE_NAV.find(item => item.slug === slug);
}
