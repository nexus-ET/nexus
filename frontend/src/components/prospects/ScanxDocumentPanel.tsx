import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Eye,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import {
  apiFetch,
  apiFetchBlob,
  apiUpload,
  API_SCANX_BULK_DELETE_TIMEOUT_MS,
  API_SCANX_LIST_TIMEOUT_MS,
  API_SCANX_UPLOAD_TIMEOUT_MS,
  isScanxClientTimeoutError,
} from '../../utils/api';
import {
  buildScanxPreuploadRuleGroups,
  formatHumanFileSize,
  formatScanxMessage,
  isScanxFileTypeAllowed,
  isScanxInProgress,
  normalizeScanxStatus,
  SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP,
  SCANX_DEFAULT_MAX_FILE_SIZE_BYTES,
  SCANX_STATUS_LABELS,
  scanxStatusBadgeClass,
  type ScanxStatus,
} from '../../constants/scanxMessages';
import {
  consumeScanxConfigSoftWarning,
  getCachedScanxConfig,
  loadScanxConfigCached,
  wasScanxConfigFetchFailed,
  type ScanxConfig,
} from '../../utils/scanxConfigCache';
import { writeLastScannedLeadId } from '../../utils/documentReadinessPrefs';
import {
  coercePassportScalar,
  hydratePassportExtract,
  PASSPORT_DOCUMENT_KEYS,
  PASSPORT_FIELD_LABELS,
  PASSPORT_MRZ_KEYS,
  PASSPORT_PERSONAL_KEYS,
  type ScanxPassportExtract,
} from '../../utils/scanxPassport';
import ConfirmationModal from '../ConfirmationModal';

