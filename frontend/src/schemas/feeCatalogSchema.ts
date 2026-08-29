import { z } from 'zod';

/**
 * Nexus Fee Architecture — Admin catalog (Phase 1).
 *
 * Student billing is INR + GST (not USD). List prices here are the audit anchor;
 * packages define included services; charged price comes from list sum + Discount policy
 * (and optional future package overrides) at invoice time.
 *
 * Parked for Phase 2 / Invoice Generator:
 * - Charge mode: itemized | bundle | custom_group
 * - Counselor price override (Manager/Admin RBAC)
 * - Multi-select "Group & Charge" flat fee
 * - Savings badge on package selection
 */

export const FEE_CATALOG_CURRENCY = 'INR' as const;

const slugIdSchema = z
  .string()
  .trim()
  .min(1)
  .max(64)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Use lowercase letters, numbers, and hyphens.');

export const feeAuditFieldsSchema = z.object({
  createdAt: z.string().default(''),
  updatedAt: z.string().default(''),
  createdBy: z.string().trim().max(120).default(''),
  updatedBy: z.string().trim().max(120).default(''),
});

export type FeeAuditFields = z.infer<typeof feeAuditFieldsSchema>;

export const EMPTY_FEE_AUDIT: FeeAuditFields = {
  createdAt: '',
  updatedAt: '',
  createdBy: '',
  updatedBy: '',
};

export const feeServiceSchema = z.object({
  id: slugIdSchema,
  name: z.string().trim().min(1, 'Service name is required.').max(80),
  description: z.string().trim().max(240).default(''),
  /** List / anchor price in INR (ex-GST). */
  basePriceInr: z.coerce
    .number()
    .min(0, 'Base price cannot be negative.')
    .max(10_000_000, 'Base price is too large.'),
  active: z.boolean().default(true),
  sortOrder: z.coerce.number().int().min(0).max(999).default(0),
  /**
   * Explicit Master Workflow process assignment (counselling, visa_processing, …).
   * Use "other" (or empty) to keep the service in Other services — name heuristics must not move it.
   */
  masterProcessKey: z.string().trim().max(64).default(''),
  createdAt: z.string().default(''),
  updatedAt: z.string().default(''),
  createdBy: z.string().trim().max(120).default(''),
  updatedBy: z.string().trim().max(120).default(''),
});

export type FeeService = z.infer<typeof feeServiceSchema>;

export const feeBundleSchema = z
  .object({
    id: slugIdSchema,
    name: z.string().trim().min(1, 'Package name is required.').max(80),
    description: z.string().trim().max(240).default(''),
    /** Optional short blurb printed on invoices under the package name (max 75). */
    invoiceDescription: z.string().trim().max(75).default(''),
    serviceIds: z.array(z.string().trim().min(1)).min(1, 'Select at least one service.'),
    /** Optional stored package override; catalog UI no longer edits this — discount policy applies at invoice. */
    packagePriceInr: z.coerce
      .number()
      .min(0, 'Package price cannot be negative.')
      .max(10_000_000, 'Package price is too large.')
      .default(0),
    active: z.boolean().default(true),
    sortOrder: z.coerce.number().int().min(0).max(999).default(0),
    createdAt: z.string().default(''),
    updatedAt: z.string().default(''),
    createdBy: z.string().trim().max(120).default(''),
    updatedBy: z.string().trim().max(120).default(''),
  })
  .superRefine((values, ctx) => {
    const unique = new Set(values.serviceIds);
    if (unique.size !== values.serviceIds.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['serviceIds'],
        message: 'Package contains duplicate services.',
      });
    }
  });

export type FeeBundle = z.infer<typeof feeBundleSchema>;

export const feeCatalogSchema = z
  .object({
    currency: z.literal(FEE_CATALOG_CURRENCY).default(FEE_CATALOG_CURRENCY),
    services: z.array(feeServiceSchema).max(80),
    bundles: z.array(feeBundleSchema).max(40),
  })
  .superRefine((values, ctx) => {
    const serviceIds = new Set(values.services.map(service => service.id));
    if (serviceIds.size !== values.services.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['services'],
        message: 'Service ids must be unique.',
      });
    }
    const bundleIds = new Set(values.bundles.map(bundle => bundle.id));
    if (bundleIds.size !== values.bundles.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['bundles'],
        message: 'Package ids must be unique.',
      });
    }
    values.bundles.forEach((bundle, index) => {
      const missing = bundle.serviceIds.filter(id => !serviceIds.has(id));
      if (missing.length) {
        ctx.addIssue({
          code: 'custom',
          path: ['bundles', index, 'serviceIds'],
          message: `Unknown service id(s): ${missing.join(', ')}.`,
        });
      }
    });
  });

export type FeeCatalog = z.infer<typeof feeCatalogSchema>;

export type SessionPurposeSeed = {
  label: string;
  description?: string;
};

/** Default list prices keyed by lowercase session-purpose / service name. */
export const DEFAULT_SESSION_PURPOSE_LIST_PRICES: Record<string, number> = {
  'general counselling': 5000,
  'university shortlisting': 15000,
  'documentation': 12000,
  'visa application help': 15000,
  'test prep guidance': 6000,
  'application review': 10000,
  'sop drafting': 8000,
  'statement of purpose / essay writing': 8000,
  'interview prep': 7000,
};

/**
 * Near-duplicate / alias names → preferred display name (lowercase).
 * Used when regenerating the catalog so legacy labels collapse into one service.
 */
export const FEE_SERVICE_NAME_ALIASES: Record<string, string> = {
  // Keep original catalog name "SOP Drafting" as the canonical essay service.
  sop: 'sop drafting',
  'statement of purpose': 'sop drafting',
  'statement of purpose / essay writing': 'sop drafting',
  'essay writing': 'sop drafting',
  'personal history statement': 'sop drafting',
  'personal history': 'sop drafting',
  phs: 'sop drafting',
  'university shortlisting help': 'university shortlisting',
};

/** Names never offered in Base Price Catalog (even if still used as booking purposes). */
export const FEE_CATALOG_EXCLUDED_SERVICE_KEYS = new Set<string>([]);

export function normalizeFeeServiceNameKey(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/\s+/g, ' ');
}

export function canonicalFeeServiceNameKey(name: string): string {
  const key = normalizeFeeServiceNameKey(name);
  return FEE_SERVICE_NAME_ALIASES[key] || key;
}

export function isExcludedFromFeeCatalog(name: string): boolean {
  return FEE_CATALOG_EXCLUDED_SERVICE_KEYS.has(canonicalFeeServiceNameKey(name));
}

/**
 * Master Workflow main processes (FlowX JOURNEY_STAGES) — fee catalog grouping.
 * Labels match backend JOURNEY_STAGE_LABELS / Master Workflow board.
 */
export const FLOWX_MASTER_PROCESS_ORDER = [
  'counselling',
  'college_finding',
  'document_submission',
  'tests',
  'admission_processing',
  'visa_processing',
  'predeparture_travel',
  'landing',
] as const;

export type FlowxMasterProcessKey = (typeof FLOWX_MASTER_PROCESS_ORDER)[number];

export const FLOWX_MASTER_PROCESS_LABELS: Record<FlowxMasterProcessKey, string> = {
  counselling: 'Counselling',
  college_finding: 'College finding',
  document_submission: 'Document readiness',
  tests: 'Tests',
  admission_processing: 'Admission processing',
  visa_processing: 'Visa processing',
  predeparture_travel: 'Pre-departure & travel',
  landing: 'Landing',
};

