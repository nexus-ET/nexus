import type { InvoiceSequenceStrategy } from '../schemas/billingSettingsSchema';
import {
  DEFAULT_INVOICE_NUMBER_FORMAT,
  normalizeInvoiceNumberFormat,
} from '../schemas/billingSettingsSchema';

/** Indian financial year starts on April 1 (month index 3). */
export function getIndianFinancialYearStart(date: Date = new Date()): number {
  return date.getMonth() >= 3 ? date.getFullYear() : date.getFullYear() - 1;
}

/** FY label like 2025-26 from FY start year. */
export function formatFinancialYearLabel(fyStartYear: number): string {
  return `${fyStartYear}-${String(fyStartYear + 1).slice(-2)}`;
}

/** Short FY span like 26-27 from FY start year. */
export function formatShortFinancialYearSpan(fyStartYear: number): string {
  const start = String(fyStartYear).slice(-2);
  const end = String(fyStartYear + 1).slice(-2);
  return `${start}-${end}`;
}

/**
 * Build an invoice id from a format pattern.
 * Tokens: {YYYY}, {YY}, {FY}, {FY-FY}, {SEQ}, {SEQ:n} (n = 1–8 pad width).
 */
export function formatInvoiceId(
  fyStartYear: number,
  sequence: number,
  pattern: string = DEFAULT_INVOICE_NUMBER_FORMAT
): string {
  const safeSequence = Math.max(1, Math.floor(sequence));
  const format = normalizeInvoiceNumberFormat(pattern);
  const yyyy = String(fyStartYear);
  const yy = yyyy.slice(-2);
  const fy = formatFinancialYearLabel(fyStartYear);
  const fyFy = formatShortFinancialYearSpan(fyStartYear);

  return format
    .replace(/\{YYYY\}/g, yyyy)
    .replace(/\{FY-FY\}/g, fyFy)
    .replace(/\{YY\}/g, yy)
    .replace(/\{FY\}/g, fy)
    .replace(/\{SEQ:([1-8])\}/g, (_match, width: string) =>
      String(safeSequence).padStart(Number(width), '0')
    )
    .replace(/\{SEQ\}/g, String(safeSequence));
}

export type InvoiceSequenceState = {
  strategy: InvoiceSequenceStrategy;
  /** Last issued sequence number (0 = none issued yet). */
  lastInvoiceSequence: number;
  /** FY start year of the last issued invoice, or null if never issued. */
  lastInvoiceFinancialYearStart: number | null;
  /** Pattern used to render the invoice id. */
  invoiceNumberFormat?: string;
};

export type NextInvoiceAllocation = {
  financialYearStart: number;
  sequence: number;
  invoiceId: string;
  resetApplied: boolean;
};

/**
 * Resolve the next invoice number under the April-1 FY policy.
 * - continue: sequence keeps incrementing across FY boundaries
 * - reset: sequence restarts at 1 when the active FY differs from the last issued FY
 */
export function resolveNextInvoiceAllocation(
  state: InvoiceSequenceState,
  now: Date = new Date()
): NextInvoiceAllocation {
  const financialYearStart = getIndianFinancialYearStart(now);
  const lastSequence = Math.max(0, Math.floor(state.lastInvoiceSequence || 0));
  const lastFy = state.lastInvoiceFinancialYearStart;
  const sameFy = lastFy === financialYearStart;
  const crossedFy = lastFy != null && lastFy !== financialYearStart;
  const format = normalizeInvoiceNumberFormat(state.invoiceNumberFormat);

  if (sameFy) {
    const sequence = lastSequence + 1;
    return {
      financialYearStart,
      sequence,
      invoiceId: formatInvoiceId(financialYearStart, sequence, format),
      resetApplied: false,
    };
  }

  if (state.strategy === 'reset') {
    const sequence = 1;
    return {
      financialYearStart,
      sequence,
      invoiceId: formatInvoiceId(financialYearStart, sequence, format),
      resetApplied: crossedFy || lastFy == null,
    };
  }

  const sequence = lastSequence + 1;
  return {
    financialYearStart,
    sequence,
    invoiceId: formatInvoiceId(financialYearStart, sequence, format),
    resetApplied: false,
  };
}

/** Live preview string for admin settings (does not mutate store). */
export function previewNextInvoiceId(
  strategy: InvoiceSequenceStrategy,
  lastInvoiceSequence: number,
  lastInvoiceFinancialYearStart: number | null,
  now: Date = new Date(),
  invoiceNumberFormat: string = DEFAULT_INVOICE_NUMBER_FORMAT
): string {
  return resolveNextInvoiceAllocation(
    {
      strategy,
      lastInvoiceSequence,
      lastInvoiceFinancialYearStart,
      invoiceNumberFormat,
    },
    now
  ).invoiceId;
}

/**
 * After an invoice is issued, return the sequence fields to persist.
 * Call from Student Invoice Generator after a successful allocate.
 */
export function applyIssuedInvoice(
  state: InvoiceSequenceState,
  now: Date = new Date()
): {
  nextState: Pick<InvoiceSequenceState, 'lastInvoiceSequence' | 'lastInvoiceFinancialYearStart'>;
  invoiceId: string;
} {
  const allocation = resolveNextInvoiceAllocation(state, now);
  return {
    invoiceId: allocation.invoiceId,
    nextState: {
      lastInvoiceSequence: allocation.sequence,
      lastInvoiceFinancialYearStart: allocation.financialYearStart,
    },
  };
}
