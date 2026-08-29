/**
 * Parked for later use (e.g. Student Invoice Generator).
 * Not currently mounted in Billing settings.
 */
import React, { useEffect, useMemo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertTriangle, Calculator } from 'lucide-react';
import {
  invoiceAdjustmentPreviewSchema,
  type InvoiceAdjustmentPreviewValues,
} from '../../schemas/billingSettingsSchema';
import {
  computeInvoiceAdjustmentTotals,
  formatMoneyInr,
  type DiscountType,
} from '../../utils/invoiceMoney';

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary';

type InvoiceAdjustmentPreviewProps = {
  gstPercentage: number;
  maxAutoApproveDiscountPercent: number;
  discountReasons: string[];
  defaultDiscountType: DiscountType;
  defaultDiscountValue: number;
  defaultDiscountReason: string;
};

const InvoiceAdjustmentPreview: React.FC<InvoiceAdjustmentPreviewProps> = ({
  gstPercentage,
  maxAutoApproveDiscountPercent,
  discountReasons,
  defaultDiscountType,
  defaultDiscountValue,
  defaultDiscountReason,
}) => {
  const reasons = discountReasons.length ? discountReasons : [defaultDiscountReason || 'Other'];

  const {
    register,
    control,
    watch,
    reset,
    formState: { errors },
  } = useForm<InvoiceAdjustmentPreviewValues>({
    resolver: zodResolver(invoiceAdjustmentPreviewSchema),
    defaultValues: {
      subtotal: 10000,
      discountType: defaultDiscountType,
      discountValue: defaultDiscountValue,
      discountReason: defaultDiscountReason || reasons[0],
      adjustmentAmount: 0,
      adjustmentNote: '',
    },
    mode: 'onChange',
  });

  const reasonsKey = reasons.join('|');

  useEffect(() => {
    const reasonList = reasonsKey ? reasonsKey.split('|') : ['Other'];
    reset({
      subtotal: 10000,
      discountType: defaultDiscountType,
      discountValue: defaultDiscountValue,
      discountReason: reasonList.includes(defaultDiscountReason)
        ? defaultDiscountReason
        : reasonList[0],
      adjustmentAmount: 0,
      adjustmentNote: '',
    });
  }, [
    defaultDiscountType,
    defaultDiscountValue,
    defaultDiscountReason,
    reasonsKey,
    reset,
  ]);

  const watched = watch();
  const totals = useMemo(
    () =>
      computeInvoiceAdjustmentTotals({
        subtotal: Number(watched.subtotal) || 0,
        discountType: watched.discountType === 'fixed' ? 'fixed' : 'percentage',
        discountValue: Number(watched.discountValue) || 0,
        adjustmentAmount: Number(watched.adjustmentAmount) || 0,
        gstPercentage,
        maxAutoApproveDiscountPercent,
      }),
    [watched, gstPercentage, maxAutoApproveDiscountPercent]
  );

  return (
    <section className="space-y-4 rounded-2xl border border-border-subtle bg-card p-4 md:p-5">
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-text-main">
          <Calculator size={16} />
          Invoice adjustment preview
        </h3>
        <p className="mt-1 text-xs text-text-muted">
          Live calculator for Student Invoice totals. Math is rounded to 2 decimals:{' '}
          Subtotal − Discount − Adjustment + GST = Final.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="preview-subtotal" className="block text-sm font-medium text-text-main">
              Subtotal (₹)
            </label>
            <input
              id="preview-subtotal"
              type="number"
              min={0}
              step={0.01}
              className={fieldClass}
              {...register('subtotal', { valueAsNumber: true })}
            />
            {errors.subtotal ? (
              <p className="text-xs text-red-700">{errors.subtotal.message}</p>
            ) : null}
          </div>

          <Controller
            name="discountType"
            control={control}
            render={({ field }) => (
              <div className="space-y-1.5" role="radiogroup" aria-label="Discount type">
                <p className="text-sm font-medium text-text-main">Discount type</p>
                <div className="grid grid-cols-2 gap-2">
                  {(
                    [
                      { value: 'percentage', label: 'Percentage (%)' },
                      { value: 'fixed', label: 'Fixed amount' },
                    ] as const
                  ).map(option => (
                    <label
                      key={option.value}
                      className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                        field.value === option.value
                          ? 'border-accent bg-accent/5 font-semibold text-text-main'
                          : 'border-border-subtle bg-surface-bg text-text-muted'
                      }`}
                    >
                      <input
                        type="radio"
                        checked={field.value === option.value}
                        onChange={() => field.onChange(option.value)}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>
            )}
          />

          <div className="space-y-1.5">
            <label htmlFor="preview-discount-value" className="block text-sm font-medium text-text-main">
              Discount {watched.discountType === 'fixed' ? '(₹)' : '(%)'}
            </label>
            <input
              id="preview-discount-value"
              type="number"
              min={0}
              step={watched.discountType === 'fixed' ? 100 : 1}
              className={fieldClass}
              {...register('discountValue', { valueAsNumber: true })}
            />
            {errors.discountValue ? (
              <p className="text-xs text-red-700">{errors.discountValue.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="preview-discount-reason" className="block text-sm font-medium text-text-main">
              Discount reason
            </label>
            <select id="preview-discount-reason" className={fieldClass} {...register('discountReason')}>
              {reasons.map(reason => (
                <option key={reason} value={reason}>
                  {reason}
                </option>
              ))}
            </select>
            {errors.discountReason ? (
              <p className="text-xs text-red-700">{errors.discountReason.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="preview-adjustment-amount"
              className="block text-sm font-medium text-text-main"
            >
              Adjustment / credit (₹)
            </label>
            <input
              id="preview-adjustment-amount"
              type="number"
              min={0}
              step={0.01}
              className={fieldClass}
              {...register('adjustmentAmount', { valueAsNumber: true })}
            />
            <p className="text-xs text-text-muted">
              Non-discount credits such as refunds or goodwill adjustments.
            </p>
            {errors.adjustmentAmount ? (
              <p className="text-xs text-red-700">{errors.adjustmentAmount.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="preview-adjustment-note" className="block text-sm font-medium text-text-main">
              Adjustment note
            </label>
            <input
              id="preview-adjustment-note"
              type="text"
              maxLength={200}
              placeholder="Optional ledger note"
              className={fieldClass}
              {...register('adjustmentNote')}
            />
          </div>
        </div>

        <div className="space-y-3 rounded-xl border border-border-subtle bg-surface-bg/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Live totals
          </p>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">Subtotal</dt>
              <dd className="font-medium text-text-main">₹{formatMoneyInr(totals.subtotal)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">
                Discount
                {watched.discountReason ? ` · ${watched.discountReason}` : ''}
              </dt>
              <dd className="font-medium text-text-main">
                −₹{formatMoneyInr(totals.discountAmount)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">After discount</dt>
              <dd className="font-medium text-text-main">
                ₹{formatMoneyInr(totals.taxableAfterDiscount)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">Adjustment / credit</dt>
              <dd className="font-medium text-text-main">
                −₹{formatMoneyInr(totals.adjustmentAmount)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">Taxable (GST {gstPercentage}%)</dt>
              <dd className="font-medium text-text-main">
                ₹{formatMoneyInr(totals.taxableAfterAdjustment)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-muted">GST</dt>
              <dd className="font-medium text-text-main">₹{formatMoneyInr(totals.gstAmount)}</dd>
            </div>
            <div className="flex justify-between gap-3 border-t border-border-subtle pt-2 text-base">
              <dt className="font-semibold text-text-main">Final total</dt>
              <dd className="font-bold text-text-main">₹{formatMoneyInr(totals.finalTotal)}</dd>
            </div>
          </dl>

          {totals.requiresAuthorization ? (
            <div
              className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
              role="alert"
            >
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <p>
                <span className="font-semibold">Authorization required.</span> Discount is{' '}
                {totals.discountPercentOfSubtotal}% of subtotal, above the auto-approve limit of{' '}
                {maxAutoApproveDiscountPercent}%.
              </p>
            </div>
          ) : (
            <p className="text-xs text-text-muted">
              Auto-approve limit: {maxAutoApproveDiscountPercent}% of subtotal.
            </p>
          )}
        </div>
      </div>
    </section>
  );
};

export default InvoiceAdjustmentPreview;