/** Explicit catalog assignment for services that stay outside Master Workflow processes. */
export const FEE_SERVICE_OTHER_PROCESS_KEY = 'other';

/** Fallback blurbs when a service has no name-specific copy (new / custom rows). */
export const FEE_SERVICE_PROCESS_DESCRIPTIONS: Record<FlowxMasterProcessKey, string> = {
  counselling:
    'One-to-one counselling to clarify study goals, budget, and the right pathway forward.',
  college_finding:
    'Build and refine a target university/program shortlist that fits the student profile.',
  document_submission:
    'Collect, check, and prepare application documents so the file is submission-ready.',
  tests:
    'Plan language/entrance exams, set score targets, and track official results.',
  admission_processing:
    'Support applications from draft review through offer tracking and decision follow-up.',
  visa_processing:
    'Prepare visa paperwork, evidence, and interview readiness through to filing.',
  predeparture_travel:
    'Complete fee, travel, and logistics steps before the student leaves for campus.',
  landing:
    'Support arrival, campus registration, housing checks, and local handoff.',
};

/** Unique copy per known service name — never reuse a single process blurb for different rows. */
export const FEE_SERVICE_NAME_DESCRIPTIONS: Record<string, string> = {
  'general counselling':
    'Open counselling to clarify study goals, budget, timeline, and the overall pathway abroad.',
  'scholarship guidance':
    'Research scholarships and funding fits, then shortlist awards the student can realistically chase.',
  'digital presence and profile boosting':
    'Upgrade LinkedIn and public profiles so outreach, applications, and interviews look professional.',
  'university shortlisting':
    'Research destinations and programs, then lock a realistic university shortlist for the student.',
  'university shortlisting help':
    'Research destinations and programs, then lock a realistic university shortlist for the student.',
  documentation:
    'Collect, verify, and file transcripts, IDs, and supporting docs so applications are complete.',
  'sop drafting':
    'Write and refine the statement of purpose and essays that universities will actually read.',
  'statement of purpose / essay writing':
    'Write and refine the statement of purpose and essays that universities will actually read.',
  'personal history statement':
    'Draft the personal history / background statement some universities require with the application.',
  'test prep guidance':
    'Choose IELTS / TOEFL / GRE / GMAT options, set score targets, and plan the prep timeline.',
  'application review':
    'Quality-check the full application pack for gaps, inconsistencies, and submission readiness.',
  'application filing':
    'Lodge applications on university portals and confirm each submission was received correctly.',
  'application support':
    'Manage application timelines, portal steps, and follow-ups until every chosen file is lodged.',
  'offer acceptance':
    'Compare offers, accept the chosen place, and complete deposit and confirmation formalities.',
  'enrollment support':
    'Finish enrollment, tuition, and registration tasks once the offer has been accepted.',
  'visa application help':
    'Complete visa forms, gather evidence, and file for the student’s chosen study destination.',
  'visa filing':
    'Submit the visa file and track biometrics, acknowledgements, and decision updates.',
  'interview prep':
    'Coach university or visa interviews with practice questions, structure, and feedback.',
  'visa mock interview':
    'Run a scored mock visa interview and coach answers, confidence, and presentation.',
  'job application help':
    'Prepare CVs, cover letters, and job applications for internships or post-study work roles.',
  'job application':
    'Prepare CVs, cover letters, and job applications for internships or post-study work roles.',
  'resume drafting':
    'Draft and polish a CV / resume tailored to the roles or programs the student is targeting.',
  'profile assessment and building':
    'Assess the student profile and strengthen academics, activities, and positioning for applications.',
  'application documentation':
    'Collect, verify, and file transcripts, IDs, and supporting docs so applications are complete.',
  'statement of purpose drafting/ essay writing':
    'Write and refine the statement of purpose and essays that universities will actually read.',
  'education loan assistance':
    'Guide education-loan options, paperwork, and lender follow-ups for funding the study plan.',
  'letter of recommendation drafting':
    'Draft and refine recommendation letters with recommenders for university applications.',
  'aptitude test prep guidance':
    'Plan SAT / GRE / GMAT prep, timelines, and target score bands for aptitude tests.',
  'english test prep guidance':
    'Plan IELTS / TOEFL / PTE / Duolingo prep, timelines, and target score bands.',
  'visa application guidance':
    'Complete visa forms, gather evidence, and file for the student’s chosen study destination.',
  'forex and remittance guidance':
    'Advise on forex, tuition remittance, and compliant money-transfer steps before departure.',
  'housing and accommodation guidance':
    'Help shortlist and secure student housing or temporary stay options before arrival.',
  'student health and campus insurance':
    'Guide student health cover and campus insurance requirements before travel and enrollment.',
  'career counselling':
    'Advise on career paths, role targets, and next steps linked to the student’s study plan.',
  'resume writing':
    'Draft and polish a CV / resume tailored to the roles or programs the student is targeting.',
  'cv writing':
    'Draft and polish a CV / resume tailored to the roles or programs the student is targeting.',
  'cover letter writing':
    'Write targeted cover letters that match each role or internship the student applies for.',
  'linkedin profile':
    'Build a clear LinkedIn profile that supports applications, networking, and outreach.',
  'accommodation help':
    'Help shortlist and secure student housing or temporary stay options before departure.',
  'airport pickup':
    'Arrange arrival pickup and the first transfer from airport to housing or campus.',
  'pre departure briefing':
    'Brief the student on travel, packing, finances, and first-week logistics before departure.',
  'pre-departure briefing':
    'Brief the student on travel, packing, finances, and first-week logistics before departure.',
};

/** Older / generic blurbs that should be replaced with stronger service-specific copy. */
const STALE_FEE_SERVICE_DESCRIPTIONS = new Set(
  [
    'Document preparation and review support.',
    'Document preparation and review support',
    'Guidance and planning support for this counselling step.',
    'Guidance and planning support for this counselling step',
    'University and program matching support.',
    'University and program matching support',
    'Test planning, booking, and score support.',
    'Test planning, booking, and score support',
    'Application and admission processing support.',
    'Application and admission processing support',
    'Visa preparation, filing, and interview support.',
    'Visa preparation, filing, and interview support',
    'Pre-departure and travel readiness support.',
    'Pre-departure and travel readiness support',
    'Arrival, registration, and settling-in support.',
    'Arrival, registration, and settling-in support',
    'Custom service for the student journey.',
    'Custom service for the student journey',
    'Billable counselling service tied to the student journey.',
    'Billable counselling service tied to the student journey',
    'Initial study-abroad guidance, goals, and pathway overview.',
    'Initial study-abroad guidance, goals, and pathway overview',
    'Match destinations, institutions, and programs to the profile.',
    'Collect, review, and organise application documents.',
    'Draft and refine statement of purpose / essays.',
    'Review application drafts and submission readiness.',
    'Visa forms, evidence checklist, and interview prep.',
    'IELTS / TOEFL / GRE / GMAT prep planning.',
    'University or visa interview coaching.',
    'First counselling sessions to map goals, constraints, and an overall study-abroad plan.',
    'Compare destinations, universities, and programs and lock a realistic target shortlist.',
    'Gather, verify, and organise transcripts, IDs, and other documents needed for applications.',
    'Draft and polish the statement of purpose / essays used in university applications.',
    'Review the full application pack for completeness, consistency, and submission readiness.',
    'Guide visa forms, supporting evidence, and filing steps for the chosen destination.',
    'Advise on IELTS / TOEFL / GRE / GMAT options, timelines, and target score bands.',
    'Coach the student for university or visa interviews with practice questions and feedback.',
    ...Object.values(FEE_SERVICE_PROCESS_DESCRIPTIONS),
  ].map(value => value.trim().toLowerCase())
);

