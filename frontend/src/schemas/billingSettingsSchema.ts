import { z } from 'zod';

/** Official Indian GSTIN pattern (state + PAN + entity + Z + checksum). */
export const GSTIN_REGEX =
  /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;

export const DEFAULT_GST_PERCENTAGE = 18;
/** Default discount on student invoices; 0% is a valid (no discount) setting. */
export const DEFAULT_DISCOUNT_PERCENTAGE = 0;
export const DEFAULT_DISCOUNT_FIXED_AMOUNT = 0;
/** Discounts above this % of subtotal require authorization / hard max on invoices. */
export const DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT = 20;
/** Hard max for fixed ₹ discounts on invoices. */
export const DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT = 10_000;

export const discountTypeSchema = z.enum(['percentage', 'fixed']);
export type DiscountType = z.infer<typeof discountTypeSchema>;
export const DEFAULT_DISCOUNT_TYPE: DiscountType = 'percentage';

export const DEFAULT_DISCOUNT_REASONS = [
  'Early Bird',
  'Referral',
  'Scholarship',
  'Sibling Discount',
  'Loyalty',
  'Promotional Offer',
  'Management Approval',
] as const;

export function normalizeDiscountReasonLabel(value: string): string {
  return value.trim().replace(/\s+/g, ' ').slice(0, 60);
}

export function normalizeDiscountReasons(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [...DEFAULT_DISCOUNT_REASONS];
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of raw) {
    const label = normalizeDiscountReasonLabel(String(item ?? ''));
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push(label);
  }
  return cleaned.length ? cleaned : [...DEFAULT_DISCOUNT_REASONS];
}

/** Indian IFSC: 4 letters + 0 + 6 alphanumeric. */
export const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
/** SWIFT/BIC: 8 or 11 alphanumeric characters. */
export const SWIFT_BIC_REGEX = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
/** IBAN: 2-letter country + 2 check digits + up to 30 alphanumerics. */
export const IBAN_REGEX = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/;

export const invoiceSequenceStrategySchema = z.enum(['continue', 'reset']);

export type InvoiceSequenceStrategy = z.infer<typeof invoiceSequenceStrategySchema>;

export const taxRegimesSchema = z
  .object({
    cgst: z.boolean(),
    sgst: z.boolean(),
    igst: z.boolean(),
    exempt: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.cgst !== values.sgst) {
      ctx.addIssue({
        code: 'custom',
        path: ['cgst'],
        message: 'CGST and SGST must both be on or both off (intra-state pair).',
      });
    }
    if (!values.cgst && !values.sgst && !values.igst && !values.exempt) {
      ctx.addIssue({
        code: 'custom',
        path: ['cgst'],
        message: 'Select at least one tax regime.',
      });
    }
  });

export type TaxRegimesFormValues = z.infer<typeof taxRegimesSchema>;

export const DEFAULT_TAX_REGIMES: TaxRegimesFormValues = {
  cgst: true,
  sgst: true,
  igst: true,
  exempt: false,
};

/** Default matches historic INV-YYYY-0001 style. */
export const DEFAULT_INVOICE_NUMBER_FORMAT = 'INV-{YYYY}-{SEQ:4}';

export const INVOICE_NUMBER_FORMAT_PRESETS = [
  { label: 'INV-YYYY-0001', value: 'INV-{YYYY}-{SEQ:4}' },
  { label: 'INV-YYYY-YY-0001', value: 'INV-{FY}-{SEQ:4}' },
  { label: 'YYYY/0001', value: '{YYYY}/{SEQ:4}' },
  { label: 'NEX-FY-00001', value: 'NEX-{FY}-{SEQ:5}' },
  { label: 'NEX-26-27-00001', value: 'NEX-{FY-FY}-{SEQ:5}' },
] as const;

/** Pattern may use {YYYY}, {YY}, {FY}, {FY-FY}, {SEQ}, {SEQ:1-8}. */
export const INVOICE_NUMBER_FORMAT_PATTERN =
  /^(?:[A-Za-z0-9._/\-]+|\{YYYY\}|\{YY\}|\{FY-FY\}|\{FY\}|\{SEQ(?::[1-8])?\})+$/;

export const invoiceNumberFormatSchema = z
  .string()
  .trim()
  .min(3, 'Invoice format must be at least 3 characters.')
  .max(60, 'Invoice format must be 60 characters or fewer.')
  .refine(
    value => INVOICE_NUMBER_FORMAT_PATTERN.test(value),
    'Use letters, numbers, - _ . /, and tokens {YYYY}, {YY}, {FY}, {FY-FY}, {SEQ}, or {SEQ:4}.'
  )
  .refine(
    value => /\{SEQ(?::[1-8])?\}/.test(value),
    'Include a sequence token such as {SEQ} or {SEQ:4}.'
  );

