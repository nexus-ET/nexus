/** At least 5 checklist steps (3–5 words each) shown on main-process hover. */
const PROCESS_STEPS: Record<string, string[]> = {
  Counselling: [
    'Open student case',
    'Run intake session',
    'Capture goals profile',
    'Agree destination shortlist',
    'Hand off next process',
  ],
  'College finding': [
    'Review eligibility filters',
    'Build university shortlist',
    'Confirm program fit',
    'Submit university enquiries',
    'Track enquiry responses',
  ],
  'Document readiness': [
    'List required documents',
    'Collect academic transcripts',
    'Prepare SOP draft',
    'Gather recommendation letters',
    'Verify document completeness',
  ],
  Tests: [
    'Confirm required exams',
    'Book exam slots',
    'Coach score targets',
    'Upload score reports',
    'Map scores to programs',
  ],
  'Admission processing': [
    'Finalize application pack',
    'Submit university applications',
    'Track admission status',
    'Respond to conditions',
    'Secure offer letter',
  ],
  'Visa processing': [
    'Compile visa checklist',
    'Verify proof funds',
    'Complete visa forms',
    'Book visa appointment',
    'Track visa decision',
  ],
  'Pre-departure & travel': [
    'Confirm travel documents',
    'Complete fee payments',
    'Book flight tickets',
    'Arrange airport pickup',
    'Brief pre-departure checklist',
  ],
  Landing: [
    'Confirm arrival status',
    'Complete campus registration',
    'Activate local support',
    'Verify housing arrangement',
    'Close journey handoff',
  ],
};

const PROCESS_STEPS_BY_KEY: Record<string, string[]> = {
  counselling: PROCESS_STEPS.Counselling,
  college_finding: PROCESS_STEPS['College finding'],
  document_submission: PROCESS_STEPS['Document readiness'],
  tests: PROCESS_STEPS.Tests,
  admission_processing: PROCESS_STEPS['Admission processing'],
  visa_processing: PROCESS_STEPS['Visa processing'],
  predeparture_travel: PROCESS_STEPS['Pre-departure & travel'],
  landing: PROCESS_STEPS.Landing,
};

const FALLBACK_STEPS = [
  'Review process goals',
  'Complete required sub-processes',
  'Validate student readiness',
  'Update journey status',
  'Advance to next process',
];

function normalizeKey(label: string): string {
  return label.trim().replace(/\s+/g, ' ');
}

/** Five actionable steps (3–5 words) for a main-process hover checklist. */
export function processSteps(label: string, stageKey?: string | null): string[] {
  if (stageKey) {
    const byKey = PROCESS_STEPS_BY_KEY[stageKey.trim().toLowerCase()];
    if (byKey && byKey.length >= 5) return byKey.slice(0, 5);
  }
  const mapped = PROCESS_STEPS[normalizeKey(label)];
  if (mapped && mapped.length >= 5) return mapped.slice(0, 5);
  return FALLBACK_STEPS;
}