export function defaultFeeServiceDescription(masterProcessKey?: string | null): string {
  const key = (masterProcessKey || '').trim();
  if (key && key in FEE_SERVICE_PROCESS_DESCRIPTIONS) {
    return FEE_SERVICE_PROCESS_DESCRIPTIONS[key as FlowxMasterProcessKey];
  }
  return 'Billable counselling service tailored to the student’s journey and goals.';
}

/** Canonical fee-service keys → Master Workflow process. */
export const FEE_SERVICE_TO_MASTER_PROCESS: Record<string, FlowxMasterProcessKey> = {
  'general counselling': 'counselling',
  'scholarship guidance': 'counselling',
  'digital presence and profile boosting': 'counselling',
  'university shortlisting': 'college_finding',
  documentation: 'document_submission',
  'sop drafting': 'document_submission',
  'statement of purpose / essay writing': 'document_submission',
  'test prep guidance': 'tests',
  'application review': 'admission_processing',
  'application filing': 'admission_processing',
  'application support': 'admission_processing',
  'offer acceptance': 'admission_processing',
  'enrollment support': 'admission_processing',
  'visa application help': 'visa_processing',
  'visa filing': 'visa_processing',
  'interview prep': 'visa_processing',
  'visa mock interview': 'visa_processing',
};

/**
 * Within-process service order (study-abroad delivery sequence).
 * Unknown / custom services sort after these, alphabetically.
 */
export const FEE_SERVICE_JOURNEY_ORDER: string[] = [
  'general counselling',
  'university shortlisting',
  'documentation',
  'sop drafting',
  'application review',
  'visa application help',
  'test prep guidance',
  'interview prep',
  'scholarship guidance',
  'digital presence and profile boosting',
  'application filing',
  'application support',
  'offer acceptance',
  'enrollment support',
  'visa filing',
  'visa mock interview',
];

export type FeeMasterProcessContext = {
  /** Live Master Workflow process labels keyed by stage_key. */
  labels?: Partial<Record<string, string>>;
  /** Normalized Master sub-process title → stage_key. */
  titleToStage?: Map<string, string>;
};

/** Map free-text names onto the nearest known fee-service slot when possible. */
export function feeServiceJourneyPlacementKey(name: string): string {
  const key = canonicalFeeServiceNameKey(name);
  if (FEE_SERVICE_JOURNEY_ORDER.includes(key)) return key;
  if (/\b(scholarship|funding|financial aid)\b/.test(key)) return 'scholarship guidance';
  if (/\b(test prep|ielts|toefl|gre|gmat)\b/.test(key)) return 'test prep guidance';
  if (/\bshortlist/.test(key)) return 'university shortlisting';
  if (/\b(digital presence|profile boost)/.test(key)) return 'digital presence and profile boosting';
  if (/\bdocument/.test(key)) return 'documentation';
  if (/\b(sop|essay|statement of purpose|personal history|personal statement)\b/.test(key)) {
    return 'sop drafting';
  }
  if (/\bapplication\b/.test(key) && /\breview\b/.test(key)) return 'application review';
  if (/\b(application filing|file application|application support)\b/.test(key)) {
    return 'application filing';
  }
  if (/\benrol/.test(key) || /\benroll/.test(key)) return 'enrollment support';
  if (/\boffer\b/.test(key)) return 'offer acceptance';
  if (/\bvisa\b/.test(key) && /\b(mock|interview)\b/.test(key)) return 'visa mock interview';
  if (/\b(interview prep|mock interview)\b/.test(key)) return 'interview prep';
  if (/\bvisa\b/.test(key)) return 'visa application help';
  if (/\bcounsel/.test(key)) return 'general counselling';
  return key;
}

/** Build a readable description from a custom service name when no catalog copy exists. */
export function composeFeeServiceDescriptionFromName(
  name: string,
  masterProcessKey?: string | null
): string {
  const label = name.trim().replace(/\s+/g, ' ');
  const key = normalizeFeeServiceNameKey(label);
  if (!key || key === 'new service') {
    return defaultFeeServiceDescription(masterProcessKey);
  }

  if (/\bjob\b/.test(key) && /\b(application|apply|apps?)\b/.test(key)) {
    return 'Prepare CVs, cover letters, and job applications for internships or post-study work roles.';
  }
  if (/\b(resume|cv)\b/.test(key)) {
    return `Draft and polish a CV / resume for ${label}, tailored to the student’s target roles.`;
  }
  if (/\bcover letter\b/.test(key)) {
    return 'Write targeted cover letters that match each role or internship application.';
  }
  if (/\b(career|placement|internship)\b/.test(key)) {
    return `Guide career / placement steps for ${label}, aligned with the study-abroad plan.`;
  }
  if (/\b(accommodation|housing|hostel)\b/.test(key)) {
    return 'Help shortlist and secure student housing or temporary stay options before arrival.';
  }
  if (/\b(airport|pickup|transfer)\b/.test(key)) {
    return 'Arrange arrival pickup and the first transfer from airport to housing or campus.';
  }
  if (/\b(pre-?departure|briefing|orientation)\b/.test(key)) {
    return 'Brief the student on travel, packing, finances, and first-week logistics before departure.';
  }
  if (/\b(scholarship|funding|financial aid)\b/.test(key)) {
    return 'Identify funding options and help the student prioritise realistic scholarship applications.';
  }
  if (/\b(mock interview|interview)\b/.test(key)) {
    return `Coach interview performance for ${label} with practice questions and feedback.`;
  }
  if (/\bvisa\b/.test(key)) {
    return `Support visa paperwork and filing steps related to ${label}.`;
  }
  if (/\b(sop|essay|statement of purpose|personal statement)\b/.test(key)) {
    return `Draft and refine written statements for ${label} used in university applications.`;
  }
  if (/\b(document|documentation|transcript)\b/.test(key)) {
    return `Collect and organise the documents required for ${label}.`;
  }
  if (/\b(shortlist|university|college|program)\b/.test(key)) {
    return `Research and refine university / program options under ${label}.`;
  }
  if (/\b(test|ielts|toefl|gre|gmat|exam)\b/.test(key)) {
    return `Plan exam strategy, timeline, and score targets for ${label}.`;
  }
  if (/\b(counsel|guidance|help|support|coaching)\b/.test(key)) {
    return `Provide focused ${label.toLowerCase()} for the student’s goals, timeline, and next steps.`;
  }

  const processKey = (masterProcessKey || '').trim();
  if (processKey && processKey !== FEE_SERVICE_OTHER_PROCESS_KEY) {
    const processFallback = defaultFeeServiceDescription(processKey);
    return `${processFallback.replace(/\.$/, '')} — scoped as ${label}.`.slice(0, 240);
  }
  return `Deliver ${label} as a billable service tailored to the student’s goals and timeline.`.slice(
    0,
    240
  );
}

/** Prefer unique per-service copy; refresh stale or empty blurbs for every row. */
export function resolveFeeServiceDescription(
  name: string,
  masterProcessKey?: string | null,
  currentDescription?: string | null
): string {
  const named =
    FEE_SERVICE_NAME_DESCRIPTIONS[canonicalFeeServiceNameKey(name)] ||
    FEE_SERVICE_NAME_DESCRIPTIONS[feeServiceJourneyPlacementKey(name)];
  // Known catalog services always get the curated copy.
  if (named) {
    return named.slice(0, 240);
  }

  const composed = composeFeeServiceDescriptionFromName(name, masterProcessKey);
  const current = String(currentDescription ?? '').trim().slice(0, 240);
  const currentKey = current.toLowerCase();
  const isStale =
    !current ||
    STALE_FEE_SERVICE_DESCRIPTIONS.has(currentKey) ||
    currentKey === defaultFeeServiceDescription(masterProcessKey).toLowerCase();

  if (isStale) {
    return composed.slice(0, 240);
  }
  return current;
}

