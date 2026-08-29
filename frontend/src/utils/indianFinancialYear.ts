/** Indian financial year helpers (1 April → 31 March). */

export type IndianFy = {
  /** Calendar year when the FY starts (April). */
  startYear: number;
  /** Folder/key form used in R2: FY_2026_2027 */
  folder: string;
  /** Short UI label: FY 2026–27 */
  label: string;
  /** Inclusive start date YYYY-MM-DD */
  startDate: string;
  /** Inclusive end date YYYY-MM-DD */
  endDate: string;
};

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** FY start year for a YYYY-MM-DD calendar date. */
export function indianFyStartYearFromIsoDate(isoDate: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec((isoDate || '').trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) {
    return null;
  }
  return month >= 4 ? year : year - 1;
}

export function buildIndianFy(startYear: number): IndianFy {
  const endYear = startYear + 1;
  return {
    startYear,
    folder: `FY_${startYear}_${endYear}`,
    label: `FY ${startYear}–${String(endYear).slice(-2)}`,
    startDate: `${startYear}-04-01`,
    endDate: `${endYear}-03-31`,
  };
}

/** Current Indian FY based on a YYYY-MM-DD “today” (business calendar). */
export function currentIndianFy(todayIso: string): IndianFy {
  const start =
    indianFyStartYearFromIsoDate(todayIso) ??
    (() => {
      const d = new Date();
      const y = d.getUTCFullYear();
      const m = d.getUTCMonth() + 1;
      return m >= 4 ? y : y - 1;
    })();
  return buildIndianFy(start);
}

export function invoiceInIndianFy(
  invoiceDate: string,
  fyStartYear: number
): boolean {
  const start = indianFyStartYearFromIsoDate(invoiceDate);
  return start === fyStartYear;
}

/** True when the invoice date belongs to a closed (prior) Indian FY. */
export function isPriorIndianFyInvoice(
  invoiceDate: string,
  currentFyStartYear: number
): boolean {
  const start = indianFyStartYearFromIsoDate(invoiceDate);
  return start != null && start < currentFyStartYear;
}

/** Collect FY start years present in invoice dates, newest first. */
export function collectInvoiceFyStartYears(
  invoiceDates: Array<string | null | undefined>
): number[] {
  const years = new Set<number>();
  for (const raw of invoiceDates) {
    const start = indianFyStartYearFromIsoDate(raw || '');
    if (start != null) years.add(start);
  }
  return [...years].sort((a, b) => b - a);
}

/**
 * FY options for the selector: current FY, then older years found in data,
 * ensuring at least `minPriorYears` previous FYs are listed.
 */
export function buildInvoiceFyOptions(
  todayIso: string,
  invoiceDates: Array<string | null | undefined>,
  minPriorYears = 3
): IndianFy[] {
  const current = currentIndianFy(todayIso);
  const years = new Set<number>([current.startYear]);
  for (const y of collectInvoiceFyStartYears(invoiceDates)) {
    years.add(y);
  }
  for (let i = 1; i <= minPriorYears; i += 1) {
    years.add(current.startYear - i);
  }
  return [...years]
    .sort((a, b) => b - a)
    .map(startYear => buildIndianFy(startYear));
}

/** Mid-FY sample date helper (15th of a month within the FY). */
export function sampleDateInFy(
  startYear: number,
  month: number,
  day = 15
): string {
  const year = month >= 4 ? startYear : startYear + 1;
  return `${year}-${pad2(month)}-${pad2(day)}`;
}
