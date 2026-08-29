/** Round currency to two decimal places (banker's-safe enough for UI totals). */
export function roundMoney(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export type DiscountType = 'percentage' | 'fixed';

export type InvoiceAdjustmentInput = {
  subtotal: number;
  discountType: DiscountType;
  /** Percentage 0–100 or fixed amount, depending on discountType. */
  discountValue: number;
  /** Non-discount credit (refunds/credits), reduces amount due. */
  adjustmentAmount: number;
  gstPercentage: number;
  maxAutoApproveDiscountPercent: number;
};

export type InvoiceAdjustmentTotals = {
  subtotal: number;
  discountAmount: number;
  taxableAfterDiscount: number;
  adjustmentAmount: number;
  taxableAfterAdjustment: number;
  gstAmount: number;
  finalTotal: number;
  /** Discount as % of subtotal (for authorization checks). */
  discountPercentOfSubtotal: number;
  requiresAuthorization: boolean;
};

/**
 * Precise invoice math:
 * Subtotal → Discount → Adjustment (credit) → GST on remaining taxable → Final.
 * All money values are rounded to 2 decimals.
 */
export function computeInvoiceAdjustmentTotals(
  input: InvoiceAdjustmentInput
): InvoiceAdjustmentTotals {
  const subtotal = roundMoney(Math.max(0, input.subtotal));
  const discountValue = Math.max(0, input.discountValue);
  const adjustmentAmount = roundMoney(Math.max(0, input.adjustmentAmount));
  const gstPercentage = Math.min(100, Math.max(0, input.gstPercentage));
  const maxAuto = Math.min(100, Math.max(0, input.maxAutoApproveDiscountPercent));

  const discountAmount =
    input.discountType === 'percentage'
      ? roundMoney((subtotal * Math.min(100, discountValue)) / 100)
      : roundMoney(Math.min(discountValue, subtotal));

  const taxableAfterDiscount = roundMoney(Math.max(0, subtotal - discountAmount));
  const taxableAfterAdjustment = roundMoney(Math.max(0, taxableAfterDiscount - adjustmentAmount));
  const gstAmount = roundMoney((taxableAfterAdjustment * gstPercentage) / 100);
  const finalTotal = roundMoney(taxableAfterAdjustment + gstAmount);
  const discountPercentOfSubtotal =
    subtotal > 0 ? roundMoney((discountAmount / subtotal) * 100) : 0;

  return {
    subtotal,
    discountAmount,
    taxableAfterDiscount,
    adjustmentAmount: Math.min(adjustmentAmount, taxableAfterDiscount),
    taxableAfterAdjustment,
    gstAmount,
    finalTotal,
    discountPercentOfSubtotal,
    requiresAuthorization: discountPercentOfSubtotal > maxAuto,
  };
}

export function formatMoneyInr(value: number): string {
  return roundMoney(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
