/** Short 3–5 word blurbs for FlowX sub-process bricks (defaults until edited). */
const SUBPROCESS_BLURBS: Record<string, string> = {
  'Intake Session': 'First student meeting',
  'Candidate Registration': 'Register new candidate',
  'Profile Creations': 'Build student profile',
  'Profile & goals capture': 'Capture goals profile',
  'Destination shortlist discussion': 'Discuss target countries',
  'Shortlist target universities': 'Pick target universities',
  'Confirm program fit': 'Validate program match',
  'Submit university enquiry': 'Send university enquiry',
  'Collect academic transcripts': 'Gather academic records',
  'Prepare SOP draft': 'Draft statement purpose',
  'Gather recommendation letters': 'Collect recommendation letters',
  'Confirm required tests': 'Identify required exams',
  'Book exam slot': 'Schedule exam booking',
  'Upload score report': 'Upload exam scores',
  'Proof of funds checklist': 'Verify funding proof',
  'Visa document pack': 'Assemble visa documents',
  'Fee payment plan': 'Plan fee payments',
  'APS Certificate': 'Germany APS certificate',
  'SEVIS / I-20 tracking': 'Track SEVIS I-20',
  'DS-160 prep': 'Prepare DS-160 form',
  'TB Test': 'Complete TB screening',
  'IHS payment': 'Pay UK IHS fee',
};

function normalizeKey(title: string): string {
  return title.trim().replace(/\s+/g, ' ');
}

/** Clamp free text to at most 5 words. */
export function clampSubprocessBlurb(text: string): string {
  return text
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 5)
    .join(' ');
}

/** Return a 3–5 word definition for a sub-process brick. Saved description wins. */
export function subprocessBlurb(title: string, description?: string | null): string {
  const saved = clampSubprocessBlurb(description || '');
  if (saved) return saved;

  const key = normalizeKey(title);
  const mapped = SUBPROCESS_BLURBS[key];
  if (mapped) return mapped;

  const fromTitle = key
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 5)
    .join(' ');
  return fromTitle || 'Process step';
}
