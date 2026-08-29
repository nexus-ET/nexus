import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  DEFAULT_EMAIL_CONTACT_TYPES,
  DEFAULT_PHONE_CONTACT_TYPES,
  normalizeContactTypeLabel,
  toContactTypeOptions,
  type ContactTypeOption,
} from '../constants/contactTypes';
import {
  createEmptyBankPaymentDetails,
  DEFAULT_DISCOUNT_FIXED_AMOUNT,
  DEFAULT_DISCOUNT_PERCENTAGE,
  DEFAULT_DISCOUNT_REASONS,
  DEFAULT_DISCOUNT_TYPE,
  DEFAULT_GST_PERCENTAGE,
  DEFAULT_INVOICE_NUMBER_FORMAT,
  DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT,
  DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT,
  DEFAULT_TAX_REGIMES,
  normalizeBankPaymentList,
  normalizeDiscountReasonLabel,
  normalizeDiscountReasons,
  normalizeInvoiceNumberFormat,
  type BankPaymentDetails,
  type DiscountType,
  type InvoiceSequenceStrategy,
  type TaxRegimesFormValues,
} from '../schemas/billingSettingsSchema';
import {
  DEFAULT_FEE_CATALOG,
  normalizeFeeCatalog,
  type FeeCatalog,
} from '../schemas/feeCatalogSchema';
import { RECOVERED_FEE_CATALOG } from '../schemas/feeCatalogRecovery';
import {
  applyIssuedInvoice,
  previewNextInvoiceId,
  resolveNextInvoiceAllocation,
} from '../utils/invoiceSequence';
import { normalizeTaxRegimes } from '../utils/taxRegimes';

export type AdminBillingSettings = {
  gstNumber: string;
  /** GST rate applied on student invoices (0–100). Default 18%. */
  gstPercentage: number;
  /** Which GST regimes are available for invoicing. */
  taxRegimes: TaxRegimesFormValues;
  /** Default discount mode for student invoices. */
  discountType: DiscountType;
  /** Default discount applied on student invoices (0–100). Default 0%. */
  discountPercentage: number;
  /** Default fixed discount amount when discountType is fixed. */
  discountFixedAmount: number;
  /** Allowed discount reason labels. */
  discountReasons: string[];
  /** Default selected discount reason. */
  defaultDiscountReason: string;
  /** Discounts above this % of subtotal require authorization / hard max on invoices. */
  maxAutoApproveDiscountPercent: number;
  /** Hard max for fixed ₹ discounts on invoices. */
  maxDiscountFixedAmount: number;
  invoiceSequenceStrategy: InvoiceSequenceStrategy;
  /** Pattern for rendered invoice ids, e.g. INV-{YYYY}-{SEQ:4}. */
  invoiceNumberFormat: string;
  /** Domestic + international bank accounts shown on invoices. */
  bankPayments: BankPaymentDetails[];
  /** Base price catalog: list prices (INR) and packages for student invoicing. */
  feeCatalog: FeeCatalog;
  /** Last issued invoice sequence within / across FYs depending on strategy. */
  lastInvoiceSequence: number;
  lastInvoiceFinancialYearStart: number | null;
};

export type ContactTypeKind = 'email' | 'phone';