export function normalizeInvoiceNumberFormat(value: unknown): string {
  if (typeof value !== 'string') return DEFAULT_INVOICE_NUMBER_FORMAT;
  const trimmed = value.trim();
  const parsed = invoiceNumberFormatSchema.safeParse(trimmed);
  return parsed.success ? parsed.data : DEFAULT_INVOICE_NUMBER_FORMAT;
}

export const bankAccountTypeSchema = z.enum(['current', 'savings', 'other']);

export type BankAccountType = z.infer<typeof bankAccountTypeSchema>;

export const DEFAULT_BANK_ACCOUNT_TYPE: BankAccountType = 'current';

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Must be ${max} characters or fewer.`);

export const bankPaymentDetailsSchema = z.object({
  /** Optional display name for this account in Bank Details / invoice picker. */
  accountNickname: optionalText(80).default(''),
  beneficiaryName: optionalText(200),
  bankName: optionalText(200),
  accountNumber: optionalText(40).refine(
    value => !value || /^[0-9A-Za-z\- ]{4,40}$/.test(value),
    'Enter a valid account number (4–40 characters).'
  ),
  accountType: bankAccountTypeSchema,
  ifscCode: z
    .string()
    .trim()
    .transform(value => value.toUpperCase().replace(/\s+/g, ''))
    .refine(
      value => !value || IFSC_REGEX.test(value),
      'Enter a valid 11-character IFSC (e.g. HDFC0001234).'
    ),
  branchNameCity: optionalText(200),
  swiftBicCode: z
    .string()
    .trim()
    .transform(value => value.toUpperCase().replace(/\s+/g, ''))
    .refine(
      value => !value || SWIFT_BIC_REGEX.test(value),
      'Enter a valid 8 or 11-character SWIFT/BIC code.'
    ),
  iban: z
    .string()
    .trim()
    .transform(value => value.toUpperCase().replace(/\s+/g, ''))
    .refine(
      value => !value || IBAN_REGEX.test(value),
      'Enter a valid IBAN (country code + check digits + account identifier).'
    ),
  intermediaryBankDetails: optionalText(1000),
  /** Optional UPI VPA for invoice QR / remittance (e.g. nexus@hdfcbank). */
  upiVpa: z
    .string()
    .trim()
    .max(100)
    .refine(
      value => !value || /^[\w.\-]+@[\w.\-]+$/.test(value),
      'Enter a valid UPI ID (e.g. nexus@hdfcbank).'
    )
    .default(''),
});

export type BankPaymentDetails = z.infer<typeof bankPaymentDetailsSchema>;

export const EMPTY_BANK_PAYMENT_DETAILS: BankPaymentDetails = {
  accountNickname: '',
  beneficiaryName: '',
  bankName: '',
  accountNumber: '',
  accountType: DEFAULT_BANK_ACCOUNT_TYPE,
  ifscCode: '',
  branchNameCity: '',
  swiftBicCode: '',
  iban: '',
  intermediaryBankDetails: '',
  upiVpa: '',
};

export function createEmptyBankPaymentDetails(): BankPaymentDetails {
  return { ...EMPTY_BANK_PAYMENT_DETAILS };
}

export const billingSettingsSchema = z
  .object({
    gstNumber: z
      .string()
      .trim()
      .transform(value => value.toUpperCase())
      .pipe(
        z
          .string()
          .min(1, 'Organization GSTIN is required.')
          .regex(GSTIN_REGEX, 'Enter a valid 15-character Indian GSTIN (e.g. 27AABCU9603R1ZM).')
      ),
    gstPercentage: z.coerce
      .number()
      .min(0, 'GST percentage cannot be less than 0%.')
      .max(100, 'GST percentage cannot be more than 100%.'),
    discountType: discountTypeSchema,
    discountPercentage: z.coerce
      .number()
      .min(0, 'Discount percentage cannot be less than 0%.')
      .max(100, 'Discount percentage cannot be more than 100%.'),
    discountFixedAmount: z.coerce
      .number()
      .min(0, 'Fixed discount cannot be negative.')
      .max(1_000_000, 'Fixed discount is too large.')
      .refine(value => value % 100 === 0, {
        message: 'Fixed discount must be in steps of ₹100.',
      }),
    defaultDiscountReason: z.string().trim().min(1, 'Select a default discount reason.'),
    discountReasons: z
      .array(z.string().trim().min(1).max(60))
      .min(1, 'Keep at least one discount reason.')
      .max(40),
    maxAutoApproveDiscountPercent: z.coerce
      .number()
      .min(0, 'Max discount % cannot be less than 0%.')
      .max(100, 'Max discount % cannot be more than 100%.'),
    maxDiscountFixedAmount: z.coerce
      .number()
      .min(0, 'Max fixed discount cannot be negative.')
      .max(1_000_000, 'Max fixed discount is too large.')
      .refine(value => value % 100 === 0, {
        message: 'Max fixed discount must be in steps of ₹100.',
      }),
    invoiceSequenceStrategy: invoiceSequenceStrategySchema,
    invoiceNumberFormat: invoiceNumberFormatSchema,
    taxRegimes: taxRegimesSchema,
    bankPayments: z.array(bankPaymentDetailsSchema).min(1).max(20),
  })
  .superRefine((values, ctx) => {
    const reasons = normalizeDiscountReasons(values.discountReasons);
    if (!reasons.some(reason => reason.toLowerCase() === values.defaultDiscountReason.toLowerCase())) {
      ctx.addIssue({
        code: 'custom',
        path: ['defaultDiscountReason'],
        message: 'Default reason must be one of the allowed discount reasons.',
      });
    }
    if (values.discountPercentage > values.maxAutoApproveDiscountPercent) {
      ctx.addIssue({
        code: 'custom',
        path: ['discountPercentage'],
        message: 'Default discount % cannot exceed the max discount %.',
      });
    }
    if (values.discountFixedAmount > values.maxDiscountFixedAmount) {
      ctx.addIssue({
        code: 'custom',
        path: ['discountFixedAmount'],
        message: 'Default fixed discount cannot exceed the max fixed amount.',
      });
    }
  });

export type BillingSettingsFormValues = z.infer<typeof billingSettingsSchema>;

/** Live invoice adjustment calculator (not persisted with Save billing settings). */
export const invoiceAdjustmentPreviewSchema = z
  .object({
    subtotal: z.coerce.number().min(0, 'Subtotal cannot be negative.'),
    discountType: discountTypeSchema,
    discountValue: z.coerce.number().min(0, 'Discount cannot be negative.'),
    discountReason: z.string().trim().min(1, 'Select a discount reason.'),
    adjustmentAmount: z.coerce.number().min(0, 'Adjustment cannot be negative.'),
    adjustmentNote: z.string().trim().max(200).optional().default(''),
  })
  .superRefine((values, ctx) => {
    if (values.discountType === 'percentage' && values.discountValue > 100) {
      ctx.addIssue({
        code: 'custom',
        path: ['discountValue'],
        message: 'Percentage discount cannot exceed 100%.',
      });
    }
  });

export type InvoiceAdjustmentPreviewValues = z.infer<typeof invoiceAdjustmentPreviewSchema>;

export function isValidGstin(value: string): boolean {
  return GSTIN_REGEX.test(value.trim().toUpperCase());
}

export function clampGstPercentage(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_GST_PERCENTAGE;
  return Math.min(100, Math.max(0, value));
}

export function clampDiscountPercentage(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_DISCOUNT_PERCENTAGE;
  return Math.min(100, Math.max(0, value));
}

export function clampDiscountFixedAmount(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_DISCOUNT_FIXED_AMOUNT;
  const rounded = Math.round(Math.max(0, value) / 100) * 100;
  return Math.min(1_000_000, rounded);
}

export function clampMaxAutoApproveDiscountPercent(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT;
  return Math.min(100, Math.max(0, value));
}

export function clampMaxDiscountFixedAmount(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT;
  const rounded = Math.round(Math.max(0, value) / 100) * 100;
  return Math.min(1_000_000, rounded);
}

export function normalizeBankPaymentDetails(
  raw: Partial<BankPaymentDetails> | null | undefined
): BankPaymentDetails {
  const parsed = bankPaymentDetailsSchema.safeParse({
    ...EMPTY_BANK_PAYMENT_DETAILS,
    ...(raw ?? {}),
  });
  return parsed.success ? parsed.data : createEmptyBankPaymentDetails();
}

/** Accepts a list, a legacy single object, or empty → always returns 1–20 entries. */
export function normalizeBankPaymentList(raw: unknown): BankPaymentDetails[] {
  if (Array.isArray(raw)) {
    const entries = raw
      .filter(item => item && typeof item === 'object')
      .map(item => normalizeBankPaymentDetails(item as Partial<BankPaymentDetails>));
    return entries.length > 0 ? entries.slice(0, 20) : [createEmptyBankPaymentDetails()];
  }
  if (raw && typeof raw === 'object') {
    return [normalizeBankPaymentDetails(raw as Partial<BankPaymentDetails>)];
  }
  return [createEmptyBankPaymentDetails()];
}
