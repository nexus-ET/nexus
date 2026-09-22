/**
 * ScanX D11 message catalog + status badge helpers (CRM counsellor UI).
 * Keep copy aligned with backend app/constants/scanx.py MESSAGE_CATALOG.
 */

export const SCANX_MESSAGE_CATALOG = {
  M1: 'Select a student before uploading a document.',
  M2: 'Document type could not be auto-detected. Use Re-process after OCR, or review manually.',
  M3: 'This file type isn’t supported. Please upload a PDF, DOCX, PNG, JPEG, or TIFF.',
  M4: 'This file is too large. Maximum size is {X}.',
  M5: 'This document has too many pages. Maximum is {N} pages for PDF.',
  M6: 'This PDF is password-protected. Remove the password and upload again.',
  M7: 'We couldn’t read this file. It may be damaged — try re-exporting or a different copy.',
  M8: 'Image quality looks low (under 150 DPI). OCR may be less accurate — consider a clearer scan.',
  M9: 'You already have the maximum number of uploads in progress. Wait for one to finish.',
  M10: 'Upload didn’t complete. Check your connection and try again.',
  M11: 'This file couldn’t be accepted for security reasons. Contact your admin if you believe this is a mistake.',
  M12: 'Review needed — open the document to check extracted details and confirm.',
  /** Soft notice when live limits could not be fetched — defaults still apply. */
  M13: 'Using default upload limits. Server settings were unavailable — you can still upload.',
  M14: 'No extractable text was found (scanned or empty PDF/DOCX). Open the file and review manually.',
  M15: 'OCR found no readable text (or OCR timed out/failed). Use Re-process, or open the file and review manually.',
  M16: 'Processing failed after the file was accepted. Use Re-process — the file itself does not look damaged.',
  M17: 'A ScanX job for “{NAME}” is already in progress for this student. Wait until it finishes, fails, or is cancelled before uploading that filename again.',
} as const;

export type ScanxMessageId = keyof typeof SCANX_MESSAGE_CATALOG;

export type ScanxStatus =
  | 'uploading'
  | 'parsing'
  | 'action_required'
  | 'verified'
  | 'red_flag';

export const SCANX_STATUS_LABELS: Record<ScanxStatus, string> = {
  uploading: 'Uploading',
  parsing: 'Parsing',
  action_required: 'Review Scan',
  verified: 'Verified',
  red_flag: 'Red Flags',
};

/** Defaults matching backend Settings when env is unset (optimistic UI / offline fallback). */
export const SCANX_DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
export const SCANX_DEFAULT_MAX_PAGES = 10;
export const SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP = 10;

export const SCANX_ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/tiff',
  'image/tif',
] as const;

/** Browsers often report DOCX as zip/octet-stream — allow when extension is allowed. */
export const SCANX_GENERIC_UPLOAD_MIME_TYPES = [
  'application/octet-stream',
  'application/zip',
  'application/x-zip-compressed',
  'application/x-zip',
  'multipart/x-zip',
] as const;

export const SCANX_ALLOWED_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.png',
  '.jpg',
  '.jpeg',
  '.tif',
  '.tiff',
] as const;