type AdminSettingsState = AdminBillingSettings & {
  billingSavedAt: string | null;
  emailContactTypes: string[];
  phoneContactTypes: string[];
  setGstNumber: (gstNumber: string) => void;
  setGstPercentage: (gstPercentage: number) => void;
  setDiscountPercentage: (discountPercentage: number) => void;
  setInvoiceSequenceStrategy: (strategy: InvoiceSequenceStrategy) => void;
  saveBillingSettings: (payload: {
    gstNumber: string;
    gstPercentage: number;
    taxRegimes: TaxRegimesFormValues;
    discountType: DiscountType;
    discountPercentage: number;
    discountFixedAmount: number;
    discountReasons: string[];
    defaultDiscountReason: string;
    maxAutoApproveDiscountPercent: number;
    maxDiscountFixedAmount: number;
    invoiceSequenceStrategy: InvoiceSequenceStrategy;
    invoiceNumberFormat: string;
    bankPayments: BankPaymentDetails[];
  }) => void;
  saveFeeCatalog: (feeCatalog: FeeCatalog) => void;
  /** Allocate next invoice id for Student Invoice Generator and persist counters. */
  allocateNextInvoiceId: (now?: Date) => string;
  previewNextInvoiceId: (now?: Date) => string;
  getOrganizationGstin: () => string;
  getGstPercentage: () => number;
  getDiscountPercentage: () => number;
  getMaxAutoApproveDiscountPercent: () => number;
  getMaxDiscountFixedAmount: () => number;
  getDiscountReasons: () => string[];
  getFeeCatalog: () => FeeCatalog;
  addDiscountReason: (label: string) => { ok: true } | { ok: false; error: string };
  removeDiscountReason: (index: number) => { ok: true } | { ok: false; error: string };
  addEmailType: (label: string) => { ok: true } | { ok: false; error: string };
  updateEmailType: (
    index: number,
    label: string
  ) => { ok: true } | { ok: false; error: string };
  removeEmailType: (index: number) => { ok: true } | { ok: false; error: string };
  addPhoneType: (label: string) => { ok: true } | { ok: false; error: string };
  updatePhoneType: (
    index: number,
    label: string
  ) => { ok: true } | { ok: false; error: string };
  removePhoneType: (index: number) => { ok: true } | { ok: false; error: string };
  resetEmailTypesToDefaults: () => void;
  resetPhoneTypesToDefaults: () => void;
  getEmailContactTypeOptions: () => ContactTypeOption[];
  getPhoneContactTypeOptions: () => ContactTypeOption[];
};

const DEFAULT_BILLING: AdminBillingSettings = {
  gstNumber: '',
  gstPercentage: DEFAULT_GST_PERCENTAGE,
  taxRegimes: { ...DEFAULT_TAX_REGIMES },
  discountType: DEFAULT_DISCOUNT_TYPE,
  discountPercentage: DEFAULT_DISCOUNT_PERCENTAGE,
  discountFixedAmount: DEFAULT_DISCOUNT_FIXED_AMOUNT,
  discountReasons: [...DEFAULT_DISCOUNT_REASONS],
  defaultDiscountReason: DEFAULT_DISCOUNT_REASONS[0],
  maxAutoApproveDiscountPercent: DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT,
  maxDiscountFixedAmount: DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT,
  invoiceSequenceStrategy: 'continue',
  invoiceNumberFormat: DEFAULT_INVOICE_NUMBER_FORMAT,
  bankPayments: [createEmptyBankPaymentDetails()],
  feeCatalog: {
    currency: DEFAULT_FEE_CATALOG.currency,
    services: DEFAULT_FEE_CATALOG.services.map(service => ({ ...service })),
    bundles: DEFAULT_FEE_CATALOG.bundles.map(bundle => ({
      ...bundle,
      serviceIds: [...bundle.serviceIds],
    })),
  },
  lastInvoiceSequence: 0,
  lastInvoiceFinancialYearStart: null,
};

const DEFAULT_EMAIL_TYPES = [...DEFAULT_EMAIL_CONTACT_TYPES];
const DEFAULT_PHONE_TYPES = [...DEFAULT_PHONE_CONTACT_TYPES];

function sanitizeTypeList(raw: unknown, fallback: string[]): string[] {
  if (!Array.isArray(raw)) return [...fallback];
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of raw) {
    const label = normalizeContactTypeLabel(String(item ?? ''));
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push(label);
  }
  return cleaned.length ? cleaned : [...fallback];
}

function addTypeToList(
  list: string[],
  label: string
): { ok: true; next: string[] } | { ok: false; error: string } {
  const cleaned = normalizeContactTypeLabel(label);
  if (!cleaned) {
    return { ok: false, error: 'Enter a contact type name.' };
  }
  if (cleaned.length > 60) {
    return { ok: false, error: 'Contact type must be 60 characters or fewer.' };
  }
  if (list.some(item => item.toLowerCase() === cleaned.toLowerCase())) {
    return { ok: false, error: 'That contact type already exists.' };
  }
  return { ok: true, next: [...list, cleaned] };
}

