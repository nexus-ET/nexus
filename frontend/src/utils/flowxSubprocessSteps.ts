/** At least 5 checklist steps (3–5 words each) shown on sub-process hover. */
const SUBPROCESS_STEPS: Record<string, string[]> = {
  'Intake Session': [
    'Confirm student identity',
    'Review study goals',
    'Capture preferred destinations',
    'Explain next process',
    'Schedule follow-up call',
  ],
  'Candidate Registration': [
    'Collect basic biodata',
    'Verify contact details',
    'Create CRM record',
    'Assign counsellor owner',
    'Confirm registration complete',
  ],
  'Profile Creations': [
    'Enter education history',
    'Add work experience',
    'Upload identity documents',
    'Set target intake',
    'Save profile draft',
  ],
  'Profile & goals capture': [
    'Capture academic background',
    'Record career goals',
    'Note budget range',
    'List preferred courses',
    'Confirm profile completeness',
  ],
  'Destination shortlist discussion': [
    'Review country options',
    'Compare entry requirements',
    'Discuss lifestyle fit',
    'Shortlist two destinations',
    'Agree next milestones',
  ],
  'Shortlist target universities': [
    'Filter by eligibility',
    'Compare program rankings',
    'Check intake availability',
    'Select target universities',
    'Share shortlist with student',
  ],
  'Confirm program fit': [
    'Match academic prerequisites',
    'Validate English scores',
    'Confirm course duration',
    'Review tuition estimate',
    'Get student confirmation',
  ],
  'Submit university enquiry': [
    'Prepare enquiry details',
    'Submit portal request',
    'Log enquiry reference',
    'Track university response',
    'Update student status',
  ],
  'Collect academic transcripts': [
    'List required transcripts',
    'Request school copies',
    'Verify document authenticity',
    'Scan and upload files',
    'Mark collection complete',
  ],
  'Prepare SOP draft': [
    'Outline statement structure',
    'Draft opening paragraph',
    'Add academic motivation',
    'Review with counsellor',
    'Finalize SOP version',
  ],
  'Gather recommendation letters': [
    'Identify recommenders list',
    'Send request templates',
    'Follow up pending letters',
    'Review letter quality',
    'Upload signed letters',
  ],
  'Confirm required tests': [
    'Check program test rules',
    'Confirm accepted exams',
    'Set target score band',
    'Choose preferred test',
    'Record decision in CRM',
  ],
  'Book exam slot': [
    'Select exam date',
    'Choose test centre',
    'Complete exam registration',
    'Pay booking fee',
    'Save booking confirmation',
  ],
  'Upload score report': [
    'Download official score',
    'Verify score authenticity',
    'Upload report to CRM',
    'Map scores to programs',
    'Notify counsellor owner',
  ],
  'Proof of funds checklist': [
    'List funding documents',
    'Collect bank statements',
    'Verify sponsor letters',
    'Check amount sufficiency',
    'Mark funds verified',
  ],
  'Visa document pack': [
    'Compile visa checklist',
    'Collect passport copies',
    'Attach offer letter',
    'Add financial proofs',
    'Package for submission',
  ],
  'Fee payment plan': [
    'Confirm fee breakdown',
    'Set payment milestones',
    'Share payment instructions',
    'Track receipt uploads',
    'Confirm fee completion',
  ],
  'APS Certificate': [
    'Confirm APS requirement',
    'Prepare academic dossier',
    'Submit APS application',
    'Track APS status',
    'Upload APS certificate',
  ],
  'SEVIS / I-20 tracking': [
    'Confirm I-20 issuance',
    'Verify SEVIS details',
    'Pay SEVIS fee',
    'Save SEVIS receipt',
    'Update tracking status',
  ],
  'DS-160 prep': [
    'Gather DS-160 answers',
    'Complete online form',
    'Review form accuracy',
    'Submit DS-160 application',
    'Store confirmation number',
  ],
  'TB Test': [
    'Confirm clinic requirement',
    'Book medical appointment',
    'Complete TB screening',
    'Collect medical report',
    'Upload TB certificate',
  ],
  'IHS payment': [
    'Calculate IHS amount',
    'Pay immigration surcharge',
    'Download payment receipt',
    'Link receipt to case',
    'Confirm payment logged',
  ],
};

const FALLBACK_STEPS = [
  'Review process checklist',
  'Collect required inputs',
  'Complete assigned actions',
  'Verify work quality',
  'Mark step complete',
];

function normalizeKey(title: string): string {
  return title.trim().replace(/\s+/g, ' ');
}

/** Parse a multi-line steps textarea into ordered non-empty steps. */
export function parseActionStepsText(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

/** Prefer saved brick steps; otherwise fall back to the built-in title map. */
export function subprocessSteps(title: string, savedSteps?: string[] | null): string[] {
  const fromSaved = (savedSteps || []).map(s => s.trim()).filter(Boolean);
  if (fromSaved.length > 0) {
    if (fromSaved.length >= 5) return fromSaved;
    const filled = [...fromSaved];
    while (filled.length < 5) {
      filled.push(FALLBACK_STEPS[filled.length % FALLBACK_STEPS.length]);
    }
    return filled;
  }

  const key = normalizeKey(title);
  const steps = SUBPROCESS_STEPS[key];
  if (steps && steps.length >= 5) return steps.slice(0, 5);
  if (steps && steps.length > 0) {
    const filled = [...steps];
    while (filled.length < 5) {
      filled.push(FALLBACK_STEPS[filled.length % FALLBACK_STEPS.length]);
    }
    return filled.slice(0, 5);
  }
  return FALLBACK_STEPS;
}

/**
 * Textarea value for Edit Brick: exact saved steps when present,
 * otherwise the same checklist shown on hover (built-in / fallback).
 */
export function actionStepsEditorValue(title: string, savedSteps?: string[] | null): string {
  const saved = (savedSteps || []).map(s => s.trim()).filter(Boolean);
  if (saved.length > 0) return saved.join('\n');
  return subprocessSteps(title).join('\n');
}