/** Client pre-check: extension wins; generic MIME is OK for allowed extensions (esp. DOCX). */
export function isScanxFileTypeAllowed(file: { name: string; type?: string | null }): boolean {
  const nameLower = (file.name || '').toLowerCase();
  const ext = nameLower.includes('.') ? nameLower.slice(nameLower.lastIndexOf('.')) : '';
  const mime = (file.type || '').toLowerCase().split(';')[0].trim();
  const extAllowed = (SCANX_ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
  if (ext && !extAllowed) return false;
  if (!mime) return extAllowed || !ext;
  if ((SCANX_ALLOWED_MIME_TYPES as readonly string[]).includes(mime)) return true;
  if ((SCANX_GENERIC_UPLOAD_MIME_TYPES as readonly string[]).includes(mime)) {
    return extAllowed;
  }
  // Unknown MIME: still allow when the extension is an allowed ScanX type.
  return extAllowed;
}

export type ScanxDocumentTypeOption = {
  id: string;
  label: string;
  subfolder: string;
};

/** Static document types (aligned with backend DOCUMENT_TYPE_TO_SUBFOLDER). */
export const SCANX_DOCUMENT_TYPES: ScanxDocumentTypeOption[] = [
  { id: 'TR_TRANSCRIPT', label: 'Academic transcript', subfolder: 'ACADEMICS' },
  { id: 'DIPLOMA', label: 'Diploma / degree certificate', subfolder: 'ACADEMICS' },
  { id: 'GRADE_SHEET', label: 'Grade sheet', subfolder: 'ACADEMICS' },
  { id: 'ACADEMIC_CERTIFICATE', label: 'Academic certificate', subfolder: 'ACADEMICS' },
  { id: 'APPLICATION_FORM', label: 'Application form', subfolder: 'APPLICATIONS' },
  { id: 'OFFER_LETTER', label: 'Offer letter', subfolder: 'APPLICATIONS' },
  { id: 'SOP', label: 'Statement of purpose', subfolder: 'APPLICATIONS' },
  { id: 'LOR', label: 'Letter of recommendation', subfolder: 'APPLICATIONS' },
  { id: 'PORTFOLIO', label: 'Portfolio', subfolder: 'DIGITAL-PRESENCE' },
  { id: 'SOCIAL_PROFILE', label: 'Social / digital profile', subfolder: 'DIGITAL-PRESENCE' },
  { id: 'EXTRACURRICULAR', label: 'Extracurricular', subfolder: 'NON-ACADEMICS' },
  { id: 'VOLUNTEERING', label: 'Volunteering', subfolder: 'NON-ACADEMICS' },
  { id: 'AWARD', label: 'Award / recognition', subfolder: 'NON-ACADEMICS' },
  { id: 'CV_RESUME', label: 'CV / resume', subfolder: 'PROFESSIONAL-EXPERIENCE' },
  { id: 'EMPLOYMENT_LETTER', label: 'Employment letter', subfolder: 'PROFESSIONAL-EXPERIENCE' },
  { id: 'INTERNSHIP', label: 'Internship letter', subfolder: 'PROFESSIONAL-EXPERIENCE' },
  { id: 'PASSPORT', label: 'Passport', subfolder: 'PROFILE' },
  { id: 'PHOTO', label: 'Photo', subfolder: 'PROFILE' },
  { id: 'PERSONAL_PARTICULARS', label: 'Personal particulars', subfolder: 'PROFILE' },
  { id: 'PROJECT_REPORT', label: 'Project report', subfolder: 'PROJECTS-AND-RESEARCH' },
  { id: 'RESEARCH_PAPER', label: 'Research paper', subfolder: 'PROJECTS-AND-RESEARCH' },
  { id: 'PUBLICATION', label: 'Publication', subfolder: 'PROJECTS-AND-RESEARCH' },
  { id: 'IELTS', label: 'IELTS score', subfolder: 'TEST-SCORES' },
  { id: 'TOEFL', label: 'TOEFL score', subfolder: 'TEST-SCORES' },
  { id: 'GRE', label: 'GRE score', subfolder: 'TEST-SCORES' },
  { id: 'GMAT', label: 'GMAT score', subfolder: 'TEST-SCORES' },
  { id: 'OTHER_TEST_SCORE', label: 'Other test score', subfolder: 'TEST-SCORES' },
];

export function formatHumanFileSize(bytes: number): string {
  const n = Math.max(0, Math.floor(bytes));
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${Math.round(n / (1024 * 1024))} MB`;
}

/** D11 pre-upload rules. Pass live limits when known; otherwise show pending placeholders. */
export function buildScanxPreuploadRules(limits?: {
  maxFileSizeLabel?: string | null;
  maxPages?: number | null;
  concurrentCap?: number | null;
  limitsPending?: boolean;
}): string[] {
  return buildScanxPreuploadRuleGroups(limits).flatMap(g => g.items);
}

export type ScanxRuleGroup = {
  id: string;
  title: string;
  items: string[];
};

/** Formats & limits copy for the ScanX Upload Instructions hover popup. */
export function buildScanxPreuploadRuleGroups(limits?: {
  maxFileSizeLabel?: string | null;
  maxPages?: number | null;
  concurrentCap?: number | null;
  limitsPending?: boolean;
}): ScanxRuleGroup[] {
  const sizeLabel =
    limits?.maxFileSizeLabel?.trim() ||
    (limits?.limitsPending
      ? 'limit from server…'
      : formatHumanFileSize(SCANX_DEFAULT_MAX_FILE_SIZE_BYTES));
  const pages =
    limits?.maxPages != null
      ? String(limits.maxPages)
      : limits?.limitsPending
        ? 'limit from server…'
        : String(SCANX_DEFAULT_MAX_PAGES);
  const concurrent =
    limits?.concurrentCap != null
      ? String(limits.concurrentCap)
      : String(SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP);

  return [
    {
      id: 'formats',
      title: 'Formats & limits',
      items: [
        'Supported formats: PDF, DOCX, PNG, JPEG, TIFF.',
        `Max file size: ${sizeLabel}.`,
        `Max page count: ${pages} pages for PDF; DOCX limited by file size.`,
        `Up to ${concurrent} uploads can be in progress at once for your account.`,
      ],
    },
  ];
}

/**
 * Normalize API status codes / labels so UI matches Uploading|Parsing.
 * Accepts: parsing, PARSING, Parsing, "Parsing document…", etc.
 */
export function normalizeScanxStatus(status: string | null | undefined): string {
  const raw = (status || '').trim();
  if (!raw) return '';
  const lower = raw.toLowerCase().replace(/[\s-]+/g, '_');
  if (lower === 'uploading' || lower.startsWith('upload')) return 'uploading';
  if (lower === 'parsing' || lower.startsWith('pars')) return 'parsing';
  if (lower === 'action_required' || lower === 'actionrequired' || lower.includes('action_required')) {
    return 'action_required';
  }
  if (lower.includes('action') && lower.includes('required')) return 'action_required';
  if (lower === 'verified' || lower.startsWith('verif')) return 'verified';
  if (lower === 'red_flag' || lower === 'redflag' || lower.includes('red_flag')) {
    return 'red_flag';
  }
  if (lower.includes('red') && lower.includes('flag')) return 'red_flag';
  return lower;
}

/** True while ScanX is still accepting or parsing the file (show spinner). */
export function isScanxInProgress(status: string | null | undefined): boolean {
  const code = normalizeScanxStatus(status);
  return code === 'uploading' || code === 'parsing';
}

/** Tailwind token classes — icon + label required (not color alone). */
export function scanxStatusBadgeClass(status: string): string {
  switch (normalizeScanxStatus(status)) {
    case 'verified':
      return 'border-emerald-600/30 bg-emerald-500/10 text-emerald-800';
    case 'red_flag':
      return 'border-rose-600/30 bg-rose-500/10 text-rose-800';
    case 'action_required':
      return 'border-amber-700/30 bg-amber-500/10 text-amber-950';
    case 'parsing':
    case 'uploading':
      return 'border-sky-600/30 bg-sky-500/10 text-sky-900';
    default:
      return 'border-sky-600/30 bg-sky-500/10 text-sky-900';
  }
}

export function formatScanxMessage(
  id: ScanxMessageId,
  vars?: { X?: string; N?: number | string; NAME?: string }
): string {
  let text: string = SCANX_MESSAGE_CATALOG[id];
  if (vars?.X != null) text = text.replace('{X}', String(vars.X));
  if (vars?.N != null) text = text.replace('{N}', String(vars.N));
  if (vars?.NAME != null) text = text.replace('{NAME}', String(vars.NAME));
  return text;
}