function updateTypeInList(
  list: string[],
  index: number,
  label: string
): { ok: true; next: string[] } | { ok: false; error: string } {
  if (index < 0 || index >= list.length) {
    return { ok: false, error: 'Contact type not found.' };
  }
  const cleaned = normalizeContactTypeLabel(label);
  if (!cleaned) {
    return { ok: false, error: 'Enter a contact type name.' };
  }
  if (cleaned.length > 60) {
    return { ok: false, error: 'Contact type must be 60 characters or fewer.' };
  }
  if (
    list.some(
      (item, itemIndex) =>
        itemIndex !== index && item.toLowerCase() === cleaned.toLowerCase()
    )
  ) {
    return { ok: false, error: 'That contact type already exists.' };
  }
  const next = [...list];
  next[index] = cleaned;
  return { ok: true, next };
}

function removeTypeFromList(
  list: string[],
  index: number
): { ok: true; next: string[] } | { ok: false; error: string } {
  if (index < 0 || index >= list.length) {
    return { ok: false, error: 'Contact type not found.' };
  }
  if (list.length <= 1) {
    return { ok: false, error: 'Keep at least one contact type.' };
  }
  return { ok: true, next: list.filter((_, itemIndex) => itemIndex !== index) };
}

export const useAdminSettingsStore = create<AdminSettingsState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_BILLING,
      billingSavedAt: null,
      emailContactTypes: DEFAULT_EMAIL_TYPES,
      phoneContactTypes: DEFAULT_PHONE_TYPES,

      setGstNumber: gstNumber => set({ gstNumber: gstNumber.toUpperCase() }),

      setGstPercentage: gstPercentage =>
        set({
          gstPercentage: Math.min(100, Math.max(0, gstPercentage)),
        }),

      setDiscountPercentage: discountPercentage =>
        set({
          discountPercentage: Math.min(100, Math.max(0, discountPercentage)),
        }),

      setInvoiceSequenceStrategy: invoiceSequenceStrategy => set({ invoiceSequenceStrategy }),

      saveBillingSettings: ({
        gstNumber,
        gstPercentage,
        taxRegimes,
        discountType,
        discountPercentage,
        discountFixedAmount,
        discountReasons,
        defaultDiscountReason,
        maxAutoApproveDiscountPercent,
        maxDiscountFixedAmount,
        invoiceSequenceStrategy,
        invoiceNumberFormat,
        bankPayments,
      }) => {
        const reasons = normalizeDiscountReasons(discountReasons);
        const reason =
          normalizeDiscountReasonLabel(defaultDiscountReason) ||
          reasons[0] ||
          DEFAULT_DISCOUNT_REASONS[0];
        const resolvedReason = reasons.some(item => item.toLowerCase() === reason.toLowerCase())
          ? reasons.find(item => item.toLowerCase() === reason.toLowerCase()) || reasons[0]
          : reasons[0];
        set({
          gstNumber: gstNumber.trim().toUpperCase(),
          gstPercentage: Math.min(100, Math.max(0, gstPercentage)),
          taxRegimes: normalizeTaxRegimes(taxRegimes),
          discountType: discountType === 'fixed' ? 'fixed' : 'percentage',
          discountPercentage: Math.min(100, Math.max(0, discountPercentage)),
          discountFixedAmount: Math.min(
            1_000_000,
            Math.round(Math.max(0, discountFixedAmount) / 100) * 100
          ),
          discountReasons: reasons,
          defaultDiscountReason: resolvedReason,
          maxAutoApproveDiscountPercent: Math.min(
            100,
            Math.max(0, maxAutoApproveDiscountPercent)
          ),
          maxDiscountFixedAmount: Math.min(
            1_000_000,
            Math.round(Math.max(0, maxDiscountFixedAmount) / 100) * 100
          ),
          invoiceSequenceStrategy,
          invoiceNumberFormat: normalizeInvoiceNumberFormat(invoiceNumberFormat),
          bankPayments: normalizeBankPaymentList(bankPayments),
          billingSavedAt: new Date().toISOString(),
        });
      },

      saveFeeCatalog: feeCatalog => {
        set({
          feeCatalog: normalizeFeeCatalog(feeCatalog),
          billingSavedAt: new Date().toISOString(),
        });
      },

      allocateNextInvoiceId: (now = new Date()) => {
        const state = get();
        const { invoiceId, nextState } = applyIssuedInvoice(
          {
            strategy: state.invoiceSequenceStrategy,
            lastInvoiceSequence: state.lastInvoiceSequence,
            lastInvoiceFinancialYearStart: state.lastInvoiceFinancialYearStart,
            invoiceNumberFormat: state.invoiceNumberFormat,
          },
          now
        );
        set({
          lastInvoiceSequence: nextState.lastInvoiceSequence,
          lastInvoiceFinancialYearStart: nextState.lastInvoiceFinancialYearStart,
        });
        return invoiceId;
      },

      previewNextInvoiceId: (now = new Date()) => {
        const state = get();
        return previewNextInvoiceId(
          state.invoiceSequenceStrategy,
          state.lastInvoiceSequence,
          state.lastInvoiceFinancialYearStart,
          now,
          state.invoiceNumberFormat
        );
      },

      getOrganizationGstin: () => get().gstNumber.trim().toUpperCase(),

      getGstPercentage: () => {
        const value = get().gstPercentage;
        if (!Number.isFinite(value)) return DEFAULT_GST_PERCENTAGE;
        return Math.min(100, Math.max(0, value));
      },

      getDiscountPercentage: () => {
        const value = get().discountPercentage;
        if (!Number.isFinite(value)) return DEFAULT_DISCOUNT_PERCENTAGE;
        return Math.min(100, Math.max(0, value));
      },

      getMaxAutoApproveDiscountPercent: () => {
        const value = get().maxAutoApproveDiscountPercent;
        if (!Number.isFinite(value)) return DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT;
        return Math.min(100, Math.max(0, value));
      },

      getMaxDiscountFixedAmount: () => {
        const value = get().maxDiscountFixedAmount;
        if (!Number.isFinite(value)) return DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT;
        return Math.min(1_000_000, Math.max(0, value));
      },

      getDiscountReasons: () => normalizeDiscountReasons(get().discountReasons),

      getFeeCatalog: () => normalizeFeeCatalog(get().feeCatalog),

      addDiscountReason: label => {
        const cleaned = normalizeDiscountReasonLabel(label);
        if (!cleaned) return { ok: false, error: 'Enter a discount reason.' };
        const current = normalizeDiscountReasons(get().discountReasons);
        if (current.some(item => item.toLowerCase() === cleaned.toLowerCase())) {
          return { ok: false, error: 'That discount reason already exists.' };
        }
        if (current.length >= 40) {
          return { ok: false, error: 'You can add at most 40 discount reasons.' };
        }
        set({ discountReasons: [...current, cleaned] });
        return { ok: true };
      },

      removeDiscountReason: index => {
        const current = normalizeDiscountReasons(get().discountReasons);
        if (index < 0 || index >= current.length) {
          return { ok: false, error: 'Discount reason not found.' };
        }
        if (current.length <= 1) {
          return { ok: false, error: 'Keep at least one discount reason.' };
        }
        const removed = current[index];
        const next = current.filter((_, itemIndex) => itemIndex !== index);
        const defaultReason =
          get().defaultDiscountReason.toLowerCase() === removed.toLowerCase()
            ? next[0]
            : get().defaultDiscountReason;
        set({ discountReasons: next, defaultDiscountReason: defaultReason });
        return { ok: true };
      },

      addEmailType: label => {
        const result = addTypeToList(get().emailContactTypes, label);
        if (!result.ok) return result;
        set({ emailContactTypes: result.next });
        return { ok: true };
      },

      updateEmailType: (index, label) => {
        const result = updateTypeInList(get().emailContactTypes, index, label);
        if (!result.ok) return result;
        set({ emailContactTypes: result.next });
        return { ok: true };
      },

      removeEmailType: index => {
        const result = removeTypeFromList(get().emailContactTypes, index);
        if (!result.ok) return result;
        set({ emailContactTypes: result.next });
        return { ok: true };
      },

      addPhoneType: label => {
        const result = addTypeToList(get().phoneContactTypes, label);
        if (!result.ok) return result;
        set({ phoneContactTypes: result.next });
        return { ok: true };
      },

      updatePhoneType: (index, label) => {
        const result = updateTypeInList(get().phoneContactTypes, index, label);
        if (!result.ok) return result;
        set({ phoneContactTypes: result.next });
        return { ok: true };
      },

      removePhoneType: index => {
        const result = removeTypeFromList(get().phoneContactTypes, index);
        if (!result.ok) return result;
        set({ phoneContactTypes: result.next });
        return { ok: true };
      },

      resetEmailTypesToDefaults: () => set({ emailContactTypes: [...DEFAULT_EMAIL_TYPES] }),

      resetPhoneTypesToDefaults: () => set({ phoneContactTypes: [...DEFAULT_PHONE_TYPES] }),

      getEmailContactTypeOptions: () => toContactTypeOptions(get().emailContactTypes),

      getPhoneContactTypeOptions: () => toContactTypeOptions(get().phoneContactTypes),
    }),
    {
      name: 'nexus.admin-settings',
      version: 10,
      partialize: state => ({
        gstNumber: state.gstNumber,
        gstPercentage: state.gstPercentage,
        taxRegimes: state.taxRegimes,
        discountType: state.discountType,
        discountPercentage: state.discountPercentage,
        discountFixedAmount: state.discountFixedAmount,
        discountReasons: state.discountReasons,
        defaultDiscountReason: state.defaultDiscountReason,
        maxAutoApproveDiscountPercent: state.maxAutoApproveDiscountPercent,
        maxDiscountFixedAmount: state.maxDiscountFixedAmount,
        invoiceSequenceStrategy: state.invoiceSequenceStrategy,
        invoiceNumberFormat: state.invoiceNumberFormat,
        bankPayments: state.bankPayments,
        feeCatalog: state.feeCatalog,
        lastInvoiceSequence: state.lastInvoiceSequence,
        lastInvoiceFinancialYearStart: state.lastInvoiceFinancialYearStart,
        billingSavedAt: state.billingSavedAt,
        emailContactTypes: state.emailContactTypes,
        phoneContactTypes: state.phoneContactTypes,
      }),
      migrate: (persisted, version) => {
        const saved = (persisted ?? {}) as Record<string, unknown>;
        let next = { ...saved };
        if (version < 2) {
          next = {
            ...next,
            emailContactTypes: sanitizeTypeList(saved.emailContactTypes, DEFAULT_EMAIL_TYPES),
            phoneContactTypes: sanitizeTypeList(saved.phoneContactTypes, DEFAULT_PHONE_TYPES),
          };
        }
        if (version < 3) {
          next = {
            ...next,
            feeCatalog: normalizeFeeCatalog(saved.feeCatalog),
          };
        }
        if (version < 4) {
          // Restore the original simple Base Price Catalog seed (8 services + 2 packages).
          next = {
            ...next,
            feeCatalog: {
              currency: DEFAULT_FEE_CATALOG.currency,
              services: DEFAULT_FEE_CATALOG.services.map(service => ({ ...service })),
              bundles: DEFAULT_FEE_CATALOG.bundles.map(bundle => ({
                ...bundle,
                serviceIds: [...bundle.serviceIds],
              })),
            },
          };
        }
        if (version < 5) {
          // Replace repeated process-level blurbs with unique per-service descriptions.
          next = {
            ...next,
            feeCatalog: normalizeFeeCatalog(next.feeCatalog ?? saved.feeCatalog),
          };
        }
        if (version < 6) {
          // Refresh all service descriptions to the curated / name-aware copy.
          next = {
            ...next,
            feeCatalog: normalizeFeeCatalog(next.feeCatalog ?? saved.feeCatalog),
          };
        }
        if (version < 7) {
          // Restore catalog recovered after accidental Reset to Nexus defaults.
          next = {
            ...next,
            feeCatalog: normalizeFeeCatalog(RECOVERED_FEE_CATALOG),
            billingSavedAt: new Date().toISOString(),
          };
        }
        if (version < 8) {
          next = {
            ...next,
            taxRegimes: normalizeTaxRegimes(next.taxRegimes ?? saved.taxRegimes),
          };
        }
        if (version < 10) {
          // Restart invoice numbering at 1 after test-data wipe.
          next = {
            ...next,
            lastInvoiceSequence: 0,
            lastInvoiceFinancialYearStart: null,
          };
        }
        return next;
      },
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<AdminBillingSettings> & {
          billingSavedAt?: string | null;
          emailContactTypes?: unknown;
          phoneContactTypes?: unknown;
          feeCatalog?: unknown;
        };

        // One-time pull from the previous billing-only persist key.
        let legacyBilling: Partial<AdminBillingSettings> & { billingSavedAt?: string | null } =
          {};
        try {
          const raw = localStorage.getItem('nexus.admin-billing-settings');
          if (raw) {
            const parsed = JSON.parse(raw) as { state?: Record<string, unknown> };
            legacyBilling = (parsed.state ?? {}) as typeof legacyBilling;
          }
        } catch {
          /* ignore corrupt legacy */
        }

        const gstPercentageRaw =
          typeof saved.gstPercentage === 'number'
            ? saved.gstPercentage
            : typeof legacyBilling.gstPercentage === 'number'
              ? legacyBilling.gstPercentage
              : DEFAULT_GST_PERCENTAGE;
        const gstPercentage = Number.isFinite(gstPercentageRaw)
          ? Math.min(100, Math.max(0, gstPercentageRaw))
          : DEFAULT_GST_PERCENTAGE;

        const discountPercentageRaw =
          typeof saved.discountPercentage === 'number'
            ? saved.discountPercentage
            : typeof legacyBilling.discountPercentage === 'number'
              ? legacyBilling.discountPercentage
              : DEFAULT_DISCOUNT_PERCENTAGE;
        const discountPercentage = Number.isFinite(discountPercentageRaw)
          ? Math.min(100, Math.max(0, discountPercentageRaw))
          : DEFAULT_DISCOUNT_PERCENTAGE;

        const savedRecord = saved as Partial<AdminBillingSettings> & {
          bankPayment?: BankPaymentDetails;
          billingSavedAt?: string | null;
          emailContactTypes?: unknown;
          phoneContactTypes?: unknown;
        };
        const legacyRecord = legacyBilling as Partial<AdminBillingSettings> & {
          bankPayment?: BankPaymentDetails;
        };
        const bankPayments = normalizeBankPaymentList(
          savedRecord.bankPayments ??
            savedRecord.bankPayment ??
            legacyRecord.bankPayments ??
            legacyRecord.bankPayment
        );

        const invoiceNumberFormat = normalizeInvoiceNumberFormat(
          savedRecord.invoiceNumberFormat ?? legacyRecord.invoiceNumberFormat
        );

        const discountReasons = normalizeDiscountReasons(
          savedRecord.discountReasons ?? legacyRecord.discountReasons
        );
        const defaultDiscountReasonRaw = normalizeDiscountReasonLabel(
          String(
            savedRecord.defaultDiscountReason ??
              legacyRecord.defaultDiscountReason ??
              discountReasons[0] ??
              ''
          )
        );
        const defaultDiscountReason = discountReasons.some(
          reason => reason.toLowerCase() === defaultDiscountReasonRaw.toLowerCase()
        )
          ? discountReasons.find(
              reason => reason.toLowerCase() === defaultDiscountReasonRaw.toLowerCase()
            ) || discountReasons[0]
          : discountReasons[0];

        const discountTypeRaw = savedRecord.discountType ?? legacyRecord.discountType;
        const discountType: DiscountType =
          discountTypeRaw === 'fixed' ? 'fixed' : DEFAULT_DISCOUNT_TYPE;

        const discountFixedRaw =
          typeof savedRecord.discountFixedAmount === 'number'
            ? savedRecord.discountFixedAmount
            : typeof legacyRecord.discountFixedAmount === 'number'
              ? legacyRecord.discountFixedAmount
              : DEFAULT_DISCOUNT_FIXED_AMOUNT;
        const discountFixedAmount = Number.isFinite(discountFixedRaw)
          ? Math.min(1_000_000, Math.round(Math.max(0, discountFixedRaw) / 100) * 100)
          : DEFAULT_DISCOUNT_FIXED_AMOUNT;

        const maxAutoRaw =
          typeof savedRecord.maxAutoApproveDiscountPercent === 'number'
            ? savedRecord.maxAutoApproveDiscountPercent
            : typeof legacyRecord.maxAutoApproveDiscountPercent === 'number'
              ? legacyRecord.maxAutoApproveDiscountPercent
              : DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT;
        const maxAutoApproveDiscountPercent = Number.isFinite(maxAutoRaw)
          ? Math.min(100, Math.max(0, maxAutoRaw))
          : DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT;

        const maxFixedRaw =
          typeof savedRecord.maxDiscountFixedAmount === 'number'
            ? savedRecord.maxDiscountFixedAmount
            : typeof legacyRecord.maxDiscountFixedAmount === 'number'
              ? legacyRecord.maxDiscountFixedAmount
              : DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT;
        const maxDiscountFixedAmount = Number.isFinite(maxFixedRaw)
          ? Math.min(1_000_000, Math.round(Math.max(0, maxFixedRaw) / 100) * 100)
          : DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT;

        return {
          ...current,
          ...legacyBilling,
          ...saved,
          gstPercentage,
          taxRegimes: normalizeTaxRegimes(
            savedRecord.taxRegimes ?? (legacyBilling as { taxRegimes?: unknown }).taxRegimes
          ),
          discountPercentage,
          discountType,
          discountFixedAmount,
          discountReasons,
          defaultDiscountReason,
          maxAutoApproveDiscountPercent,
          maxDiscountFixedAmount,
          bankPayments,
          feeCatalog: normalizeFeeCatalog(
            saved.feeCatalog ?? (legacyBilling as { feeCatalog?: unknown }).feeCatalog
          ),
          invoiceNumberFormat,
          emailContactTypes: sanitizeTypeList(saved.emailContactTypes, DEFAULT_EMAIL_TYPES),
          phoneContactTypes: sanitizeTypeList(saved.phoneContactTypes, DEFAULT_PHONE_TYPES),
        };
      },
    }
  )
);

