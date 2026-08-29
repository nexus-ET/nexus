import type { DiscountType } from './invoiceMoney';
import { roundMoney } from './invoiceMoney';
import {
  computeTaxLineBreakdown,
  type InvoiceSupplyType,
  type TaxLineBreakdown,
  type TaxRegimes,
} from './taxRegimes';

export type InvoiceLineInput = {
  quantity: number;
  unitPriceInr: number;
};

export type InvoiceWorkspaceTotals = {
  linesSubtotal: number;
  discountAmount: number;
  taxableAmount: number;
  tax: TaxLineBreakdown;
  amountBeforeRoundOff: number;
  roundOffAmount: number;
  finalPayableAmount: number;
  discountPercentOfSubtotal: number;
  requiresAuthorization: boolean;
};

/**
 * Line sum → discount → GST (regime-aware) → nearest-rupee round-off → payable.
 */
export function computeInvoiceWorkspaceTotals(input: {
  lines: InvoiceLineInput[];
  discountType: DiscountType;
  discountValue: number;
  gstPercentage: number;
  regimes: TaxRegimes;
  supplyType: InvoiceSupplyType;
  maxAutoApproveDiscountPercent: number;
}): InvoiceWorkspaceTotals {
  const linesSubtotal = roundMoney(
    input.lines.reduce((sum, line) => {
      const qty = Math.max(0, Number(line.quantity) || 0);
      const price = Math.max(0, Number(line.unitPriceInr) || 0);
      return sum + qty * price;
    }, 0)
  );

  const discountValue = Math.max(0, input.discountValue);
  const discountAmount =
    input.discountType === 'percentage'
      ? roundMoney((linesSubtotal * Math.min(100, discountValue)) / 100)
      : roundMoney(Math.min(discountValue, linesSubtotal));

  const taxableAmount = roundMoney(Math.max(0, linesSubtotal - discountAmount));
  const tax = computeTaxLineBreakdown({
    taxableAmount,
    gstPercentage: input.gstPercentage,
    regimes: input.regimes,
    supplyType: input.supplyType,
  });

  const amountBeforeRoundOff = roundMoney(taxableAmount + tax.totalTaxAmount);
  const finalPayableAmount = Math.round(amountBeforeRoundOff);
  const roundOffAmount = roundMoney(finalPayableAmount - amountBeforeRoundOff);

  const discountPercentOfSubtotal =
    linesSubtotal > 0 ? roundMoney((discountAmount / linesSubtotal) * 100) : 0;
  const maxAuto = Math.min(100, Math.max(0, input.maxAutoApproveDiscountPercent));

  return {
    linesSubtotal,
    discountAmount,
    taxableAmount,
    tax,
    amountBeforeRoundOff,
    roundOffAmount,
    finalPayableAmount,
    discountPercentOfSubtotal,
    requiresAuthorization: discountPercentOfSubtotal > maxAuto,
  };
}

export function resolveSupplyType(input: {
  placeOfSupplyStateCode: string;
  organizationGstin: string;
  forceExempt?: boolean;
}): InvoiceSupplyType {
  if (input.forceExempt) return 'exempt';
  const pos = input.placeOfSupplyStateCode.trim().padStart(2, '0');
  const orgState = input.organizationGstin.trim().toUpperCase().slice(0, 2).padStart(2, '0');
  // Empty / invalid codes must not silently fall through as inter-state IGST.
  if (!/^\d{2}$/.test(pos) || pos === '00') return 'inter';
  if (!/^\d{2}$/.test(orgState) || orgState === '00') return 'inter';
  return pos === orgState ? 'intra' : 'inter';
}
