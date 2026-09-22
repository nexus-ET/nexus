/**
 * Session-scoped ScanX config cache.
 * Survives panel remounts (e.g. selecting a lead) so we never re-hit a slow
 * tunnel for the same settings, and never re-flash a timeout warning.
 */
import { apiFetch } from './api';
import {
  SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP,
  SCANX_DEFAULT_MAX_FILE_SIZE_BYTES,
  SCANX_DEFAULT_MAX_PAGES,
  SCANX_DOCUMENT_TYPES,
  formatHumanFileSize,
  type ScanxDocumentTypeOption,
} from '../constants/scanxMessages';

export type ScanxConfig = {
  max_file_size_bytes: number;
  max_file_size_label: string;
  max_pages: number;
  r2_key_root: string;
  concurrent_upload_cap: number;
  document_types: ScanxDocumentTypeOption[];
  statuses: Record<string, string>;
  preupload_rules: string[];
  /** Configured primary image OCR engine (rapid | paddle). */
  ocr_engine?: string;
  /** Fallback engine when primary fails/empty/unavailable. */
  ocr_fallback?: string | null;
};

/** Modest budget for tunnel + auth; ScanX-specific (not the 5m PEM apply budget). */
export const SCANX_CONFIG_TIMEOUT_MS = 25_000;

/** Do not hammer a failing endpoint on every remount. */
const FAIL_COOLDOWN_MS = 60_000;

let cached: ScanxConfig | null = null;
let failedAt: number | null = null;
let inflight: Promise<ScanxConfig> | null = null;
/** Show the soft “defaults” notice at most once per session failure. */
let softWarningConsumed = false;

export function getCachedScanxConfig(): ScanxConfig | null {
  return cached;
}

export function wasScanxConfigFetchFailed(): boolean {
  return failedAt != null && cached == null;
}

/** Consume one-shot soft warning; returns true if caller should show M13. */
export function consumeScanxConfigSoftWarning(): boolean {
  if (!wasScanxConfigFetchFailed() || softWarningConsumed) return false;
  softWarningConsumed = true;
  return true;
}

export function buildDefaultScanxConfig(): ScanxConfig {
  return {
    max_file_size_bytes: SCANX_DEFAULT_MAX_FILE_SIZE_BYTES,
    max_file_size_label: formatHumanFileSize(SCANX_DEFAULT_MAX_FILE_SIZE_BYTES),
    max_pages: SCANX_DEFAULT_MAX_PAGES,
    r2_key_root: 'STUDENTS',
    concurrent_upload_cap: SCANX_DEFAULT_CONCURRENT_UPLOAD_CAP,
    document_types: SCANX_DOCUMENT_TYPES,
    statuses: {},
    preupload_rules: [],
  };
}

/**
 * Load ScanX config once per session (shared inflight + success cache).
 * On failure within cooldown, resolves null without a new network call.
 */
export async function loadScanxConfigCached(): Promise<ScanxConfig | null> {
  if (cached) return cached;

  if (failedAt != null && Date.now() - failedAt < FAIL_COOLDOWN_MS) {
    return null;
  }

  if (inflight) {
    try {
      return await inflight;
    } catch {
      return null;
    }
  }

  inflight = apiFetch<ScanxConfig>('scanx/config', {
    timeoutMs: SCANX_CONFIG_TIMEOUT_MS,
  })
    .then(data => {
      cached = data;
      failedAt = null;
      softWarningConsumed = false;
      return data;
    })
    .catch(err => {
      failedAt = Date.now();
      throw err;
    })
    .finally(() => {
      inflight = null;
    });

  try {
    return await inflight;
  } catch {
    return null;
  }
}