/** Non-hook accessor for invoice generator modules. */
export function getAdminBillingSnapshot(): AdminBillingSettings & {
  nextInvoicePreview: string;
  nextAllocation: ReturnType<typeof resolveNextInvoiceAllocation>;
} {
  const state = useAdminSettingsStore.getState();
  const nextAllocation = resolveNextInvoiceAllocation({
    strategy: state.invoiceSequenceStrategy,
    lastInvoiceSequence: state.lastInvoiceSequence,
    lastInvoiceFinancialYearStart: state.lastInvoiceFinancialYearStart,
    invoiceNumberFormat: state.invoiceNumberFormat,
  });
  return {
    gstNumber: state.gstNumber,
    gstPercentage: state.getGstPercentage(),
    taxRegimes: normalizeTaxRegimes(state.taxRegimes),
    discountType: state.discountType === 'fixed' ? 'fixed' : 'percentage',
    discountPercentage: state.getDiscountPercentage(),
    discountFixedAmount: Math.min(1_000_000, Math.max(0, state.discountFixedAmount || 0)),
    discountReasons: state.getDiscountReasons(),
    defaultDiscountReason: state.defaultDiscountReason,
    maxAutoApproveDiscountPercent: state.getMaxAutoApproveDiscountPercent(),
    maxDiscountFixedAmount: state.getMaxDiscountFixedAmount(),
    invoiceSequenceStrategy: state.invoiceSequenceStrategy,
    invoiceNumberFormat: normalizeInvoiceNumberFormat(state.invoiceNumberFormat),
    bankPayments: normalizeBankPaymentList(state.bankPayments),
    feeCatalog: state.getFeeCatalog(),
    lastInvoiceSequence: state.lastInvoiceSequence,
    lastInvoiceFinancialYearStart: state.lastInvoiceFinancialYearStart,
    nextInvoicePreview: nextAllocation.invoiceId,
    nextAllocation,
  };
}

export function getConfiguredEmailContactTypes(): string[] {
  return [...useAdminSettingsStore.getState().emailContactTypes];
}

export function getConfiguredPhoneContactTypes(): string[] {
  return [...useAdminSettingsStore.getState().phoneContactTypes];
}