type ScanxProgressStep = {
  id: string;
  label: string;
  weight?: number;
  status: 'pending' | 'in_progress' | 'complete' | 'failed' | 'skipped' | string;
  status_label?: string | null;
  note?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

type ScanxDocument = {
  id: number;
  doc_uuid: string;
  lead_id: number;
  document_type_id: string;
  document_type_label?: string | null;
  original_filename: string;
  status: string;
  status_label: string;
  error_code?: string | null;
  error_message?: string | null;
  page_count?: number | null;
  byte_size?: number | null;
  document_group_id?: string | null;
  source_page_count?: number | null;
  created_at?: string | null;
  progress_percent?: number | null;
  progress_steps?: ScanxProgressStep[] | null;
  current_step_id?: string | null;
  current_step_label?: string | null;
  /** Client upload idempotency key — used to recover after a timed-out POST. */
  upload_id?: string | null;
};

type ScanxCategoryItem = {
  label: string;
  value: string;
};

type ScanxCategory = {
  id: string;
  label: string;
  items: ScanxCategoryItem[];
};

type ScanxSubject = {
  name: string;
  marks?: string;
  grade?: string;
  /** Per-subject theory score (not a separate subject list). */
  theory?: string;
  /** Per-subject practical score. */
  practical?: string;
  /** Alias for practical (LLM / marks schema). */
  prac?: string;
  /** Consolidated total (theory+practical or printed total). */
  total?: string;
  /** English number-words for the total (e.g. ONE SIX NINE). */
  words?: string;
  /** OCR confidence 0–1 when mapped from low-confidence blocks. */
  confidence?: number | string;
  is_low_confidence?: boolean | string;
};

/** Counsellor Dynamic Table row from extracted_fields.marks. */
type ScanxMarkRow = {
  subject: string;
  theory?: string;
  prac?: string;
  practical?: string;
  total?: string;
  words?: string;
  grade?: string;
  confidence?: number | string;
  is_low_confidence?: boolean | string;
};

type ScanxOcrBlock = {
  block_id: string;
  bounding_box?: number[][];
  /** Preferred display / embedding text (cleaned when available). */
  text?: string;
  raw_ocr_text?: string;
  cleaned_text?: string;
  confidence: number;
  is_low_confidence?: boolean;
  reading_order_index?: number;
  page_index?: number;
  row_index?: number | null;
  column_index?: number | null;
};

type ScanxReview = {
  document: ScanxDocument;
  extracted_text?: string | null;
  extracted_fields?: {
    version?: number;
    categories?: ScanxCategory[];
    subjects?: ScanxSubject[];
    /** Structured marksheet rows for Dynamic Table. */
    marks?: ScanxMarkRow[];
    /** Passport biographic + MRZ schema when document_type is PASSPORT. */
    passport?: ScanxPassportExtract | null;
    fields?: Array<{ label: string; value: string; category?: string }>;
  } | null;
  /** Preferred Subject|Marks rows from review API (heuristic + optional LLM). */
  subjects?: ScanxSubject[];
  categories?: ScanxCategory[] | null;
  chunk_count: number;
  embedded_count: number;
  viewer_url?: string | null;
  file_url?: string | null;
  enhanced_viewer_url?: string | null;
  enhanced_file_url?: string | null;
  /** Per-page OpenCV enhanced preview URLs (multi-page PDFs / passports). */
  enhanced_pages?: Array<{
    page_index: number;
    file_url: string;
    viewer_url?: string | null;
  }> | null;
  /** Ordered original pages for multi-image document groups. */
  source_pages?: Array<{
    page_index: number;
    original_filename?: string | null;
    content_type?: string | null;
    byte_size?: number | null;
    file_url?: string | null;
    viewer_url?: string | null;
  }> | null;
  review_prompt?: string | null;
  /** Parse metrics (includes ocr_engine_used / ocr_fallback_reason when OCR ran). */
  metrics?: Record<string, unknown> | null;
  /** Spatially ordered OCR blocks (box + confidence) for counsellor review. */
  ocr_blocks?: ScanxOcrBlock[] | null;
  requires_manual_review?: boolean | null;
  ocr_low_confidence_count?: number | null;
  ocr_block_count?: number | null;
  ocr_mean_confidence?: number | null;
  ocr_min_confidence?: number | null;
  ocr_low_confidence_block_ids?: string[] | null;
  ocr_confidence_threshold?: number | null;
};

type Props = {
  leadId: number | null;
  candidateName?: string | null;
};

type ScanxDeleteConfirm =
  | { kind: 'single'; doc: ScanxDocument }
  | { kind: 'bulk'; docs: ScanxDocument[] };

/** Client-side row while a file is queued / POSTing / failed before a server doc exists. */
type LocalUpload = {
  localId: string;
  /** Stable idempotency key for the upload POST (must not change on retry). */
  uploadId: string;
  file: File;
  fileName: string;
  leadId: number;
  status: 'queued' | 'uploading' | 'error';
  errorText?: string;
  /** Extra status line while the POST is in flight or recovering after abort. */
  statusHint?: string;
  /** When set, this row is a multi-image group (passport front+back, etc.). */
  groupFiles?: File[];
  documentGroupId?: string;
};

/** Parallel HTTP POSTs per counsellor session (session cap of 10 is separate). */
const SCANX_UPLOAD_HTTP_CONCURRENCY = 3;

function isScanxImageFile(file: File): boolean {
  const name = (file.name || '').toLowerCase();
  const mime = (file.type || '').toLowerCase();
  if (mime.startsWith('image/')) return true;
  return /\.(png|jpe?g|tiff?)$/i.test(name);
}

function fileFingerprint(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

/** Keep first occurrence of each document id (poll / optimistic merge safety). */
function dedupeDocsById(rows: ScanxDocument[]): ScanxDocument[] {
  const seen = new Set<number>();
  const out: ScanxDocument[] = [];
  for (const row of rows) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    out.push(row);
  }
  return out;
}

function matchUploadedDoc(rows: ScanxDocument[], item: LocalUpload): ScanxDocument | undefined {
  if (item.uploadId) {
    const byKey = rows.find(d => d.upload_id && d.upload_id === item.uploadId);
    if (byKey) return byKey;
  }
  const name = (item.fileName || '').toLowerCase();
  if (!name) return undefined;
  const cutoff = Date.now() - 10 * 60_000;
  const candidates = rows.filter(d => {
    if ((d.original_filename || '').toLowerCase() !== name) return false;
    const t = d.created_at ? Date.parse(d.created_at) : NaN;
    return Number.isFinite(t) && t >= cutoff;
  });
  return candidates.find(d => isScanxInProgress(d.status)) || candidates[0];
}

function StatusBadge({
  status,
  label,
  loading,
}: {
  status: string;
  label: string;
  loading?: boolean;
}) {
  const code = normalizeScanxStatus(status);
  const inProgress = isScanxInProgress(status) || Boolean(loading);
  const displayLabel =
    code === 'action_required'
      ? SCANX_STATUS_LABELS.action_required
      : label || SCANX_STATUS_LABELS[code as ScanxStatus] || status;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${scanxStatusBadgeClass(status)}`}
      title={displayLabel}
      aria-busy={inProgress || undefined}
    >
      {inProgress ? (
        <Loader2 size={12} className="shrink-0 animate-spin" aria-hidden />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" aria-hidden />
      )}
      <span>{displayLabel}</span>
    </span>
  );
}

const SCANX_SKELETON_STEPS: ScanxProgressStep[] = [
  { id: 'queued', label: 'Queued / Started', status: 'pending', status_label: 'Started' },
  { id: 'validate_store', label: 'Validate & store', status: 'pending', status_label: 'Started' },
  { id: 'classify', label: 'Classify document', status: 'pending', status_label: 'Started' },
  { id: 'enhance', label: 'Enhance image', status: 'pending', status_label: 'Started' },
  { id: 'extract', label: 'Extract text', status: 'pending', status_label: 'Started' },
  { id: 'chunk', label: 'Chunk text', status: 'pending', status_label: 'Started' },
  { id: 'embed', label: 'Embeddings (optional)', status: 'pending', status_label: 'Started' },
  { id: 'finalize', label: 'Finalize status', status: 'pending', status_label: 'Started' },
];

function progressStatusCopy(status: string, doc?: ScanxDocument | null): string {
  if (doc?.current_step_label) return doc.current_step_label;
  const code = normalizeScanxStatus(status);
  if (code === 'uploading') return 'Uploading…';
  if (code === 'parsing') return 'Parsing document…';
  return 'Working…';
}

function MiniProgressRing({ percent, active }: { percent: number; active?: boolean }) {
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  const r = 7;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <span
      className={`relative z-10 inline-flex h-5 w-5 shrink-0 ${active ? 'drop-shadow-[0_0_4px_rgba(3,105,161,0.65)]' : ''}`}
      aria-hidden
    >
      <svg className="h-5 w-5 -rotate-90" viewBox="0 0 20 20">
        <circle cx="10" cy="10" r={r} fill="none" stroke="currentColor" strokeWidth="2" className="text-sky-200" />
        <circle
          cx="10"
          cy="10"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          className="text-sky-800 transition-[stroke-dashoffset] duration-300 ease-out"
        />
      </svg>
    </span>
  );
}

/** Soft ceiling while waiting on OCR/LLM — never claim 100% until the worker finishes. */
const SCANX_SMOOTH_PROGRESS_CEILING = 90;

function scanxReassuranceStatus(
  displayPct: number,
  opts: {
    uploading: boolean;
    hasDoc: boolean;
    stepId?: string | null;
    stepLabel?: string | null;
  }
): string {
  const { uploading, hasDoc, stepId, stepLabel } = opts;
  if (uploading && !hasDoc) return 'Uploading file to ScanX…';
  const id = (stepId || '').toLowerCase();
  // Prefer live backend step when it is more specific than a generic threshold line.
  if (stepLabel && (id === 'enhance' || id === 'extract' || id === 'embed' || id === 'chunk')) {
    if (id === 'enhance') return 'Enhancing scan clarity (≈300 DPI)…';
    if (id === 'extract') {
      if (displayPct >= 55) return 'Cleaning artifacts with Ollama…';
      return 'Running RapidOCR spatial detection…';
    }
    if (id === 'chunk') return 'Chunking extracted text…';
    if (id === 'embed') return 'Building embeddings…';
  }
  if (displayPct < 12) return 'Analyzing document layout…';
  if (displayPct < 28) return 'Preparing pages for OCR…';
  if (displayPct < 48) return 'Running RapidOCR spatial detection…';
  if (displayPct < 68) return 'Cleaning artifacts with Ollama…';
  if (displayPct < 82) return 'Compiling structured data…';
  if (displayPct < SCANX_SMOOTH_PROGRESS_CEILING) {
    return 'Finalizing extraction — almost done…';
  }
  return stepLabel?.trim() || 'Wrapping up…';
}

/**
 * Smooth progress while the backend is busy: never freeze on a stale %,
 * tick gently toward 90%, then snap to 100% when the job completes.
 */
function useSmoothScanxProgress(
  serverPercent: number,
  opts: { active: boolean; floorWhileUploading?: number }
): number {
  const { active, floorWhileUploading } = opts;
  const floor = Math.max(
    0,
    Math.min(
      SCANX_SMOOTH_PROGRESS_CEILING,
      Math.round(serverPercent) || (floorWhileUploading ?? 0)
    )
  );
  const [display, setDisplay] = useState(() => floor);

  useEffect(() => {
    if (!active) {
      setDisplay(100);
      return;
    }
    setDisplay(prev => Math.max(prev, floor));
  }, [active, floor]);

  useEffect(() => {
    if (!active) return;
    const tickMs = 320;
    const id = window.setInterval(() => {
      setDisplay(prev => {
        const base = Math.max(prev, floor);
        if (base >= SCANX_SMOOTH_PROGRESS_CEILING) {
          return SCANX_SMOOTH_PROGRESS_CEILING;
        }
        // Ease: larger steps early, slower near the soft ceiling.
        const room = SCANX_SMOOTH_PROGRESS_CEILING - base;
        const step = Math.min(
          1.85,
          Math.max(0.35, room * 0.035 + 0.45 + Math.random() * 0.55)
        );
        return Math.min(SCANX_SMOOTH_PROGRESS_CEILING, base + step);
      });
    }, tickMs);
    return () => window.clearInterval(id);
  }, [active, floor]);

  if (!active) return 100;
  return Math.max(display, floor);
}

function StepStatusIcon({ status }: { status: string }) {
  if (status === 'complete' || status === 'skipped') {
    return <Check size={12} className="text-emerald-700" aria-hidden />;
  }
  if (status === 'failed') {
    return <X size={12} className="text-rose-700" aria-hidden />;
  }
  if (status === 'in_progress') {
    return <Loader2 size={12} className="animate-spin text-sky-700" aria-hidden />;
  }
  return <Circle size={10} className="text-text-muted/50" aria-hidden />;
}

/** True when this review should use passport panels (never Dynamic Table). */
function looksLikePassportDocument(opts: {
  documentTypeId?: string | null;
  filename?: string | null;
  extractedText?: string | null;
  passport?: unknown;
}): boolean {
  if (opts.passport && typeof opts.passport === 'object') return true;
  const typeId = (opts.documentTypeId || '').trim().toUpperCase();
  if (typeId === 'PASSPORT') return true;
  const fname = (opts.filename || '').toUpperCase();
  if (/\bPASSE?PORTS?\b/.test(fname) || /\bPASSEPORT\b/.test(fname)) return true;
  const text = opts.extractedText || '';
  if (/\bP<[A-Z<]{3}/.test(text)) return true;
  if (
    /REPUBLIC\s+OF\s+INDIA/i.test(text) &&
    /(?:passport\s*no|type\s*\/?\s*country|given\s*name|surname|mrz)/i.test(text)
  ) {
    return true;
  }
  return false;
}

/** Derive subject+marks rows from full OCR text when API subjects are empty. */
function deriveSubjectsFromExtractedText(text: string | null | undefined): ScanxSubject[] {
  const raw = (text || '').trim();
  if (!raw) return [] as ScanxSubject[];
  // Never invent marksheet rows from passport / ID OCR.
  if (
    looksLikePassportDocument({
      extractedText: raw,
    })
  ) {
    return [] as ScanxSubject[];
  }

  const deny = new Set([
    'subject',
    'subjects',
    'marks',
    'mark',
    'score',
    'grade',
    'total',
    'grand total',
    'aggregate',
    'percentage',
    'cgpa',
    'gpa',
    'result',
    'name',
    'roll',
    'board',
    'school',
    'college',
    'university',
    'theory',
    'practical',
    'maximum',
    'obtained',
  ]);

  const out: ScanxSubject[] = [];
  const seen = new Set<string>();
  const marksRe = /^\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?$/;

  const push = (
    name: string,
    marks?: string,
    grade?: string,
    theory?: string,
    practical?: string
  ) => {
    let n = name.replace(/\s+/g, ' ').trim();
    n = n.replace(/[\s:\-–—|]+$/g, '').trim();
    n = n.replace(/^(subject|paper|course|module)\s+/i, '').trim();
    n = n.replace(/\s+(marks?|score|obtained)$/i, '').trim();
    if (!n || n.length < 2 || n.length > 80) return;
    if (deny.has(n.toLowerCase())) return;
    if (/^(theory|thory|practical|prac\.?|total(?:\s*marks?)?)$/i.test(n)) return;
    // Accept Latin or local-script letters (Tamil etc.); reject digit-only.
    if (![...n].some(ch => /\p{L}/u.test(ch))) return;
    // Reject OCR crumbs like "Gu LG" / "C L".
    if (/^[A-Za-z]{1,2}(?:\s+[A-Za-z]{1,2})+$/i.test(n)) return;
    const tokens = n.split(/\s+/);
    const hasLocal = [...n].some(ch => /\p{L}/u.test(ch) && ch.charCodeAt(0) > 127);
    const hasLatinWord = tokens.some(t => t.length >= 3 && /[A-Za-z]/.test(t));
    if (!hasLocal && !hasLatinWord) return;
    if (/^(class|year|form|std|standard|level)$/i.test(n)) return;
    if (/marks?\s*obtained|name\s+of\s+the\s+school/i.test(n)) return;
    const th = (theory || '').trim();
    const pr = (practical || '').trim();
    const m = (marks || '').trim();
    const g = (grade || '').trim();
    if (!m && !g && !th && !pr) return;
    if (m && !marksRe.test(m)) return;
    if (th && !marksRe.test(th)) return;
    if (pr && !marksRe.test(pr)) return;
    const key = n.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      name: n,
      marks: m || undefined,
      grade: g || undefined,
      theory: th || undefined,
      practical: pr || undefined,
      total: m || undefined,
    });
  };

  const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  let pendingSubject: string | null = null;
  let inSubjectBlock = false;

  for (let idx = 0; idx < lines.length; idx++) {
    let line = lines[idx];
    if (!line || line.length > 160) continue;
    if (/^(grand\s*total|aggregate|percentage|result|remarks|date\s*of\s*birth|roll\s*no)\b/i.test(line)) {
      pendingSubject = null;
      inSubjectBlock = false;
      continue;
    }
    // Soft-skip TOTAL MARKS (+ following score lines) so misplaced totals
    // do not hide later subjects (Mathematics) on DOCX/OCR reorder.
    if (/^total(?:\s*marks?|\s*scores?)?\b/i.test(line)) {
      pendingSubject = null;
      continue;
    }
    if (/^subjects?$/i.test(line) || /obtained\s+the\s+following\s+marks/i.test(line)) {
      inSubjectBlock = true;
      pendingSubject = null;
      continue;
    }
    // Strip leading serial: "1.", "1)", "01"
    line = line.replace(/^(?:\d{1,4}[.)]|#?\d{1,4})\s+/, '');

    // Same-line labeled: Subject: Tamil Marks: 169
    let m = line.match(
      /(?:subject|paper|course)\s*[:\-–—|]?\s*([A-Za-z][A-Za-z0-9 .,&'/\-]{1,60}?)\s+(?:marks?|score)\s*[:\-–—|]?\s*(\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?)/i
    );
    if (m) {
      push(m[1], m[2]);
      pendingSubject = null;
      continue;
    }

    // Subject: Tamil  (pending marks on next line)
    m = line.match(/^(?:subject|paper|course|module)(?:\s*name)?\s*[:\-–—|]?\s*(.+)$/i);
    if (m) {
      const rest = m[1].trim();
      const inline = rest.match(
        /^([A-Za-z][A-Za-z0-9 .,&'/\-]{1,60}?)\s*[:\-–—|]?\s*(\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?)\s*$/i
      );
      if (inline) {
        push(inline[1], inline[2]);
        pendingSubject = null;
      } else {
        pendingSubject = rest;
      }
      continue;
    }

    // Marks: 169 / Score: 169
    m = line.match(
      /^(?:marks?|score|marks?\s*obtained|obtained(?:\s*marks?)?|scored)\s*[:\-–—|]?\s*(\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?)\s*$/i
    );
    if (m && pendingSubject) {
      push(pendingSubject, m[1]);
      pendingSubject = null;
      continue;
    }
    if (pendingSubject && marksRe.test(line)) {
      push(pendingSubject, line);
      pendingSubject = null;
      continue;
    }

    // Dot / ellipsis leaders
    m = line.match(
      /^([A-Za-z][A-Za-z0-9 .,&'/\-]{1,60}?)\s*[.·•…]{2,}\s*(\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?)(?:\s+([A-F][+-]?|Pass|Fail))?$/i
    );
    if (m) {
      push(m[1], m[2], m[3]);
      continue;
    }

    // Pipe row: Name | 85 | A  or  Name | 100 | 169
    if (line.includes('|')) {
      const cells = line
        .split(/\s*\|\s*/)
        .map(c => c.trim())
        .filter(Boolean);
      if (cells.length >= 2 && !/^(subject|subjects|course)$/i.test(cells[0])) {
        const nums = cells.slice(1).filter(c => marksRe.test(c));
        const gradeCell = cells.slice(1).find(c => /^([A-F][+-]?|Pass|Fail|Distinction)$/i.test(c));
        if (nums.length) push(cells[0], nums[nums.length - 1], gradeCell);
      }
      continue;
    }

    // Multi-space / tab columns
    const loose = line.split(/(?:[ \t]{2,}|\t)/).map(c => c.trim()).filter(Boolean);
    if (loose.length >= 2 && /^[A-Za-z]/.test(loose[0])) {
      const nums = loose.slice(1).filter(c => marksRe.test(c));
      const gradeCell = loose.slice(1).find(c => /^([A-F][+-]?|Pass|Fail|Distinction)$/i.test(c));
      if (nums.length) {
        push(loose[0], nums[nums.length - 1], gradeCell);
        continue;
      }
    }

    // Stacked marksheet: TAMIL \n 169 \n ONE SIX NINE (also local-script names)
    if (
      inSubjectBlock &&
      /^[^\d\s][\p{L}\p{N} .,&'/\-]{1,40}$/u.test(line) &&
      !/^(theory|thory|practical|prac\.?|marks?\s*obtained)/i.test(line)
    ) {
      const nums: string[] = [];
      let j = idx + 1;
      let grade: string | undefined;
      while (j < lines.length) {
        const nxt = lines[j];
        if (/^(total|grand\s*total|date\s*of\s*birth|roll\s*no)\b/i.test(nxt)) break;
        if (/^(ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED)(\s|$)/i.test(nxt)) {
          j += 1;
          if (j < lines.length && /^\([A-Za-z][A-Za-z+\-]{0,12}\)$|^([A-F][+-]?|Pass|Fail|Distinction)$/i.test(lines[j])) {
            grade = lines[j].replace(/[()]/g, '');
            j += 1;
          }
          break;
        }
        if (marksRe.test(nxt)) {
          nums.push(nxt);
          j += 1;
          continue;
        }
        if (/^\([A-Za-z][A-Za-z+\-]{0,12}\)$|^([A-F][+-]?|Pass|Fail|Distinction)$/i.test(nxt) && nums.length) {
          grade = nxt.replace(/[()]/g, '');
          j += 1;
          break;
        }
        break;
      }
      if (nums.length) {
        push(
          line,
          nums[nums.length - 1],
          grade,
          nums.length >= 2 ? nums[0] : undefined,
          nums.length >= 3 ? nums[1] : undefined
        );
        idx = j - 1;
        continue;
      }
    }

    // Name + score: Tamil 169 / தமிழ் 169 / Tamil: 169
    m = line.match(
      /^(\p{L}[\p{L}\p{N} .,&'/\-]{1,60}?)\s*[:\-–—]?\s*((?:\d{1,4}(?:\.\d{1,2})?(?:\s*\/\s*\d{1,4}(?:\.\d{1,2})?)?)(?:\s+\d{1,4}(?:\.\d{1,2})?){0,3})(?:\s+([A-F][+-]?|Pass|Fail|Distinction))?$/iu
    );
    if (m) {
      const nums = m[2].trim().split(/\s+/).filter(n => marksRe.test(n));
      // Reject month+year false positives (MAR 2016).
      if (nums.length === 1 && /^(?:19|20)\d{2}$/.test(nums[0]) && m[1].trim().length <= 12) {
        continue;
      }
      if (nums.length) {
        push(
          m[1],
          nums[nums.length - 1],
          m[3],
          nums.length >= 2 ? nums[0] : undefined,
          nums.length >= 3 ? nums[1] : undefined
        );
      }
    }
  }

  return out.slice(0, 60);
}

/**
 * Merge API categories + flat fields into ordered category tables
 * (Identity, Contact, Academic, Dates, Other, …).
 */
function groupExtractedIntoCategories(
  categories: ScanxCategory[],
  fields?: Array<{ label: string; value: string; category?: string }> | null,
  subjects?: ScanxSubject[] | null
): ScanxCategory[] {
  const order: Array<{ id: string; label: string }> = [
    { id: 'document_summary', label: 'Document summary' },
    { id: 'identity', label: 'Identity & personal' },
    { id: 'contact', label: 'Contact' },
    { id: 'academic', label: 'Academic / credentials' },
    { id: 'dates_references', label: 'Dates & references' },
    { id: 'other', label: 'Other details' },
  ];
  const subjectRows =
    Array.isArray(subjects) && subjects.length > 0
      ? subjects.filter(s => (s.name || '').trim())
      : [];
  const skipSubjectDup = subjectRows.length > 0;
  const subjectNames = new Set(
    subjectRows.map(s => (s.name || '').trim().toLowerCase()).filter(Boolean)
  );

  const buckets = new Map<
    string,
    { label: string; items: ScanxCategoryItem[]; seen: Set<string> }
  >();
  for (const def of order) {
    buckets.set(def.id, { label: def.label, items: [], seen: new Set() });
  }

  const push = (catId: string, label: string, value: string) => {
    const lab = (label || '').trim();
    const val = (value || '').trim();
    if (!lab || !val) return;
    if (lab === 'Full text preview') return;
    if (skipSubjectDup && lab === 'Subject') return;
    if (/^(theory|thory|practical|pracal|prac\.?)$/i.test(lab)) return;
    if (/^(Score \/ grade|Academic detail|Section|Line)$/i.test(lab)) {
      if (
        /marks?\s*obtained|name\s+of\s+the\s+school|^gu\s*\/?/i.test(val) ||
        /^(theory|thory|practical|prac\.?|total(?:\s*marks?)?)$/i.test(val) ||
        subjectNames.has(val.toLowerCase()) ||
        val.length < 8
      ) {
        return;
      }
      if (
        skipSubjectDup &&
        /\d{1,4}/.test(val) &&
        [...subjectNames].some(n => n && val.toLowerCase().includes(n))
      ) {
        return;
      }
    }
    const id = buckets.has(catId) ? catId : 'other';
    const bucket = buckets.get(id)!;
    const labelKey = lab.toLowerCase();
    if (/^(total\s*marks|total\s*scores)$/i.test(lab)) {
      const existingTotal = bucket.items.findIndex(r =>
        /^(total\s*marks|total\s*scores)$/i.test(r.label)
      );
      if (existingTotal >= 0) {
        if (val.length > bucket.items[existingTotal].value.length + 1) {
          bucket.items[existingTotal] = { label: 'Total Marks', value: val };
        }
        return;
      }
    }
    const existingIdx = bucket.items.findIndex(
      r => r.label.toLowerCase() === labelKey
    );
    if (existingIdx >= 0) {
      if (val.length > bucket.items[existingIdx].value.length + 1) {
        bucket.items[existingIdx] = { label: lab, value: val };
      }
      return;
    }
    const key = `${labelKey}|${val.toLowerCase()}`;
    if (bucket.seen.has(key)) return;
    bucket.seen.add(key);
    bucket.items.push({ label: lab, value: val });
  };

  for (const cat of categories) {
    const id = (cat.id || 'other').trim() || 'other';
    if (!buckets.has(id)) {
      buckets.set(id, {
        label: (cat.label || id).trim() || id,
        items: [],
        seen: new Set(),
      });
    } else if (cat.label?.trim()) {
      buckets.get(id)!.label = cat.label.trim();
    }
    for (const item of cat.items || []) {
      push(id, item.label, item.value);
    }
  }

  if (Array.isArray(fields)) {
    for (const f of fields) {
      const catId = (f.category || 'other').trim() || 'other';
      push(catId, f.label, f.value);
    }
  }

  const out: ScanxCategory[] = [];
  for (const def of order) {
    const b = buckets.get(def.id);
    if (b && b.items.length > 0) {
      out.push({ id: def.id, label: b.label, items: b.items });
    }
  }
  for (const [id, b] of buckets) {
    if (order.some(d => d.id === id)) continue;
    if (b.items.length > 0) {
      out.push({ id, label: b.label, items: b.items });
    }
  }
  return out;
}

/** Flatten for Total Marks lookup etc. */
function collectDocumentFields(
  categories: ScanxCategory[],
  fields?: Array<{ label: string; value: string; category?: string }> | null,
  subjects?: ScanxSubject[] | null
): ScanxCategoryItem[] {
  const grouped = groupExtractedIntoCategories(categories, fields, subjects);
  const out: ScanxCategoryItem[] = [];
  for (const cat of grouped) {
    for (const item of cat.items) out.push(item);
  }
  return out;
}

/** Heuristic category for a Field|Value pair when API categories are missing. */
function inferFieldCategory(label: string, value: string): string {
  const lab = label.toLowerCase();
  const val = value.toLowerCase();
  if (
    /\b(name|surname|given|father|mother|guardian|sex|gender|nationality|citizenship|dob|birth|passport|aadhaar|aadhar|pan|voter)\b/i.test(
      lab
    ) ||
    /\b(mr|mrs|ms)\.?\s+[a-z]/i.test(val)
  ) {
    return 'identity';
  }
  if (
    /\b(email|phone|mobile|tel|address|pin|postal|city|state|country|contact)\b/i.test(lab) ||
    /@/.test(value) ||
    /^\+?\d[\d\s\-()]{7,}$/.test(value.trim())
  ) {
    return 'contact';
  }
  if (
    /\b(school|college|university|board|class|stream|subject|marks|grade|cgpa|percentage|roll|registration|enrol|seat|exam|result|degree|program|course)\b/i.test(
      lab
    )
  ) {
    return 'academic';
  }
  if (
    /\b(date|year|issued|valid|expiry|session|admit|reference|ref\.?|serial|no\.?|number|id)\b/i.test(
      lab
    ) ||
    /\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b/.test(value)
  ) {
    return 'dates_references';
  }
  if (/\b(document|type|title|certificate|marksheet|transcript)\b/i.test(lab)) {
    return 'document_summary';
  }
  return 'other';
}

/** When categories are empty, turn OCR lines into categorized Field|Value tables. */
function tableFromExtractedText(text: string | null | undefined): ScanxCategory[] {
  const raw = (text || '').trim();
  if (!raw) return [];
  const pairs: Array<{ label: string; value: string; category: string }> = [];
  const seen = new Set<string>();
  for (const line of raw.split(/\r?\n/)) {
    const cleaned = line.replace(/\s+/g, ' ').trim();
    if (!cleaned || cleaned.length < 3 || cleaned.length > 200) continue;
    let label = 'Line';
    let value = cleaned;
    const m = cleaned.match(
      /^([A-Za-z][A-Za-z0-9 .,&'/%\-]{1,40}?)\s*[:\-–—|]\s*(.+)$/
    );
    if (m) {
      label = m[1].trim();
      value = m[2].trim();
    } else if (cleaned.includes('|')) {
      const cells = cleaned
        .split('|')
        .map(c => c.trim())
        .filter(Boolean);
      if (cells.length >= 2) {
        label = cells[0];
        value = cells.slice(1).join(' · ');
      }
    }
    const key = `${label.toLowerCase()}|${value.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    pairs.push({
      label,
      value,
      category: label === 'Line' ? 'other' : inferFieldCategory(label, value),
    });
    if (pairs.length >= 80) break;
  }
  if (pairs.length === 0) return [];
  return groupExtractedIntoCategories(
    [],
    pairs.map(p => ({ label: p.label, value: p.value, category: p.category })),
    null
  );
}

/** Known OCR garbage labels/values that must never appear in Other Details. */
const HIDDEN_OTHER_DETAIL_EXACT = new Set([
  'tiwaruorontoeletdmod',
]);

/**
 * True for MRZ-like / consonant-blob OCR tokens that are not real field names.
 * Keeps legitimate Other Details rows (names with spaces, file numbers with digits,
 * short labels, Title-Case multi-word fields).
 */
function isOcrJunkOtherDetailToken(raw: string): boolean {
  const text = (raw || '').trim();
  if (!text) return false;
  const compact = text.replace(/[\s_\-./]+/g, '');
  if (!compact) return false;
  if (HIDDEN_OTHER_DETAIL_EXACT.has(compact.toLowerCase())) return true;

  // MRZ-style: long run of A–Z / < with no spaces
  if (
    compact.length >= 20 &&
    /^[A-Z<]+$/i.test(compact) &&
    !/\s/.test(text)
  ) {
    return true;
  }

  // Single token only (no spaces)
  if (/\s/.test(text)) return false;
  if (compact.length <= 12) return false;
  if (/\d/.test(compact)) return false;
  if (!/^[A-Za-z]+$/.test(compact)) return false;

  const letters = compact.toLowerCase();
  const vowels = (letters.match(/[aeiou]/g) || []).length;
  // Consonant-only / no-vowel OCR soup
  if (vowels === 0) return true;
  // Long ALL-CAPS OCR blob (e.g. TIWARUORONTOELETDMOD) — not a real field label
  if (compact.length >= 14 && compact === compact.toUpperCase()) return true;
  // Dense consonant soup with very few vowels
  if (letters.length >= 14 && vowels / letters.length <= 0.22) return true;
  return false;
}

/** Hide noisy OCR rows from Other Details (case-insensitive; H.No / H NO → hno). */
function isHiddenOtherDetailLabel(label: string): boolean {
  const compact = label
    .trim()
    .toLowerCase()
    .replace(/[.\s_\-\/]+/g, '');
  if (
    compact === 'date' ||
    compact === 'hno' ||
    compact === 'pin' ||
    compact === 'line' ||
    compact === 'subject' ||
    compact === 'passportidtoken' ||
    compact === 'passporttoken'
  ) {
    return true;
  }
  return isOcrJunkOtherDetailToken(label);
}

/** Drop Other Details rows whose label or value is OCR garbage. */
function isHiddenOtherDetailRow(label: string, value?: string): boolean {
  if (isHiddenOtherDetailLabel(label || '')) return true;
  if (value && isOcrJunkOtherDetailToken(value)) return true;
  const lab = (label || '').trim().toLowerCase().replace(/[\s_\-./]+/g, '');
  const val = (value || '').trim().toLowerCase().replace(/[\s_\-./]+/g, '');
  if (HIDDEN_OTHER_DETAIL_EXACT.has(lab) || HIDDEN_OTHER_DETAIL_EXACT.has(val)) {
    return true;
  }
  return false;
}

function CategoryFieldTable({
  cat,
}: {
  cat: ScanxCategory;
}) {
  return (
    <section
      className="min-w-0 w-full rounded-md border border-border-subtle bg-surface-bg/40 px-2.5 py-2"
      aria-label={cat.label}
    >
      <h6 className="text-[11px] font-semibold text-text-main">{cat.label}</h6>
      <div className="mt-1.5 overflow-x-auto rounded border border-border-subtle/80">
        <table className="w-full min-w-[260px] border-collapse text-left text-[11px] text-text-main">
          <thead>
            <tr className="border-b border-border-subtle bg-surface-bg/70 text-text-muted">
              <th className="w-[34%] min-w-[5.5rem] px-2 py-1.5 font-semibold">Field</th>
              <th className="min-w-[8rem] px-2 py-1.5 font-semibold">Value</th>
            </tr>
          </thead>
          <tbody>
            {cat.items.map((item, idx) => (
              <tr
                key={`${cat.id}-${idx}-${item.label}`}
                className="border-b border-border-subtle/60 last:border-b-0"
              >
                <td className="px-2 py-1.5 align-top font-medium text-text-muted">
                  {item.label}
                </td>
                <td className="px-2 py-1.5 align-top whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                  {item.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CategorizedExtractionTables({
  categories,
}: {
  categories: ScanxCategory[];
}) {
  const visible = categories
    .map(c => ({
      ...c,
      items: (c.items || []).filter(
        i => !isHiddenOtherDetailRow(i.label || '', i.value || '')
      ),
    }))
    .filter(c => (c.items || []).length > 0);
  if (visible.length === 0) return null;

  const personal = visible.find(c => c.id === 'personal_info');
  const document = visible.find(c => c.id === 'document_details');
  const rest = visible.filter(
    c => c.id !== 'personal_info' && c.id !== 'document_details'
  );
  const sideBySide = Boolean(personal && document);

  return (
    <div className="space-y-2" aria-label="Categorized extracted data">
      <div className="px-0.5">
        <h5 className="text-[11px] font-semibold text-text-main">Extracted data</h5>
      </div>
      {sideBySide ? (
        <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-2">
          <CategoryFieldTable cat={personal!} />
          <CategoryFieldTable cat={document!} />
        </div>
      ) : (
        <>
          {personal ? <CategoryFieldTable cat={personal} /> : null}
          {document ? <CategoryFieldTable cat={document} /> : null}
        </>
      )}
      {rest.map(cat => (
        <CategoryFieldTable key={cat.id} cat={cat} />
      ))}
    </div>
  );
}

function parseMarkNumber(value?: string | null): number | null {
  const raw = (value || '').trim();
  if (!raw) return null;
  const m = raw.match(/^(\d{1,4}(?:\.\d{1,2})?)/);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function subjectIsLowConfidence(row: ScanxSubject): boolean {
  const flag = row.is_low_confidence;
  if (flag === true || flag === 'true' || flag === '1') return true;
  const conf =
    typeof row.confidence === 'number'
      ? row.confidence
      : typeof row.confidence === 'string'
        ? Number(row.confidence)
        : null;
  return typeof conf === 'number' && Number.isFinite(conf) && conf < 0.8;
}

function theoryPracMismatch(row: ScanxSubject): boolean {
  const theory = parseMarkNumber(row.theory);
  const prac = parseMarkNumber(row.practical || row.prac);
  const total = parseMarkNumber(row.total || row.marks);
  if (theory == null || prac == null || total == null) return false;
  return Math.abs(theory + prac - total) > 0.051;
}

type MarkCellTone = 'ok' | 'warn' | 'bad' | 'neutral';

function markCellClass(tone: MarkCellTone): string {
  if (tone === 'bad') {
    return 'bg-red-100 text-red-950 tabular-nums';
  }
  if (tone === 'warn') {
    return 'bg-orange-100 text-orange-950 tabular-nums';
  }
  if (tone === 'ok') {
    return 'bg-emerald-50 text-emerald-950 tabular-nums';
  }
  return 'tabular-nums';
}

function normalizeBoundingBox(
  box: number[][] | number[] | null | undefined
): { points: Array<{ x: number; y: number }>; normalized: boolean } | null {
  if (!Array.isArray(box) || box.length < 4) return null;
  const points: Array<{ x: number; y: number }> = [];
  for (const pt of box) {
    if (Array.isArray(pt) && pt.length >= 2) {
      const x = Number(pt[0]);
      const y = Number(pt[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      points.push({ x, y });
    } else if (typeof pt === 'number' && points.length < 2) {
      // Flat [x1,y1,x2,y2,...] — accumulate in pairs below
    }
  }
  if (points.length < 4 && box.length >= 4 && typeof box[0] === 'number') {
    const flat = box as number[];
    for (let i = 0; i + 1 < flat.length; i += 2) {
      const x = Number(flat[i]);
      const y = Number(flat[i + 1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      points.push({ x, y });
    }
  }
  if (points.length < 2) return null;
  const maxCoord = Math.max(...points.flatMap(p => [p.x, p.y]));
  return { points, normalized: maxCoord <= 1.5 };
}

function boundingBoxToOverlayRect(
  box: number[][] | number[] | null | undefined,
  imgW: number,
  imgH: number
): { x: number; y: number; width: number; height: number } | null {
  const parsed = normalizeBoundingBox(box);
  if (!parsed || imgW <= 0 || imgH <= 0) return null;
  const scaleX = parsed.normalized ? imgW : 1;
  const scaleY = parsed.normalized ? imgH : 1;
  const xs = parsed.points.map(p => p.x * scaleX);
  const ys = parsed.points.map(p => p.y * scaleY);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return {
    x: minX,
    y: minY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
  };
}

type ViewerHighlight = {
  pageIndex: number;
  box: number[][];
  label?: string;
};

function PassportGroupedTables({
  passport,
  fields,
  categories,
  onHighlightField,
}: {
  passport: ScanxPassportExtract;
  fields?: Array<{ label: string; value: string; category?: string }> | null;
  categories?: ScanxCategory[] | null;
  onHighlightField?: (fieldKey: string, box: number[][] | null, pageIndex: number) => void;
}) {
  const resolved = useMemo(
    () => hydratePassportExtract(passport, { fields, categories }),
    [passport, fields, categories]
  );
  const scores = resolved.confidence_scores || {};
  const critical = new Set([
    'surname',
    'given_names',
    'date_of_birth',
    'document_number',
    'date_of_expiry',
    'nationality',
  ]);

  const toneFor = (key: string, value: string): MarkCellTone => {
    const conf = Number(scores[key]);
    if (!value) return 'bad';
    if (Number.isFinite(conf) && conf < 0.8) return 'warn';
    if (critical.has(key) && (!Number.isFinite(conf) || conf < 0.8)) return 'warn';
    return 'ok';
  };

  type GroupRow = { key: string; label: string; value: string; showConf?: boolean };
  type Group = { id: string; label: string; rows: GroupRow[] };

  const personal: GroupRow[] = PASSPORT_PERSONAL_KEYS.map(key => ({
    key,
    label: PASSPORT_FIELD_LABELS[key] || key,
    value: coercePassportScalar(resolved[key]),
    showConf: true,
  }));

  const document: GroupRow[] = [
    ...PASSPORT_DOCUMENT_KEYS.map(key => ({
      key,
      label: PASSPORT_FIELD_LABELS[key] || key,
      value: coercePassportScalar(resolved[key]),
      showConf: key !== 'address',
    })),
    ...PASSPORT_MRZ_KEYS.map(key => ({
      key,
      label: PASSPORT_FIELD_LABELS[key] || key,
      value: coercePassportScalar(resolved[key]),
      showConf: false,
    })),
  ];

  const groups: Group[] = [
    { id: 'personal_info', label: 'Personal Info', rows: personal },
    { id: 'document_details', label: 'Document Details', rows: document },
  ];

  const renderGroup = (group: Group) => {
    const showConfCol = group.rows.some(r => r.showConf);
    return (
      <section
        key={group.id}
        className="min-w-0 w-full rounded-md border border-border-subtle bg-surface-bg/40 px-2.5 py-2"
        aria-label={group.label}
      >
        <h6 className="text-[11px] font-semibold text-text-main">{group.label}</h6>
        <div className="mt-1.5 overflow-x-auto rounded border border-border-subtle/80">
          <table className="w-full min-w-[280px] border-collapse text-left text-[11px] text-text-main">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-bg/70 text-text-muted">
                <th className="w-[32%] min-w-[6rem] px-2 py-1.5 font-semibold">Field</th>
                <th className="min-w-[9rem] px-2 py-1.5 font-semibold">Value</th>
                {showConfCol ? (
                  <th className="w-[4.5rem] shrink-0 px-2 py-1.5 font-semibold">Conf.</th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {group.rows.map(row => {
                const tone = row.showConf ? toneFor(row.key, row.value) : 'ok';
                const conf = Number(scores[row.key]);
                const isMrz = row.key === 'mrz_string';
                const box = resolved.bounding_boxes?.[row.key];
                const pageFromPassport = Number(resolved.bounding_box_pages?.[row.key] ?? 0);
                const canHighlight =
                  Boolean(onHighlightField) &&
                  Array.isArray(box) &&
                  box.length >= 4;
                return (
                  <tr
                    key={`${group.id}-${row.key}`}
                    className={`border-b border-border-subtle/60 last:border-b-0 ${
                      canHighlight
                        ? 'cursor-pointer hover:bg-accent/5'
                        : ''
                    }`}
                    title={canHighlight ? 'Show on document viewer' : undefined}
                    onClick={() => {
                      if (!canHighlight || !onHighlightField) return;
                      onHighlightField(
                        row.key,
                        box as number[][],
                        Number.isFinite(pageFromPassport) ? pageFromPassport : 0
                      );
                    }}
                  >
                    <td className="px-2 py-1.5 align-top font-medium text-text-muted">
                      {row.label}
                    </td>
                    <td
                      className={`px-2 py-1.5 align-top break-words font-mono text-[10px] [overflow-wrap:anywhere] ${
                        isMrz ? 'whitespace-pre-wrap' : 'whitespace-normal'
                      } ${row.showConf ? markCellClass(tone) : ''}`}
                    >
                      {row.value || '—'}
                    </td>
                    {showConfCol ? (
                      <td
                        className={`whitespace-nowrap px-2 py-1.5 align-top tabular-nums ${
                          row.showConf ? markCellClass(tone) : 'text-text-muted'
                        }`}
                      >
                        {row.showConf && Number.isFinite(conf)
                          ? `${Math.round(conf * 100)}%`
                          : '—'}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  return (
    <div className="space-y-2" aria-label="Passport extracted data">
      <div className="px-0.5">
        <h5 className="text-[11px] font-semibold text-text-main">Passport extraction</h5>
      </div>
      {/* Stack until xl: parent review column is already ~half viewport at lg. */}
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-2">
        {groups.map(renderGroup)}
      </div>
    </div>
  );
}

function SubjectsMarksTable({
  subjects,
  totalMarks,
}: {
  subjects: ScanxSubject[];
  totalMarks?: string | null;
}) {
  const rows = subjects.filter(s => (s.name || '').trim());
  const total = (totalMarks || '').trim();
  const showTheory = rows.some(r => (r.theory || '').trim());
  const showPractical = rows.some(
    r => (r.practical || r.prac || '').trim()
  );
  const showWords = rows.some(r => (r.words || '').trim());
  if (rows.length === 0 && !total) return null;

  const rowTone = (row: ScanxSubject): MarkCellTone => {
    if (theoryPracMismatch(row)) return 'bad';
    if (subjectIsLowConfidence(row)) return 'warn';
    const hasScore =
      !!(row.theory || '').trim() ||
      !!(row.practical || row.prac || '').trim() ||
      !!(row.total || row.marks || '').trim();
    return hasScore ? 'ok' : 'neutral';
  };

  return (
    <section
      className="rounded-md border border-border-subtle bg-surface-bg/40 px-2.5 py-2"
      aria-label="Dynamic marks table"
    >
      <h5 className="text-[11px] font-semibold text-text-main">Dynamic Table</h5>
      <p className="mt-0.5 text-[10px] text-text-muted">
        Subject · Theory · Prac · Total
        {showWords ? ' · Words' : ''} — orange/red = low OCR confidence or
        Theory+Prac ≠ Total; green = verified
      </p>
      <div className="mt-1.5 overflow-x-auto rounded border border-border-subtle/80">
        <table className="w-full min-w-[280px] border-collapse text-left text-[11px] text-text-main">
          <thead>
            <tr className="border-b border-border-subtle bg-surface-bg/70 text-text-muted">
              <th className="px-2 py-1 font-semibold">Subject</th>
              {showTheory ? (
                <th className="px-2 py-1 font-semibold">Theory</th>
              ) : null}
              {showPractical ? (
                <th className="px-2 py-1 font-semibold">Prac</th>
              ) : null}
              <th className="px-2 py-1 font-semibold">Total</th>
              {showWords ? (
                <th className="px-2 py-1 font-semibold">Words</th>
              ) : null}
              <th className="px-2 py-1 font-semibold">Grade</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const tone = rowTone(row);
              const rowTotal =
                (row.total || '').trim() ||
                (row.marks || '').trim() ||
                '';
              const pracVal =
                (row.practical || '').trim() || (row.prac || '').trim();
              return (
                <tr
                  key={`subj-top-${idx}-${row.name}`}
                  className="border-b border-border-subtle/60 last:border-b-0"
                >
                  <td
                    className={`px-2 py-1 align-top font-medium ${
                      tone === 'bad'
                        ? 'bg-red-50'
                        : tone === 'warn'
                          ? 'bg-orange-50'
                          : tone === 'ok'
                            ? 'bg-emerald-50/60'
                            : ''
                    }`}
                  >
                    {row.name}
                  </td>
                  {showTheory ? (
                    <td className={`px-2 py-1 align-top ${markCellClass(tone)}`}>
                      {row.theory?.trim() || '—'}
                    </td>
                  ) : null}
                  {showPractical ? (
                    <td className={`px-2 py-1 align-top ${markCellClass(tone)}`}>
                      {pracVal || '—'}
                    </td>
                  ) : null}
                  <td className={`px-2 py-1 align-top ${markCellClass(tone)}`}>
                    {rowTotal || '—'}
                  </td>
                  {showWords ? (
                    <td className="px-2 py-1 align-top text-text-muted">
                      {row.words?.trim() || '—'}
                    </td>
                  ) : null}
                  <td className="px-2 py-1 align-top">{row.grade?.trim() || '—'}</td>
                </tr>
              );
            })}
            {total ? (
              <tr className="border-t border-border-subtle bg-surface-bg/50 font-semibold">
                <td className="px-2 py-1 align-top">Total marks</td>
                {showTheory ? <td className="px-2 py-1 align-top">—</td> : null}
                {showPractical ? <td className="px-2 py-1 align-top">—</td> : null}
                <td className="px-2 py-1 align-top tabular-nums">{total}</td>
                {showWords ? <td className="px-2 py-1 align-top">—</td> : null}
                <td className="px-2 py-1 align-top">—</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

type BatchProgressItem = {
  key: string;
  name: string;
  statusLabel: string;
  percent: number | null;
  tone: 'active' | 'queued' | 'error';
  steps?: ScanxProgressStep[] | null;
  onCancel?: () => void;
  cancelLabel?: string;
};

function ScanxBatchProgressPill({
  items,
  expanded,
  onToggle,
}: {
  items: BatchProgressItem[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const activeItem = items.find(item => item.tone === 'active') ?? null;
  const serverPercent = Math.max(0, Math.min(100, Number(activeItem?.percent ?? 0) || 0));
  const processing = items.some(item => item.tone === 'active' || item.tone === 'queued');
  const displayPercent = useSmoothScanxProgress(serverPercent, {
    active: Boolean(activeItem),
    floorWhileUploading: activeItem && (activeItem.percent == null || activeItem.percent < 5) ? 5 : undefined,
  });
  const shownPct = activeItem ? Math.round(displayPercent) : 0;
  const workItems = items.filter(item => item.tone !== 'error');
  const total = workItems.length || items.length;
  const activeIndex = Math.max(
    0,
    workItems.findIndex(item => item.key === activeItem?.key)
  );
  const position = activeItem ? activeIndex + 1 : 1;
  const headline = !processing
    ? `${items.length} failed`
    : total <= 1
      ? `Processing ${activeItem?.name || items[0]?.name || 'document'}…`
      : `Processing Doc ${position} of ${total}…`;

  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-40 flex w-[min(24rem,calc(100vw-1.5rem))] -translate-x-1/2 flex-col items-stretch">
      {expanded ? (
        <div
          id="scanx-batch-progress-drawer"
          role="region"
          aria-label="Batch extraction details"
          className="pointer-events-auto mb-2 max-h-72 overflow-y-auto rounded-xl border border-sky-700/20 bg-card/95 p-2 text-[12px] text-text-main shadow-lg backdrop-blur-sm"
        >
          <ul className="space-y-1.5">
            {items.map(item => {
              const pct = item.tone === 'active' && item.key === activeItem?.key
                ? shownPct
                : item.percent != null
                  ? Math.round(item.percent)
                  : null;
              return (
                <li
                  key={item.key}
                  className="rounded-lg border border-border-subtle bg-surface-bg/70 px-2.5 py-2"
                >
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5">
                      {item.tone === 'error' ? (
                        <AlertTriangle size={12} className="text-rose-700" aria-hidden />
                      ) : item.tone === 'queued' ? (
                        <Circle size={10} className="text-text-muted/60" aria-hidden />
                      ) : (
                        <Loader2 size={12} className="animate-spin text-sky-700" aria-hidden />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{item.name}</p>
                      <p
                        className={`truncate text-[10px] ${
                          item.tone === 'error' ? 'text-rose-800' : 'text-text-muted'
                        }`}
                      >
                        {item.statusLabel}
                        {pct != null && item.tone !== 'error' ? ` · ${pct}%` : ''}
                      </p>
                      {item.tone !== 'error' ? (
                        <div className="mt-1 h-0.5 overflow-hidden rounded-full bg-sky-100">
                          <div
                            className="h-full rounded-full bg-sky-700 transition-[width] duration-300"
                            style={{ width: `${pct ?? 0}%` }}
                          />
                        </div>
                      ) : null}
                      {item.steps && item.steps.length > 0 ? (
                        <ul className="mt-1.5 space-y-0.5">
                          {item.steps.map(step => (
                            <li key={step.id} className="flex items-center gap-1.5 text-[10px] text-text-muted">
                              <StepStatusIcon status={step.status} />
                              <span className="min-w-0 flex-1 truncate">{step.label}</span>
                              <span className="shrink-0">{step.status_label || step.status}</span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    {item.onCancel ? (
                      <button
                        type="button"
                        className="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold text-text-muted hover:bg-white hover:text-text-main"
                        onClick={item.onCancel}
                      >
                        {item.cancelLabel || 'Cancel'}
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls="scanx-batch-progress-drawer"
        aria-live="polite"
        onClick={onToggle}
        className="pointer-events-auto relative flex items-center gap-2 self-center rounded-full border border-sky-700/30 bg-sky-50/95 py-1 pl-1.5 pr-3 text-[12px] font-semibold text-sky-950 shadow-md backdrop-blur-sm"
      >
        {processing ? (
          <span
            className="pointer-events-none absolute inset-0 animate-pulse rounded-full bg-sky-400/20"
            aria-hidden
          />
        ) : null}
        <MiniProgressRing percent={processing ? shownPct : 0} active={processing} />
        <span className="relative z-10 max-w-[16rem] truncate">{headline}</span>
        <ChevronDown
          size={14}
          className={`relative z-10 shrink-0 text-sky-800 transition-transform ${expanded ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>
    </div>
  );
}

export default function ScanxDocumentPanel({ leadId, candidateName }: Props) {
  const initialCached = getCachedScanxConfig();
  const [config, setConfig] = useState<ScanxConfig | null>(initialCached);
  const [configFailed, setConfigFailed] = useState(
    () => !initialCached && wasScanxConfigFetchFailed()
  );
  const [docs, setDocs] = useState<ScanxDocument[]>([]);
  const [alert, setAlert] = useState<{ tone: 'error' | 'warning' | 'info'; text: string } | null>(
    null
  );
  const [localUploads, setLocalUploads] = useState<LocalUpload[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [review, setReview] = useState<ScanxReview | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [openingView, setOpeningView] = useState(false);
  const [openingReviewId, setOpeningReviewId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<ScanxDeleteConfirm | null>(null);
  const [cancelConfirm, setCancelConfirm] = useState<ScanxDocument | null>(null);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [progressOpen, setProgressOpen] = useState(false);
  /** Keep silent list polls going after a client timeout until a fetch succeeds. */
  const [forceListPoll, setForceListPoll] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [originalPreviewUrl, setOriginalPreviewUrl] = useState<string | null>(null);
  const [originalPageUrls, setOriginalPageUrls] = useState<string[]>([]);
  const [viewerPageIndex, setViewerPageIndex] = useState(0);
  const [viewerHighlight, setViewerHighlight] = useState<ViewerHighlight | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [imgNaturalSize, setImgNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  /** Config is fetched once per mount path via session cache — never on document-type change. */
  const configLoadStarted = useRef(false);
  const blobUrlRef = useRef<string | null>(null);
  const originalPreviewRef = useRef<string | null>(null);
  const originalPageUrlsRef = useRef<string[]>([]);
  const selectAllRef = useRef<HTMLInputElement>(null);
  /** Tracks whether the selected doc was Uploading/Parsing so we refresh review when it settles. */
  const selectedWasBusyRef = useRef(false);
  const docsRef = useRef<ScanxDocument[]>([]);
  const localUploadsRef = useRef<LocalUpload[]>([]);
  const httpInFlightRef = useRef(0);
  /** Skip silent polls while a list request is still in flight (avoids pile-up). */
  const listInFlightRef = useRef(false);
  const uploadPumpRunning = useRef(false);
  /** Prevents drop+change (or Strict Mode) from queueing the same FileList twice. */
  const filesIngestLockRef = useRef(false);
  /** How many local uploads from the current picker batch still need a POST result. */
  const ingestPendingRef = useRef(0);
  const recentIngestFingerprintsRef = useRef<Map<string, number>>(new Map());
  /** localIds already handed to uploadOneLocal — blocks double POST if pump races. */
  const uploadStartedLocalIdsRef = useRef<Set<string>>(new Set());
  const [ingestLocked, setIngestLocked] = useState(false);

  useEffect(() => {
    if (configLoadStarted.current) return;
    configLoadStarted.current = true;

    const hit = getCachedScanxConfig();
    if (hit) {
      setConfig(hit);
      setConfigFailed(false);
      return;
    }
    if (wasScanxConfigFetchFailed()) {
      setConfigFailed(true);
      if (consumeScanxConfigSoftWarning()) {
        setAlert({ tone: 'info', text: formatScanxMessage('M13') });
      }
      return;
    }

    let cancelled = false;
    void (async () => {
      const data = await loadScanxConfigCached();
      if (cancelled) return;
      if (data) {
        setConfig(data);
        setConfigFailed(false);
        return;
      }
      setConfigFailed(true);
      if (consumeScanxConfigSoftWarning()) {
        setAlert({ tone: 'info', text: formatScanxMessage('M13') });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      if (originalPreviewRef.current) {
        URL.revokeObjectURL(originalPreviewRef.current);
        originalPreviewRef.current = null;
      }
      for (const url of originalPageUrlsRef.current) {
        URL.revokeObjectURL(url);
      }
      originalPageUrlsRef.current = [];
    };
  }, []);

  const loadDocs = useCallback(async (opts?: { silent?: boolean }) => {
    if (!leadId) {
      setDocs([]);
      return;
    }
    const silent = Boolean(opts?.silent);
    // Polls every ~1.2s must not stack if a prior list call is still open.
    if (silent && listInFlightRef.current) return;
    listInFlightRef.current = true;
    if (!silent) setLoadingList(true);
    try {
      const data = await apiFetch<ScanxDocument[]>(`scanx/documents?lead_id=${leadId}`, {
        // Silent polls must not flood Exception Report or wait the full budget.
        reportFailures: !silent,
        // Silent: short so polls do not stack. Initial load uses list budget (2m).
        timeoutMs: silent ? 20_000 : API_SCANX_LIST_TIMEOUT_MS,
      });
      // Merge progress fields so a brief empty response does not wipe the checklist.
      setDocs(prev => {
        const prevById = new Map(prev.map(d => [d.id, d]));
        const merged = dedupeDocsById(data).map(row => {
          const old = prevById.get(row.id);
          if (!old) return row;
          const steps =
            row.progress_steps && row.progress_steps.length > 0
              ? row.progress_steps
              : isScanxInProgress(row.status)
                ? old.progress_steps ?? null
                : row.progress_steps ?? null;
          return {
            ...row,
            progress_percent:
              row.progress_percent ??
              (isScanxInProgress(row.status) ? old.progress_percent : null) ??
              null,
            progress_steps: steps,
            current_step_id: row.current_step_id ?? old.current_step_id ?? null,
            current_step_label:
              row.current_step_label ?? old.current_step_label ?? null,
          };
        });
        return dedupeDocsById(merged);
      });
      setForceListPoll(false);
    } catch (err) {
      if (!silent) {
        const timedOut = isScanxClientTimeoutError(err);
        setAlert({
          tone: timedOut ? 'info' : 'error',
          text: timedOut
            ? 'Document list is slow while ScanX OCR is running. Processing continues in the background — this list will refresh automatically.'
            : err instanceof Error
              ? err.message
              : 'Could not load documents.',
        });
        if (timedOut) setForceListPoll(true);
      } else if (isScanxClientTimeoutError(err)) {
        setForceListPoll(true);
      }
    } finally {
      listInFlightRef.current = false;
      if (!silent) setLoadingList(false);
    }
  }, [leadId]);

  useEffect(() => {
    void loadDocs();
    setSelectedId(null);
    setReview(null);
    setSelectedIds(new Set());
    setDeleteConfirm(null);
    setCancelConfirm(null);
    setLocalUploads([]);
    localUploadsRef.current = [];
    httpInFlightRef.current = 0;
    uploadStartedLocalIdsRef.current.clear();
    recentIngestFingerprintsRef.current.clear();
    filesIngestLockRef.current = false;
    ingestPendingRef.current = 0;
    setIngestLocked(false);
  }, [loadDocs]);

  docsRef.current = docs;
  localUploadsRef.current = localUploads;

  const docIds = useMemo(() => docs.map(d => d.id), [docs]);
  const selectedCount = selectedIds.size;
  const allSelected = docIds.length > 0 && docIds.every(id => selectedIds.has(id));
  const someSelected = docIds.some(id => selectedIds.has(id)) && !allSelected;
  const anyDeleting = bulkDeleting || deletingId != null || cancellingId != null;
  const anyDocInProgress = docs.some(d => isScanxInProgress(d.status));
  const activeLocalUploads = localUploads.filter(u => u.status === 'queued' || u.status === 'uploading');
  const uploading = activeLocalUploads.length > 0;
  const concurrentCap =
    config?.concurrent_upload_cap ?? SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  // Drop stale checkbox ids when the list refreshes (poll / upload / delete).
  useEffect(() => {
    const alive = new Set(docIds);
    setSelectedIds(prev => {
      let changed = false;
      const next = new Set<number>();
      for (const id of prev) {
        if (alive.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [docIds]);

  const toggleOne = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(docIds));
  }, [allSelected, docIds]);

  // Poll while any doc is in flight (WS fallback) — ~2.5s keeps tunnel load down.
  useEffect(() => {
    if (!leadId) return;
    if (!anyDocInProgress && !uploading && !forceListPoll) return;
    const t = window.setInterval(() => {
      void loadDocs({ silent: true });
    }, 2500);
    return () => window.clearInterval(t);
  }, [anyDocInProgress, uploading, forceListPoll, leadId, loadDocs]);

  // After a timed-out POST, silent list polls should drop the local card once
  // the server row exists — do not leave a timeout error over in-progress OCR.
  useEffect(() => {
    const pending = localUploads.filter(
      u => u.status === 'uploading' || u.status === 'queued'
    );
    if (!pending.length || !docs.length) return;
    const matched = new Set<string>();
    for (const item of pending) {
      if (matchUploadedDoc(docs, item)) matched.add(item.localId);
    }
    if (!matched.size) return;
    setLocalUploads(prev => {
      const next = prev.filter(u => !matched.has(u.localId));
      localUploadsRef.current = next;
      return next;
    });
  }, [docs, localUploads]);

  const revokePreviewUrls = useCallback(() => {
    if (originalPreviewRef.current) {
      URL.revokeObjectURL(originalPreviewRef.current);
      originalPreviewRef.current = null;
    }
    for (const url of originalPageUrlsRef.current) {
      URL.revokeObjectURL(url);
    }
    originalPageUrlsRef.current = [];
    setOriginalPageUrls([]);
    setOriginalPreviewUrl(null);
    setViewerPageIndex(0);
    setViewerHighlight(null);
    setImgNaturalSize(null);
  }, []);

  const openReview = useCallback(async (docId: number) => {
    setOpeningReviewId(docId);
    setSelectedId(docId);
    revokePreviewUrls();
    setPreviewLoading(true);
    try {
      const data = await apiFetch<ScanxReview>(`scanx/documents/${docId}/review`);
      setReview(data);
      if (data.review_prompt) {
        setAlert({ tone: 'info', text: data.review_prompt });
      }
      const sourceSpecs =
        data.source_pages && data.source_pages.length > 0
          ? [...data.source_pages].sort((a, b) => a.page_index - b.page_index)
          : [];
      if (sourceSpecs.length > 1) {
        const loadedOrig: string[] = [];
        for (const spec of sourceSpecs) {
          const raw = spec.file_url || `scanx/documents/${docId}/file?page=${spec.page_index}`;
          const path = raw.replace(/^\/api\/v1\//, '');
          try {
            const blob = await apiFetchBlob(path);
            loadedOrig.push(URL.createObjectURL(blob));
          } catch {
            // skip missing page
          }
        }
        originalPageUrlsRef.current = loadedOrig;
        setOriginalPageUrls(loadedOrig);
        if (loadedOrig[0]) {
          setOriginalPreviewUrl(loadedOrig[0]);
        }
      } else {
        try {
          const origBlob = await apiFetchBlob(`scanx/documents/${docId}/file`);
          const origUrl = URL.createObjectURL(origBlob);
          originalPreviewRef.current = origUrl;
          setOriginalPreviewUrl(origUrl);
        } catch {
          setOriginalPreviewUrl(null);
        }
      }
    } catch (err) {
      const timedOut = isScanxClientTimeoutError(err);
      if (timedOut) setForceListPoll(true);
      setAlert({
        tone: timedOut ? 'info' : 'error',
        text: timedOut
          ? 'Review is slow while OCR is running. Processing continues — wait and refresh.'
          : err instanceof Error
            ? err.message
            : 'Could not load review.',
      });
    } finally {
      setPreviewLoading(false);
      setOpeningReviewId(null);
    }
  }, [revokePreviewUrls]);

  const highlightFieldOnViewer = useCallback(
    (fieldKey: string, box: number[][] | null, pageIndex: number) => {
      if (!box) return;
      setViewerPageIndex(Math.max(0, pageIndex));
      setViewerHighlight({ pageIndex: Math.max(0, pageIndex), box, label: fieldKey });
    },
    []
  );

  // Keep selected review status in sync with list polls; reload details when parsing finishes.
  useEffect(() => {
    if (selectedId == null) {
      selectedWasBusyRef.current = false;
      return;
    }
    const row = docs.find(d => d.id === selectedId);
    if (!row) return;

    const busy = isScanxInProgress(row.status);
    setReview(prev => {
      if (!prev || prev.document.id !== row.id) return prev;
      if (
        prev.document.status === row.status &&
        prev.document.status_label === row.status_label &&
        prev.document.error_code === row.error_code &&
        prev.document.progress_percent === row.progress_percent &&
        prev.document.current_step_id === row.current_step_id &&
        prev.document.current_step_label === row.current_step_label
      ) {
        return prev;
      }
      return {
        ...prev,
        document: {
          ...prev.document,
          status: row.status,
          status_label: row.status_label,
          error_code: row.error_code ?? null,
          error_message: row.error_message ?? null,
          progress_percent: row.progress_percent ?? null,
          progress_steps: row.progress_steps ?? null,
          current_step_id: row.current_step_id ?? null,
          current_step_label: row.current_step_label ?? null,
        },
      };
    });

    if (selectedWasBusyRef.current && !busy) {
      void openReview(selectedId);
    }
    selectedWasBusyRef.current = busy;
  }, [docs, selectedId, openReview]);

  const openDocumentView = useCallback(
    async (docId: number, signedUrl?: string | null) => {
      setOpeningView(true);
      try {
        try {
          const blob = await apiFetchBlob(`scanx/documents/${docId}/file`);
          if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
          const url = URL.createObjectURL(blob);
          blobUrlRef.current = url;
          window.open(url, '_blank', 'noopener,noreferrer');
          return;
        } catch (streamErr) {
          if (signedUrl && /^https?:\/\//i.test(signedUrl)) {
            window.open(signedUrl, '_blank', 'noopener,noreferrer');
            return;
          }
          throw streamErr;
        }
      } catch (err) {
        setAlert({
          tone: 'error',
          text: err instanceof Error ? err.message : 'Could not open document.',
        });
      } finally {
        setOpeningView(false);
      }
    },
    []
  );

  const deleteDocument = useCallback((doc: ScanxDocument) => {
    if (anyDeleting) return;
    setDeleteConfirm({ kind: 'single', doc });
  }, [anyDeleting]);

  const deleteSelected = useCallback(() => {
    if (!selectedCount || anyDeleting) return;
    const selectedDocs = docs.filter(d => selectedIds.has(d.id));
    if (selectedDocs.length === 0) return;
    setDeleteConfirm({ kind: 'bulk', docs: selectedDocs });
  }, [anyDeleting, docs, selectedCount, selectedIds]);

  const closeDeleteConfirm = useCallback(() => {
    if (anyDeleting) return;
    setDeleteConfirm(null);
  }, [anyDeleting]);

  const requestCancelJob = useCallback((doc: ScanxDocument) => {
    if (anyDeleting) return;
    setCancelConfirm(doc);
  }, [anyDeleting]);

  const closeCancelConfirm = useCallback(() => {
    if (cancellingId != null) return;
    setCancelConfirm(null);
  }, [cancellingId]);

  const confirmCancelJob = useCallback(async () => {
    if (!cancelConfirm || cancellingId != null) return;
    const doc = cancelConfirm;
    setCancellingId(doc.id);
    setDocs(prev => prev.filter(row => row.id !== doc.id));
    if (selectedId === doc.id) {
      setSelectedId(null);
      setReview(null);
    }
    setSelectedIds(prev => {
      if (!prev.has(doc.id)) return prev;
      const next = new Set(prev);
      next.delete(doc.id);
      return next;
    });
    try {
      await apiFetch(`scanx/documents/${doc.id}/cancel`, { method: 'POST' });
      setCancelConfirm(null);
      setAlert({
        tone: 'info',
        text: 'ScanX job cancelled. The uploaded file and extracted data were deleted.',
      });
      try {
        await loadDocs({ silent: true });
      } catch {
        /* list refresh is best-effort after a successful cancel */
      }
    } catch (err) {
      setCancelConfirm(null);
      if (isScanxClientTimeoutError(err)) {
        setAlert({
          tone: 'info',
          text: 'Cancel was sent. The document will disappear from the list when cleanup finishes.',
        });
        void loadDocs({ silent: true });
      } else {
        setAlert({
          tone: 'error',
          text: err instanceof Error ? err.message : 'Could not cancel this ScanX job.',
        });
        await loadDocs();
      }
    } finally {
      setCancellingId(null);
    }
  }, [cancelConfirm, cancellingId, loadDocs, selectedId]);

  const confirmDelete = useCallback(async () => {
    if (!deleteConfirm || anyDeleting) return;

    if (deleteConfirm.kind === 'single') {
      const doc = deleteConfirm.doc;
      setDeletingId(doc.id);
      try {
        await apiFetch(`scanx/documents/${doc.id}/delete`, { method: 'POST' });
        if (selectedId === doc.id) {
          setSelectedId(null);
          setReview(null);
        }
        setSelectedIds(prev => {
          if (!prev.has(doc.id)) return prev;
          const next = new Set(prev);
          next.delete(doc.id);
          return next;
        });
        setDeleteConfirm(null);
        setAlert({ tone: 'info', text: 'Document deleted.' });
        await loadDocs();
      } catch (err) {
        setDeleteConfirm(null);
        setAlert({
          tone: 'error',
          text: err instanceof Error ? err.message : 'Could not delete document.',
        });
      } finally {
        setDeletingId(null);
      }
      return;
    }

    const ids = deleteConfirm.docs.map(d => d.id);
    setBulkDeleting(true);
    try {
      const result = await apiFetch<{
        deleted: number;
        skipped: number;
        ids: number[];
      }>('scanx/documents/bulk-delete', {
        method: 'POST',
        body: JSON.stringify({ ids }),
        timeoutMs: API_SCANX_BULK_DELETE_TIMEOUT_MS,
      });
      if (selectedId != null && ids.includes(selectedId)) {
        setSelectedId(null);
        setReview(null);
      }
      setSelectedIds(new Set());
      setDeleteConfirm(null);
      setAlert({
        tone: 'info',
        text: `Deleted ${result.deleted} document${result.deleted === 1 ? '' : 's'}${
          result.skipped ? ` (${result.skipped} not found)` : ''
        }.`,
      });
      await loadDocs();
    } catch (err) {
      setDeleteConfirm(null);
      setAlert({
        tone: 'error',
        text: err instanceof Error ? err.message : 'Could not delete selected documents.',
      });
    } finally {
      setBulkDeleting(false);
    }
  }, [anyDeleting, deleteConfirm, loadDocs, selectedId]);

  const reprocessDocument = useCallback(
    async (docId: number) => {
      setReprocessing(true);
      try {
        await apiFetch(`scanx/documents/${docId}/reprocess`, { method: 'POST' });
        setAlert({ tone: 'info', text: 'Re-processing started…' });
        await loadDocs();
        window.setTimeout(() => void openReview(docId), 2000);
      } catch (err) {
        const timedOut = isScanxClientTimeoutError(err);
        if (timedOut) setForceListPoll(true);
        setAlert({
          tone: timedOut ? 'info' : 'error',
          text: timedOut
            ? 'Re-process is running in the background — wait and refresh the list.'
            : err instanceof Error
              ? err.message
              : 'Could not re-process document.',
        });
      } finally {
        setReprocessing(false);
      }
    },
    [loadDocs, openReview]
  );

  const maxFileSizeBytes = config?.max_file_size_bytes ?? SCANX_DEFAULT_MAX_FILE_SIZE_BYTES;
  const maxFileSizeLabel =
    config?.max_file_size_label ?? formatHumanFileSize(SCANX_DEFAULT_MAX_FILE_SIZE_BYTES);

  const ruleGroups = useMemo(
    () =>
      buildScanxPreuploadRuleGroups({
        maxFileSizeLabel: config?.max_file_size_label,
        maxPages: config?.max_pages,
        concurrentCap: config?.concurrent_upload_cap,
        limitsPending: !config && !configFailed,
      }),
    [config, configFailed]
  );

  const uploadActionsLocked = anyDeleting;
  const inFlightCount =
    docs.filter(d => isScanxInProgress(d.status)).length + activeLocalUploads.length;
  const atConcurrentCap = inFlightCount >= concurrentCap;
  const canUpload = Boolean(
    leadId && !uploadActionsLocked && !atConcurrentCap && !uploading && !ingestLocked
  );

  const needsReprocess =
    Boolean(review) &&
    (!review?.extracted_text?.trim() || (review?.chunk_count ?? 0) === 0) &&
    (normalizeScanxStatus(review?.document.status) === 'verified' ||
      normalizeScanxStatus(review?.document.status) === 'red_flag' ||
      review?.document.error_code === 'M14' ||
      review?.document.error_code === 'M15' ||
      review?.document.error_code === 'M16');

  const releaseIngestSlot = useCallback(() => {
    ingestPendingRef.current = Math.max(0, ingestPendingRef.current - 1);
    if (ingestPendingRef.current === 0) {
      filesIngestLockRef.current = false;
      setIngestLocked(false);
    }
  }, []);

  const dismissLocalUpload = useCallback((localId: string) => {
    const item = localUploadsRef.current.find(u => u.localId === localId);
    // Only queued rows still hold an ingest slot; uploading/error already released in finally.
    const releaseSlot = item?.status === 'queued';
    setLocalUploads(prev => {
      const next = prev.filter(u => u.localId !== localId);
      localUploadsRef.current = next;
      return next;
    });
    if (releaseSlot) releaseIngestSlot();
  }, [releaseIngestSlot]);

  const uploadOneLocal = useCallback(
    async (item: LocalUpload) => {
      setLocalUploads(prev => {
        const next = prev.map(u =>
          u.localId === item.localId ? { ...u, status: 'uploading' as const, errorText: undefined } : u
        );
        localUploadsRef.current = next;
        return next;
      });
      try {
        const form = new FormData();
        form.append('lead_id', String(item.leadId));
        form.append('document_type_id', 'UNKNOWN');
        form.append('upload_id', item.uploadId);
        const groupFiles = item.groupFiles && item.groupFiles.length > 1 ? item.groupFiles : null;
        let endpoint = 'scanx/documents';
        if (groupFiles) {
          endpoint = 'scanx/documents/group';
          if (item.documentGroupId) {
            form.append('document_group_id', item.documentGroupId);
          }
          for (const f of groupFiles) {
            form.append('files', f);
          }
        } else {
          form.append('file', item.file);
        }
        const uploaded = (await apiUpload(endpoint, form, {
          timeoutMs: API_SCANX_UPLOAD_TIMEOUT_MS,
        })) as {
          document?: ScanxDocument;
        };
        if (
          uploaded?.document?.lead_id != null &&
          uploaded.document.lead_id !== item.leadId
        ) {
          setLocalUploads(prev => {
            const next = prev.map(u =>
              u.localId === item.localId
                ? {
                    ...u,
                    status: 'error' as const,
                    errorText: `Upload stored under lead ${uploaded.document!.lead_id}, expected ${item.leadId}.`,
                  }
                : u
            );
            localUploadsRef.current = next;
            return next;
          });
          await loadDocs({ silent: true });
          return;
        }
        if (uploaded?.document?.id) {
          setDocs(prev => {
            const without = prev.filter(d => d.id !== uploaded.document!.id);
            return dedupeDocsById([uploaded.document!, ...without]);
          });
        }
        writeLastScannedLeadId(item.leadId);
        setLocalUploads(prev => {
          const next = prev.filter(u => u.localId !== item.localId);
          localUploadsRef.current = next;
          return next;
        });
        await loadDocs({ silent: true });
      } catch (err) {
        if (isScanxClientTimeoutError(err)) {
          setLocalUploads(prev => {
            const next = prev.map(u =>
              u.localId === item.localId
                ? {
                    ...u,
                    status: 'uploading' as const,
                    errorText: undefined,
                    statusHint:
                      'Processing in the background… this list will update when OCR finishes.',
                  }
                : u
            );
            localUploadsRef.current = next;
            return next;
          });
          setForceListPoll(true);
          setAlert({
            tone: 'info',
            text: 'Upload is still processing in the background. Wait for the document to appear — do not re-upload yet.',
          });
          writeLastScannedLeadId(item.leadId);
          return;
        }
        const text = err instanceof Error ? err.message : formatScanxMessage('M10');
        setLocalUploads(prev => {
          const next = prev.map(u =>
            u.localId === item.localId ? { ...u, status: 'error' as const, errorText: text } : u
          );
          localUploadsRef.current = next;
          return next;
        });
      } finally {
        uploadStartedLocalIdsRef.current.delete(item.localId);
        releaseIngestSlot();
      }
    },
    [loadDocs, releaseIngestSlot]
  );

  const pumpLocalUploads = useCallback(async () => {
    if (uploadPumpRunning.current) return;
    uploadPumpRunning.current = true;
    try {
      const hasQueued = () => localUploadsRef.current.some(u => u.status === 'queued');
      while (hasQueued() || httpInFlightRef.current > 0) {
        const cap =
          config?.concurrent_upload_cap ?? SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP;
        const serverBusy = docsRef.current.filter(d => isScanxInProgress(d.status)).length;
        const httpBusy = httpInFlightRef.current;
        const roomHttp = SCANX_UPLOAD_HTTP_CONCURRENCY - httpBusy;
        const roomCap = cap - serverBusy - httpBusy;
        const next =
          roomHttp > 0 && roomCap > 0
            ? localUploadsRef.current.find(
                u =>
                  u.status === 'queued' && !uploadStartedLocalIdsRef.current.has(u.localId)
              )
            : undefined;

        if (next) {
          uploadStartedLocalIdsRef.current.add(next.localId);
          setLocalUploads(prev => {
            const claimed = prev.map(u =>
              u.localId === next.localId ? { ...u, status: 'uploading' as const } : u
            );
            localUploadsRef.current = claimed;
            return claimed;
          });
          httpInFlightRef.current += 1;
          void (async () => {
            try {
              await uploadOneLocal(next);
            } finally {
              httpInFlightRef.current = Math.max(0, httpInFlightRef.current - 1);
            }
          })();
          continue;
        }

        if (httpInFlightRef.current > 0 || hasQueued()) {
          await new Promise<void>(resolve => {
            window.setTimeout(resolve, 350);
          });
          continue;
        }
        break;
      }
    } finally {
      uploadPumpRunning.current = false;
      if (localUploadsRef.current.some(u => u.status === 'queued')) {
        void pumpLocalUploads();
      }
    }
  }, [config?.concurrent_upload_cap, uploadOneLocal]);

  // Kick the queue when new files are added (pump also self-waits on session cap).
  useEffect(() => {
    if (!localUploads.some(u => u.status === 'queued')) return;
    void pumpLocalUploads();
  }, [localUploads, pumpLocalUploads]);

  const onFilesChosen = useCallback(
    (files: FileList | File[] | null) => {
      const list = files ? Array.from(files) : [];
      if (fileRef.current) fileRef.current.value = '';
      if (list.length === 0) return;

      // One picker confirmation → one ingest. Hold until POSTs for this batch return.
      if (filesIngestLockRef.current || ingestPendingRef.current > 0) {
        setAlert({
          tone: 'warning',
          text: 'Upload already in progress. Wait for it to finish before selecting files again.',
        });
        return;
      }
      filesIngestLockRef.current = true;
      setIngestLocked(true);

      if (uploadActionsLocked) {
        filesIngestLockRef.current = false;
        setIngestLocked(false);
        return;
      }

      const uploadLeadId = leadId;
      if (!uploadLeadId) {
        filesIngestLockRef.current = false;
        setIngestLocked(false);
        setAlert({ tone: 'error', text: formatScanxMessage('M1') });
        return;
      }

      const now = Date.now();
      // Drop fingerprints older than 15s so intentional re-uploads of the same file still work.
      for (const [fp, at] of recentIngestFingerprintsRef.current) {
        if (now - at > 15_000) recentIngestFingerprintsRef.current.delete(fp);
      }
      const activeFps = new Set(
        localUploadsRef.current
          .filter(u => u.status === 'queued' || u.status === 'uploading')
          .map(u => fileFingerprint(u.file))
      );
      const activeNames = new Set(
        [
          ...localUploadsRef.current
            .filter(u => u.status === 'queued' || u.status === 'uploading')
            .flatMap(u =>
              u.groupFiles && u.groupFiles.length > 1
                ? u.groupFiles.map(f => f.name)
                : [u.fileName || u.file.name]
            ),
          ...docsRef.current
            .filter(d => isScanxInProgress(d.status))
            .map(d => d.original_filename || ''),
        ]
          .map(n => n.trim().toLowerCase())
          .filter(Boolean)
      );

      const acceptedFiles: File[] = [];
      const rejectNotes: string[] = [];
      const batchFps = new Set<string>();
      const batchNames = new Set<string>();
      for (const file of list) {
        const fp = fileFingerprint(file);
        const nameKey = (file.name || '').trim().toLowerCase();
        if (batchFps.has(fp) || activeFps.has(fp) || recentIngestFingerprintsRef.current.has(fp)) {
          rejectNotes.push(
            formatScanxMessage('M17', { NAME: file.name || 'this file' })
          );
          continue;
        }
        if (nameKey && (batchNames.has(nameKey) || activeNames.has(nameKey))) {
          rejectNotes.push(formatScanxMessage('M17', { NAME: file.name || 'this file' }));
          continue;
        }
        if (file.size > maxFileSizeBytes) {
          rejectNotes.push(
            `${file.name}: ${formatScanxMessage('M4', { X: maxFileSizeLabel })}`
          );
          continue;
        }
        if (!isScanxFileTypeAllowed(file)) {
          rejectNotes.push(`${file.name}: ${formatScanxMessage('M3')}`);
          continue;
        }
        batchFps.add(fp);
        if (nameKey) batchNames.add(nameKey);
        recentIngestFingerprintsRef.current.set(fp, now);
        acceptedFiles.push(file);
      }

      if (rejectNotes.length > 0) {
        setAlert({
          tone: 'error',
          text:
            rejectNotes.length === 1
              ? rejectNotes[0]
              : `${rejectNotes.length} files could not be queued — ${rejectNotes
                  .slice(0, 3)
                  .join(' · ')}${rejectNotes.length > 3 ? '…' : ''}`,
        });
      } else {
        setAlert(null);
      }

      if (acceptedFiles.length === 0) {
        filesIngestLockRef.current = false;
        setIngestLocked(false);
        return;
      }

      // Multi-image selection (e.g. passport front + back) → one document group.
      const imageFiles = acceptedFiles
        .filter(isScanxImageFile)
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      const otherFiles = acceptedFiles.filter(f => !isScanxImageFile(f));
      const accepted: LocalUpload[] = [];
      if (imageFiles.length >= 2) {
        const groupId = crypto.randomUUID();
        accepted.push({
          localId: crypto.randomUUID(),
          uploadId: crypto.randomUUID(),
          file: imageFiles[0],
          fileName: `${imageFiles[0].name} (+${imageFiles.length - 1} page${
            imageFiles.length === 2 ? '' : 's'
          })`,
          leadId: uploadLeadId,
          status: 'queued',
          groupFiles: imageFiles,
          documentGroupId: groupId,
        });
      } else {
        for (const file of imageFiles) {
          accepted.push({
            localId: crypto.randomUUID(),
            uploadId: crypto.randomUUID(),
            file,
            fileName: file.name,
            leadId: uploadLeadId,
            status: 'queued',
          });
        }
      }
      for (const file of otherFiles) {
        accepted.push({
          localId: crypto.randomUUID(),
          uploadId: crypto.randomUUID(),
          file,
          fileName: file.name,
          leadId: uploadLeadId,
          status: 'queued',
        });
      }

      if (accepted.length === 0) {
        filesIngestLockRef.current = false;
        setIngestLocked(false);
        return;
      }

      const serverBusy = docsRef.current.filter(d => isScanxInProgress(d.status)).length;
      const alreadyLocal = localUploadsRef.current.filter(
        u => u.status === 'queued' || u.status === 'uploading'
      ).length;
      const remainingSlots = Math.max(0, concurrentCap - serverBusy - alreadyLocal);
      if (remainingSlots <= 0) {
        filesIngestLockRef.current = false;
        setIngestLocked(false);
        setAlert({ tone: 'error', text: formatScanxMessage('M9') });
        return;
      }

      let toQueue = accepted;
      if (accepted.length > remainingSlots) {
        const deferred = accepted.slice(remainingSlots);
        toQueue = accepted.slice(0, remainingSlots);
        setAlert({
          tone: 'warning',
          text: `${formatScanxMessage('M9')} Queued ${toQueue.length} of ${accepted.length}; skipped ${
            deferred.length
          }.`,
        });
      } else if (rejectNotes.length === 0) {
        const groupQueued = toQueue.some(u => (u.groupFiles?.length || 0) > 1);
        setAlert({
          tone: 'info',
          text:
            groupQueued && toQueue.length === 1
              ? `Uploading ${toQueue[0].groupFiles!.length} pages as one document…`
              : toQueue.length === 1
                ? `Uploading ${toQueue[0].fileName}…`
                : `Uploading ${toQueue.length} documents…`,
        });
      }

      ingestPendingRef.current += toQueue.length;
      setLocalUploads(prev => {
        const next = [...toQueue, ...prev];
        localUploadsRef.current = next;
        return next;
      });
    },
    [
      uploadActionsLocked,
      leadId,
      maxFileSizeBytes,
      maxFileSizeLabel,
      concurrentCap,
    ]
  );

  const busyDocs = docs.filter(d => isScanxInProgress(d.status));
  const batchProgressItems: BatchProgressItem[] = [
    ...localUploads.flatMap((item): BatchProgressItem[] => {
      if (item.status === 'error') {
        return [
          {
            key: item.localId,
            name: item.fileName,
            statusLabel: item.errorText || 'Upload failed',
            percent: null,
            tone: 'error',
            onCancel: () => dismissLocalUpload(item.localId),
            cancelLabel: 'Dismiss',
          },
        ];
      }
      if (item.status !== 'queued' && item.status !== 'uploading') return [];
      const uploadingNow = item.status === 'uploading';
      return [
        {
          key: item.localId,
          name: item.fileName,
          statusLabel: item.statusHint || (uploadingNow ? 'Uploading…' : 'Queued…'),
          percent: uploadingNow ? 8 : 0,
          tone: uploadingNow ? 'active' : 'queued',
          steps: SCANX_SKELETON_STEPS.map((step, index) =>
            uploadingNow && index === 0
              ? { ...step, status: 'in_progress', status_label: 'Progressing', note: 'Uploading…' }
              : step
          ),
          onCancel: uploadingNow ? undefined : () => dismissLocalUpload(item.localId),
          cancelLabel: 'Cancel',
        },
      ];
    }),
    ...busyDocs.map((doc): BatchProgressItem => ({
      key: `doc-${doc.id}`,
      name: doc.original_filename,
      statusLabel: scanxReassuranceStatus(
        typeof doc.progress_percent === 'number' ? doc.progress_percent : 0,
        {
          uploading: false,
          hasDoc: true,
          stepId: doc.current_step_id,
          stepLabel: doc.current_step_label,
        }
      ),
      percent: typeof doc.progress_percent === 'number' ? doc.progress_percent : 0,
      tone: 'active',
      steps: doc.progress_steps,
      onCancel: () => requestCancelJob(doc),
      cancelLabel: 'Cancel',
    })),
  ];
  const showProgressPanel = batchProgressItems.length > 0;
  const reviewCategories = useMemo(() => {
    if (!review) return [] as ScanxCategory[];
    if (review.categories && review.categories.length > 0) return review.categories;
    const nested = review.extracted_fields?.categories;
    return Array.isArray(nested) ? nested : [];
  }, [review]);
  const reviewSubjects = useMemo(() => {
    const byName = new Map<string, ScanxSubject>();
    const addAll = (rows: ScanxSubject[]) => {
      for (const s of rows) {
        const name = (s?.name || '').trim();
        if (!name) continue;
        if (
          /^(theory|thory|practical|pracal|prac\.?|total(?:\s*marks?)?)$/i.test(
            name
          )
        ) {
          continue;
        }
        const marks = (s?.marks || s?.total || '').trim();
        const theory = (s?.theory || '').trim();
        const practical = (s?.practical || s?.prac || '').trim();
        const total = (s?.total || s?.marks || '').trim();
        const words = (s?.words || '').trim();
        let grade = (s?.grade || '').trim();
        if (!marks && !grade && !theory && !practical) continue;
        // Drop known OCR false positives (org lines / years).
        if (/department|examinations?|chennai|marks?\s*obtained\s+for/i.test(name)) {
          continue;
        }
        if (/^(?:19|20)\d{2}$/.test(marks) && name.length <= 12) continue;
        if (/^[A-Za-z]{1,2}(?:\s+[A-Za-z]{1,2})+$/i.test(name)) continue;
        // Reject junk grades from OCR ("d") — keep A–F / Pass / P.
        if (grade && !/^[A-F][+-]?$/.test(grade) && !/^(?:pass|fail|p)$/i.test(grade)) {
          grade = '';
        }
        if (!marks && !grade && !theory && !practical) continue;
        const key = name.toLowerCase();
        const prev = byName.get(key);
        const lowConf =
          s.is_low_confidence === true ||
          s.is_low_confidence === 'true' ||
          s.is_low_confidence === '1';
        if (!prev) {
          byName.set(key, {
            name,
            marks: marks || undefined,
            grade: grade || undefined,
            theory: theory || undefined,
            practical: practical || undefined,
            prac: practical || undefined,
            total: total || undefined,
            words: words || undefined,
            confidence: s.confidence,
            is_low_confidence: lowConf || undefined,
          });
          continue;
        }
        const merged: ScanxSubject = { ...prev };
        if ((!prev.marks || !String(prev.marks).trim()) && marks) {
          merged.marks = marks;
        } else if (marks && marks.length >= String(prev.marks || '').length) {
          merged.marks = marks;
        }
        if (grade && !merged.grade?.trim()) {
          merged.grade = grade;
        }
        if (theory && !merged.theory?.trim()) merged.theory = theory;
        if (practical && !merged.practical?.trim()) {
          merged.practical = practical;
          merged.prac = practical;
        }
        if (total && !merged.total?.trim()) merged.total = total;
        if (words && !merged.words?.trim()) merged.words = words;
        if (merged.total && !merged.marks) merged.marks = merged.total;
        if (lowConf) merged.is_low_confidence = true;
        if (s.confidence != null && merged.confidence == null) {
          merged.confidence = s.confidence;
        }
        byName.set(key, merged);
      }
    };

    const markRowsToSubjects = (rows: ScanxMarkRow[] | undefined | null): ScanxSubject[] => {
      if (!Array.isArray(rows)) return [];
      return rows
        .map(r => {
          const subject = (r?.subject || '').trim();
          if (!subject) return null;
          const prac = (r.prac || r.practical || '').trim();
          const total = (r.total || '').trim();
          return {
            name: subject,
            theory: (r.theory || '').trim() || undefined,
            practical: prac || undefined,
            prac: prac || undefined,
            total: total || undefined,
            marks: total || undefined,
            words: (r.words || '').trim() || undefined,
            grade: (r.grade || '').trim() || undefined,
            confidence: r.confidence,
            is_low_confidence: r.is_low_confidence,
          } as ScanxSubject;
        })
        .filter((x): x is ScanxSubject => !!x);
    };

    // Passports must never become marksheet subject rows (OCR looks numeric).
    if (
      looksLikePassportDocument({
        documentTypeId: review?.document?.document_type_id,
        filename: review?.document?.original_filename,
        extractedText: review?.extracted_text,
        passport: review?.extracted_fields?.passport,
      })
    ) {
      return [] as ScanxSubject[];
    }

    // Prefer API subjects; marks schema fills theory/prac/words.
    if (Array.isArray(review?.subjects)) {
      addAll(review.subjects);
    }
    addAll(markRowsToSubjects(review?.extracted_fields?.marks));
    const metricsMarks = (review?.metrics as { marks?: ScanxMarkRow[] } | null | undefined)
      ?.marks;
    addAll(markRowsToSubjects(metricsMarks));
    const fromFields = review?.extracted_fields?.subjects;
    if (Array.isArray(fromFields)) {
      addAll(fromFields);
    }
    // Fallback: parse "Subject: Name — Marks X · Grade Y" items if JSON subjects thin.
    if (byName.size < 2) {
      const academic = reviewCategories.find(c => c.id === 'academic');
      if (academic?.items?.length) {
        const fromItems: ScanxSubject[] = [];
        for (const item of academic.items) {
          if (item.label !== 'Subject') continue;
          const value = item.value || '';
          const m = value.match(
            /^(.+?)\s+—\s+(?:Marks\s+(.+?))?(?:\s*·\s*)?(?:Grade\s+(.+))?$/i
          );
          if (m) {
            fromItems.push({
              name: m[1].trim(),
              marks: (m[2] || '').trim() || undefined,
              grade: (m[3] || '').trim() || undefined,
            });
          }
        }
        addAll(fromItems);
      }
    }
    // Derive from OCR text only when API/category subjects are missing.
    if (byName.size < 2) {
      addAll(deriveSubjectsFromExtractedText(review?.extracted_text));
    }
    return Array.from(byName.values());
  }, [review, reviewCategories]);

  const reviewDocumentFields = useMemo(
    () =>
      collectDocumentFields(
        reviewCategories,
        review?.extracted_fields?.fields,
        reviewSubjects
      ),
    [reviewCategories, review?.extracted_fields?.fields, reviewSubjects]
  );
  const isPassportDoc = looksLikePassportDocument({
    documentTypeId: review?.document?.document_type_id,
    filename: review?.document?.original_filename,
    extractedText: review?.extracted_text,
    passport: review?.extracted_fields?.passport,
  });
  const isPassportReview =
    isPassportDoc && Boolean(review?.extracted_fields?.passport);
  const isPassportDocMissingFields =
    isPassportDoc &&
    !review?.extracted_fields?.passport &&
    !isScanxInProgress(review?.document.status) &&
    !(review?.extracted_text || '').trim();

  const categorizedTables = useMemo(() => {
    const grouped = groupExtractedIntoCategories(
      reviewCategories,
      review?.extracted_fields?.fields,
      reviewSubjects
    );
    if (grouped.length > 0) return grouped;
    return tableFromExtractedText(review?.extracted_text);
  }, [
    reviewCategories,
    review?.extracted_fields?.fields,
    reviewSubjects,
    review?.extracted_text,
  ]);

  /** Passport: leftover OCR rows only. Personal/Document (+ MRZ) come from passport schema. */
  const passportOtherOnly = useMemo(() => {
    if (!isPassportReview || !review?.extracted_fields?.passport) {
      return [] as ScanxCategory[];
    }
    const known = new Set([
      'surname',
      'given names',
      'date of birth',
      'sex',
      'nationality',
      'place of birth',
      'document number',
      'passport number',
      'document type',
      'issuing state',
      'place of issue',
      'date of issue',
      'date of expiry',
      'mrz string',
      'mrz',
      'father / guardian name',
      'mother name',
      'spouse name',
      'address',
      'file number',
      'bounding boxes',
      'confidence scores',
      'is low confidence',
      'full text preview',
    ]);
    // Prefer backend "other" category when present (post-fix payload).
    const fromApi = (reviewCategories || []).find(c => c.id === 'other');
    if (fromApi?.items?.length) {
      const items = fromApi.items.filter(i => {
        const lab = (i.label || '').trim().toLowerCase();
        return (
          lab &&
          !known.has(lab) &&
          !isHiddenOtherDetailRow(i.label || '', i.value || '')
        );
      });
      if (items.length > 0) {
        return [{ id: 'other', label: 'Other Details', items }];
      }
    }
    const items: ScanxCategoryItem[] = [];
    const seen = new Set<string>();
    const push = (label: string, value: string) => {
      const lab = label.trim();
      const val = value.trim();
      if (!lab || !val) return;
      if (isHiddenOtherDetailRow(lab, val)) return;
      const key = lab.toLowerCase();
      if (known.has(key) || seen.has(key)) return;
      seen.add(key);
      items.push({ label: lab, value: val });
    };
    for (const cat of reviewCategories || []) {
      if (
        ['personal_info', 'document_details', 'mrz_data', 'audit_ui'].includes(cat.id)
      ) {
        continue;
      }
      for (const item of cat.items || []) {
        push(item.label || '', item.value || '');
      }
    }
    for (const f of review?.extracted_fields?.fields || []) {
      push(f.label || '', f.value || '');
    }
    if (items.length === 0) return [] as ScanxCategory[];
    return [{ id: 'other', label: 'Other Details', items }];
  }, [
    isPassportReview,
    review?.extracted_fields?.passport,
    reviewCategories,
    review?.extracted_fields?.fields,
  ]);
  const reviewTotalMarks = useMemo(() => {
    const hit = reviewDocumentFields.find(f =>
      /^(total\s*marks|total\s*scores)$/i.test((f.label || '').trim())
    );
    return (hit?.value || '').trim() || null;
  }, [reviewDocumentFields]);

  // Clear a leftover parse banner once in-flight docs settle. Live status is the progress pill.
  useEffect(() => {
    if (uploading || busyDocs.length > 0) return;
    setAlert(prev => {
      if (!prev || prev.tone !== 'info') return prev;
      const t = prev.text.toLowerCase();
      const looksLikeParseProgress =
        /\d+\s*%/.test(prev.text) ||
        t.includes('upload accepted') ||
        t.includes('tracking parse') ||
        t.includes('documents parsing') ||
        t.includes('uploading') ||
        t.startsWith('classifying') ||
        t.startsWith('enhancing') ||
        t.startsWith('extracting') ||
        t.startsWith('chunking') ||
        t.startsWith('embedding') ||
        t.startsWith('validating') ||
        t.startsWith('finalizing') ||
        t.startsWith('waiting for') ||
        t.startsWith('parsing') ||
        t.startsWith('queued') ||
        t.startsWith('starting');
      return looksLikeParseProgress ? null : prev;
    });
  }, [uploading, busyDocs.length]);

  const deleteModalTitle =
    deleteConfirm?.kind === 'bulk'
      ? `Delete ${deleteConfirm.docs.length} document${
          deleteConfirm.docs.length === 1 ? '' : 's'
        }?`
      : 'Delete document?';

  const deleteModalMessage =
    deleteConfirm?.kind === 'single' ? (
      <p>
        Delete “{deleteConfirm.doc.original_filename}”? This removes the file and extracted text
        permanently.
      </p>
    ) : deleteConfirm?.kind === 'bulk' ? (
      <div className="space-y-2">
        <p>
          Delete {deleteConfirm.docs.length} selected document
          {deleteConfirm.docs.length === 1 ? '' : 's'}? This removes the files and extracted text
          permanently.
        </p>
        <ul className="max-h-40 list-disc space-y-0.5 overflow-auto pl-5 text-text-main">
          {deleteConfirm.docs.slice(0, 8).map(doc => (
            <li key={doc.id} className="truncate">
              {doc.original_filename}
            </li>
          ))}
        </ul>
        {deleteConfirm.docs.length > 8 ? (
          <p className="text-text-muted">…and {deleteConfirm.docs.length - 8} more</p>
        ) : null}
      </div>
    ) : (
      ''
    );

  return (
    <div className="relative space-y-4">
      <div className="flex items-start justify-between gap-3 rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent/70">ScanX</p>
          <p className="mt-0.5 text-sm font-semibold text-text-main">
            {candidateName || 'Student'}{' '}
            <span className="font-normal text-text-muted">
              {leadId ? `· CRM lead #${leadId} · STUDENTS/${leadId}/` : '· select a student'}
            </span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 pt-0.5">
          <div className="group relative">
            <button
              type="button"
              className="text-[11px] font-medium text-accent underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 rounded-sm"
              aria-describedby="scanx-upload-instructions-popup"
            >
              Upload Instructions
            </button>
            <div
              id="scanx-upload-instructions-popup"
              role="tooltip"
              className="invisible absolute right-0 top-full z-30 w-72 pt-1.5 opacity-0 transition-opacity duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
            >
              <div className="rounded-lg border border-border-subtle bg-card p-3 shadow-lg">
                {!config && !configFailed ? (
                  <p className="mb-2 text-[11px] text-text-muted">Updating limits…</p>
                ) : null}
                <div className="space-y-2.5">
                  {ruleGroups.map(group => (
                    <div key={group.id}>
                      <p className="text-[11px] font-semibold text-text-main">{group.title}</p>
                      <ul className="mt-1 space-y-1 text-[11px] leading-snug text-text-muted">
                        {group.items.map(item => (
                          <li key={item} className="flex gap-2">
                            <span
                              className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent/50"
                              aria-hidden
                            />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <button
            type="button"
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canUpload}
            aria-busy={uploading || undefined}
            title={atConcurrentCap ? formatScanxMessage('M9') : undefined}
            onClick={() => {
              if (uploadActionsLocked) return;
              if (!leadId) {
                setAlert({ tone: 'error', text: formatScanxMessage('M1') });
                return;
              }
              if (atConcurrentCap) {
                setAlert({ tone: 'error', text: formatScanxMessage('M9') });
                return;
              }
              fileRef.current?.click();
            }}
          >
            {uploading ? (
              <Loader2 size={12} className="animate-spin" aria-hidden />
            ) : (
              <Upload size={12} />
            )}
            {uploading
              ? `Uploading${activeLocalUploads.length > 1 ? ` ${activeLocalUploads.length}` : ''}…`
              : 'Upload'}
          </button>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/tiff"
            className="sr-only pointer-events-none"
            tabIndex={-1}
            disabled={!canUpload}
            onChange={e => onFilesChosen(e.target.files)}
          />
        </div>
      </div>

      {showProgressPanel ? (
        <ScanxBatchProgressPill
          items={batchProgressItems}
          expanded={progressOpen}
          onToggle={() => setProgressOpen(open => !open)}
        />
      ) : null}

      {alert ? (
        <div
          role="alert"
          className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[12px] ${
            alert.tone === 'error'
              ? 'border-rose-600/30 bg-rose-500/10 text-rose-900'
              : alert.tone === 'warning'
                ? 'border-amber-700/30 bg-amber-500/10 text-amber-950'
                : 'border-sky-600/30 bg-sky-500/10 text-sky-900'
          }`}
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
          <span>{alert.text}</span>
        </div>
      ) : null}

      <div className="rounded-lg border border-border-subtle bg-card">
        <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
          <h4 className="text-xs font-semibold text-text-main">Documents</h4>
          {loadingList || anyDocInProgress || uploading ? (
            <Loader2 size={14} className="animate-spin text-sky-700" aria-label="Refreshing" />
          ) : (
            <span className="text-[11px] text-text-muted">{docs.length}</span>
          )}
        </div>
        {!leadId ? (
          <p className="px-3 py-4 text-[12px] text-text-muted">{formatScanxMessage('M1')}</p>
        ) : docs.length === 0 && localUploads.length === 0 ? (
          <p className="px-3 py-4 text-[12px] text-text-muted">No documents uploaded yet.</p>
        ) : (
          <>
            {selectedCount > 0 ? (
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-rose-500/[0.04] px-3 py-2">
                <span className="text-[12px] font-medium text-text-main">
                  {selectedCount} selected
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-md border border-rose-600/30 bg-rose-500/10 px-2.5 py-1 text-[12px] font-semibold text-rose-800 hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={anyDeleting}
                  onClick={() => deleteSelected()}
                >
                  {bulkDeleting ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                  {bulkDeleting ? 'Deleting…' : 'Delete selected'}
                </button>
              </div>
            ) : null}
            <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-1.5">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                disabled={anyDeleting || docs.length === 0}
                className="h-3.5 w-3.5 rounded border-border-subtle"
                aria-label="Select all documents"
              />
              <span className="text-[11px] text-text-muted">Select all</span>
            </div>
            <ul className="divide-y divide-border-subtle">
              {localUploads.map(item => {
                const rowBusy = item.status === 'queued' || item.status === 'uploading';
                const typeLabel = 'Auto-detecting type…';
                return (
                  <li key={item.localId} className="flex items-stretch gap-1">
                    <div className="flex shrink-0 items-center pl-3">
                      <input
                        type="checkbox"
                        disabled
                        className="h-3.5 w-3.5 rounded border-border-subtle opacity-40"
                        aria-label={`Pending ${item.fileName}`}
                      />
                    </div>
                    <div
                      className="flex min-w-0 flex-1 items-center gap-3 px-2 py-2.5"
                      aria-busy={rowBusy || undefined}
                    >
                      {rowBusy ? (
                        <Loader2
                          size={16}
                          className="shrink-0 animate-spin text-sky-700"
                          aria-hidden
                        />
                      ) : (
                        <AlertTriangle
                          size={16}
                          className="shrink-0 text-rose-700"
                          aria-hidden
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-text-main">
                          {item.fileName}
                        </p>
                        <p
                          className={`truncate text-[11px] ${
                            item.status === 'error'
                              ? 'font-medium text-rose-800'
                              : 'font-medium text-sky-800'
                          }`}
                        >
                          {item.status === 'error'
                            ? item.errorText || formatScanxMessage('M10')
                            : item.statusHint
                              ? item.statusHint
                              : item.status === 'uploading'
                                ? 'Uploading…'
                                : 'Queued…'}
                        </p>
                      </div>
                      {item.status === 'error' ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-rose-600/30 bg-rose-500/10 px-2 py-0.5 text-[11px] font-semibold text-rose-800">
                          Failed
                        </span>
                      ) : (
                        <StatusBadge
                          status="uploading"
                          label={item.status === 'uploading' ? 'Uploading' : 'Queued'}
                        />
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5 pr-2">
                      {item.status === 'error' ? (
                        <button
                          type="button"
                          title="Dismiss"
                          className="rounded-md p-1.5 text-text-muted hover:bg-surface-bg hover:text-accent"
                          onClick={() => dismissLocalUpload(item.localId)}
                        >
                          <X size={14} />
                        </button>
                      ) : (
                        <span className="px-2 text-[10px] text-text-muted">{typeLabel}</span>
                      )}
                    </div>
                  </li>
                );
              })}
              {docs.map(doc => {
                const rowBusy = isScanxInProgress(doc.status);
                const rowOpening = openingReviewId === doc.id;
                return (
                  <li key={doc.id} className="flex items-stretch gap-1">
                    <div className="flex shrink-0 items-center pl-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.id)}
                        onChange={() => toggleOne(doc.id)}
                        disabled={anyDeleting}
                        className="h-3.5 w-3.5 rounded border-border-subtle"
                        aria-label={`Select ${doc.original_filename}`}
                        onClick={e => e.stopPropagation()}
                      />
                    </div>
                    <button
                      type="button"
                      className={`flex min-w-0 flex-1 items-center gap-3 px-2 py-2.5 text-left hover:bg-surface-bg/80 ${
                        selectedId === doc.id ? 'bg-accent/[0.06]' : ''
                      }`}
                      onClick={() => void openReview(doc.id)}
                      disabled={anyDeleting || rowOpening}
                      aria-busy={rowBusy || rowOpening || undefined}
                      aria-label={
                        normalizeScanxStatus(doc.status) === 'action_required'
                          ? `Review Scan: ${doc.original_filename}`
                          : `Open ${doc.original_filename}`
                      }
                    >
                      {rowBusy || rowOpening ? (
                        <Loader2
                          size={16}
                          className="shrink-0 animate-spin text-sky-700"
                          aria-hidden
                        />
                      ) : (
                        <FileText size={16} className="shrink-0 text-accent/80" aria-hidden />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-text-main">
                          {doc.original_filename}
                        </p>
                        <p
                          className={`truncate text-[11px] ${
                            rowBusy || rowOpening
                              ? 'font-medium text-sky-800'
                              : 'text-text-muted'
                          }`}
                        >
                          {rowOpening
                            ? 'Opening review…'
                            : rowBusy
                              ? `${progressStatusCopy(doc.status, doc)}${
                                  typeof doc.progress_percent === 'number'
                                    ? ` · ${Math.round(doc.progress_percent)}%`
                                    : ''
                                }`
                              : doc.document_type_id?.toUpperCase() === 'UNKNOWN'
                                ? 'Type unknown — needs review'
                                : doc.document_type_label || doc.document_type_id}
                        </p>
                      </div>
                      <StatusBadge
                        status={doc.status}
                        label={doc.status_label}
                        loading={rowOpening}
                      />
                    </button>
                    <div className="flex shrink-0 items-center gap-0.5 pr-2">
                      <button
                        type="button"
                        title="View document"
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-bg hover:text-accent disabled:opacity-40"
                        disabled={openingView || anyDeleting || rowBusy}
                        onClick={e => {
                          e.stopPropagation();
                          void openDocumentView(doc.id, null);
                        }}
                      >
                        {openingView && selectedId === doc.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Eye size={14} />
                        )}
                      </button>
                      {rowBusy ? (
                        <button
                          type="button"
                          title="Cancel ScanX job"
                          className="rounded-md px-1.5 py-1 text-[11px] font-semibold text-rose-800 hover:bg-rose-500/10 disabled:opacity-40"
                          disabled={anyDeleting}
                          onClick={e => {
                            e.stopPropagation();
                            requestCancelJob(doc);
                          }}
                        >
                          {cancellingId === doc.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            'Cancel'
                          )}
                        </button>
                      ) : (
                        <button
                          type="button"
                          title="Delete document"
                          className="rounded-md p-1.5 text-text-muted hover:bg-rose-500/10 hover:text-rose-700 disabled:opacity-40"
                          disabled={anyDeleting}
                          onClick={e => {
                            e.stopPropagation();
                            deleteDocument(doc);
                          }}
                        >
                          {deletingId === doc.id || (bulkDeleting && selectedIds.has(doc.id)) ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      {selectedId && review ? (
        <div className="grid gap-3 lg:grid-cols-2 lg:h-[min(78vh,56rem)] lg:min-h-[28rem]">
          <section className="flex min-h-[22rem] flex-col overflow-hidden rounded-lg border border-border-subtle bg-card lg:min-h-0 lg:h-full">
            <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-text-main">Viewer</span>
                {originalPageUrls.length > 1 ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <div
                        className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-1 py-0.5 text-[11px]"
                        role="group"
                        aria-label="Document page navigation"
                      >
                        <button
                          type="button"
                          className="rounded p-0.5 text-text-muted hover:bg-surface-bg hover:text-text-main disabled:opacity-40"
                          disabled={viewerPageIndex <= 0}
                          aria-label="Previous page"
                          onClick={() => {
                            setViewerPageIndex(p => Math.max(0, p - 1));
                            setImgNaturalSize(null);
                          }}
                        >
                          <ChevronLeft size={14} />
                        </button>
                        <span className="min-w-[4.5rem] text-center font-semibold tabular-nums text-text-main">
                          Page {viewerPageIndex + 1} of {originalPageUrls.length}
                        </span>
                        <button
                          type="button"
                          className="rounded p-0.5 text-text-muted hover:bg-surface-bg hover:text-text-main disabled:opacity-40"
                          disabled={viewerPageIndex >= originalPageUrls.length - 1}
                          aria-label="Next page"
                          onClick={() => {
                            setViewerPageIndex(p =>
                              Math.min(originalPageUrls.length - 1, p + 1)
                            );
                            setImgNaturalSize(null);
                          }}
                        >
                          <ChevronRight size={14} />
                        </button>
                      </div>
                      <div
                        className="flex max-w-[14rem] gap-1 overflow-x-auto py-0.5"
                        role="list"
                        aria-label="Page thumbnails"
                      >
                        {originalPageUrls.map((url, idx) => (
                          <button
                            key={`source-thumb-${idx}`}
                            type="button"
                            role="listitem"
                            className={`h-10 w-8 shrink-0 overflow-hidden rounded border ${
                              viewerPageIndex === idx
                                ? 'border-accent ring-1 ring-accent'
                                : 'border-border-subtle opacity-80 hover:opacity-100'
                            }`}
                            aria-label={`Go to page ${idx + 1}`}
                            aria-current={viewerPageIndex === idx ? 'page' : undefined}
                            onClick={() => {
                              setViewerPageIndex(idx);
                              setImgNaturalSize(null);
                            }}
                          >
                            <img
                              src={url}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                          </button>
                        ))}
                      </div>
                    </div>
                ) : null}
              </div>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle px-2 py-1 text-[11px] font-semibold text-accent hover:bg-accent/5 disabled:opacity-50"
                disabled={openingView}
                onClick={() =>
                  void openDocumentView(review.document.id, review.viewer_url)
                }
              >
                {openingView ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Eye size={12} />
                )}
                Open in new tab
              </button>
            </header>
            <div className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden bg-surface-bg/50 p-1">
              {previewLoading ? (
                <Loader2 size={20} className="animate-spin text-text-muted" />
              ) : originalPageUrls.length > 1 &&
                originalPageUrls[viewerPageIndex] ? (
                <div className="relative mx-auto w-full max-w-full">
                  <img
                    src={originalPageUrls[viewerPageIndex]}
                    alt={`Document page ${viewerPageIndex + 1}`}
                    className="block h-auto w-full max-w-full object-contain"
                    onLoad={e => {
                      const img = e.currentTarget;
                      setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
                    }}
                  />
                  {viewerHighlight &&
                  viewerHighlight.pageIndex === viewerPageIndex &&
                  imgNaturalSize ? (
                    <svg
                      className="pointer-events-none absolute inset-0 h-full w-full"
                      viewBox={`0 0 ${imgNaturalSize.w} ${imgNaturalSize.h}`}
                      preserveAspectRatio="none"
                      aria-hidden
                    >
                      {(() => {
                        const rect = boundingBoxToOverlayRect(
                          viewerHighlight.box,
                          imgNaturalSize.w,
                          imgNaturalSize.h
                        );
                        if (!rect) return null;
                        return (
                          <rect
                            x={rect.x}
                            y={rect.y}
                            width={rect.width}
                            height={rect.height}
                            fill="rgba(59, 130, 246, 0.22)"
                            stroke="rgb(37, 99, 235)"
                            strokeWidth={Math.max(2, imgNaturalSize.w / 400)}
                          />
                        );
                      })()}
                    </svg>
                  ) : null}
                </div>
              ) : originalPreviewUrl ? (
                (review.document.original_filename || '')
                  .toLowerCase()
                  .match(/\.(png|jpe?g|gif|webp|tif{1,2})$/) ||
                (review.source_pages && review.source_pages.length > 0) ? (
                  <div className="relative mx-auto w-full max-w-full">
                    <img
                      src={
                        originalPageUrls[viewerPageIndex] || originalPreviewUrl
                      }
                      alt="Document preview"
                      className="block h-auto w-full max-w-full object-contain"
                      onLoad={e => {
                        const img = e.currentTarget;
                        setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
                      }}
                    />
                    {viewerHighlight &&
                    viewerHighlight.pageIndex === viewerPageIndex &&
                    imgNaturalSize ? (
                      <svg
                        className="pointer-events-none absolute inset-0 h-full w-full"
                        viewBox={`0 0 ${imgNaturalSize.w} ${imgNaturalSize.h}`}
                        preserveAspectRatio="none"
                        aria-hidden
                      >
                        {(() => {
                          const rect = boundingBoxToOverlayRect(
                            viewerHighlight.box,
                            imgNaturalSize.w,
                            imgNaturalSize.h
                          );
                          if (!rect) return null;
                          return (
                            <rect
                              x={rect.x}
                              y={rect.y}
                              width={rect.width}
                              height={rect.height}
                              fill="rgba(59, 130, 246, 0.22)"
                              stroke="rgb(37, 99, 235)"
                              strokeWidth={Math.max(2, imgNaturalSize.w / 400)}
                            />
                          );
                        })()}
                      </svg>
                    ) : null}
                  </div>
                ) : (
                  <iframe
                    title="Document preview"
                    src={originalPreviewUrl}
                    className="h-full w-full border-0 bg-white"
                  />
                )
              ) : (
                <span className="p-4 text-[12px] text-text-muted">
                  Use <span className="font-medium text-text-main">Open in new tab</span> to view{' '}
                  {review.document.original_filename}.
                </span>
              )}
            </div>
          </section>
          <section className="flex min-h-[22rem] min-w-0 flex-col overflow-hidden rounded-lg border border-border-subtle bg-card lg:min-h-0 lg:h-full">
            <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
              <span className="text-xs font-semibold text-text-main">Extracted details</span>
              {needsReprocess ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-main hover:bg-surface-bg disabled:opacity-50"
                  disabled={reprocessing}
                  onClick={() => void reprocessDocument(review.document.id)}
                >
                  {reprocessing ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <RefreshCw size={12} />
                  )}
                  Re-process
                </button>
              ) : null}
            </header>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 text-[12px]">
              <StatusBadge
                status={review.document.status}
                label={review.document.status_label}
              />
              {review.review_prompt && !isScanxInProgress(review.document.status) ? (
                <p className="text-amber-950">{review.review_prompt}</p>
              ) : null}
              {isScanxInProgress(review.document.status) ? (
                <p className="rounded-md border border-border-subtle bg-surface-bg/60 p-2 text-[11px] text-text-muted">
                  Categorized details will appear when parsing finishes.
                </p>
              ) : (
                <>
                  {isPassportDocMissingFields ? (
                    <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-950">
                      Passport fields were not saved after OCR. Close and reopen Review
                      Scan to backfill Personal Info and Document Details, or use
                      Re-process if they still do not appear.
                    </p>
                  ) : null}
                  {isPassportReview && review.extracted_fields?.passport ? (
                    <>
                      <PassportGroupedTables
                        passport={review.extracted_fields.passport}
                        fields={review.extracted_fields.fields}
                        categories={reviewCategories}
                        onHighlightField={highlightFieldOnViewer}
                      />
                      <CategorizedExtractionTables categories={passportOtherOnly} />
                    </>
                  ) : isPassportDoc ? null : (
                    <CategorizedExtractionTables categories={categorizedTables} />
                  )}
                  {!isPassportDoc &&
                  (reviewSubjects.length > 0 || reviewTotalMarks) ? (
                    <SubjectsMarksTable
                      subjects={reviewSubjects}
                      totalMarks={reviewTotalMarks}
                    />
                  ) : null}
                </>
              )}
            </div>
          </section>
        </div>
      ) : null}

      <ConfirmationModal
        open={deleteConfirm != null}
        title={deleteModalTitle}
        message={deleteModalMessage}
        confirmLabel={anyDeleting ? 'Deleting…' : 'Delete'}
        cancelLabel="Cancel"
        variant="danger"
        confirming={deletingId != null || bulkDeleting}
        onConfirm={() => void confirmDelete()}
        onCancel={closeDeleteConfirm}
      />
      <ConfirmationModal
        open={cancelConfirm != null}
        title="Cancel this ScanX job?"
        message="This cannot be resumed from the current step. The uploaded file and all extracted data will be deleted."
        confirmLabel={cancellingId != null ? 'Cancelling…' : 'Confirm'}
        cancelLabel="Keep processing"
        variant="danger"
        confirming={cancellingId != null}
        onConfirm={() => void confirmCancelJob()}
        onCancel={closeCancelConfirm}
      />
    </div>
  );
}
