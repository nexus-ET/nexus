import {
  clampGstPercentage,
  DEFAULT_TAX_REGIMES,
  type TaxRegimesFormValues,
} from '../schemas/billingSettingsSchema';
import { roundMoney } from './invoiceMoney';

export type TaxRegimes = TaxRegimesFormValues;
export type { TaxRegimesFormValues };
export { DEFAULT_TAX_REGIMES };

export type InvoiceSupplyType = 'intra' | 'inter' | 'exempt';

export type TaxLineBreakdown = {
  supplyType: InvoiceSupplyType;
  taxableAmount: number;
  cgstRate: number;
  sgstRate: number;
  igstRate: number;
  cgstAmount: number;
  sgstAmount: number;
  igstAmount: number;
  totalTaxAmount: number;
  /** True when regimes cannot produce a taxable line for this supply type. */
  unavailable: boolean;
};

/** Keep CGST and SGST paired for intra-state supply. */
export function coupleCgstSgst(regimes: TaxRegimes, changed: 'cgst' | 'sgst'): TaxRegimes {
  const paired = changed === 'cgst' ? regimes.cgst : regimes.sgst;
  return { ...regimes, cgst: paired, sgst: paired };
}

export function normalizeTaxRegimes(raw: unknown): TaxRegimes {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_TAX_REGIMES };
  const row = raw as Record<string, unknown>;
  let next: TaxRegimes = {
    cgst: row.cgst !== false,
    sgst: row.sgst !== false,
    igst: row.igst !== false,
    exempt: row.exempt === true,
  };
  // Legacy / partial rows: if only one of CGST/SGST is on, turn both on.
  if (next.cgst !== next.sgst) {
    next = { ...next, cgst: true, sgst: true };
  }
  if (!next.cgst && !next.sgst && !next.igst && !next.exempt) {
    return { ...DEFAULT_TAX_REGIMES };
  }
  return next;
}

export function hasAnyTaxRegime(regimes: TaxRegimes): boolean {
  return regimes.cgst || regimes.sgst || regimes.igst || regimes.exempt;
}

export function formatTaxRegimePreview(gstPercentage: number, regimes: TaxRegimes): string {
  const rate = clampGstPercentage(gstPercentage);
  const half = roundMoney(rate / 2);
  const parts: string[] = [];
  if (regimes.cgst && regimes.sgst) {
    parts.push(`Intra-state split: ${half}% CGST + ${half}% SGST`);
  }
  if (regimes.igst) {
    parts.push(`Inter-state: ${rate}% IGST`);
  }
  if (regimes.exempt) {
    parts.push('Exempt / zero-rated lines available at 0%');
  }
  if (!parts.length) {
    return 'Select at least one tax regime before saving.';
  }
  return parts.join(' · ');
}

/**
 * Pure helper for future Invoicing page.
 * Given taxable amount, headline GST %, active regimes, and supply type, return tax lines.
 */
export function computeTaxLineBreakdown(input: {
  taxableAmount: number;
  gstPercentage: number;
  regimes: TaxRegimes;
  supplyType: InvoiceSupplyType;
}): TaxLineBreakdown {
  const taxableAmount = roundMoney(Math.max(0, input.taxableAmount));
  const rate = clampGstPercentage(input.gstPercentage);
  const regimes = normalizeTaxRegimes(input.regimes);
  const half = roundMoney(rate / 2);

  if (input.supplyType === 'exempt') {
    if (!regimes.exempt) {
      return {
        supplyType: 'exempt',
        taxableAmount,
        cgstRate: 0,
        sgstRate: 0,
        igstRate: 0,
        cgstAmount: 0,
        sgstAmount: 0,
        igstAmount: 0,
        totalTaxAmount: 0,
        unavailable: true,
      };
    }
    return {
      supplyType: 'exempt',
      taxableAmount,
      cgstRate: 0,
      sgstRate: 0,
      igstRate: 0,
      cgstAmount: 0,
      sgstAmount: 0,
      igstAmount: 0,
      totalTaxAmount: 0,
      unavailable: false,
    };
  }

  if (input.supplyType === 'intra') {
    if (!(regimes.cgst && regimes.sgst)) {
      return {
        supplyType: 'intra',
        taxableAmount,
        cgstRate: 0,
        sgstRate: 0,
        igstRate: 0,
        cgstAmount: 0,
        sgstAmount: 0,
        igstAmount: 0,
        totalTaxAmount: 0,
        unavailable: true,
      };
    }
    const cgstAmount = roundMoney((taxableAmount * half) / 100);
    const sgstAmount = roundMoney((taxableAmount * half) / 100);
    return {
      supplyType: 'intra',
      taxableAmount,
      cgstRate: half,
      sgstRate: half,
      igstRate: 0,
      cgstAmount,
      sgstAmount,
      igstAmount: 0,
      totalTaxAmount: roundMoney(cgstAmount + sgstAmount),
      unavailable: false,
    };
  }

  // inter
  if (!regimes.igst) {
    return {
      supplyType: 'inter',
      taxableAmount,
      cgstRate: 0,
      sgstRate: 0,
      igstRate: 0,
      cgstAmount: 0,
      sgstAmount: 0,
      igstAmount: 0,
      totalTaxAmount: 0,
      unavailable: true,
    };
  }
  const igstAmount = roundMoney((taxableAmount * rate) / 100);
  return {
    supplyType: 'inter',
    taxableAmount,
    cgstRate: 0,
    sgstRate: 0,
    igstRate: rate,
    cgstAmount: 0,
    sgstAmount: 0,
    igstAmount,
    totalTaxAmount: igstAmount,
    unavailable: false,
  };
}