function inferMasterProcessFromKeywords(name: string): FlowxMasterProcessKey | null {
  const key = normalizeFeeServiceNameKey(name);
  if (/\b(test prep|ielts|toefl|gre|gmat|exam|score)\b/.test(key)) return 'tests';
  if (/\b(visa|ds-160|sevis|ihs|i-20|mock interview)\b/.test(key)) return 'visa_processing';
  if (/\b(pre-?departure|flight|travel|housing|accommodation)\b/.test(key)) {
    return 'predeparture_travel';
  }
  if (/\b(landing|arrival|airport pickup|campus registration)\b/.test(key)) return 'landing';
  // "Job application" is not university admission processing.
  if (/\b(admission|offer|enrol|enroll)\b/.test(key)) return 'admission_processing';
  if (/\bapplication\b/.test(key) && !/\bjob\b/.test(key)) return 'admission_processing';
  if (/\b(document|sop|essay|transcript|recommendation|lor|personal history)\b/.test(key)) {
    return 'document_submission';
  }
  if (/\b(college|university|shortlist|program fit|enquiry)\b/.test(key)) return 'college_finding';
  if (/\b(counsel|intake|profile|goal|scholarship|destination)\b/.test(key)) return 'counselling';
  return null;
}

function matchMasterProcessFromTitles(
  name: string,
  titleToStage?: Map<string, string>
): FlowxMasterProcessKey | null {
  if (!titleToStage?.size) return null;
  const key = normalizeFeeServiceNameKey(name);
  const direct = titleToStage.get(key);
  if (direct && FLOWX_MASTER_PROCESS_ORDER.includes(direct as FlowxMasterProcessKey)) {
    return direct as FlowxMasterProcessKey;
  }
  let best: { stage: FlowxMasterProcessKey; score: number } | null = null;
  for (const [title, stage] of titleToStage.entries()) {
    if (!FLOWX_MASTER_PROCESS_ORDER.includes(stage as FlowxMasterProcessKey)) continue;
    if (key.includes(title) || title.includes(key)) {
      const score = Math.min(key.length, title.length) / Math.max(key.length, title.length);
      if (!best || score > best.score) {
        best = { stage: stage as FlowxMasterProcessKey, score };
      }
    }
  }
  return best && best.score >= 0.45 ? best.stage : null;
}

/** Resolve which Master Workflow process a fee service belongs to. */
export function feeServiceMasterProcessKey(
  name: string,
  ctx?: FeeMasterProcessContext,
  explicitKey?: string | null
): FlowxMasterProcessKey | null {
  const hasExplicit = explicitKey !== undefined && explicitKey !== null;
  const assigned = String(explicitKey ?? '').trim();

  // User placed the row in Other services — never re-home via name heuristics.
  if (assigned === FEE_SERVICE_OTHER_PROCESS_KEY) {
    return null;
  }
  if (assigned && FLOWX_MASTER_PROCESS_ORDER.includes(assigned as FlowxMasterProcessKey)) {
    return assigned as FlowxMasterProcessKey;
  }

  // Known catalog / alias names keep their process even without an explicit key.
  const placement = feeServiceJourneyPlacementKey(name);
  const mapped = FEE_SERVICE_TO_MASTER_PROCESS[placement];
  if (mapped) return mapped;

  const fromTitle = matchMasterProcessFromTitles(name, ctx?.titleToStage);
  if (fromTitle) return fromTitle;

  // Empty explicit key means Other (e.g. Add service under Other services).
  if (hasExplicit && !assigned) {
    return null;
  }

  return inferMasterProcessFromKeywords(name);
}

export function formatMasterProcessHeading(
  processKey: FlowxMasterProcessKey | null,
  ctx?: FeeMasterProcessContext
): string {
  if (!processKey) return 'Other services';
  const idx = FLOWX_MASTER_PROCESS_ORDER.indexOf(processKey);
  const label =
    ctx?.labels?.[processKey]?.trim() ||
    FLOWX_MASTER_PROCESS_LABELS[processKey] ||
    processKey;
  return idx >= 0 ? `${idx + 1} ${label}` : label;
}

export function feeServiceMasterProcessLabel(
  name: string,
  ctx?: FeeMasterProcessContext,
  explicitKey?: string | null
): string {
  return formatMasterProcessHeading(feeServiceMasterProcessKey(name, ctx, explicitKey), ctx);
}

/** @deprecated Use feeServiceMasterProcessLabel — kept for call-site compatibility. */
export function feeServiceJourneyStage(
  name: string,
  ctx?: FeeMasterProcessContext,
  explicitKey?: string | null
): string {
  return feeServiceMasterProcessLabel(name, ctx, explicitKey);
}

export function feeServiceJourneyRank(
  name: string,
  ctx?: FeeMasterProcessContext,
  explicitKey?: string | null
): number {
  const processKey = feeServiceMasterProcessKey(name, ctx, explicitKey);
  const processIdx = processKey ? FLOWX_MASTER_PROCESS_ORDER.indexOf(processKey) : -1;
  const processRank = processIdx >= 0 ? (processIdx + 1) * 100 : 900;
  const placement = feeServiceJourneyPlacementKey(name);
  const within = FEE_SERVICE_JOURNEY_ORDER.indexOf(placement);
  const withinRank = within >= 0 ? within : 80;
  return processRank + withinRank;
}

