import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Controller,
  useFieldArray,
  useForm,
  type FieldErrors,
  type UseFormRegister,
} from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Building2,
  CheckCircle2,
  FileText,
  Globe2,
  Landmark,
  ListOrdered,
  Loader2,
  Percent,
  Plus,
  Receipt,
  Save,
  Trash2,
} from 'lucide-react';
import BasePriceCatalogPanel from './BasePriceCatalogPanel';
import {
  billingSettingsSchema,
  clampDiscountFixedAmount,
  clampDiscountPercentage,
  clampGstPercentage,
  clampMaxAutoApproveDiscountPercent,
  clampMaxDiscountFixedAmount,
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
  INVOICE_NUMBER_FORMAT_PRESETS,
  isValidGstin,
  normalizeBankPaymentList,
  normalizeDiscountReasonLabel,
  normalizeDiscountReasons,
  type BillingSettingsFormValues,
} from '../../schemas/billingSettingsSchema';
import { useAdminSettingsStore } from '../../stores/adminSettingsStore';
import {
  getIndianFinancialYearStart,
  previewNextInvoiceId,
} from '../../utils/invoiceSequence';
import {
  coupleCgstSgst,
  formatTaxRegimePreview,
  normalizeTaxRegimes,
  type TaxRegimes,
} from '../../utils/taxRegimes';

const gstinInputClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary uppercase tracking-wide font-mono';

const fieldInputClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary';

const discountControlClass =
  'box-border h-10 w-full rounded-xl border border-border-subtle bg-surface-bg px-3 text-sm text-text-main outline-none focus:border-primary';

const monoInputClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary uppercase tracking-wide font-mono';

type FormValues = BillingSettingsFormValues;

export type BillingSectionId =
  | 'base-price-catalog'
  | 'invoice-format'
  | 'organization-gstin'
  | 'discount-policy'
  | 'bank-details';

export const DEFAULT_BILLING_SECTION: BillingSectionId = 'base-price-catalog';

const BILLING_SECTIONS: Array<{
  id: BillingSectionId;
  label: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    id: 'base-price-catalog',
    label: 'Base Price Catalog',
    description:
      'INR list prices and packages that anchor student invoice calculations (ex-GST).',
    icon: <ListOrdered size={13} strokeWidth={2.25} />,
  },
  {
    id: 'invoice-format',
    label: 'Invoice Format',
    description: 'Invoice number pattern, FY reset strategy, and next ID preview.',
    icon: <FileText size={13} strokeWidth={2.25} />,
  },
  {
    id: 'organization-gstin',
    label: 'GST & Tax',
    description: 'GSTIN, default GST rate, and active tax regimes for student invoices.',
    icon: <Building2 size={13} strokeWidth={2.25} />,
  },
  {
    id: 'discount-policy',
    label: 'Discount Policy',
    description: 'Default discount, reasons, and auto-approve threshold.',
    icon: <Percent size={13} strokeWidth={2.25} />,
  },
  {
    id: 'bank-details',
    label: 'Bank Details',
    description: 'Bank accounts shown on invoices for students and sponsors.',
    icon: <Landmark size={13} strokeWidth={2.25} />,
  },
];

export function isBillingSectionId(value: string | null): value is BillingSectionId {
  return BILLING_SECTIONS.some(section => section.id === value);
}

const panelClass =
  'flex h-full min-h-0 flex-col gap-3 rounded-xl border border-border-subtle bg-surface-bg/50 p-3';

const panelLabelClass = 'block min-h-5 text-sm font-medium leading-5 text-text-main';

const panelHintClass = 'min-h-8 text-xs leading-4 text-text-muted';

const BANK_ACCOUNT_TYPE_OPTIONS = [
  { value: 'current', label: 'Current Account' },
  { value: 'savings', label: 'Savings Account' },
  { value: 'other', label: 'Other' },
] as const;

type BankAccountCardProps = {
  index: number;
  total: number;
  register: UseFormRegister<FormValues>;
  errors: FieldErrors<FormValues>;
  onRemove: () => void;
};