/** Sort services by Master Workflow process order and rewrite dense sortOrder (10, 20, …). */
export function applyFeeServiceJourneyOrder(
  services: FeeService[],
  ctx?: FeeMasterProcessContext
): FeeService[] {
  return [...services]
    .map(service => ({
      ...service,
      sortOrder: feeServiceJourneyRank(
        service.name || '',
        ctx,
        service.masterProcessKey || null
      ),
    }))
    .sort(
      (a, b) =>
        a.sortOrder - b.sortOrder ||
        (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' })
    )
    .map((service, index) => ({
      ...service,
      sortOrder: (index + 1) * 10,
    }));
}

/** Build title→stage index from a Master Workflow / country detail payload. */
export function buildFeeMasterProcessTitleIndex(stages: Array<{
  stage_key: string;
  bricks?: Array<{ title?: string | null; children?: Array<{ title?: string | null }> | null }> | null;
  tracks?: Array<{
    task_templates?: Array<{ title?: string | null; children?: Array<{ title?: string | null }> | null }> | null;
  }> | null;
}>): Map<string, string> {
  const map = new Map<string, string>();
  const addTitle = (title: string | null | undefined, stageKey: string) => {
    const key = normalizeFeeServiceNameKey(title || '');
    if (!key) return;
    if (!map.has(key)) map.set(key, stageKey);
  };
  const walk = (
    bricks: Array<{ title?: string | null; children?: Array<{ title?: string | null }> | null }> | null | undefined,
    stageKey: string
  ) => {
    for (const brick of bricks || []) {
      addTitle(brick.title, stageKey);
      walk(brick.children || [], stageKey);
    }
  };
  for (const stage of stages) {
    walk(stage.bricks, stage.stage_key);
    for (const track of stage.tracks || []) {
      walk(track.task_templates, stage.stage_key);
    }
  }
  return map;
}

export type FeeServiceDuplicateGroup = {
  key: string;
  preferredName: string;
  services: FeeService[];
};

/** Groups services that share a canonical name (exact or alias). */
export function findFeeServiceDuplicateGroups(services: FeeService[]): FeeServiceDuplicateGroup[] {
  const groups = new Map<string, FeeService[]>();
  for (const service of services) {
    const key = canonicalFeeServiceNameKey(service.name || '');
    if (!key) continue;
    const list = groups.get(key) ?? [];
    list.push(service);
    groups.set(key, list);
  }
  return [...groups.entries()]
    .filter(([, list]) => list.length > 1)
    .map(([key, list]) => ({
      key,
      preferredName:
        list.find(item => normalizeFeeServiceNameKey(item.name) === key)?.name ||
        list.sort((a, b) => b.name.length - a.name.length)[0]?.name ||
        key,
      services: list,
    }))
    .sort((a, b) => a.preferredName.localeCompare(b.preferredName));
}

function nameTokenSet(name: string): Set<string> {
  return new Set(
    normalizeFeeServiceNameKey(name)
      .split(/[^a-z0-9]+/)
      .filter(token => token.length > 2 && !['and', 'the', 'for', 'with'].includes(token))
  );
}

function nameTokenOverlap(a: string, b: string): number {
  const left = nameTokenSet(a);
  const right = nameTokenSet(b);
  if (!left.size || !right.size) return 0;
  let overlap = 0;
  for (const token of left) {
    if (right.has(token)) overlap += 1;
  }
  return overlap / Math.min(left.size, right.size);
}

/** Near-duplicate pairs/groups that are not already covered by alias/exact canonical matching. */
export function findFeeServiceNearDuplicateGroups(services: FeeService[]): FeeServiceDuplicateGroup[] {
  const remaining = services.filter(
    service => Boolean(service?.id) && Boolean(service?.name?.trim())
  );
  const used = new Set<string>();
  const groups: FeeServiceDuplicateGroup[] = [];

  for (let i = 0; i < remaining.length; i += 1) {
    const anchor = remaining[i];
    if (used.has(anchor.id)) continue;
    const cluster = [anchor];
    for (let j = i + 1; j < remaining.length; j += 1) {
      const candidate = remaining[j];
      if (used.has(candidate.id)) continue;
      if (canonicalFeeServiceNameKey(anchor.name) === canonicalFeeServiceNameKey(candidate.name)) {
        continue;
      }
      if (nameTokenOverlap(anchor.name, candidate.name) >= 0.6) {
        cluster.push(candidate);
        used.add(candidate.id);
      }
    }
    if (cluster.length > 1) {
      used.add(anchor.id);
      groups.push({
        key: `near:${anchor.id}`,
        preferredName: cluster.sort((a, b) => b.name.length - a.name.length)[0].name,
        services: cluster,
      });
    }
  }

  return groups.sort((a, b) => a.preferredName.localeCompare(b.preferredName));
}

/** Mirrors backend COUNSELING_SESSION_PURPOSES / DEFAULT_SESSION_PURPOSES. */
export const DEFAULT_SESSION_PURPOSE_SEEDS: SessionPurposeSeed[] = [
  {
    label: 'General Counselling',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['general counselling'],
  },
  {
    label: 'Visa Application Help',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['visa application help'],
  },
  {
    label: 'Documentation',
    description: FEE_SERVICE_NAME_DESCRIPTIONS.documentation,
  },
  {
    label: 'University Shortlisting',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['university shortlisting'],
  },
  {
    label: 'Test Prep Guidance',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['test prep guidance'],
  },
  {
    label: 'Application Review',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['application review'],
  },
];

function preferredFeeServiceDisplayName(name: string): string {
  const key = normalizeFeeServiceNameKey(name);
  const canonical = FEE_SERVICE_NAME_ALIASES[key] || key;
  if (canonical === 'sop drafting') {
    return 'SOP Drafting';
  }
  if (canonical === 'digital presence and profile boosting') {
    return 'Digital Presence & Profile Boosting';
  }
  // Prefer the label that already matches the canonical key.
  if (key === canonical) return name.trim();
  return name.trim();
}

function feeServiceFromSessionPurpose(
  purpose: SessionPurposeSeed,
  existingIds: string[],
  sortOrder: number
): FeeService {
  const name = preferredFeeServiceDisplayName(purpose.label).slice(0, 80);
  const nameKey = canonicalFeeServiceNameKey(name);
  const preferredId = suggestServiceIdFromName(name, []);
  const id = existingIds.includes(preferredId)
    ? suggestServiceIdFromName(name, existingIds)
    : preferredId;

  return {
    id,
    name,
    description: (purpose.description || '').trim().slice(0, 240),
    basePriceInr:
      DEFAULT_SESSION_PURPOSE_LIST_PRICES[nameKey] ??
      DEFAULT_SESSION_PURPOSE_LIST_PRICES[normalizeFeeServiceNameKey(purpose.label)] ??
      0,
    active: true,
    sortOrder,
    masterProcessKey: FEE_SERVICE_TO_MASTER_PROCESS[nameKey] || '',
    ...EMPTY_FEE_AUDIT,
  };
}

function pickPreferredService(a: FeeService, b: FeeService): FeeService {
  const canon = canonicalFeeServiceNameKey(a.name || b.name);
  const aMatchesCanon = normalizeFeeServiceNameKey(a.name) === canon;
  const bMatchesCanon = normalizeFeeServiceNameKey(b.name) === canon;
  const preferredId = suggestServiceIdFromName(preferredFeeServiceDisplayName(a.name || b.name), []);
  const preferA = aMatchesCanon
    ? !bMatchesCanon || a.id === preferredId || (a.updatedAt || '') >= (b.updatedAt || '')
    : bMatchesCanon
      ? false
      : a.id === preferredId
        ? true
        : b.id === preferredId
          ? false
          : (a.updatedAt || '') >= (b.updatedAt || '');
  const keep = preferA ? a : b;
  const other = preferA ? b : a;
  return {
    ...keep,
    name: preferredFeeServiceDisplayName(
      aMatchesCanon ? a.name : bMatchesCanon ? b.name : keep.name
    ).slice(0, 80),
    basePriceInr: keep.basePriceInr || other.basePriceInr,
    description: keep.description || other.description,
    masterProcessKey:
      keep.masterProcessKey ||
      other.masterProcessKey ||
      FEE_SERVICE_TO_MASTER_PROCESS[canon] ||
      '',
    createdAt: keep.createdAt || other.createdAt,
    createdBy: keep.createdBy || other.createdBy,
    updatedAt: keep.updatedAt || other.updatedAt,
    updatedBy: keep.updatedBy || other.updatedBy,
    active: keep.active !== false && other.active !== false ? keep.active : keep.active || other.active,
  };
}

/**
 * Deduplicate services by canonical name (including aliases) and rebuild from Session purposes.
 * Preserves list prices / audit when a matching name already exists.
 * Example: "SOP Drafting" collapses into "Statement of Purpose / Essay Writing".
 */
export function regenerateFeeCatalogFromSessionPurposes(
  catalog: FeeCatalog,
  purposes: SessionPurposeSeed[]
): { catalog: FeeCatalog; changed: boolean; removedDuplicateCount: number } {
  const normalized = normalizeFeeCatalog(catalog);
  const seeds = (purposes.length ? purposes : DEFAULT_SESSION_PURPOSE_SEEDS)
    .map(purpose => ({
      label: purpose.label.trim(),
      description: (purpose.description || '').trim(),
    }))
    .filter(purpose => purpose.label && !isExcludedFromFeeCatalog(purpose.label));

  // Deduplicate purpose seeds by canonical/alias key.
  const uniqueSeeds: SessionPurposeSeed[] = [];
  const seedByCanonical = new Map<string, SessionPurposeSeed>();
  for (const seed of seeds) {
    const key = canonicalFeeServiceNameKey(seed.label);
    const prev = seedByCanonical.get(key);
    if (!prev) {
      seedByCanonical.set(key, {
        label: preferredFeeServiceDisplayName(seed.label),
        description: seed.description,
      });
      continue;
    }
    const preferNew = normalizeFeeServiceNameKey(seed.label) === key;
    seedByCanonical.set(key, {
      label: preferNew
        ? preferredFeeServiceDisplayName(seed.label)
        : preferredFeeServiceDisplayName(prev.label),
      description: (preferNew ? seed.description : prev.description) || seed.description || prev.description,
    });
  }
  uniqueSeeds.push(...seedByCanonical.values());

  const existingByCanonical = new Map<string, FeeService>();
  for (const service of normalized.services) {
    const key = canonicalFeeServiceNameKey(service.name);
    if (!key) continue;
    const prev = existingByCanonical.get(key);
    existingByCanonical.set(key, prev ? pickPreferredService(prev, service) : {
      ...service,
      name: preferredFeeServiceDisplayName(service.name),
    });
  }

  const idRemap = new Map<string, string>();
  const services: FeeService[] = [];
  const usedIds: string[] = [];

  uniqueSeeds.forEach((purpose, index) => {
    const key = canonicalFeeServiceNameKey(purpose.label);
    const existing = existingByCanonical.get(key);
    const displayName = preferredFeeServiceDisplayName(purpose.label);
    const preferredId = suggestServiceIdFromName(displayName, []);
    const id = usedIds.includes(preferredId)
      ? suggestServiceIdFromName(displayName, usedIds)
      : preferredId;
    usedIds.push(id);

    services.push({
      id,
      name: displayName.slice(0, 80),
      description: (purpose.description || existing?.description || '').trim().slice(0, 240),
      basePriceInr:
        existing?.basePriceInr ??
        DEFAULT_SESSION_PURPOSE_LIST_PRICES[key] ??
        0,
      active: existing?.active !== false,
      sortOrder: (index + 1) * 10,
      masterProcessKey:
        existing?.masterProcessKey ||
        FEE_SERVICE_TO_MASTER_PROCESS[key] ||
        '',
      createdAt: existing?.createdAt || '',
      updatedAt: existing?.updatedAt || '',
      createdBy: existing?.createdBy || '',
      updatedBy: existing?.updatedBy || '',
    });

    for (const old of normalized.services) {
      if (canonicalFeeServiceNameKey(old.name) === key) {
        idRemap.set(old.id, id);
      }
    }
    idRemap.set(id, id);
    existingByCanonical.delete(key);
  });

  // Keep non-purpose custom services (deduped by canonical name), after purpose rows.
  // Drop catalog-excluded names (e.g. Test Prep Guidance, University Shortlisting).
  let sortOrder = (services.length + 1) * 10;
  for (const existing of existingByCanonical.values()) {
    if (isExcludedFromFeeCatalog(existing.name)) continue;
    const displayName = preferredFeeServiceDisplayName(existing.name);
    const preferredId = suggestServiceIdFromName(displayName, []);
    const id = usedIds.includes(preferredId)
      ? suggestServiceIdFromName(displayName, usedIds)
      : preferredId;
    usedIds.push(id);
    for (const old of normalized.services) {
      if (canonicalFeeServiceNameKey(old.name) === canonicalFeeServiceNameKey(existing.name)) {
        idRemap.set(old.id, id);
      }
    }
    services.push({
      ...existing,
      id,
      name: displayName.slice(0, 80),
      sortOrder,
    });
    sortOrder += 10;
  }

  const orderedServices = applyFeeServiceJourneyOrder(services);
  const serviceIdSet = new Set(orderedServices.map(service => service.id));
  const bundles = normalized.bundles
    .map(bundle => ({
      ...bundle,
      serviceIds: [
        ...new Set(
          bundle.serviceIds
            .map(id => idRemap.get(id) || id)
            .filter(id => serviceIdSet.has(id))
        ),
      ],
    }))
    .filter(bundle => bundle.serviceIds.length > 0);

  const removedDuplicateCount = Math.max(0, normalized.services.length - orderedServices.length);
  const beforeIds = normalized.services.map(service => service.id).join('|');
  const afterIds = orderedServices.map(service => service.id).join('|');
  const beforeSort = normalized.services.map(service => service.sortOrder).join('|');
  const afterSort = orderedServices.map(service => service.sortOrder).join('|');
  const changed =
    removedDuplicateCount > 0 ||
    beforeIds !== afterIds ||
    beforeSort !== afterSort ||
    orderedServices.length !== normalized.services.length;

  return {
    catalog: {
      currency: FEE_CATALOG_CURRENCY,
      services: orderedServices,
      bundles: bundles.length
        ? bundles
        : [
            {
              id: 'essentials',
              name: 'Essentials Package',
              description:
                'Starter package covering counselling, shortlisting, and documentation at a bundled rate.',
              invoiceDescription: '',
              serviceIds: orderedServices
                .filter(service =>
                  ['general-counselling', 'university-shortlisting', 'documentation'].includes(
                    service.id
                  )
                )
                .map(service => service.id),
              packagePriceInr: 0,
              active: true,
              sortOrder: 10,
              ...EMPTY_FEE_AUDIT,
            },
            {
              id: 'end-to-end',
              name: 'End-to-End Package',
              description:
                'Full journey package covering all active catalog services from counselling through landing.',
              invoiceDescription: '',
              serviceIds: orderedServices.map(service => service.id),
              packagePriceInr: 0,
              active: true,
              sortOrder: 20,
              ...EMPTY_FEE_AUDIT,
            },
          ].filter(bundle => bundle.serviceIds.length > 0),
    },
    changed,
    removedDuplicateCount,
  };
}

/** Original Nexus Base Price Catalog seed (module creation defaults). */
export const DEFAULT_FEE_SERVICES: FeeService[] = applyFeeServiceJourneyOrder([
  {
    id: 'general-counselling',
    name: 'General Counselling',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['general counselling'],
    basePriceInr: 5000,
    active: true,
    sortOrder: 10,
    masterProcessKey: 'counselling',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'university-shortlisting',
    name: 'University Shortlisting',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['university shortlisting'],
    basePriceInr: 15000,
    active: true,
    sortOrder: 20,
    masterProcessKey: 'college_finding',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'documentation',
    name: 'Documentation',
    description: FEE_SERVICE_NAME_DESCRIPTIONS.documentation,
    basePriceInr: 12000,
    active: true,
    sortOrder: 30,
    masterProcessKey: 'document_submission',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'sop-drafting',
    name: 'SOP Drafting',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['sop drafting'],
    basePriceInr: 8000,
    active: true,
    sortOrder: 40,
    masterProcessKey: 'document_submission',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'application-review',
    name: 'Application Review',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['application review'],
    basePriceInr: 10000,
    active: true,
    sortOrder: 50,
    masterProcessKey: 'admission_processing',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'visa-application-help',
    name: 'Visa Application Help',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['visa application help'],
    basePriceInr: 15000,
    active: true,
    sortOrder: 60,
    masterProcessKey: 'visa_processing',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'test-prep-guidance',
    name: 'Test Prep Guidance',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['test prep guidance'],
    basePriceInr: 6000,
    active: true,
    sortOrder: 70,
    masterProcessKey: 'tests',
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'interview-prep',
    name: 'Interview Prep',
    description: FEE_SERVICE_NAME_DESCRIPTIONS['interview prep'],
    basePriceInr: 7000,
    active: true,
    sortOrder: 80,
    masterProcessKey: 'visa_processing',
    ...EMPTY_FEE_AUDIT,
  },
]);

export const DEFAULT_FEE_BUNDLES: FeeBundle[] = [
  {
    id: 'essentials',
    name: 'Essentials Package',
    description:
      'Starter package covering counselling, shortlisting, and documentation at a bundled rate.',
    invoiceDescription: '',
    serviceIds: ['general-counselling', 'university-shortlisting', 'documentation'],
    packagePriceInr: 0,
    active: true,
    sortOrder: 10,
    ...EMPTY_FEE_AUDIT,
  },
  {
    id: 'end-to-end',
    name: 'End-to-End Package',
    description:
      'Full journey package covering all active catalog services from counselling through landing.',
    invoiceDescription: '',
    serviceIds: DEFAULT_FEE_SERVICES.map(service => service.id),
    packagePriceInr: 0,
    active: true,
    sortOrder: 20,
    ...EMPTY_FEE_AUDIT,
  },
];

export const DEFAULT_FEE_CATALOG: FeeCatalog = {
  currency: FEE_CATALOG_CURRENCY,
  services: DEFAULT_FEE_SERVICES.map(service => ({ ...service })),
  bundles: DEFAULT_FEE_BUNDLES.map(bundle => ({
    ...bundle,
    serviceIds: [...bundle.serviceIds],
  })),
};

function slugifyLabel(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

export function createEmptyFeeService(
  existingIds: string[] = [],
  masterProcessKey: string = ''
): FeeService {
  const processKey =
    masterProcessKey &&
    FLOWX_MASTER_PROCESS_ORDER.includes(masterProcessKey as FlowxMasterProcessKey)
      ? masterProcessKey
      : FEE_SERVICE_OTHER_PROCESS_KEY;
  const id = suggestServiceIdFromName('New service', existingIds);
  return {
    id,
    name: '',
    description: '',
    basePriceInr: 0,
    active: true,
    sortOrder: (existingIds.length + 1) * 10,
    masterProcessKey: processKey,
    ...EMPTY_FEE_AUDIT,
  };
}

export function createEmptyFeeBundle(existingIds: string[] = []): FeeBundle {
  const id = suggestServiceIdFromName('New package', existingIds);
  return {
    id,
    name: '',
    description: '',
    invoiceDescription: '',
    serviceIds: [],
    packagePriceInr: 0,
    active: true,
    sortOrder: (existingIds.length + 1) * 10,
    ...EMPTY_FEE_AUDIT,
  };
}

export function suggestServiceIdFromName(name: string, existingIds: string[]): string {
  const base = slugifyLabel(name) || 'service';
  if (!existingIds.includes(base)) return base;
  let n = 2;
  while (existingIds.includes(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/** Force unique service ids (keeps first occurrence; remaps collisions). */
export function ensureUniqueFeeServiceIds(services: FeeService[]): {
  services: FeeService[];
  idRemap: Map<string, string>;
} {
  const used = new Set<string>();
  const idRemap = new Map<string, string>();
  const next = services.map((service, index) => {
    const name = (service.name || '').trim() || `service-${index + 1}`;
    const previousId = (service.id || '').trim();
    let id = previousId;
    if (!id || used.has(id)) {
      id = suggestServiceIdFromName(name, [...used]);
    }
    used.add(id);
    if (previousId) idRemap.set(previousId, id);
    idRemap.set(id, id);
    return { ...service, id };
  });
  return { services: next, idRemap };
}

/** Remap package serviceIds through an id remap and drop unknown ids. */
export function remapFeeBundleServiceIds(
  bundles: FeeBundle[],
  idRemap: Map<string, string>,
  validServiceIds: Set<string>
): FeeBundle[] {
  return bundles.map(bundle => ({
    ...bundle,
    serviceIds: [
      ...new Set(
        (bundle.serviceIds || [])
          .map(id => idRemap.get(id) || id)
          .filter(id => validServiceIds.has(id))
      ),
    ],
  }));
}

export function sumServiceListPrices(
  services: FeeService[],
  serviceIds: string[],
  options?: { requireActive?: boolean }
): number {
  const requireActive = options?.requireActive === true;
  const byId = new Map(services.map(service => [service.id, service]));
  return serviceIds.reduce((sum, id) => {
    const service = byId.get(id);
    if (!service) return sum;
    if (requireActive && !service.active) return sum;
    return sum + (Number.isFinite(service.basePriceInr) ? service.basePriceInr : 0);
  }, 0);
}

export function packageSavingsInr(
  services: FeeService[],
  bundle: Pick<FeeBundle, 'serviceIds' | 'packagePriceInr'>,
  options?: { requireActive?: boolean }
): number {
  const listTotal = sumServiceListPrices(services, bundle.serviceIds, options);
  return Math.max(0, listTotal - (Number.isFinite(bundle.packagePriceInr) ? bundle.packagePriceInr : 0));
}

export function withMissingDefaultFeeServices(catalog: FeeCatalog): {
  catalog: FeeCatalog;
  restoredIds: string[];
} {
  const normalized = normalizeFeeCatalog(catalog);
  const existing = new Set(normalized.services.map(service => service.id));
  const missing = DEFAULT_FEE_SERVICES.filter(service => !existing.has(service.id)).map(service => {
    const now = new Date().toISOString();
    return {
      ...service,
      createdAt: now,
      updatedAt: now,
      createdBy: 'Nexus',
      updatedBy: 'Nexus',
    };
  });
  if (!missing.length) {
    return { catalog: normalized, restoredIds: [] };
  }
  return {
    catalog: {
      ...normalized,
      services: [...normalized.services, ...missing].sort(
        (a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name)
      ),
    },
    restoredIds: missing.map(service => service.id),
  };
}

function readFeeAudit(row: Record<string, unknown>): FeeAuditFields {
  return {
    createdAt: String(row.createdAt ?? '').trim(),
    updatedAt: String(row.updatedAt ?? '').trim(),
    createdBy: String(row.createdBy ?? '').trim().slice(0, 120),
    updatedBy: String(row.updatedBy ?? '').trim().slice(0, 120),
  };
}

function serviceContentKey(service: FeeService): string {
  return [
    service.id,
    service.name,
    service.description,
    service.basePriceInr,
    service.active ? '1' : '0',
    service.sortOrder,
  ].join('\u0001');
}

function bundleContentKey(bundle: FeeBundle): string {
  return [
    bundle.id,
    bundle.name,
    bundle.description,
    bundle.invoiceDescription,
    bundle.serviceIds.join(','),
    bundle.packagePriceInr,
    bundle.active ? '1' : '0',
    bundle.sortOrder,
  ].join('\u0001');
}

/** Stamp created/updated audit fields when catalog rows are added or changed. */
export function applyFeeCatalogAudit(
  next: FeeCatalog,
  previous: FeeCatalog,
  actor: string,
  now = new Date().toISOString()
): FeeCatalog {
  const actorLabel = actor.trim() || 'Unknown user';
  const prevServices = new Map(previous.services.map(service => [service.id, service]));
  const prevBundles = new Map(previous.bundles.map(bundle => [bundle.id, bundle]));

  const services = next.services.map(service => {
    const prev = prevServices.get(service.id);
    if (!prev) {
      return {
        ...service,
        createdAt: service.createdAt || now,
        updatedAt: now,
        createdBy: service.createdBy || actorLabel,
        updatedBy: actorLabel,
      };
    }
    if (!prev.createdAt) {
      return {
        ...service,
        createdAt: now,
        createdBy: actorLabel,
        updatedAt: now,
        updatedBy: actorLabel,
      };
    }
    if (serviceContentKey(service) !== serviceContentKey(prev)) {
      return {
        ...service,
        createdAt: prev.createdAt || now,
        createdBy: prev.createdBy || actorLabel,
        updatedAt: now,
        updatedBy: actorLabel,
      };
    }
    return {
      ...service,
      createdAt: prev.createdAt,
      updatedAt: prev.updatedAt,
      createdBy: prev.createdBy,
      updatedBy: prev.updatedBy,
    };
  });

  const bundles = next.bundles.map(bundle => {
    const prev = prevBundles.get(bundle.id);
    if (!prev) {
      return {
        ...bundle,
        createdAt: bundle.createdAt || now,
        updatedAt: now,
        createdBy: bundle.createdBy || actorLabel,
        updatedBy: actorLabel,
      };
    }
    if (!prev.createdAt) {
      return {
        ...bundle,
        createdAt: now,
        createdBy: actorLabel,
        updatedAt: now,
        updatedBy: actorLabel,
      };
    }
    if (bundleContentKey(bundle) !== bundleContentKey(prev)) {
      return {
        ...bundle,
        createdAt: prev.createdAt || now,
        createdBy: prev.createdBy || actorLabel,
        updatedAt: now,
        updatedBy: actorLabel,
      };
    }
    return {
      ...bundle,
      createdAt: prev.createdAt,
      updatedAt: prev.updatedAt,
      createdBy: prev.createdBy,
      updatedBy: prev.updatedBy,
    };
  });

  return { ...next, services, bundles };
}

export function formatFeeAuditDate(iso: string): string {
  const value = (iso || '').trim();
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
}

export function formatFeeAuditUser(value: string): string {
  const label = (value || '').trim();
  return label || '—';
}

export function normalizeFeeCatalog(raw: unknown): FeeCatalog {
  if (!raw || typeof raw !== 'object') {
    return {
      currency: FEE_CATALOG_CURRENCY,
      services: DEFAULT_FEE_SERVICES.map(service => ({ ...service })),
      bundles: DEFAULT_FEE_BUNDLES.map(bundle => ({
        ...bundle,
        serviceIds: [...bundle.serviceIds],
      })),
    };
  }

  const record = raw as Record<string, unknown>;
  const servicesRaw = Array.isArray(record.services) ? record.services : [];
  const bundlesRaw = Array.isArray(record.bundles) ? record.bundles : [];

  const services: FeeService[] = [];
  const seenServiceIds = new Set<string>();
  for (const [index, item] of servicesRaw.entries()) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const name = String(row.name ?? '').trim();
    if (!name || isExcludedFromFeeCatalog(name)) continue;
    let id = slugifyLabel(String(row.id ?? '')) || suggestServiceIdFromName(name, [...seenServiceIds]);
    if (seenServiceIds.has(id)) {
      id = suggestServiceIdFromName(name, [...seenServiceIds]);
    }
    seenServiceIds.add(id);
    const price = Number(row.basePriceInr);
    const rawProcess = String(row.masterProcessKey ?? '').trim();
    const mappedProcess = FEE_SERVICE_TO_MASTER_PROCESS[canonicalFeeServiceNameKey(name)] || '';
    const masterProcessKey = FLOWX_MASTER_PROCESS_ORDER.includes(
      rawProcess as FlowxMasterProcessKey
    )
      ? rawProcess
      : rawProcess === FEE_SERVICE_OTHER_PROCESS_KEY
        ? FEE_SERVICE_OTHER_PROCESS_KEY
        : mappedProcess || FEE_SERVICE_OTHER_PROCESS_KEY;
    const description = resolveFeeServiceDescription(
      name,
      masterProcessKey,
      String(row.description ?? '')
    );
    services.push({
      id,
      name: name.slice(0, 80),
      description,
      basePriceInr: Number.isFinite(price) ? Math.min(10_000_000, Math.max(0, price)) : 0,
      active: row.active !== false,
      sortOrder:
        Number.isFinite(Number(row.sortOrder)) && Number(row.sortOrder) >= 0
          ? Math.min(999, Math.floor(Number(row.sortOrder)))
          : (index + 1) * 10,
      masterProcessKey,
      ...readFeeAudit(row),
    });
  }

  // Collapse same-name / alias duplicates (e.g. Digital Presence listed twice with different ids).
  const idRemap = new Map<string, string>();
  const byCanonical = new Map<string, FeeService>();
  for (const service of services) {
    const key = canonicalFeeServiceNameKey(service.name);
    if (!key) continue;
    const prev = byCanonical.get(key);
    if (!prev) {
      const displayName = preferredFeeServiceDisplayName(service.name);
      const kept = { ...service, name: displayName.slice(0, 80) };
      byCanonical.set(key, kept);
      idRemap.set(service.id, kept.id);
      continue;
    }
    const keep = {
      ...pickPreferredService(prev, service),
      name: preferredFeeServiceDisplayName(prev.name || service.name).slice(0, 80),
    };
    byCanonical.set(key, keep);
    idRemap.set(prev.id, keep.id);
    idRemap.set(service.id, keep.id);
    for (const [from, to] of [...idRemap.entries()]) {
      if (to === prev.id || to === service.id) idRemap.set(from, keep.id);
    }
  }
  const dedupedServices = [...byCanonical.values()];

  const serviceIdSet = new Set(dedupedServices.map(service => service.id));
  const bundles: FeeBundle[] = [];
  const seenBundleIds = new Set<string>();
  for (const [index, item] of bundlesRaw.entries()) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const name = String(row.name ?? '').trim();
    if (!name) continue;
    let id = slugifyLabel(String(row.id ?? '')) || suggestServiceIdFromName(name, [...seenBundleIds]);
    if (seenBundleIds.has(id)) {
      id = suggestServiceIdFromName(name, [...seenBundleIds]);
    }
    seenBundleIds.add(id);
    const serviceIds = Array.isArray(row.serviceIds)
      ? [
          ...new Set(
            row.serviceIds
              .map(value => {
                const rawId = String(value);
                return idRemap.get(rawId) || rawId;
              })
              .filter(value => serviceIdSet.has(value))
          ),
        ]
      : [];
    if (!serviceIds.length) continue;
    const price = Number(row.packagePriceInr);
    bundles.push({
      id,
      name: name.slice(0, 80),
      description: String(row.description ?? '').trim().slice(0, 240),
      invoiceDescription: String(
        (row as { invoiceDescription?: unknown }).invoiceDescription ?? ''
      )
        .trim()
        .slice(0, 75),
      serviceIds,
      packagePriceInr: Number.isFinite(price) ? Math.min(10_000_000, Math.max(0, price)) : 0,
      active: row.active !== false,
      sortOrder:
        Number.isFinite(Number(row.sortOrder)) && Number(row.sortOrder) >= 0
          ? Math.min(999, Math.floor(Number(row.sortOrder)))
          : (index + 1) * 10,
      ...readFeeAudit(row),
    });
  }

  if (!dedupedServices.length) {
    return {
      currency: FEE_CATALOG_CURRENCY,
      services: DEFAULT_FEE_SERVICES.map(service => ({ ...service })),
      bundles: DEFAULT_FEE_BUNDLES.map(bundle => ({
        ...bundle,
        serviceIds: [...bundle.serviceIds],
      })),
    };
  }

  return {
    currency: FEE_CATALOG_CURRENCY,
    services: applyFeeServiceJourneyOrder(dedupedServices),
    bundles: bundles.sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name)),
  };
}