const BankAccountCard: React.FC<BankAccountCardProps> = ({
  index,
  total,
  register,
  errors,
  onRemove,
}) => {
  const entryErrors = errors.bankPayments?.[index];
  const prefix = `bankPayments.${index}` as const;

  return (
    <div className="space-y-5 rounded-xl border border-border-subtle bg-card p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5 sm:max-w-sm">
          <label
            htmlFor={`${prefix}-account-nickname`}
            className="block text-sm font-medium text-text-main"
          >
            Account / nick name
          </label>
          <input
            id={`${prefix}-account-nickname`}
            type="text"
            maxLength={80}
            placeholder={`Bank account ${index + 1}`}
            className={fieldInputClass}
            {...register(`${prefix}.accountNickname`)}
          />
          <p className="text-xs text-text-muted">
            Optional label for this account (shown on Bank Details and invoices).
          </p>
          {entryErrors?.accountNickname ? (
            <p className="text-xs text-red-700" role="alert">
              {entryErrors.accountNickname.message}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          disabled={total <= 1}
          onClick={onRemove}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-medium text-alert hover:bg-alert/10 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label={`Remove bank account ${index + 1}`}
        >
          <Trash2 size={14} />
          Remove
        </button>
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
          <Building2 size={14} />
          Core domestic bank details
        </div>
        <div className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-7">
            <div className="space-y-1.5">
              <label
                htmlFor={`${prefix}-beneficiary-name`}
                className="block text-sm font-medium text-text-main"
              >
                Beneficiary / Account Name
              </label>
              <input
                id={`${prefix}-beneficiary-name`}
                type="text"
                autoComplete="organization"
                placeholder="Official registered business name"
                className={fieldInputClass}
                {...register(`${prefix}.beneficiaryName`)}
              />
              {entryErrors?.beneficiaryName ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.beneficiaryName.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <label htmlFor={`${prefix}-bank-name`} className="block text-sm font-medium text-text-main">
                Bank Name
              </label>
              <input
                id={`${prefix}-bank-name`}
                type="text"
                placeholder="Full bank name"
                className={fieldInputClass}
                {...register(`${prefix}.bankName`)}
              />
              {entryErrors?.bankName ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.bankName.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor={`${prefix}-account-number`}
                className="block text-sm font-medium text-text-main"
              >
                Account Number
              </label>
              <input
                id={`${prefix}-account-number`}
                type="text"
                inputMode="numeric"
                autoComplete="off"
                placeholder="Current account number"
                className={monoInputClass}
                {...register(`${prefix}.accountNumber`)}
              />
              {entryErrors?.accountNumber ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.accountNumber.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor={`${prefix}-account-type`}
                className="block text-sm font-medium text-text-main"
              >
                Account Type
              </label>
              <select
                id={`${prefix}-account-type`}
                className={fieldInputClass}
                {...register(`${prefix}.accountType`)}
              >
                {BANK_ACCOUNT_TYPE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label htmlFor={`${prefix}-ifsc`} className="block text-sm font-medium text-text-main">
                IFSC Code
              </label>
              <input
                id={`${prefix}-ifsc`}
                type="text"
                maxLength={11}
                autoComplete="off"
                spellCheck={false}
                placeholder="HDFC0001234"
                className={monoInputClass}
                {...register(`${prefix}.ifscCode`, {
                  onChange: event => {
                    event.target.value = event.target.value
                      .toUpperCase()
                      .replace(/[^0-9A-Z]/g, '')
                      .slice(0, 11);
                  },
                })}
              />
              {entryErrors?.ifscCode ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.ifscCode.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor={`${prefix}-branch-name-city`}
                className="block text-sm font-medium text-text-main"
              >
                Branch Name &amp; City
              </label>
              <input
                id={`${prefix}-branch-name-city`}
                type="text"
                placeholder="Branch name, City"
                className={fieldInputClass}
                {...register(`${prefix}.branchNameCity`)}
              />
              {entryErrors?.branchNameCity ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.branchNameCity.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <label htmlFor={`${prefix}-upi`} className="block text-sm font-medium text-text-main">
                UPI ID (VPA)
              </label>
              <input
                id={`${prefix}-upi`}
                type="text"
                autoComplete="off"
                spellCheck={false}
                placeholder="nexus@hdfcbank"
                className={monoInputClass}
                {...register(`${prefix}.upiVpa`)}
              />
              {entryErrors?.upiVpa ? (
                <p className="text-xs text-red-700" role="alert">
                  {entryErrors.upiVpa.message}
                </p>
              ) : null}
            </div>
          </div>
      </div>

      <div className="space-y-4 border-t border-border-subtle pt-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
            <Globe2 size={14} />
            International wire transfer details
          </div>
          <p className="mt-1 text-xs text-text-muted">
            For overseas clients, international students, or foreign sponsors.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <label htmlFor={`${prefix}-swift`} className="block text-sm font-medium text-text-main">
              SWIFT / BIC Code
            </label>
            <input
              id={`${prefix}-swift`}
              type="text"
              maxLength={11}
              autoComplete="off"
              spellCheck={false}
              placeholder="HDFCINBBXXX"
              className={monoInputClass}
              {...register(`${prefix}.swiftBicCode`, {
                onChange: event => {
                  event.target.value = event.target.value
                    .toUpperCase()
                    .replace(/[^0-9A-Z]/g, '')
                    .slice(0, 11);
                },
              })}
            />
            <p className="text-xs text-text-muted">International bank identifier code.</p>
            {entryErrors?.swiftBicCode ? (
              <p className="text-xs text-red-700" role="alert">
                {entryErrors.swiftBicCode.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label htmlFor={`${prefix}-iban`} className="block text-sm font-medium text-text-main">
              IBAN
            </label>
            <input
              id={`${prefix}-iban`}
              type="text"
              maxLength={34}
              autoComplete="off"
              spellCheck={false}
              placeholder="If applicable for destination country"
              className={monoInputClass}
              {...register(`${prefix}.iban`, {
                onChange: event => {
                  event.target.value = event.target.value
                    .toUpperCase()
                    .replace(/[^0-9A-Z]/g, '')
                    .slice(0, 34);
                },
              })}
            />
            <p className="text-xs text-text-muted">Required when the destination country uses IBAN.</p>
            {entryErrors?.iban ? (
              <p className="text-xs text-red-700" role="alert">
                {entryErrors.iban.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor={`${prefix}-intermediary`}
              className="block text-sm font-medium text-text-main"
            >
              Intermediary Bank Details
            </label>
            <input
              id={`${prefix}-intermediary`}
              type="text"
              placeholder="Intermediary bank name, SWIFT, routing notes"
              className={fieldInputClass}
              {...register(`${prefix}.intermediaryBankDetails`)}
            />
            <p className="text-xs text-text-muted">Optional cross-border wire routing notes.</p>
            {entryErrors?.intermediaryBankDetails ? (
              <p className="text-xs text-red-700" role="alert">
                {entryErrors.intermediaryBankDetails.message}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

const BillingSettingsSection: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const sectionFromUrl = searchParams.get('section');
  const [activeSection, setActiveSection] = useState<BillingSectionId>(() =>
    isBillingSectionId(sectionFromUrl) ? sectionFromUrl : DEFAULT_BILLING_SECTION
  );

  const gstNumber = useAdminSettingsStore(s => s.gstNumber);
  const gstPercentage = useAdminSettingsStore(s => s.gstPercentage ?? DEFAULT_GST_PERCENTAGE);
  const taxRegimesStored = useAdminSettingsStore(s => s.taxRegimes);
  const taxRegimes = useMemo(
    () => normalizeTaxRegimes(taxRegimesStored),
    [
      taxRegimesStored?.cgst,
      taxRegimesStored?.sgst,
      taxRegimesStored?.igst,
      taxRegimesStored?.exempt,
    ]
  );
  const discountType = useAdminSettingsStore(s => s.discountType ?? DEFAULT_DISCOUNT_TYPE);
  const discountPercentage = useAdminSettingsStore(
    s => s.discountPercentage ?? DEFAULT_DISCOUNT_PERCENTAGE
  );
  const discountFixedAmount = useAdminSettingsStore(
    s => s.discountFixedAmount ?? DEFAULT_DISCOUNT_FIXED_AMOUNT
  );
  const discountReasonsRaw = useAdminSettingsStore(s => s.discountReasons);
  const discountReasons = useMemo(
    () => normalizeDiscountReasons(discountReasonsRaw),
    [discountReasonsRaw]
  );
  const defaultDiscountReason = useAdminSettingsStore(
    s => s.defaultDiscountReason || discountReasons[0] || DEFAULT_DISCOUNT_REASONS[0]
  );
  const maxAutoApproveDiscountPercent = useAdminSettingsStore(
    s => s.maxAutoApproveDiscountPercent ?? DEFAULT_MAX_AUTO_APPROVE_DISCOUNT_PERCENT
  );
  const maxDiscountFixedAmount = useAdminSettingsStore(
    s => s.maxDiscountFixedAmount ?? DEFAULT_MAX_DISCOUNT_FIXED_AMOUNT
  );
  const invoiceSequenceStrategy = useAdminSettingsStore(s => s.invoiceSequenceStrategy);
  const invoiceNumberFormat = useAdminSettingsStore(
    s => s.invoiceNumberFormat ?? DEFAULT_INVOICE_NUMBER_FORMAT
  );
  const bankPaymentsRaw = useAdminSettingsStore(s => s.bankPayments);
  const bankPayments = useMemo(
    () => normalizeBankPaymentList(bankPaymentsRaw),
    [bankPaymentsRaw]
  );
  const lastInvoiceSequence = useAdminSettingsStore(s => s.lastInvoiceSequence);
  const lastInvoiceFinancialYearStart = useAdminSettingsStore(
    s => s.lastInvoiceFinancialYearStart
  );
  const billingSavedAt = useAdminSettingsStore(s => s.billingSavedAt);
  const saveBillingSettings = useAdminSettingsStore(s => s.saveBillingSettings);

  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [newDiscountReason, setNewDiscountReason] = useState('');
  const [discountReasonError, setDiscountReasonError] = useState<string | null>(null);
  const [catalogDirty, setCatalogDirty] = useState(false);
  const isDirtyRef = useRef(false);

  const {
    register,
    control,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors, isDirty, isSubmitted, touchedFields, dirtyFields },
  } = useForm<FormValues>({
    resolver: zodResolver(billingSettingsSchema),
    defaultValues: {
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
    },
    mode: 'onChange',
  });

  isDirtyRef.current = isDirty;

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'bankPayments',
  });

  // Sync from store only when the form has no local edits. Otherwise persist
  // rehydration / new array identities would reset() and keep Save disabled.
  useEffect(() => {
    if (isDirtyRef.current) return;
    reset({
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
    });
  }, [
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
    reset,
  ]);

  useEffect(() => {
    if (isBillingSectionId(sectionFromUrl) && sectionFromUrl !== activeSection) {
      setActiveSection(sectionFromUrl);
    }
  }, [sectionFromUrl, activeSection]);

  useEffect(() => {
    // Only enforce billing section while the Settings page is on the billing tab.
    // Without this guard, clearing `section` when switching to Organization/Workspace/
    // Monitoring re-forced `tab=billing` and made those tabs appear broken.
    if (searchParams.get('tab') !== 'billing') return;
    if (isBillingSectionId(sectionFromUrl)) return;
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        next.set('tab', 'billing');
        next.set('section', activeSection);
        return next;
      },
      { replace: true }
    );
  }, [sectionFromUrl, activeSection, searchParams, setSearchParams]);

  const selectSection = useCallback(
    (sectionId: BillingSectionId) => {
      setActiveSection(sectionId);
      const next = new URLSearchParams(searchParams);
      next.set('tab', 'billing');
      next.set('section', sectionId);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const sectionDirty: Record<BillingSectionId, boolean> = useMemo(
    () => ({
      'base-price-catalog': catalogDirty,
      'invoice-format': Boolean(
        dirtyFields.invoiceNumberFormat || dirtyFields.invoiceSequenceStrategy
      ),
      'organization-gstin': Boolean(
        dirtyFields.gstNumber || dirtyFields.gstPercentage || dirtyFields.taxRegimes
      ),
      'discount-policy': Boolean(
        dirtyFields.discountType ||
          dirtyFields.discountPercentage ||
          dirtyFields.discountFixedAmount ||
          dirtyFields.discountReasons ||
          dirtyFields.defaultDiscountReason ||
          dirtyFields.maxAutoApproveDiscountPercent ||
          dirtyFields.maxDiscountFixedAmount
      ),
      'bank-details': Boolean(dirtyFields.bankPayments),
    }),
    [dirtyFields, catalogDirty]
  );

  const watchedGst = watch('gstNumber') ?? '';
  const watchedGstPercentage = watch('gstPercentage') ?? DEFAULT_GST_PERCENTAGE;
  const watchedTaxRegimes = watch('taxRegimes') ?? DEFAULT_TAX_REGIMES;
  const watchedStrategy = watch('invoiceSequenceStrategy') ?? 'continue';
  const watchedInvoiceFormat = watch('invoiceNumberFormat') ?? DEFAULT_INVOICE_NUMBER_FORMAT;
  const watchedDiscountType = watch('discountType') ?? 'percentage';
  const watchedMaxDiscountPercent = Math.min(
    100,
    Math.max(0, Number(watch('maxAutoApproveDiscountPercent')) || 0)
  );
  const watchedMaxDiscountFixed = Math.min(
    1_000_000,
    Math.max(0, Number(watch('maxDiscountFixedAmount')) || 0)
  );
  const watchedDiscountReasons = watch('discountReasons') ?? discountReasons;
  const watchedDefaultDiscountReason = watch('defaultDiscountReason') ?? defaultDiscountReason;
  const gstNormalized = watchedGst.trim().toUpperCase();
  const gstLooksValid = gstNormalized.length === 15 && isValidGstin(gstNormalized);
  const showGstError =
    Boolean(errors.gstNumber) &&
    (isSubmitted || Boolean(touchedFields.gstNumber) || gstNormalized.length === 15);

  useEffect(() => {
    if (watchedDiscountType !== 'percentage') return;
    const current = Number(watch('discountPercentage'));
    if (!Number.isFinite(current)) return;
    if (current > watchedMaxDiscountPercent) {
      setValue('discountPercentage', watchedMaxDiscountPercent, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }, [watchedDiscountType, watchedMaxDiscountPercent, setValue, watch]);

  useEffect(() => {
    if (watchedDiscountType !== 'fixed') return;
    const current = Number(watch('discountFixedAmount'));
    if (!Number.isFinite(current)) return;
    if (current > watchedMaxDiscountFixed) {
      setValue(
        'discountFixedAmount',
        Math.round(watchedMaxDiscountFixed / 100) * 100,
        { shouldDirty: true, shouldValidate: true }
      );
    }
  }, [watchedDiscountType, watchedMaxDiscountFixed, setValue, watch]);

  const nextPreview = useMemo(
    () =>
      previewNextInvoiceId(
        watchedStrategy,
        lastInvoiceSequence,
        lastInvoiceFinancialYearStart,
        new Date(),
        watchedInvoiceFormat
      ),
    [
      watchedStrategy,
      watchedInvoiceFormat,
      lastInvoiceSequence,
      lastInvoiceFinancialYearStart,
    ]
  );

  const fyStart = getIndianFinancialYearStart();
  const fyLabel = `${fyStart}–${String(fyStart + 1).slice(-2)}`;

  const addDiscountReasonToForm = () => {
    const cleaned = normalizeDiscountReasonLabel(newDiscountReason);
    if (!cleaned) {
      setDiscountReasonError('Enter a discount reason.');
      return;
    }
    const current = normalizeDiscountReasons(watchedDiscountReasons);
    if (current.some(item => item.toLowerCase() === cleaned.toLowerCase())) {
      setDiscountReasonError('That discount reason already exists.');
      return;
    }
    if (current.length >= 40) {
      setDiscountReasonError('You can add at most 40 discount reasons.');
      return;
    }
    const next = [...current, cleaned];
    setValue('discountReasons', next, { shouldDirty: true, shouldValidate: true });
    if (!watchedDefaultDiscountReason) {
      setValue('defaultDiscountReason', cleaned, { shouldDirty: true, shouldValidate: true });
    }
    setNewDiscountReason('');
    setDiscountReasonError(null);
  };

  const removeDiscountReasonFromForm = (index: number) => {
    const current = normalizeDiscountReasons(watchedDiscountReasons);
    if (current.length <= 1) {
      setDiscountReasonError('Keep at least one discount reason.');
      return;
    }
    const removed = current[index];
    const next = current.filter((_, itemIndex) => itemIndex !== index);
    setValue('discountReasons', next, { shouldDirty: true, shouldValidate: true });
    if (watchedDefaultDiscountReason.toLowerCase() === removed.toLowerCase()) {
      setValue('defaultDiscountReason', next[0], { shouldDirty: true, shouldValidate: true });
    }
    setDiscountReasonError(null);
  };

  const focusSectionForErrors = (formErrors: FieldErrors<FormValues>) => {
    if (formErrors.invoiceNumberFormat || formErrors.invoiceSequenceStrategy) {
      selectSection('invoice-format');
      return;
    }
    if (formErrors.gstNumber || formErrors.gstPercentage || formErrors.taxRegimes) {
      selectSection('organization-gstin');
      return;
    }
    if (
      formErrors.discountType ||
      formErrors.discountPercentage ||
      formErrors.discountFixedAmount ||
      formErrors.discountReasons ||
      formErrors.defaultDiscountReason ||
      formErrors.maxAutoApproveDiscountPercent ||
      formErrors.maxDiscountFixedAmount
    ) {
      selectSection('discount-policy');
      return;
    }
    if (formErrors.bankPayments) {
      selectSection('bank-details');
    }
  };

  const onSubmit = handleSubmit(
    (values: BillingSettingsFormValues) => {
      setSaving(true);
      setSuccessMessage(null);
      try {
        const payload = {
          gstNumber: values.gstNumber,
          gstPercentage: clampGstPercentage(values.gstPercentage),
          taxRegimes: normalizeTaxRegimes(values.taxRegimes),
          discountType: values.discountType,
          discountPercentage: clampDiscountPercentage(values.discountPercentage),
          discountFixedAmount: clampDiscountFixedAmount(values.discountFixedAmount),
          discountReasons: normalizeDiscountReasons(values.discountReasons),
          defaultDiscountReason: values.defaultDiscountReason,
          maxAutoApproveDiscountPercent: clampMaxAutoApproveDiscountPercent(
            values.maxAutoApproveDiscountPercent
          ),
          maxDiscountFixedAmount: clampMaxDiscountFixedAmount(values.maxDiscountFixedAmount),
          invoiceSequenceStrategy: values.invoiceSequenceStrategy,
          invoiceNumberFormat: values.invoiceNumberFormat,
          bankPayments: values.bankPayments,
        };
        saveBillingSettings(payload);
        // Clear dirty against the values just saved (avoid a wipe mid-edit from store sync).
        reset({
          ...payload,
          taxRegimes: payload.taxRegimes,
          discountReasons: payload.discountReasons,
          bankPayments: normalizeBankPaymentList(payload.bankPayments),
        });
        isDirtyRef.current = false;
        setSuccessMessage('Billing & invoicing settings saved.');
      } finally {
        setSaving(false);
      }
    },
    focusSectionForErrors
  );

  return (
    <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
      <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-main flex items-center gap-2">
              <Receipt size={18} />
              Billing &amp; Invoicing Settings
            </h2>
            <p className="text-xs text-text-muted mt-1 max-w-2xl">
              Base price catalog, GSTIN, discount policy, bank details, and April–March financial
              year invoice numbering for the Student Invoice Generator.
            </p>
          </div>
          <div className="text-[11px] text-text-muted space-y-0.5 md:text-right">
            <p>
              Active FY: <span className="font-semibold text-text-main">{fyLabel}</span> (begins Apr
              1)
            </p>
            {billingSavedAt ? (
              <p>Last saved: {new Date(billingSavedAt).toLocaleString()}</p>
            ) : (
              <p>Not saved yet</p>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-4 p-4 md:p-5">
        {successMessage && activeSection !== 'base-price-catalog' ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <CheckCircle2 size={16} />
            {successMessage}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2.5">
          <div className="hidden items-center gap-2 sm:flex">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
              Billing
            </span>
            <span className="h-3 w-px bg-border-subtle" aria-hidden />
          </div>
          <div
            className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-card p-1"
            role="tablist"
            aria-label="Billing sections"
          >
            {BILLING_SECTIONS.map(section => {
              const active = activeSection === section.id;
              const dirty = sectionDirty[section.id];
              return (
                <button
                  key={section.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => selectSection(section.id)}
                  className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
                    active
                      ? 'bg-accent text-text-dark-bg shadow-sm'
                      : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
                  }`}
                >
                  {section.icon}
                  {section.label}
                  {dirty ? (
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        active ? 'bg-amber-200' : 'bg-amber-500'
                      }`}
                      title="Unsaved changes"
                      aria-label="Unsaved changes"
                    />
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>

        <p className="text-xs text-text-muted">
          {BILLING_SECTIONS.find(section => section.id === activeSection)?.description}
        </p>

        {activeSection === 'base-price-catalog' ? (
          <BasePriceCatalogPanel onDirtyChange={setCatalogDirty} />
        ) : null}

        <form
          className={activeSection === 'base-price-catalog' ? 'hidden' : 'space-y-4'}
          onSubmit={onSubmit}
          noValidate
          aria-hidden={activeSection === 'base-price-catalog'}
        >
        {activeSection === 'invoice-format' ? (
          <div
            className={panelClass}
            role="group"
            aria-labelledby="invoice-numbering-label"
          >
            <div className="flex h-9 shrink-0 items-center">
              <p id="invoice-numbering-label" className={panelLabelClass}>
                Invoice numbering
              </p>
            </div>

            <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
              <div className="w-full max-w-[16rem] space-y-1.5">
                <label
                  htmlFor="invoice-number-format"
                  className="block text-xs font-medium text-text-main"
                >
                  Invoice format
                </label>
                <input
                  id="invoice-number-format"
                  type="text"
                  spellCheck={false}
                  autoComplete="off"
                  placeholder={DEFAULT_INVOICE_NUMBER_FORMAT}
                  aria-invalid={Boolean(errors.invoiceNumberFormat)}
                  className={`${monoInputClass} h-9 normal-case tracking-normal ${
                    errors.invoiceNumberFormat ? 'border-red-400 ring-1 ring-red-200' : ''
                  }`}
                  {...register('invoiceNumberFormat')}
                />
                <div className="flex flex-wrap gap-1">
                  {INVOICE_NUMBER_FORMAT_PRESETS.map(preset => (
                    <button
                      key={preset.value}
                      type="button"
                      onClick={() =>
                        setValue('invoiceNumberFormat', preset.value, {
                          shouldDirty: true,
                          shouldValidate: true,
                        })
                      }
                      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
                        watchedInvoiceFormat === preset.value
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border-subtle bg-card text-text-muted hover:border-accent/40 hover:text-text-main'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
                {errors.invoiceNumberFormat ? (
                  <p className="text-[11px] text-red-700" role="alert">
                    {errors.invoiceNumberFormat.message}
                  </p>
                ) : (
                  <p className="text-[11px] leading-4 text-text-muted">
                    Tokens: {'{YYYY}'} {'{YY}'} {'{FY}'} {'{FY-FY}'} {'{SEQ}'} {'{SEQ:5}'}
                  </p>
                )}
              </div>

              <Controller
                name="invoiceSequenceStrategy"
                control={control}
                render={({ field }) => (
                  <div
                    className="grid shrink-0 grid-cols-2 gap-1.5 lg:w-[26rem]"
                    role="radiogroup"
                    aria-label="Invoice numbering strategy"
                  >
                    <p className="col-span-2 text-xs font-medium text-text-main">FY strategy</p>
                    <label
                      className={`flex min-w-0 cursor-pointer items-start gap-1.5 rounded-lg border px-2 py-2 transition-colors ${
                        field.value === 'continue'
                          ? 'border-accent bg-accent/5'
                          : 'border-border-subtle bg-card hover:border-border-subtle/80'
                      }`}
                    >
                      <input
                        type="radio"
                        className="mt-0.5 shrink-0"
                        checked={field.value === 'continue'}
                        onChange={() => field.onChange('continue')}
                      />
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold leading-4 text-text-main">
                          Continue across FYs
                        </span>
                        <span className="mt-0.5 block text-[11px] leading-4 text-text-muted">
                          Keep incrementing into the next FY.
                        </span>
                      </span>
                    </label>

                    <label
                      className={`flex min-w-0 cursor-pointer items-start gap-1.5 rounded-lg border px-2 py-2 transition-colors ${
                        field.value === 'reset'
                          ? 'border-accent bg-accent/5'
                          : 'border-border-subtle bg-card hover:border-border-subtle/80'
                      }`}
                    >
                      <input
                        type="radio"
                        className="mt-0.5 shrink-0"
                        checked={field.value === 'reset'}
                        onChange={() => field.onChange('reset')}
                      />
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold leading-4 text-text-main">
                          Reset each FY
                        </span>
                        <span className="mt-0.5 block text-[11px] leading-4 text-text-muted">
                          Restart at 0001 every April 1st.
                        </span>
                      </span>
                    </label>
                  </div>
                )}
              />

              <div
                className={`${panelHintClass} flex shrink-0 items-start gap-1.5 rounded-lg border border-border-subtle bg-card px-2 py-2 lg:mt-5 lg:w-52`}
              >
                <FileText size={12} className="mt-0.5 shrink-0 text-text-main" />
                <p className="min-w-0 break-all">
                  FY Apr 1 · Next{' '}
                  <span className="font-mono font-semibold text-text-main">{nextPreview}</span>
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {activeSection === 'organization-gstin' ? (
          <div className="space-y-4 max-w-3xl">
            <div className="rounded-xl border border-border-subtle bg-surface-bg/50 p-3 space-y-3">
              <div className="flex h-9 shrink-0 items-center">
                <label htmlFor="organization-gstin" className={panelLabelClass}>
                  Organization GSTIN
                </label>
              </div>
              <div className="relative">
                <input
                  id="organization-gstin"
                  type="text"
                  maxLength={15}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="27AABCU9603R1ZM"
                  aria-invalid={showGstError}
                  className={`${gstinInputClass} h-9 ${
                    showGstError
                      ? 'border-red-400 ring-1 ring-red-200'
                      : gstLooksValid
                        ? 'border-emerald-400 ring-1 ring-emerald-200'
                        : ''
                  }`}
                  {...register('gstNumber', {
                    onChange: event => {
                      event.target.value = event.target.value
                        .toUpperCase()
                        .replace(/[^0-9A-Z]/gi, '');
                    },
                  })}
                />
                {gstLooksValid ? (
                  <span className="pointer-events-none absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">
                    <CheckCircle2 size={12} />
                    Valid
                  </span>
                ) : null}
              </div>
              {showGstError ? (
                <p className={`${panelHintClass} text-red-700`} role="alert">
                  {errors.gstNumber?.message}
                </p>
              ) : (
                <p className={panelHintClass}>15-char Indian GSTIN (e.g. 27AABCU9603R1ZM).</p>
              )}
            </div>

            <div className="rounded-xl border border-border-subtle bg-surface-bg/50 p-3 space-y-3">
              <div>
                <p className={panelLabelClass}>Tax percentage</p>
                <p className="mt-0.5 text-[11px] leading-4 text-text-muted">
                  Set the headline GST rate used on student invoices. Intra-state bills split this
                  into CGST + SGST; inter-state uses the full rate as IGST.
                </p>
              </div>

              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1.5">
                  <label
                    htmlFor="gst-percentage"
                    className="block text-xs font-medium text-text-main"
                  >
                    Default GST rate
                  </label>
                  <Controller
                    name="gstPercentage"
                    control={control}
                    render={({ field }) => {
                      const value = clampGstPercentage(Number(field.value));
                      return (
                        <div className="flex items-center gap-1.5">
                          <input
                            id="gst-percentage"
                            type="number"
                            min={0}
                            max={100}
                            step={1}
                            inputMode="numeric"
                            aria-invalid={Boolean(errors.gstPercentage)}
                            className="h-10 w-24 rounded-xl border border-border-subtle bg-card px-3 text-right text-base font-semibold text-text-main outline-none focus:border-primary"
                            value={Number.isFinite(value) ? value : DEFAULT_GST_PERCENTAGE}
                            onChange={event => {
                              field.onChange(clampGstPercentage(Number(event.target.value)));
                            }}
                            onBlur={field.onBlur}
                            name={field.name}
                            ref={field.ref}
                          />
                          <span className="text-sm font-semibold text-text-main">%</span>
                        </div>
                      );
                    }}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5 pb-1">
                  {[0, 5, 12, 18, 28].map(preset => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() =>
                        setValue('gstPercentage', preset, {
                          shouldDirty: true,
                          shouldValidate: true,
                        })
                      }
                      className={`rounded-md border px-2 py-1 text-[11px] font-semibold transition-colors ${
                        Number(watchedGstPercentage) === preset
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border-subtle bg-card text-text-muted hover:text-text-main'
                      }`}
                    >
                      {preset}%
                    </button>
                  ))}
                </div>
              </div>

              <Controller
                name="gstPercentage"
                control={control}
                render={({ field }) => {
                  const value = clampGstPercentage(Number(field.value));
                  const safeValue = Number.isFinite(value) ? value : DEFAULT_GST_PERCENTAGE;
                  return (
                    <div className="space-y-2">
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={safeValue}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={safeValue}
                        aria-label="Tax percentage slider"
                        onChange={event => {
                          field.onChange(clampGstPercentage(Number(event.target.value)));
                        }}
                        className="h-2.5 w-full cursor-pointer appearance-none rounded-full accent-[var(--color-accent)]"
                        style={{
                          background: `linear-gradient(to right, var(--color-accent) 0%, var(--color-accent) ${safeValue}%, #e2e8f0 ${safeValue}%, #e2e8f0 100%)`,
                        }}
                      />
                      <div className="flex items-center justify-between text-[11px] font-medium text-text-muted">
                        <span>0%</span>
                        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">
                          {safeValue}%
                          {safeValue === DEFAULT_GST_PERCENTAGE ? ' · default' : ''}
                        </span>
                        <span>100%</span>
                      </div>
                    </div>
                  );
                }}
              />

              {errors.gstPercentage ? (
                <p className="text-[11px] text-red-700" role="alert">
                  {errors.gstPercentage.message}
                </p>
              ) : (
                <p className="text-[11px] leading-4 text-text-muted">
                  {formatTaxRegimePreview(Number(watchedGstPercentage) || 0, watchedTaxRegimes)}
                </p>
              )}
            </div>

            <div className="space-y-3 rounded-xl border border-border-subtle bg-surface-bg/50 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className={panelLabelClass}>Active tax regimes</p>
                  <p className="mt-0.5 text-[11px] leading-4 text-text-muted">
                    Choose which GST treatments student invoices may use. CGST and SGST stay paired
                    for intra-state supply.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setValue(
                      'taxRegimes',
                      { cgst: true, sgst: true, igst: true, exempt: false },
                      { shouldDirty: true, shouldValidate: true }
                    )
                  }
                  className="rounded-lg border border-border-subtle bg-card px-2.5 py-1 text-[11px] font-semibold text-text-muted hover:text-text-main"
                >
                  Select typical India setup
                </button>
              </div>

              <Controller
                name="taxRegimes"
                control={control}
                render={({ field }) => {
                  const value = normalizeTaxRegimes(field.value);
                  const setRegime = (key: keyof TaxRegimes, nextChecked: boolean) => {
                    let next: TaxRegimes = { ...value, [key]: nextChecked };
                    if (key === 'cgst' || key === 'sgst') {
                      next = coupleCgstSgst(next, key);
                    }
                    field.onChange(next);
                  };
                  const options: Array<{
                    key: keyof TaxRegimes;
                    label: string;
                    hint: string;
                  }> = [
                    {
                      key: 'cgst',
                      label: 'CGST',
                      hint: 'Central GST — with SGST for same-state (intra-state) billing.',
                    },
                    {
                      key: 'sgst',
                      label: 'SGST',
                      hint: 'State GST — always paired with CGST for intra-state supply.',
                    },
                    {
                      key: 'igst',
                      label: 'IGST',
                      hint: 'Integrated GST — inter-state supply (student in another state).',
                    },
                    {
                      key: 'exempt',
                      label: 'Exempt / zero-rated / export',
                      hint: '0% option for exempt services or export-style student remittances.',
                    },
                  ];
                  return (
                    <div className="grid gap-2 sm:grid-cols-2" role="group" aria-label="Tax regimes">
                      {options.map(option => (
                        <label
                          key={option.key}
                          className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2.5 transition-colors ${
                            value[option.key]
                              ? 'border-accent bg-accent/5'
                              : 'border-border-subtle bg-card hover:border-border-subtle/80'
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="mt-0.5 h-4 w-4 shrink-0"
                            checked={value[option.key]}
                            onChange={event => setRegime(option.key, event.target.checked)}
                          />
                          <span className="min-w-0">
                            <span className="block text-xs font-semibold text-text-main">
                              {option.label}
                            </span>
                            <span className="mt-0.5 block text-[11px] leading-4 text-text-muted">
                              {option.hint}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  );
                }}
              />

              {errors.taxRegimes?.cgst?.message ||
              errors.taxRegimes?.sgst?.message ||
              errors.taxRegimes?.message ? (
                <p className="text-[11px] text-red-700" role="alert">
                  {errors.taxRegimes?.cgst?.message ||
                    errors.taxRegimes?.sgst?.message ||
                    String(errors.taxRegimes?.message || '')}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {activeSection === 'discount-policy' ? (
          <section className="space-y-4 rounded-2xl border border-border-subtle bg-surface-bg/40 p-4 md:p-5">
            <div className="flex w-full max-w-xl flex-col items-stretch gap-3 text-left">
              <div className="flex flex-col gap-1.5">
                <p className="block text-sm font-medium text-text-main">Discount type</p>
                <Controller
                  name="discountType"
                  control={control}
                  render={({ field }) => (
                    <div
                      className="grid h-10 grid-cols-2 gap-1"
                      role="radiogroup"
                      aria-label="Discount type"
                    >
                      {(
                        [
                          { value: 'percentage', label: '%' },
                          { value: 'fixed', label: '₹' },
                        ] as const
                      ).map(option => (
                        <label
                          key={option.value}
                          className={`flex cursor-pointer items-center justify-center rounded-xl border text-xs ${
                            field.value === option.value
                              ? 'border-accent bg-accent/5 font-semibold text-text-main'
                              : 'border-border-subtle bg-card text-text-muted'
                          }`}
                        >
                          <input
                            type="radio"
                            className="sr-only"
                            checked={field.value === option.value}
                            onChange={() => field.onChange(option.value)}
                          />
                          {option.label}
                        </label>
                      ))}
                    </div>
                  )}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                {watchedDiscountType === 'percentage' ? (
                  <div key="discount-default-percent" className="flex flex-col gap-1.5">
                    <label
                      htmlFor="discount-percentage"
                      className="block text-sm font-medium text-text-main"
                    >
                      Discount %
                    </label>
                    <input
                      id="discount-percentage"
                      type="number"
                      min={0}
                      max={watchedMaxDiscountPercent}
                      step={1}
                      className={discountControlClass}
                      {...register('discountPercentage', { valueAsNumber: true })}
                    />
                    {errors.discountPercentage ? (
                      <p className="text-xs text-red-700">{errors.discountPercentage.message}</p>
                    ) : null}
                  </div>
                ) : (
                  <div key="discount-default-fixed" className="flex flex-col gap-1.5">
                    <label
                      htmlFor="discount-fixed-amount"
                      className="block text-sm font-medium text-text-main"
                    >
                      Fixed discount (₹)
                    </label>
                    <input
                      id="discount-fixed-amount"
                      type="number"
                      min={0}
                      max={watchedMaxDiscountFixed}
                      step={100}
                      inputMode="numeric"
                      className={discountControlClass}
                      {...(() => {
                        const { onBlur, ...field } = register('discountFixedAmount', {
                          valueAsNumber: true,
                          setValueAs: value => {
                            const n = typeof value === 'number' ? value : Number(value);
                            if (!Number.isFinite(n) || n <= 0) return 0;
                            return Math.round(n / 100) * 100;
                          },
                        });
                        return {
                          ...field,
                          onBlur: (event: React.FocusEvent<HTMLInputElement>) => {
                            onBlur(event);
                            const n = Number(event.target.value);
                            const snapped =
                              !Number.isFinite(n) || n <= 0 ? 0 : Math.round(n / 100) * 100;
                            const capped = Math.min(watchedMaxDiscountFixed, snapped);
                            setValue('discountFixedAmount', capped, {
                              shouldDirty: true,
                              shouldValidate: true,
                            });
                          },
                        };
                      })()}
                    />
                    {errors.discountFixedAmount ? (
                      <p className="text-xs text-red-700">{errors.discountFixedAmount.message}</p>
                    ) : null}
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                {watchedDiscountType === 'percentage' ? (
                  <div key="discount-max-percent" className="flex flex-col gap-1.5">
                    <label
                      htmlFor="max-auto-approve-discount"
                      className="block text-sm font-medium text-text-main"
                    >
                      Max discount %
                    </label>
                    <input
                      id="max-auto-approve-discount"
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      className={discountControlClass}
                      {...register('maxAutoApproveDiscountPercent', { valueAsNumber: true })}
                    />
                    {errors.maxAutoApproveDiscountPercent ? (
                      <p className="text-xs text-red-700">
                        {errors.maxAutoApproveDiscountPercent.message}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <div key="discount-max-fixed" className="flex flex-col gap-1.5">
                    <label
                      htmlFor="max-discount-fixed-amount"
                      className="block text-sm font-medium text-text-main"
                    >
                      Max fixed discount (₹)
                    </label>
                    <input
                      id="max-discount-fixed-amount"
                      type="number"
                      min={0}
                      step={100}
                      inputMode="numeric"
                      className={discountControlClass}
                      {...(() => {
                        const { onBlur, ...field } = register('maxDiscountFixedAmount', {
                          valueAsNumber: true,
                          setValueAs: value => {
                            const n = typeof value === 'number' ? value : Number(value);
                            if (!Number.isFinite(n) || n <= 0) return 0;
                            return Math.round(n / 100) * 100;
                          },
                        });
                        return {
                          ...field,
                          onBlur: (event: React.FocusEvent<HTMLInputElement>) => {
                            onBlur(event);
                            const n = Number(event.target.value);
                            const snapped =
                              !Number.isFinite(n) || n <= 0 ? 0 : Math.round(n / 100) * 100;
                            setValue('maxDiscountFixedAmount', snapped, {
                              shouldDirty: true,
                              shouldValidate: true,
                            });
                          },
                        };
                      })()}
                    />
                    {errors.maxDiscountFixedAmount ? (
                      <p className="text-xs text-red-700">
                        {errors.maxDiscountFixedAmount.message}
                      </p>
                    ) : null}
                  </div>
                )}
                {/* Keep inactive mode values registered so save does not drop them. */}
                {watchedDiscountType === 'percentage' ? (
                  <input
                    type="hidden"
                    {...register('maxDiscountFixedAmount', { valueAsNumber: true })}
                  />
                ) : (
                  <input
                    type="hidden"
                    {...register('maxAutoApproveDiscountPercent', { valueAsNumber: true })}
                  />
                )}
                {watchedDiscountType === 'percentage' ? (
                  <input
                    type="hidden"
                    {...register('discountFixedAmount', { valueAsNumber: true })}
                  />
                ) : (
                  <input
                    type="hidden"
                    {...register('discountPercentage', { valueAsNumber: true })}
                  />
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="default-discount-reason"
                  className="block text-sm font-medium text-text-main"
                >
                  Default reason
                </label>
                <select
                  id="default-discount-reason"
                  className={discountControlClass}
                  {...register('defaultDiscountReason')}
                >
                  {normalizeDiscountReasons(watchedDiscountReasons).map(reason => (
                    <option key={reason} value={reason}>
                      {reason}
                    </option>
                  ))}
                </select>
                {errors.defaultDiscountReason ? (
                  <p className="text-xs text-red-700">{errors.defaultDiscountReason.message}</p>
                ) : null}
              </div>

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="new-discount-reason"
                  className="block text-sm font-medium text-text-main"
                >
                  Allowed reasons
                </label>
                <input
                  id="new-discount-reason"
                  type="text"
                  maxLength={60}
                  placeholder="e.g. Early Bird"
                  value={newDiscountReason}
                  onChange={event => {
                    setNewDiscountReason(event.target.value);
                    setDiscountReasonError(null);
                  }}
                  onKeyDown={event => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      addDiscountReasonToForm();
                    }
                  }}
                  className={discountControlClass}
                />
                {discountReasonError || errors.discountReasons ? (
                  <p className="text-xs text-red-700">
                    {discountReasonError || errors.discountReasons?.message}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={addDiscountReasonToForm}
                  className="inline-flex h-10 w-auto self-start items-center justify-center gap-1 rounded-xl border border-accent/30 bg-accent/5 px-3 text-sm font-semibold text-accent hover:bg-accent/10"
                >
                  <Plus size={14} />
                  Add Discount Reason
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {normalizeDiscountReasons(watchedDiscountReasons).map((reason, index) => (
                <span
                  key={reason}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-card px-2.5 py-1 text-xs font-medium text-text-main"
                >
                  {reason}
                  <button
                    type="button"
                    onClick={() => removeDiscountReasonFromForm(index)}
                    className="rounded p-0.5 text-alert hover:bg-alert/10"
                    aria-label={`Remove ${reason}`}
                  >
                    <Trash2 size={12} />
                  </button>
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {activeSection === 'bank-details' ? (
          <section className="space-y-4 rounded-2xl border border-border-subtle bg-surface-bg/40 p-4 md:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-text-main">
                  <Landmark size={16} />
                  Bank Payment Details
                </h3>
                <p className="mt-1 text-xs text-text-muted">
                  Add one or more bank accounts shown on invoices for students and sponsors.
                </p>
              </div>
              <button
                type="button"
                disabled={fields.length >= 20}
                onClick={() => append(createEmptyBankPaymentDetails())}
                className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-sm font-semibold text-accent hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus size={16} />
                Add bank account
              </button>
            </div>

            <div className="space-y-4">
              {fields.map((field, index) => (
                <BankAccountCard
                  key={field.id}
                  index={index}
                  total={fields.length}
                  register={register}
                  errors={errors}
                  onRemove={() => remove(index)}
                />
              ))}
            </div>
          </section>
        ) : null}

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border-subtle pt-4">
          {!isDirty && !saving ? (
            <p className="mr-auto text-xs text-text-muted">Change a field to enable Save.</p>
          ) : null}
          <button
            type="submit"
            disabled={!isDirty || saving}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save billing settings
          </button>
        </div>
        </form>
      </div>
    </div>
  );
};

export default BillingSettingsSection;
