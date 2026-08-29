import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { AlertTriangle, ArrowRight, Loader2, Receipt } from 'lucide-react';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import { apiFetch } from '../utils/api';
import { useCountries } from '../hooks/useCountries';
import { useCounsellors } from '../hooks/useCounsellorAvailability';
import { useEducationMajors } from '../hooks/useEducationMajors';
import { useLevels } from '../hooks/useLevels';
import { useAdminSettingsStore } from '../stores/adminSettingsStore';
import { useInvoiceWorkspaceStore } from '../stores/invoiceWorkspaceStore';
import type { InvoiceDocument } from '../schemas/invoiceWorkspaceSchema';
import { formatMoneyInr } from '../utils/invoiceMoney';
import {
  computeInvoiceWorkspaceTotals,
  resolveSupplyType,
  type InvoiceWorkspaceTotals,
} from '../utils/invoiceTotals';
import { normalizeTaxRegimes } from '../utils/taxRegimes';
import type { CandidateProfile } from '../types/candidateProfile';
import {
  formatLocalIsoDate,
  parseLocalIsoDate,
  profileToForm,
  validateStudentMasterForm,
} from '../types/candidateProfile';
import {
  aspirationsToForm,
  INTAKE_CALENDAR_SYSTEMS,
  validateAspirationsForm,
  type StudentAspirationsResponse,
} from '../types/studentAspirations';
import {
  AGREEMENT_METHOD_OPTIONS,
  DECLINE_OUTCOME_OPTIONS,
  PAYMENT_MODE_OPTIONS,
  PAYMENT_PLAN_OPTIONS,
  emptyRegistrationForm,
  registrationToForm,
  registrationToSavePayload,
  registrationAgreementOnlySavePayload,
  resolveFixedPartAmount,
  remainingBalanceAfterCollectionsInr,
  totalCollectedInr,
  validateRegistrationForm,
  withChronologicalDueDates,
  withPaymentMilestones,
  type PaymentMode,
  type PaymentPlan,
  type StudentRegistrationFormState,
  type StudentRegistrationResponse,
} from '../types/studentRegistration';
import type { BookingRowForProfile } from '../utils/candidateProfileLoader';
import { loadBookingCandidateProfile } from '../utils/candidateProfileLoader';
import { computeAgeFromDob } from '../utils/phoneCountry';
import { nexusDatePickerModalPortalProps } from '../utils/nexusDatePickerPortal';
import { useAllowNextNavigation } from '../context/UnsavedChangesContext';
import {
  studentInfoAlertErrorClass as alertErrorClass,
  studentInfoAlertSuccessClass as alertSuccessClass,
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoGhostBtnClass as ghostBtnClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
  studentInfoMutedClass as mutedClass,
  studentInfoPrimaryBtnClass as primaryBtnClass,
  studentInfoSectionClass as sectionClass,
} from './studentInfoFormStyles';

interface RegistrationTabProps {
  booking: BookingRowForProfile;
  onStatusUpdated?: (stageName: string, statusId: number | null) => void;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const radioOptionClass = 'inline-flex items-center gap-1.5 text-sm text-text-main cursor-pointer';

const RequiredLabel: React.FC<{ htmlFor?: string; children: React.ReactNode }> = ({
  htmlFor,
  children,
}) => (
  <label htmlFor={htmlFor} className={labelClass}>
    {children}
    <span className="text-red-600" aria-hidden="true">
      {' '}
      *
    </span>
  </label>
);

function displayValue(value: string | null | undefined): string {
  const trimmed = (value || '').trim();
  return trimmed || '—';
}

function normalizeName(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function digitsOnly(value: string | null | undefined): string {
  return (value || '').replace(/\D/g, '');
}

function invoiceDisplayNumber(invoice: InvoiceDocument, previewNumber: string): string {
  const issued = invoice.invoiceNumber?.trim();
  if (issued) return issued;
  if (invoice.status === 'draft' && previewNumber.trim()) {
    return `${previewNumber.trim()} (preview)`;
  }
  return invoice.id;
}

function invoiceTotalsFor(
  invoice: InvoiceDocument,
  settings: {
    gstPercentage: number;
    gstNumber: string;
    taxRegimes: ReturnType<typeof normalizeTaxRegimes>;
    maxAutoApprove: number;
  }
): InvoiceWorkspaceTotals {
  const gstPercentage =
    invoice.status === 'issued' || invoice.status === 'void'
      ? invoice.gstPercentageSnapshot || settings.gstPercentage
      : settings.gstPercentage;
  return computeInvoiceWorkspaceTotals({
    lines: invoice.lines,
    discountType: invoice.discountType,
    discountValue: invoice.discountValue,
    gstPercentage,
    regimes: settings.taxRegimes,
    supplyType: resolveSupplyType({
      placeOfSupplyStateCode: invoice.placeOfSupplyStateCode,
      organizationGstin: settings.gstNumber,
      forceExempt: invoice.forceExempt,
    }),
    maxAutoApproveDiscountPercent: settings.maxAutoApprove,
  });
}

function invoiceFinalAmount(invoice: InvoiceDocument, totals: InvoiceWorkspaceTotals): number {
  if (
    (invoice.status === 'issued' || invoice.status === 'void') &&
    Number.isFinite(invoice.finalPayableSnapshot) &&
    invoice.finalPayableSnapshot > 0
  ) {
    return invoice.finalPayableSnapshot;
  }
  return totals.finalPayableAmount;
}

function discountLabel(invoice: InvoiceDocument): string {
  if (invoice.discountType === 'percentage') {
    return `Discount (${invoice.discountValue}%)`;
  }
  return 'Discount';
}

function taxRows(totals: InvoiceWorkspaceTotals): { label: string; amount: number }[] {
  if (totals.tax.supplyType === 'intra') {
    return [
      { label: `CGST (${totals.tax.cgstRate}%)`, amount: totals.tax.cgstAmount },
      { label: `SGST (${totals.tax.sgstRate}%)`, amount: totals.tax.sgstAmount },
    ];
  }
  if (totals.tax.supplyType === 'inter') {
    return [{ label: `IGST (${totals.tax.igstRate}%)`, amount: totals.tax.igstAmount }];
  }
  return [{ label: 'GST (exempt)', amount: 0 }];
}

function invoicesForStudent(
  rows: InvoiceDocument[],
  match: {
    studentMasterId?: number | string | null;
    leadId?: number | null;
    email?: string | null;
    name?: string | null;
    phone?: string | null;
  }
): InvoiceDocument[] {
  const master = String(match.studentMasterId ?? '').trim();
  const emailNorm = (match.email || '').trim().toLowerCase();
  const nameNorm = normalizeName(match.name);
  const phoneNorm = digitsOnly(match.phone);
  return rows.filter(row => {
    if (master && row.studentMasterId?.trim() === master) return true;
    if (match.leadId != null && row.leadId === match.leadId) return true;
    if (emailNorm && (row.email || '').trim().toLowerCase() === emailNorm) return true;
    if (nameNorm && normalizeName(row.studentFullName) === nameNorm) return true;
    if (phoneNorm.length >= 8 && digitsOnly(row.phone).endsWith(phoneNorm.slice(-10))) return true;
    return false;
  });
}

const INVOICE_STAMP_FORMAT: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: undefined,
  hour12: false,
};

function invoiceStatusLabel(status: InvoiceDocument['status']): string {
  if (status === 'void') return 'Cancelled';
  if (status === 'draft') return 'Draft';
  if (status === 'issued') return 'Issued';
  if (status === 'archived') return 'Archived';
  return status;
}

function snapshotInvoice(
  invoice: InvoiceDocument,
  amountInr?: number | null
): Partial<StudentRegistrationFormState> {
  const payable =
    amountInr ?? (invoice.finalPayableSnapshot > 0 ? invoice.finalPayableSnapshot : null);
  return {
    invoice_id: invoice.id,
    invoice_number: invoice.invoiceNumber || invoice.id,
    invoice_status: invoice.status,
    invoice_amount_inr: payable,
    invoice_date: invoice.invoiceDate || '',
    total_payable_inr: payable,
    amount_paid_inr: payable,
    payment_due_date: '',
    payment_paid_on: '',
    next_payment_date: '',
    payment_plan: '',
    payment_received: null,
    milestone_count: 2,
    milestone_fixed_amount_inr: null,
    payment_milestones: [],
  };
}

type InvoicePaymentDraft = Pick<
  StudentRegistrationFormState,
  | 'invoice_id'
  | 'invoice_number'
  | 'invoice_status'
  | 'invoice_amount_inr'
  | 'invoice_date'
  | 'payment_received'
  | 'payment_mode'
  | 'total_payable_inr'
  | 'amount_paid_inr'
  | 'payment_due_date'
  | 'payment_paid_on'
  | 'next_payment_date'
  | 'payment_plan'
  | 'milestone_count'
  | 'milestone_fixed_amount_inr'
  | 'payment_milestones'
>;

const INITIAL_BILLING_TAB = 'initial';

function paymentDraftFromForm(form: StudentRegistrationFormState): InvoicePaymentDraft {
  return {
    invoice_id: form.invoice_id,
    invoice_number: form.invoice_number,
    invoice_status: form.invoice_status,
    invoice_amount_inr: form.invoice_amount_inr,
    invoice_date: form.invoice_date,
    payment_received: form.payment_received,
    payment_mode: form.payment_mode,
    total_payable_inr: form.total_payable_inr,
    amount_paid_inr: form.amount_paid_inr,
    payment_due_date: form.payment_due_date,
    payment_paid_on: form.payment_paid_on,
    next_payment_date: form.next_payment_date,
    payment_plan: form.payment_plan,
    milestone_count: form.milestone_count,
    milestone_fixed_amount_inr: form.milestone_fixed_amount_inr,
    payment_milestones: form.payment_milestones,
  };
}

function freshInvoicePaymentDraft(
  invoice: InvoiceDocument,
  payable: number | null
): InvoicePaymentDraft {
  return {
    invoice_id: invoice.id,
    invoice_number: invoice.invoiceNumber || invoice.id,
    invoice_status: invoice.status,
    invoice_amount_inr: payable,
    invoice_date: invoice.invoiceDate || '',
    payment_received: null,
    payment_mode: '',
    total_payable_inr: payable,
    amount_paid_inr: null,
    payment_due_date: '',
    payment_paid_on: '',
    next_payment_date: '',
    payment_plan: '',
    milestone_count: 2,
    milestone_fixed_amount_inr: null,
    payment_milestones: [],
  };
}

function paymentTypeLabel(plan: PaymentPlan | '' | null | undefined): string {
  if (plan === 'full') return 'Full';
  if (plan === 'advance') return 'Part';
  if (plan === 'fixed_cost') return 'Instalments';
  if (plan === 'fixed_emi') return 'EMI';
  return '—';
}

function moneyOrDash(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `₹ ${formatMoneyInr(value)}`;
}

function shortDateLabel(iso: string | null | undefined): string {
  const trimmed = (iso || '').trim();
  if (!trimmed) return '—';
  const parsed = parseLocalIsoDate(trimmed);
  if (!parsed) return trimmed;
  return parsed.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  });
}

/** Days until due (negative = overdue). null if no valid due date. */
function daysUntilDue(dueIso: string | null | undefined, todayIso: string): number | null {
  const due = (dueIso || '').trim();
  if (!due || !/^\d{4}-\d{2}-\d{2}$/.test(due)) return null;
  const today = (todayIso || '').trim();
  if (!today) return null;
  const dueMs = Date.parse(`${due}T00:00:00`);
  const todayMs = Date.parse(`${today}T00:00:00`);
  if (!Number.isFinite(dueMs) || !Number.isFinite(todayMs)) return null;
  return Math.round((dueMs - todayMs) / 86_400_000);
}

const PAYMENT_DUE_APPROACHING_DAYS = 7;

type DueDateTone = 'ok' | 'approaching' | 'overdue' | 'paid' | 'none';

function dueDateTone(
  dueIso: string | null | undefined,
  received: boolean,
  todayIso: string
): DueDateTone {
  if (received) return 'paid';
  const days = daysUntilDue(dueIso, todayIso);
  if (days == null) return 'none';
  if (days < 0) return 'overdue';
  if (days <= PAYMENT_DUE_APPROACHING_DAYS) return 'approaching';
  return 'ok';
}

function dueDateClass(tone: DueDateTone): string {
  if (tone === 'overdue') return 'font-semibold text-red-700';
  if (tone === 'approaching') return 'font-semibold text-amber-800';
  if (tone === 'paid') return 'text-emerald-800';
  if (tone === 'ok') return 'text-text-muted';
  return 'text-text-muted';
}

function paymentAmountClass(received: boolean, hasAmount: boolean): string {
  if (!hasAmount) return 'font-medium tabular-nums text-text-muted';
  if (received) return 'font-semibold tabular-nums text-emerald-700';
  return 'font-semibold tabular-nums text-violet-700';
}

function MatrixPaymentCell({
  amount,
  due,
  paidOn,
  received,
  todayIso,
}: {
  amount: number | null;
  due: string;
  paidOn: string;
  received: boolean;
  todayIso: string;
}): React.ReactElement {
  const hasAmount = amount != null && Number.isFinite(amount);
  const tone = dueDateTone(due, received, todayIso);
  const dueLabel =
    tone === 'overdue'
      ? `Overdue ${shortDateLabel(due)}`
      : tone === 'approaching'
        ? `Due soon ${shortDateLabel(due)}`
        : `Due ${shortDateLabel(due)}`;

  return (
    <td className="whitespace-nowrap px-3 py-2 text-right">
      <div className={paymentAmountClass(received, hasAmount)}>{moneyOrDash(amount)}</div>
      {hasAmount ? (
        <div className="mt-0.5 space-y-0.5 text-[10px] font-normal">
          <div className={dueDateClass(tone)}>{dueLabel}</div>
          <div className={received ? 'text-emerald-700' : 'text-text-muted'}>
            Paid {shortDateLabel(received ? paidOn : '')}
          </div>
        </div>
      ) : null}
    </td>
  );
}

type PaymentReceiptStatusTone = 'muted' | 'awaiting' | 'stage1' | 'stage2' | 'stage3' | 'complete';

type PaymentReceiptStatus = {
  label: string;
  tone: PaymentReceiptStatusTone;
  receivedCount: number;
  expectedCount: number;
};

function paymentReceiptStatusClass(tone: PaymentReceiptStatusTone): string {
  if (tone === 'complete') return 'bg-emerald-100 text-emerald-800 ring-emerald-200';
  if (tone === 'stage1') return 'bg-amber-100 text-amber-950 ring-amber-200';
  if (tone === 'stage2') return 'bg-sky-100 text-sky-950 ring-sky-200';
  if (tone === 'stage3') return 'bg-violet-100 text-violet-950 ring-violet-200';
  if (tone === 'awaiting') return 'bg-slate-100 text-slate-700 ring-slate-200';
  return 'bg-surface-bg text-text-muted ring-border-subtle';
}

function derivePaymentReceiptStatus(
  draft: InvoicePaymentDraft,
  balance: number
): PaymentReceiptStatus {
  if (!draft.payment_plan) {
    return { label: 'No plan', tone: 'muted', receivedCount: 0, expectedCount: 0 };
  }

  const milestones = draft.payment_milestones || [];
  const expectedCount = 1 + milestones.length;
  let receivedCount = 0;
  if (draft.payment_received === true) receivedCount += 1;
  for (const milestone of milestones) {
    if (milestone.payment_received === true) receivedCount += 1;
  }

  const complete =
    (expectedCount > 0 && receivedCount >= expectedCount) ||
    (receivedCount > 0 && balance < 0.01);

  if (complete) {
    return {
      label: 'Payment complete',
      tone: 'complete',
      receivedCount,
      expectedCount,
    };
  }
  if (receivedCount <= 0) {
    return {
      label: 'Awaiting payment',
      tone: 'awaiting',
      receivedCount,
      expectedCount,
    };
  }
  if (receivedCount === 1) {
    return {
      label: expectedCount > 1 ? `1st of ${expectedCount} received` : '1st received',
      tone: 'stage1',
      receivedCount,
      expectedCount,
    };
  }
  if (receivedCount === 2) {
    return {
      label: expectedCount > 2 ? `2nd of ${expectedCount} received` : '2nd received',
      tone: 'stage2',
      receivedCount,
      expectedCount,
    };
  }
  return {
    label: `${receivedCount} of ${expectedCount} received`,
    tone: 'stage3',
    receivedCount,
    expectedCount,
  };
}

type BillingMatrixRow = {
  invoiceId: string;
  invoiceNumber: string;
  packageLabel: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  totalPayable: number;
  paymentType: string;
  payment1: number | null;
  payment1Due: string;
  payment1PaidOn: string;
  payment1Received: boolean;
  payment2: number | null;
  payment2Due: string;
  payment2PaidOn: string;
  payment2Received: boolean;
  payment3: number | null;
  payment3Due: string;
  payment3PaidOn: string;
  payment3Received: boolean;
  balance: number;
  debit: number;
  credit: number;
  paymentReceipt: PaymentReceiptStatus;
};

function invoicePackageLabel(invoice: InvoiceDocument): string {
  if (invoice.billingMode === 'alacarte') return 'A La Carte';
  const packageName = (invoice.packageName || '').trim();
  if (packageName) return packageName;
  return '—';
}

function paymentDraftStorageKey(bookingId: number | string): string {
  return `nexus.billing-payment-drafts.${bookingId}`;
}

function readStoredPaymentDrafts(bookingId: number | string): Record<string, InvoicePaymentDraft> {
  try {
    const raw = localStorage.getItem(paymentDraftStorageKey(bookingId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, InvoicePaymentDraft>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeStoredPaymentDrafts(
  bookingId: number | string,
  drafts: Record<string, InvoicePaymentDraft>
): void {
  try {
    localStorage.setItem(paymentDraftStorageKey(bookingId), JSON.stringify(drafts));
  } catch {
    // Ignore quota / private-mode failures; in-memory cache still works for the session.
  }
}

function resolvePaymentDraftForInvoice(
  invoice: InvoiceDocument,
  form: StudentRegistrationFormState,
  paymentByInvoiceId: Record<string, InvoicePaymentDraft>,
  payable: number | null
): InvoicePaymentDraft {
  const byId = paymentByInvoiceId[invoice.id];
  if (byId) return byId;
  if (form.invoice_id === invoice.id) return paymentDraftFromForm(form);
  const initial = paymentByInvoiceId[INITIAL_BILLING_TAB];
  if (initial?.invoice_id === invoice.id) return initial;
  return freshInvoicePaymentDraft(invoice, payable);
}

function draftCreditInr(draft: InvoicePaymentDraft): number {
  let credit = 0;
  if (draft.payment_received === true && draft.amount_paid_inr != null) {
    credit += draft.amount_paid_inr;
  }
  for (const milestone of draft.payment_milestones || []) {
    if (milestone.payment_received === true && milestone.amount_inr != null) {
      credit += milestone.amount_inr;
    }
  }
  return credit;
}

function applyPaymentDraftToForm(
  form: StudentRegistrationFormState,
  draft: InvoicePaymentDraft | null | undefined
): StudentRegistrationFormState {
  if (!draft) return form;
  const merged = { ...form, ...draft };
  return {
    ...merged,
    ...withPaymentMilestones(merged, draft),
  };
}

function paymentDraftFromRegistration(
  registration: StudentRegistrationFormState
): InvoicePaymentDraft | null {
  if (!registration.invoice_id?.trim()) return null;
  const hasDraftSignal =
    Boolean(registration.payment_plan) ||
    registration.payment_received === true ||
    Boolean(registration.payment_mode) ||
    registration.amount_paid_inr != null ||
    (registration.payment_milestones || []).length > 0;
  if (!hasDraftSignal) return null;
  return paymentDraftFromForm(registration);
}

const RegistrationTab: React.FC<RegistrationTabProps> = ({ booking, onStatusUpdated }) => {
  const { formatDateTime } = useBusinessTimezone();
  const navigate = useNavigate();
  const allowNextNavigation = useAllowNextNavigation();
  const queryClient = useQueryClient();
  const todayIso = useMemo(() => formatLocalIsoDate(new Date()), []);
  const defaultManagerId = booking.admin_id != null ? String(booking.admin_id) : '';

  const [form, setForm] = useState<StudentRegistrationFormState>(() =>
    emptyRegistrationForm({ agreementDate: todayIso, accountManagerId: defaultManagerId })
  );
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [aspirationsRaw, setAspirationsRaw] = useState<unknown>(null);
  const [statusLabel, setStatusLabel] = useState(booking.status_stage_name ?? '');
  const [futureStageName, setFutureStageName] = useState('Document: In Preparation');
  const [completesAsName, setCompletesAsName] = useState('Counselling: Prospect Qualified');
  const [studentsMasterId, setStudentsMasterId] = useState<number | null>(null);
  const [leadId, setLeadId] = useState<number | null>(booking.lead_id ?? null);
  const [registrationComplete, setRegistrationComplete] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const { countries } = useCountries();
  const { levels } = useLevels();
  const { majors } = useEducationMajors();
  const { data: counsellors = [] } = useCounsellors();
  const feeCatalog = useAdminSettingsStore(state => state.feeCatalog);
  const gstNumber = useAdminSettingsStore(state => state.gstNumber);
  const gstPercentageRaw = useAdminSettingsStore(state => state.gstPercentage);
  const taxRegimesRaw = useAdminSettingsStore(state => state.taxRegimes);
  const maxAutoApproveRaw = useAdminSettingsStore(state => state.maxAutoApproveDiscountPercent);
  const previewNextInvoiceId = useAdminSettingsStore(state => state.previewNextInvoiceId);
  const bankPayments = useAdminSettingsStore(state => state.bankPayments);
  const invoices = useInvoiceWorkspaceStore(state => state.invoices);
  const setActiveInvoiceId = useInvoiceWorkspaceStore(state => state.setActiveInvoiceId);
  const [pdfBusyId, setPdfBusyId] = useState<string | null>(null);
  const [billingSubTab, setBillingSubTab] = useState<string>(INITIAL_BILLING_TAB);
  const [paymentByInvoiceId, setPaymentByInvoiceId] = useState<Record<string, InvoicePaymentDraft>>(
    () => readStoredPaymentDrafts(booking.id)
  );
  const [invoicesHydrated, setInvoicesHydrated] = useState(() => {
    try {
      return Boolean(useInvoiceWorkspaceStore.persist?.hasHydrated?.());
    } catch {
      return true;
    }
  });

  useEffect(() => {
    const persistApi = useInvoiceWorkspaceStore.persist;
    if (!persistApi?.onFinishHydration) {
      setInvoicesHydrated(true);
      return;
    }
    const unsub = persistApi.onFinishHydration(() => setInvoicesHydrated(true));
    if (persistApi.hasHydrated?.()) setInvoicesHydrated(true);
    return unsub;
  }, []);

  const personalForm = useMemo(() => (profile ? profileToForm(profile) : null), [profile]);
  const aspirationsForm = useMemo(
    () =>
      aspirationsToForm(
        ((aspirationsRaw as { aspirations?: unknown } | null)?.aspirations ??
          aspirationsRaw) as Parameters<typeof aspirationsToForm>[0]
      ),
    [aspirationsRaw]
  );

  const personalIncomplete = useMemo(() => {
    if (!personalForm) return true;
    return Object.keys(validateStudentMasterForm(personalForm)).length > 0;
  }, [personalForm]);

  const aspirationsIncomplete = useMemo(
    () => validateAspirationsForm(aspirationsForm).length > 0,
    [aspirationsForm]
  );

  const age = useMemo(
    () => computeAgeFromDob(personalForm?.date_of_birth || profile?.date_of_birth),
    [personalForm?.date_of_birth, profile?.date_of_birth]
  );
  const under18 = age != null && age < 18;

  const fullName = useMemo(() => {
    if (!personalForm) return booking.candidate_name || '';
    return [personalForm.first_name, personalForm.middle_name, personalForm.last_name]
      .map(part => part.trim())
      .filter(Boolean)
      .join(' ');
  }, [booking.candidate_name, personalForm]);

  const phoneDisplay = useMemo(() => {
    if (!personalForm) return booking.candidate_phone || '';
    const local = personalForm.phone_local.trim();
    const iso = personalForm.phone_country_iso2.trim();
    if (iso && local) return `${iso} ${local}`;
    return local || profile?.phone_number || booking.candidate_phone || '';
  }, [booking.candidate_phone, personalForm]);

  const countryLabels = useMemo(() => {
    const byIso = new Map(countries.map(country => [country.iso2.toUpperCase(), country.name]));
    return aspirationsForm.study_countries_iso2
      .map(iso => byIso.get(iso.toUpperCase()) || iso)
      .filter(Boolean);
  }, [aspirationsForm.study_countries_iso2, countries]);

  const levelLabel = useMemo(() => {
    const code = aspirationsForm.study_level_code.trim();
    if (!code) return '';
    return levels.find(level => level.code === code)?.name || code;
  }, [aspirationsForm.study_level_code, levels]);

  const majorLabels = useMemo(() => {
    const byCode = new Map(
      majors.map(major => [(major.code || major.label).toUpperCase(), major.label])
    );
    return aspirationsForm.programs.map(program => {
      if (program === 'OTHER') return aspirationsForm.programs_other.trim() || 'Other';
      return byCode.get(program.toUpperCase()) || program;
    });
  }, [aspirationsForm.programs, aspirationsForm.programs_other, majors]);

  const intakeLabel = useMemo(() => {
    const years = aspirationsForm.intake_years.join(', ');
    const calendar = INTAKE_CALENDAR_SYSTEMS.find(
      system => system.value === aspirationsForm.intake_calendar_system
    );
    const terms = (calendar?.terms || [])
      .filter(term => aspirationsForm.intake_terms.includes(term.value))
      .map(term => term.label);
    return [terms.join(' / '), years].filter(Boolean).join(' · ');
  }, [
    aspirationsForm.intake_calendar_system,
    aspirationsForm.intake_terms,
    aspirationsForm.intake_years,
  ]);

  const billingTotalsSettings = useMemo(() => {
    const gstPercentage = Number.isFinite(gstPercentageRaw)
      ? Math.min(100, Math.max(0, gstPercentageRaw))
      : 18;
    const maxAutoApprove = Number.isFinite(maxAutoApproveRaw)
      ? Math.min(100, Math.max(0, maxAutoApproveRaw))
      : 20;
    return {
      gstPercentage,
      gstNumber,
      taxRegimes: normalizeTaxRegimes(taxRegimesRaw),
      maxAutoApprove,
    };
  }, [gstNumber, gstPercentageRaw, maxAutoApproveRaw, taxRegimesRaw]);
  const previewInvoiceNumber = previewNextInvoiceId();
  const activePackages = useMemo(
    () => feeCatalog.bundles.filter(bundle => bundle.active).sort((a, b) => a.sortOrder - b.sortOrder),
    [feeCatalog.bundles]
  );
  const activeServices = useMemo(
    () => feeCatalog.services.filter(service => service.active).sort((a, b) => a.sortOrder - b.sortOrder),
    [feeCatalog.services]
  );
  const selectedPackage = useMemo(
    () => activePackages.find(bundle => bundle.id === form.package_id) ?? null,
    [activePackages, form.package_id]
  );

  const agreementDate = useMemo(
    () => parseLocalIsoDate(form.agreement_date),
    [form.agreement_date]
  );

  const studentInvoices = useMemo(
    () =>
      invoicesForStudent(invoices, {
        studentMasterId: studentsMasterId,
        leadId: leadId ?? booking.lead_id,
        email: personalForm?.email || booking.candidate_email,
        name: fullName || booking.candidate_name,
        phone: personalForm?.phone_local || booking.candidate_phone,
      }),
    [
      booking.candidate_email,
      booking.candidate_name,
      booking.candidate_phone,
      booking.lead_id,
      fullName,
      invoices,
      leadId,
      personalForm?.email,
      personalForm?.phone_local,
      studentsMasterId,
    ]
  );
  const sortedStudentInvoices = useMemo(
    () =>
      [...studentInvoices].sort((a, b) =>
        String(a.createdAt || a.invoiceDate || a.id).localeCompare(
          String(b.createdAt || b.invoiceDate || b.id)
        )
      ),
    [studentInvoices]
  );

  /** Earliest student invoice that has a package — stays stable across later invoices. */
  const firstSelectedInvoicePackage = useMemo(() => {
    for (const invoice of sortedStudentInvoices) {
      const packageId = (invoice.packageId || '').trim();
      const packageName = (invoice.packageName || '').trim();
      if (!packageId && !packageName) continue;
      const fromCatalog =
        (packageId && activePackages.find(bundle => bundle.id === packageId)) ||
        (packageName &&
          activePackages.find(
            bundle => bundle.name.trim().toLowerCase() === packageName.toLowerCase()
          )) ||
        null;
      return {
        id: packageId || fromCatalog?.id || '',
        name: fromCatalog?.name?.trim() || packageName || '',
      };
    }
    return null;
  }, [activePackages, sortedStudentInvoices]);

  const agreementServicesPackageLabel = useMemo(() => {
    const fromForm = selectedPackage?.name?.trim();
    if (fromForm) return fromForm;
    if ((form.package_id || '').trim()) {
      const match = activePackages.find(bundle => bundle.id === (form.package_id || '').trim());
      if (match?.name?.trim()) return match.name.trim();
    }
    if (firstSelectedInvoicePackage?.name) return firstSelectedInvoicePackage.name;
    if (form.service_ids.length) {
      return form.service_ids
        .map(id => activeServices.find(service => service.id === id)?.name || id)
        .join(', ');
    }
    return '—';
  }, [
    activePackages,
    activeServices,
    firstSelectedInvoicePackage,
    form.package_id,
    form.service_ids,
    selectedPackage,
  ]);

  // Lock registration package to the first selected invoice package once known.
  useEffect(() => {
    if (!firstSelectedInvoicePackage) return;
    setForm(prev => {
      if ((prev.package_id || '').trim()) return prev;
      if (!firstSelectedInvoicePackage.id && !firstSelectedInvoicePackage.name) return prev;
      return {
        ...prev,
        package_id: firstSelectedInvoicePackage.id || prev.package_id,
      };
    });
  }, [firstSelectedInvoicePackage]);

  const focusedInvoice = useMemo(() => {
    if (billingSubTab !== INITIAL_BILLING_TAB) {
      return sortedStudentInvoices.find(row => row.id === billingSubTab) ?? null;
    }
    return (
      sortedStudentInvoices.find(row => row.id === form.invoice_id) ??
      sortedStudentInvoices.find(row => row.status === 'issued') ??
      sortedStudentInvoices[0] ??
      null
    );
  }, [billingSubTab, form.invoice_id, sortedStudentInvoices]);
  const billingInvoice = focusedInvoice;
  const hasIssuedInvoice = focusedInvoice?.status === 'issued';
  const hasBillingInvoice = Boolean(billingInvoice);
  const amountCollected = totalCollectedInr(form);
  const paymentBalance = remainingBalanceAfterCollectionsInr(form.total_payable_inr, form);
  const isInitialBillingTab = billingSubTab === INITIAL_BILLING_TAB;

  const billingMatrixRows = useMemo((): BillingMatrixRow[] => {
    return sortedStudentInvoices.map(invoice => {
      const totals = invoiceTotalsFor(invoice, billingTotalsSettings);
      const totalPayable = invoiceFinalAmount(invoice, totals);
      const draft = resolvePaymentDraftForInvoice(
        invoice,
        form,
        paymentByInvoiceId,
        totalPayable
      );
      const milestones = draft.payment_milestones || [];
      const debit = totalPayable;
      const credit = draftCreditInr(draft);
      const balance = debit - credit;
      return {
        invoiceId: invoice.id,
        invoiceNumber: invoiceDisplayNumber(invoice, previewInvoiceNumber),
        packageLabel: invoicePackageLabel(invoice),
        status: invoiceStatusLabel(invoice.status),
        createdAt: invoice.createdAt,
        updatedAt:
          invoice.status === 'draft'
            ? invoice.draftSavedAt || invoice.updatedAt || invoice.createdAt
            : invoice.updatedAt || invoice.createdAt,
        totalPayable,
        paymentType: paymentTypeLabel(draft.payment_plan),
        payment1: draft.amount_paid_inr,
        payment1Due: draft.payment_due_date || '',
        payment1PaidOn:
          draft.payment_received === true ? draft.payment_paid_on || '' : '',
        payment1Received: draft.payment_received === true,
        payment2: milestones[0]?.amount_inr ?? null,
        payment2Due: milestones[0]?.due_date || '',
        payment2PaidOn:
          milestones[0]?.payment_received === true ? milestones[0]?.paid_on || '' : '',
        payment2Received: milestones[0]?.payment_received === true,
        payment3: milestones[1]?.amount_inr ?? null,
        payment3Due: milestones[1]?.due_date || '',
        payment3PaidOn:
          milestones[1]?.payment_received === true ? milestones[1]?.paid_on || '' : '',
        payment3Received: milestones[1]?.payment_received === true,
        balance,
        debit,
        credit,
        paymentReceipt: derivePaymentReceiptStatus(draft, balance),
      };
    });
  }, [
    billingTotalsSettings,
    form,
    paymentByInvoiceId,
    previewInvoiceNumber,
    sortedStudentInvoices,
  ]);

  const billingMatrixTotals = useMemo(() => {
    return billingMatrixRows.reduce(
      (acc, row) => ({
        debit: acc.debit + row.debit,
        credit: acc.credit + row.credit,
        balance: acc.balance + row.balance,
      }),
      { debit: 0, credit: 0, balance: 0 }
    );
  }, [billingMatrixRows]);

  const load = useCallback(async () => {
    const [profileResult, aspirationsResult, registrationResult] = await Promise.all([
      loadBookingCandidateProfile(booking, apiFetch).catch(() => null),
      apiFetch(`bookings/mine/${booking.id}/aspirations`).catch(() => null),
      apiFetch(`bookings/mine/${booking.id}/registration`).catch(() => null) as Promise<StudentRegistrationResponse | null>,
    ]);
    if (profileResult?.profile) setProfile(profileResult.profile);
    if (aspirationsResult) setAspirationsRaw(aspirationsResult);
    const nextForm = registrationToForm(registrationResult?.registration, {
      agreementDate: todayIso,
      accountManagerId: defaultManagerId,
    });
    const storedDrafts = readStoredPaymentDrafts(booking.id);
    const fromRegistration = paymentDraftFromRegistration(nextForm);
    const mergedDrafts = { ...storedDrafts };
    if (fromRegistration?.invoice_id) {
      const existing = mergedDrafts[fromRegistration.invoice_id];
      // Prefer richer local draft (e.g. EMI selection) over a sparse server row.
      mergedDrafts[fromRegistration.invoice_id] =
        existing?.payment_plan || (existing?.payment_milestones || []).length
          ? existing
          : fromRegistration;
    }
    setPaymentByInvoiceId(mergedDrafts);
    writeStoredPaymentDrafts(booking.id, mergedDrafts);

    const activeInvoiceId = nextForm.invoice_id.trim();
    const restoreDraft =
      (activeInvoiceId && mergedDrafts[activeInvoiceId]) ||
      mergedDrafts[INITIAL_BILLING_TAB] ||
      fromRegistration;
    setForm(restoreDraft ? applyPaymentDraftToForm(nextForm, restoreDraft) : nextForm);
    if (registrationResult?.status_stage_name) {
      setStatusLabel(registrationResult.status_stage_name);
    }
    if (registrationResult?.future_status_stage_name) {
      setFutureStageName(registrationResult.future_status_stage_name);
    }
    if (registrationResult?.completes_as_status_stage_name) {
      setCompletesAsName(registrationResult.completes_as_status_stage_name);
    }
    if (registrationResult?.students_master_id != null) {
      setStudentsMasterId(registrationResult.students_master_id);
    } else if (profileResult?.profile?.students_master_id != null) {
      setStudentsMasterId(profileResult.profile.students_master_id);
    }
    if (registrationResult?.lead_id != null) {
      setLeadId(registrationResult.lead_id);
    }
    setRegistrationComplete(Boolean(registrationResult?.registration_complete));
  }, [booking, defaultManagerId, todayIso]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);
    load()
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load registration.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (!isInitialBillingTab) return;
    if (!billingInvoice || form.invoice_id) return;
    const totals = invoiceTotalsFor(billingInvoice, billingTotalsSettings);
    const payable = invoiceFinalAmount(billingInvoice, totals);
    const cached = paymentByInvoiceId[billingInvoice.id];
    setForm(prev =>
      cached
        ? applyPaymentDraftToForm(prev, cached)
        : {
            ...prev,
            ...snapshotInvoice(billingInvoice, payable),
          }
    );
  }, [
    billingInvoice,
    billingTotalsSettings,
    form.invoice_id,
    isInitialBillingTab,
    paymentByInvoiceId,
  ]);

  useEffect(() => {
    if (billingSubTab === INITIAL_BILLING_TAB) return;
    if (sortedStudentInvoices.some(row => row.id === billingSubTab)) return;
    setBillingSubTab(INITIAL_BILLING_TAB);
  }, [billingSubTab, sortedStudentInvoices]);

  const updateForm = (patch: Partial<StudentRegistrationFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    const keys = Object.keys(patch);
    if (keys.length) {
      setFieldErrors(prev => {
        const next = { ...prev };
        keys.forEach(key => {
          delete next[key];
        });
        return next;
      });
    }
  };

  const updatePayment = (patch: Partial<StudentRegistrationFormState>) => {
    setForm(prev => {
      const next = { ...prev, ...withPaymentMilestones(prev, patch) };
      const cacheKey =
        billingSubTab === INITIAL_BILLING_TAB
          ? (next.invoice_id || '').trim() || INITIAL_BILLING_TAB
          : (next.invoice_id || '').trim() || billingSubTab;
      if (cacheKey) {
        setPaymentByInvoiceId(prevCache => {
          const nextCache = {
            ...prevCache,
            [cacheKey]: paymentDraftFromForm(next),
          };
          writeStoredPaymentDrafts(booking.id, nextCache);
          return nextCache;
        });
      }
      return next;
    });
    setSuccess(null);
    const keys = Object.keys(patch);
    if (keys.length) {
      setFieldErrors(prev => {
        const next = { ...prev };
        [
          ...keys,
          'next_payment_date',
          'payment_plan',
          'milestone_count',
          'milestone_fixed_amount_inr',
          'payment_milestones',
        ].forEach(key => {
          delete next[key];
        });
        return next;
      });
    }
  };

  const selectBillingSubTab = (nextTab: string) => {
    if (nextTab === billingSubTab) return;
    const nextCache = { ...paymentByInvoiceId };

    if (billingSubTab === INITIAL_BILLING_TAB) {
      nextCache[INITIAL_BILLING_TAB] = paymentDraftFromForm(form);
      if (form.invoice_id.trim() && (form.payment_plan || form.payment_received != null)) {
        nextCache[form.invoice_id.trim()] = paymentDraftFromForm(form);
      }
    } else {
      const invoiceKey = form.invoice_id.trim() || billingSubTab;
      nextCache[invoiceKey] = paymentDraftFromForm(form);
    }
    setPaymentByInvoiceId(nextCache);
    writeStoredPaymentDrafts(booking.id, nextCache);

    if (nextTab === INITIAL_BILLING_TAB) {
      // Keep the current payment draft on the form so matrix totals stay correct.
      setBillingSubTab(INITIAL_BILLING_TAB);
      setSuccess(null);
      return;
    }

    const invoice = sortedStudentInvoices.find(row => row.id === nextTab);
    if (!invoice) return;
    const totals = invoiceTotalsFor(invoice, billingTotalsSettings);
    const payable = invoiceFinalAmount(invoice, totals);
    const saved = nextCache[invoice.id];
    const draft = saved ?? freshInvoicePaymentDraft(invoice, payable);
    setForm(prev => applyPaymentDraftToForm(prev, draft));
    setBillingSubTab(nextTab);
    setSuccess(null);
  };

  const openInvoiceWorkspace = (invoiceId?: string) => {
    if (invoiceId) setActiveInvoiceId(invoiceId);
    allowNextNavigation();
    navigate('/invoices');
  };

  const openInvoicePdfWindow = async (invoice: InvoiceDocument) => {
    setError(null);
    setPdfBusyId(invoice.id);
    try {
      const totals = invoiceTotalsFor(invoice, billingTotalsSettings);
      const { exportInvoicePdf } = await import('../utils/exportInvoicePdf');
      const manager = counsellors.find(
        row => String(row.id) === String(form.assigned_account_manager_id || invoice.counselorId)
      );
      const { blob } = await exportInvoicePdf({
        invoice,
        totals,
        bank: bankPayments[0] ?? null,
        orgGstin: invoice.orgGstinSnapshot || gstNumber,
        gstPercentage: invoice.gstPercentageSnapshot || billingTotalsSettings.gstPercentage,
        accountManager: {
          name: (invoice.counselorName || manager?.name || '').trim(),
          email: (manager?.email || '').trim(),
        },
        download: false,
      });
      const url = URL.createObjectURL(blob);
      const opened = window.open(url, '_blank', 'noopener,noreferrer');
      if (!opened) {
        URL.revokeObjectURL(url);
        setError('Allow pop-ups to view the invoice PDF in a new window.');
        return;
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open invoice PDF.');
    } finally {
      setPdfBusyId(null);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    const activeInvoiceKey =
      billingSubTab === INITIAL_BILLING_TAB
        ? form.invoice_id.trim()
        : form.invoice_id.trim() || billingSubTab;
    const cachedForActive =
      (activeInvoiceKey ? paymentByInvoiceId[activeInvoiceKey] : null) || null;

    if (isInitialBillingTab) {
      const validation = validateRegistrationForm(form, {
        under18,
        hasIssuedInvoice,
        todayIso,
        requirePaymentDecision: false,
      });
      // Agreement panel only — ignore payment-field errors if any slipped in.
      const agreementErrors = Object.fromEntries(
        Object.entries(validation).filter(
          ([key]) =>
            ![
              'payment_received',
              'payment_mode',
              'payment_plan',
              'amount_paid_inr',
              'payment_due_date',
              'payment_paid_on',
              'total_payable_inr',
              'invoice_id',
              'next_payment_date',
              'milestone_count',
              'milestone_fixed_amount_inr',
              'payment_milestones',
            ].includes(key)
        )
      );
      if (Object.keys(agreementErrors).length) {
        setFieldErrors(agreementErrors);
        setError('Please complete the required registration fields.');
        setSuccess(null);
        return;
      }
      try {
        setSaving(true);
        setError(null);
        setSuccess(null);
        const preserved =
          cachedForActive ||
          (form.invoice_id.trim() ? paymentDraftFromForm(form) : null);
        const response = (await apiFetch(`bookings/mine/${booking.id}/registration`, {
          method: 'PUT',
          body: JSON.stringify(
            registrationAgreementOnlySavePayload(form, preserved, {
              keepPaymentConfirmed:
                registrationComplete && form.agrees_to_register === true,
            })
          ),
        })) as StudentRegistrationResponse;
        const responseForm = registrationToForm(response.registration, {
          agreementDate: todayIso,
          accountManagerId: defaultManagerId,
        });
        // Keep local invoice payment drafts untouched by this agreement-only save.
        const restoreDraft =
          (activeInvoiceKey ? paymentByInvoiceId[activeInvoiceKey] : null) ||
          preserved ||
          paymentDraftFromRegistration(responseForm);
        setForm(
          restoreDraft ? applyPaymentDraftToForm(responseForm, restoreDraft) : responseForm
        );
        if (response.status_stage_name) setStatusLabel(response.status_stage_name);
        if (response.future_status_stage_name) {
          setFutureStageName(response.future_status_stage_name);
        }
        if (response.completes_as_status_stage_name) {
          setCompletesAsName(response.completes_as_status_stage_name);
        }
        if (response.students_master_id != null) {
          setStudentsMasterId(response.students_master_id);
        }
        if (response.lead_id != null) setLeadId(response.lead_id);
        setRegistrationComplete(Boolean(response.registration_complete));
        onStatusUpdated?.(response.status_stage_name || '', response.status_definition_id);
        await queryClient.invalidateQueries({ queryKey: ['bookings', 'mine', booking.id] });
        await queryClient.invalidateQueries({
          queryKey: ['bookings', 'profile-pulse', booking.id],
        });
        if (response.lead_id) {
          await queryClient.invalidateQueries({
            queryKey: ['student-journey', response.lead_id],
          });
          await queryClient.invalidateQueries({
            queryKey: ['valid-transitions', response.lead_id],
          });
        }
        if (response.registration.agrees_to_register === true) {
          setSuccess(
            response.registration_complete
              ? `Registration complete. Pipeline is now ${response.status_stage_name || completesAsName}.`
              : 'Registration agreement saved. Confirm payment on an invoice tab to qualify this student.'
          );
        } else if (response.registration.agrees_to_register === false) {
          setSuccess(
            response.status_stage_name
              ? `Saved. Pipeline is now ${response.status_stage_name}.`
              : 'Decline outcome saved.'
          );
        } else {
          setSuccess('Registration details saved.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save registration.');
      } finally {
        setSaving(false);
      }
      return;
    }

    const saveForm =
      cachedForActive?.payment_plan && !form.payment_plan
        ? applyPaymentDraftToForm(form, cachedForActive)
        : form;

    const validation = validateRegistrationForm(saveForm, {
      under18,
      hasIssuedInvoice,
      todayIso,
      requirePaymentDecision: true,
    });
    if (Object.keys(validation).length) {
      setFieldErrors(validation);
      const firstError = Object.values(validation)[0];
      setError(
        firstError
          ? `Please complete the required fields: ${firstError}`
          : 'Please complete the required registration fields.'
      );
      setSuccess(null);
      return;
    }
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const draftToPersist = paymentDraftFromForm(saveForm);
      const nextCache = {
        ...paymentByInvoiceId,
        ...(draftToPersist.invoice_id
          ? { [draftToPersist.invoice_id]: draftToPersist }
          : {}),
        [billingSubTab]: draftToPersist,
      };
      setPaymentByInvoiceId(nextCache);
      writeStoredPaymentDrafts(booking.id, nextCache);

      const response = (await apiFetch(`bookings/mine/${booking.id}/registration`, {
        method: 'PUT',
        body: JSON.stringify(registrationToSavePayload(saveForm)),
      })) as StudentRegistrationResponse;
      const responseForm = registrationToForm(response.registration, {
        agreementDate: todayIso,
        accountManagerId: defaultManagerId,
      });
      const responseDraft = paymentDraftFromRegistration(responseForm);
      const mergedAfterSave = { ...nextCache };
      if (responseDraft?.invoice_id) {
        mergedAfterSave[responseDraft.invoice_id] =
          responseDraft.payment_plan || (responseDraft.payment_milestones || []).length
            ? responseDraft
            : mergedAfterSave[responseDraft.invoice_id] || responseDraft;
      }
      if (draftToPersist.invoice_id && draftToPersist.payment_plan) {
        mergedAfterSave[draftToPersist.invoice_id] = draftToPersist;
      }
      setPaymentByInvoiceId(mergedAfterSave);
      writeStoredPaymentDrafts(booking.id, mergedAfterSave);

      const restoreDraft =
        mergedAfterSave[billingSubTab] ||
        (draftToPersist.payment_plan ? draftToPersist : null) ||
        responseDraft;
      setForm(
        restoreDraft ? applyPaymentDraftToForm(responseForm, restoreDraft) : responseForm
      );
      if (response.status_stage_name) setStatusLabel(response.status_stage_name);
      if (response.future_status_stage_name) setFutureStageName(response.future_status_stage_name);
      if (response.completes_as_status_stage_name) {
        setCompletesAsName(response.completes_as_status_stage_name);
      }
      if (response.students_master_id != null) setStudentsMasterId(response.students_master_id);
      if (response.lead_id != null) setLeadId(response.lead_id);
      setRegistrationComplete(Boolean(response.registration_complete));
      onStatusUpdated?.(response.status_stage_name || '', response.status_definition_id);
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'mine', booking.id] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'profile-pulse', booking.id] });
      if (response.lead_id) {
        await queryClient.invalidateQueries({ queryKey: ['student-journey', response.lead_id] });
        await queryClient.invalidateQueries({ queryKey: ['valid-transitions', response.lead_id] });
      }
      if (response.registration.agrees_to_register === true) {
        if (response.registration_complete) {
          setSuccess(
            `Registration complete. Pipeline is now ${response.status_stage_name || completesAsName}. Future stage: ${response.future_status_stage_name || futureStageName}.`
          );
        } else {
          setSuccess('Payment draft saved. Confirm Payment Received to qualify this student.');
        }
      } else if (response.registration.agrees_to_register === false) {
        setSuccess(
          response.status_stage_name
            ? `Saved. Pipeline is now ${response.status_stage_name}.`
            : 'Decline outcome saved.'
        );
      } else {
        setSuccess('Registration details saved.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save registration.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        <Loader2 size={20} className="animate-spin mr-2" />
        <span className="text-sm">Loading registration…</span>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col">
      <div className="shrink-0 border-b border-border-subtle bg-surface-bg px-3 py-2">
        <div
          className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-card p-1"
          role="tablist"
          aria-label="Billing invoices"
        >
          <button
            type="button"
            role="tab"
            aria-selected={isInitialBillingTab}
            onClick={() => selectBillingSubTab(INITIAL_BILLING_TAB)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
              isInitialBillingTab
                ? 'bg-accent text-text-dark-bg shadow-sm'
                : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
            }`}
          >
            Registration
          </button>
          {sortedStudentInvoices.map(invoice => {
            const active = billingSubTab === invoice.id;
            const label = invoiceDisplayNumber(invoice, previewInvoiceNumber);
            return (
              <button
                key={invoice.id}
                type="button"
                role="tab"
                aria-selected={active}
                title={label}
                onClick={() => selectBillingSubTab(invoice.id)}
                className={`inline-flex max-w-[14rem] items-center gap-1.5 truncate rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
                  active
                    ? 'bg-accent text-text-dark-bg shadow-sm'
                    : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
                }`}
              >
                <Receipt size={13} className="shrink-0" />
                <span className="truncate font-mono text-xs sm:text-sm">{label}</span>
              </button>
            );
          })}
        </div>
        {!sortedStudentInvoices.length ? (
          <p className={`mt-2 ${mutedClass}`}>
            No invoices yet for this student. Create one in Invoice Workspace to add payment tabs.
          </p>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-4 py-4 space-y-4">
        {error ? <div className={alertErrorClass}>{error}</div> : null}
        {success ? <div className={alertSuccessClass}>{success}</div> : null}

        {isInitialBillingTab ? (
          <>
            <section className="min-w-0 rounded-lg border border-border-subtle bg-card/80 p-3 space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
                  Student profile
                </h3>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
                  <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                    Current stage
                  </p>
                  <p
                    className="min-w-0 truncate whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                    title={displayValue(statusLabel || booking.status_stage_name)}
                  >
                    {displayValue(statusLabel || booking.status_stage_name)}
                  </p>
                </div>
                <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
                  <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                    Completes as
                  </p>
                  <p
                    className="min-w-0 truncate whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                    title={completesAsName}
                  >
                    {completesAsName}
                  </p>
                </div>
                <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
                  <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                    Future stage
                  </p>
                  <p
                    className="flex min-w-0 items-center gap-1 whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                    title={futureStageName}
                  >
                    <ArrowRight size={14} className="shrink-0" />
                    <span className="truncate">{futureStageName}</span>
                  </p>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Name</dt>
                  <dd className="text-sm text-text-main break-words">{displayValue(fullName)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Email</dt>
                  <dd className="text-sm text-text-main break-words">
                    {displayValue(personalForm?.email || booking.candidate_email)}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Phone</dt>
                  <dd className="text-sm text-text-main">{displayValue(phoneDisplay)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                    Date of birth
                  </dt>
                  <dd className="text-sm text-text-main">
                    {displayValue(personalForm?.date_of_birth || profile?.date_of_birth)}
                    {age != null ? ` · ${age} yrs` : ''}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                    Target countries
                  </dt>
                  <dd className="text-sm text-text-main break-words">
                    {countryLabels.length ? countryLabels.join(', ') : '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Level</dt>
                  <dd className="text-sm text-text-main">{displayValue(levelLabel)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Majors</dt>
                  <dd className="text-sm text-text-main break-words">
                    {majorLabels.length ? majorLabels.join(', ') : '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Intake</dt>
                  <dd className="text-sm text-text-main break-words">{displayValue(intakeLabel)}</dd>
                </div>
              </dl>
              {personalIncomplete || aspirationsIncomplete ? (
                <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-950">
                  <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                  <p>
                    {personalIncomplete ? 'Personal profile is incomplete. ' : ''}
                    {aspirationsIncomplete ? 'Aspirations are incomplete. ' : ''}
                    You can still record the registration decision.
                  </p>
                </div>
              ) : null}

              <div className="border-t border-border-subtle pt-3 space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wide text-text-muted">
                  Application Processing Registration Agreement
                </h4>
          <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,0.7fr)_minmax(0,0.75fr)_minmax(0,0.8fr)_minmax(0,0.8fr)_minmax(8rem,0.9fr)_minmax(0,3.8fr)_auto]">
            <div className="min-w-0">
              <RequiredLabel>Agrees to register</RequiredLabel>
              <div
                className={`flex h-[42px] flex-wrap items-center gap-3 rounded-md border bg-card px-3 ${
                  fieldErrors.agrees_to_register
                    ? 'border-red-400 ring-1 ring-red-200'
                    : 'border-border-subtle'
                }`}
              >
                <label className={radioOptionClass}>
                  <input
                    type="radio"
                    name="agrees_to_register"
                    checked={form.agrees_to_register === true}
                    onChange={() =>
                      updateForm({
                        agrees_to_register: true,
                        decline_outcome: '',
                        agreement_date: form.agreement_date || todayIso,
                        agreement_method: form.agreement_method || 'in_session',
                        assigned_account_manager_id:
                          form.assigned_account_manager_id || defaultManagerId,
                      })
                    }
                  />
                  Yes
                </label>
                <label className={radioOptionClass}>
                  <input
                    type="radio"
                    name="agrees_to_register"
                    checked={form.agrees_to_register === false}
                    onChange={() => updateForm({ agrees_to_register: false, bill_now: false })}
                  />
                  No
                </label>
              </div>
              {fieldErrors.agrees_to_register ? (
                <p className={fieldErrorClass}>{fieldErrors.agrees_to_register}</p>
              ) : null}
            </div>

            <div className="min-w-0">
              <p className={labelClass}>Services / package</p>
              <p
                className="mt-0 flex h-[42px] items-center truncate rounded-md border border-border-subtle bg-surface-bg px-3 text-sm font-semibold text-text-main"
                title={agreementServicesPackageLabel}
              >
                {agreementServicesPackageLabel}
              </p>
            </div>

            <div className="min-w-0">
              <RequiredLabel htmlFor="registration-agreement-date">Registered date</RequiredLabel>
              <DatePicker
                id="registration-agreement-date"
                selected={agreementDate}
                onChange={(date: Date | null) =>
                  updateForm({ agreement_date: formatLocalIsoDate(date) })
                }
                dateFormat="dd MMM yyyy"
                maxDate={new Date()}
                disabled={form.agrees_to_register !== true}
                className={fieldClass(Boolean(fieldErrors.agreement_date))}
                wrapperClassName="w-full"
                calendarClassName="nexus-roster-datepicker"
                placeholderText="Select date"
                autoComplete="off"
                {...nexusDatePickerModalPortalProps}
              />
              {fieldErrors.agreement_date ? (
                <p className={fieldErrorClass}>{fieldErrors.agreement_date}</p>
              ) : null}
            </div>

            <div className="min-w-0">
              <RequiredLabel htmlFor="registration-agreement-method">Agreement method</RequiredLabel>
              <select
                id="registration-agreement-method"
                className={fieldClass(Boolean(fieldErrors.agreement_method))}
                value={form.agreement_method}
                disabled={form.agrees_to_register !== true}
                onChange={e =>
                  updateForm({
                    agreement_method: e.target
                      .value as StudentRegistrationFormState['agreement_method'],
                  })
                }
              >
                <option value="">Select…</option>
                {AGREEMENT_METHOD_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {fieldErrors.agreement_method ? (
                <p className={fieldErrorClass}>{fieldErrors.agreement_method}</p>
              ) : null}
            </div>

            <div className="min-w-0">
              <RequiredLabel htmlFor="registration-account-manager">
                <span className="whitespace-nowrap">Account manager</span>
              </RequiredLabel>
              <select
                id="registration-account-manager"
                className={fieldClass(Boolean(fieldErrors.assigned_account_manager_id))}
                value={form.assigned_account_manager_id}
                disabled={form.agrees_to_register !== true}
                onChange={e => updateForm({ assigned_account_manager_id: e.target.value })}
              >
                <option value="">Select…</option>
                {counsellors.map(counsellor => (
                  <option key={counsellor.id} value={String(counsellor.id)}>
                    {counsellor.name || counsellor.email || `Staff #${counsellor.id}`}
                  </option>
                ))}
              </select>
              {fieldErrors.assigned_account_manager_id ? (
                <p className={fieldErrorClass}>{fieldErrors.assigned_account_manager_id}</p>
              ) : null}
            </div>

            <div className="min-w-0">
              <label htmlFor="registration-notes" className={labelClass}>
                Registration note
              </label>
              <input
                id="registration-notes"
                type="text"
                className={fieldClass(Boolean(fieldErrors.notes))}
                maxLength={500}
                value={form.notes}
                onChange={e => updateForm({ notes: e.target.value })}
                placeholder="Short note…"
              />
              {fieldErrors.notes ? <p className={fieldErrorClass}>{fieldErrors.notes}</p> : null}
            </div>

            <div className="min-w-0 flex items-end">
              <button
                type="submit"
                className={`${primaryBtnClass} h-[42px] whitespace-nowrap`}
                disabled={saving}
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                Complete Registration
              </button>
            </div>
          </div>

          {form.agrees_to_register === true && under18 ? (
            <div className="mt-3">
              <label className={radioOptionClass}>
                <input
                  type="checkbox"
                  checked={form.parent_consent}
                  onChange={e => updateForm({ parent_consent: e.target.checked })}
                />
                Parent / guardian consent given
                <span className="text-red-600" aria-hidden="true">
                  {' '}
                  *
                </span>
              </label>
              {fieldErrors.parent_consent ? (
                <p className={fieldErrorClass}>{fieldErrors.parent_consent}</p>
              ) : (
                <p className={mutedClass}>Required because this student is under 18.</p>
              )}
            </div>
          ) : null}

          {form.agrees_to_register === false ? (
            <div className="mt-3">
              <RequiredLabel>If not registering</RequiredLabel>
              <div
                className={`flex flex-wrap items-center gap-4 rounded-md border bg-card px-3 py-2 ${
                  fieldErrors.decline_outcome
                    ? 'border-red-400 ring-1 ring-red-200'
                    : 'border-border-subtle'
                }`}
              >
                {DECLINE_OUTCOME_OPTIONS.map(option => (
                  <label key={option.value} className={radioOptionClass}>
                    <input
                      type="radio"
                      name="decline_outcome"
                      checked={form.decline_outcome === option.value}
                      onChange={() => updateForm({ decline_outcome: option.value })}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
              {fieldErrors.decline_outcome ? (
                <p className={fieldErrorClass}>{fieldErrors.decline_outcome}</p>
              ) : null}
            </div>
          ) : null}
              </div>
            </section>

            <section className={sectionClass}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
                    Invoice Payment Matrix
                  </h3>
                  <p className={mutedClass}>
                    Debits are invoice totals; credits are payments marked received.
                  </p>
                </div>
                <p className="text-xs text-text-muted">
                  {invoicesHydrated
                    ? `${studentInvoices.length} invoice(s)`
                    : 'Loading invoices…'}
                </p>
              </div>

              {!invoicesHydrated ? (
                <p className={mutedClass}>Loading invoices…</p>
              ) : !billingMatrixRows.length ? (
                <p className={mutedClass}>
                  No invoices yet for this student. Create one in Invoice Workspace to populate
                  this matrix.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-md border border-border-subtle">
                  <table className="min-w-full border-collapse text-left text-sm">
                    <thead className="bg-surface-bg text-[10px] font-bold uppercase tracking-wide text-text-muted">
                      <tr>
                        <th className="whitespace-nowrap px-3 py-2">Invoice #</th>
                        <th className="whitespace-nowrap px-3 py-2">Package</th>
                        <th className="whitespace-nowrap px-3 py-2">Status</th>
                        <th className="whitespace-nowrap px-3 py-2">Created</th>
                        <th className="whitespace-nowrap px-3 py-2">Updated</th>
                        <th className="whitespace-nowrap px-3 py-2 text-right">Total payable</th>
                        <th className="whitespace-nowrap px-3 py-2">Payment type</th>
                        <th className="whitespace-nowrap px-3 py-2 text-right">1st payment</th>
                        <th className="whitespace-nowrap px-3 py-2 text-right">2nd payment</th>
                        <th className="whitespace-nowrap px-3 py-2 text-right">3rd payment</th>
                        <th className="whitespace-nowrap px-3 py-2 text-right">Balance</th>
                        <th className="whitespace-nowrap px-3 py-2">Payment status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {billingMatrixRows.map(row => (
                        <tr
                          key={row.invoiceId}
                          className="cursor-pointer border-t border-border-subtle hover:bg-surface-bg/80"
                          onClick={() => selectBillingSubTab(row.invoiceId)}
                        >
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-xs font-semibold text-text-main">
                            {row.invoiceNumber}
                          </td>
                          <td
                            className="max-w-[12rem] truncate px-3 py-2 text-text-main"
                            title={row.packageLabel}
                          >
                            {row.packageLabel}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-text-main">{row.status}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-text-main">
                            {formatDateTime(row.createdAt, INVOICE_STAMP_FORMAT)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-text-main">
                            {formatDateTime(row.updatedAt, INVOICE_STAMP_FORMAT)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right font-medium text-text-main">
                            {moneyOrDash(row.totalPayable)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-text-main">
                            {row.paymentType}
                          </td>
                          <MatrixPaymentCell
                            amount={row.payment1}
                            due={row.payment1Due}
                            paidOn={row.payment1PaidOn}
                            received={row.payment1Received}
                            todayIso={todayIso}
                          />
                          <MatrixPaymentCell
                            amount={row.payment2}
                            due={row.payment2Due}
                            paidOn={row.payment2PaidOn}
                            received={row.payment2Received}
                            todayIso={todayIso}
                          />
                          <MatrixPaymentCell
                            amount={row.payment3}
                            due={row.payment3Due}
                            paidOn={row.payment3PaidOn}
                            received={row.payment3Received}
                            todayIso={todayIso}
                          />
                          <td className="whitespace-nowrap px-3 py-2 text-right font-semibold text-text-main">
                            {moneyOrDash(row.balance)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2">
                            <span
                              className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${paymentReceiptStatusClass(
                                row.paymentReceipt.tone
                              )}`}
                            >
                              {row.paymentReceipt.label}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-border-subtle bg-surface-bg font-semibold text-text-main">
                        <td className="px-3 py-2" colSpan={7}>
                          Totals
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right" colSpan={2}>
                          Debit {moneyOrDash(billingMatrixTotals.debit)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right">
                          Credit {moneyOrDash(billingMatrixTotals.credit)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right">
                          Balance {moneyOrDash(billingMatrixTotals.balance)}
                        </td>
                        <td className="px-3 py-2" />
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : (
          <>
        <section className="min-w-0 rounded-lg border border-border-subtle bg-card/80 p-2 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">Student summary</h3>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
              <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                Current stage
              </p>
              <p
                className="min-w-0 truncate whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                title={displayValue(statusLabel || booking.status_stage_name)}
              >
                {displayValue(statusLabel || booking.status_stage_name)}
              </p>
            </div>
            <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
              <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                Completes as
              </p>
              <p
                className="min-w-0 truncate whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                title={completesAsName}
              >
                {completesAsName}
              </p>
            </div>
            <div className="flex min-w-0 items-center gap-2 rounded-md bg-accent px-3 py-2 text-text-dark-bg">
              <p className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-text-dark-bg/80">
                Future stage
              </p>
              <p
                className="flex min-w-0 items-center gap-1 whitespace-nowrap text-sm font-semibold text-text-dark-bg"
                title={futureStageName}
              >
                <ArrowRight size={14} className="shrink-0" />
                <span className="truncate">{futureStageName}</span>
              </p>
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Name</dt>
              <dd className="text-sm text-text-main break-words">{displayValue(fullName)}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Email</dt>
              <dd className="text-sm text-text-main break-words">{displayValue(personalForm?.email || booking.candidate_email)}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Phone</dt>
              <dd className="text-sm text-text-main">{displayValue(phoneDisplay)}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Date of birth</dt>
              <dd className="text-sm text-text-main">
                {displayValue(personalForm?.date_of_birth || profile?.date_of_birth)}
                {age != null ? ` · ${age} yrs` : ''}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Target countries</dt>
              <dd className="text-sm text-text-main break-words">{countryLabels.length ? countryLabels.join(', ') : '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Level</dt>
              <dd className="text-sm text-text-main">{displayValue(levelLabel)}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Majors</dt>
              <dd className="text-sm text-text-main break-words">{majorLabels.length ? majorLabels.join(', ') : '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Intake</dt>
              <dd className="text-sm text-text-main break-words">{displayValue(intakeLabel)}</dd>
            </div>
          </dl>
          {personalIncomplete || aspirationsIncomplete ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-950">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <p>
                {personalIncomplete ? 'Personal profile is incomplete. ' : ''}
                {aspirationsIncomplete ? 'Aspirations are incomplete. ' : ''}
                You can still record the registration decision.
              </p>
            </div>
          ) : null}
        </section>

        <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
        <section className={`${sectionClass} min-w-0`}>
          <div className="flex items-start gap-2">
            <Receipt size={16} className="mt-0.5 text-accent shrink-0" />
            <div>
              <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">Billing</h3>
              <p className={mutedClass}>
                Invoice details for this student. Confirm payment on the right to complete
                registration and qualify the prospect.
              </p>
              <p className="mt-1 text-xs text-text-muted">
                {displayValue(fullName || booking.candidate_name)}
                {leadId ?? booking.lead_id ? ` · Lead #${leadId ?? booking.lead_id}` : ''}
                {studentsMasterId ? ` · Master #${studentsMasterId}` : ''}
                {invoicesHydrated ? ` · ${studentInvoices.length} invoice(s)` : ''}
              </p>
            </div>
          </div>

          {!invoicesHydrated ? (
            <p className={mutedClass}>Loading invoices…</p>
          ) : billingInvoice ? (
            <div className="space-y-2">
              {(() => {
                const invoice = billingInvoice;
                const selected = true;
                const totals = invoiceTotalsFor(invoice, billingTotalsSettings);
                const finalAmount = invoiceFinalAmount(invoice, totals);
                const taxes = taxRows(totals);
                return (
                  <div
                    key={invoice.id}
                    className={`rounded-md border px-3 py-3 space-y-2 ${
                      invoice.status === 'issued'
                        ? 'border-emerald-200 bg-emerald-50/60'
                        : invoice.status === 'draft'
                          ? 'border-amber-200 bg-amber-50/70'
                          : 'border-border-subtle bg-surface-bg'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-mono text-sm font-semibold text-text-main">
                          {invoiceDisplayNumber(invoice, previewInvoiceNumber)}
                        </p>
                        {invoice.status === 'draft' && !invoice.invoiceNumber ? (
                          <p className="mt-0.5 text-[11px] text-text-muted">
                            Preview number — assigned when this invoice is issued.
                          </p>
                        ) : null}
                      </div>
                      <span className="text-xs font-bold uppercase tracking-wide text-text-muted">
                        {invoiceStatusLabel(invoice.status)}
                        {selected && invoice.status === 'issued' ? ' · selected' : ''}
                      </span>
                    </div>
                    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                          Invoice date
                        </dt>
                        <dd className="text-sm text-text-main">{displayValue(invoice.invoiceDate)}</dd>
                      </div>
                      <div className="sm:col-span-2">
                        <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                          Package / services
                        </dt>
                        <dd className="text-sm text-text-main">
                          {invoice.packageName?.trim() ||
                            invoice.lines.map(line => line.name).filter(Boolean).join(', ') ||
                            '—'}
                        </dd>
                      </div>
                    </dl>
                    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                          Created
                        </dt>
                        <dd className="text-sm text-text-main">
                          {formatDateTime(invoice.createdAt, INVOICE_STAMP_FORMAT)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                          {invoice.status === 'draft' ? 'Last saved' : 'Updated'}
                        </dt>
                        <dd className="text-sm text-text-main">
                          {formatDateTime(
                            invoice.status === 'draft'
                              ? invoice.draftSavedAt || invoice.updatedAt || invoice.createdAt
                              : invoice.updatedAt || invoice.createdAt,
                            INVOICE_STAMP_FORMAT
                          )}
                        </dd>
                      </div>
                      {invoice.issuedAt ? (
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                            Issued
                          </dt>
                          <dd className="text-sm text-text-main">
                            {formatDateTime(invoice.issuedAt, INVOICE_STAMP_FORMAT)}
                          </dd>
                        </div>
                      ) : null}
                      {invoice.voidedAt ? (
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                            Cancelled
                          </dt>
                          <dd className="text-sm text-text-main">
                            {formatDateTime(invoice.voidedAt, INVOICE_STAMP_FORMAT)}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                    <dl className="space-y-1 rounded-md border border-border-subtle/80 bg-card/70 px-3 py-2">
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <dt className="text-text-muted">Subtotal</dt>
                        <dd className="tabular-nums text-text-main">
                          ₹ {formatMoneyInr(totals.linesSubtotal)}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <dt className="text-text-muted">
                          <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-alert/10 text-xs font-semibold text-alert">
                            −
                          </span>
                          {discountLabel(invoice)}
                        </dt>
                        <dd
                          className={`tabular-nums ${
                            totals.discountAmount > 0 ? 'text-alert' : 'text-text-main'
                          }`}
                        >
                          ₹ {formatMoneyInr(totals.discountAmount)}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <dt className="text-text-muted">Taxable</dt>
                        <dd className="tabular-nums text-text-main">
                          ₹ {formatMoneyInr(totals.taxableAmount)}
                        </dd>
                      </div>
                      {taxes.map(row => (
                        <div key={row.label} className="flex items-center justify-between gap-3 text-sm">
                          <dt className="text-text-muted">
                            <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent/10 text-xs font-semibold text-accent">
                              +
                            </span>
                            {row.label}
                          </dt>
                          <dd className="tabular-nums text-text-main">
                            ₹ {formatMoneyInr(row.amount)}
                          </dd>
                        </div>
                      ))}
                      {Math.abs(totals.roundOffAmount) >= 0.01 ? (
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <dt className="text-text-muted">
                            <span
                              className={`mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold ${
                                totals.roundOffAmount < 0
                                  ? 'bg-alert/10 text-alert'
                                  : 'bg-accent/10 text-accent'
                              }`}
                            >
                              {totals.roundOffAmount >= 0 ? '+' : '−'}
                            </span>
                            Round-off
                          </dt>
                          <dd
                            className={`tabular-nums ${
                              totals.roundOffAmount < 0 ? 'text-alert' : 'text-text-main'
                            }`}
                          >
                            ₹ {formatMoneyInr(Math.abs(totals.roundOffAmount))}
                          </dd>
                        </div>
                      ) : null}
                      <div className="flex items-center justify-between gap-3 border-t border-border-subtle pt-1.5 text-sm font-semibold">
                        <dt className="text-text-main">Final payable</dt>
                        <dd className="tabular-nums text-text-main">₹ {formatMoneyInr(finalAmount)}</dd>
                      </div>
                    </dl>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <button
                        type="button"
                        className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-text-dark-bg hover:opacity-90"
                        onMouseDown={event => event.stopPropagation()}
                        onClick={event => {
                          event.preventDefault();
                          event.stopPropagation();
                          openInvoiceWorkspace(invoice.id);
                        }}
                      >
                        Open in Invoice Workspace
                      </button>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-text-dark-bg hover:opacity-90 disabled:opacity-50"
                        disabled={pdfBusyId === invoice.id}
                        onMouseDown={event => event.stopPropagation()}
                        onClick={event => {
                          event.preventDefault();
                          event.stopPropagation();
                          void openInvoicePdfWindow(invoice);
                        }}
                      >
                        {pdfBusyId === invoice.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : null}
                        View Invoice PDF
                      </button>
                    </div>
                  </div>
                );
              })()}
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div>
                <p>No invoice has been raised for this student.</p>
                <p className="mt-0.5 text-xs opacity-90">
                  Create and issue an invoice in Invoice Workspace, then return here to confirm payment.
                </p>
                <button
                  type="button"
                  className="mt-1 inline-flex font-semibold text-accent hover:underline"
                  onMouseDown={event => event.stopPropagation()}
                  onClick={event => {
                    event.preventDefault();
                    event.stopPropagation();
                    openInvoiceWorkspace();
                  }}
                >
                  Open Invoice Workspace
                </button>
              </div>
            </div>
          )}
        </section>

        <section className={`${sectionClass} min-w-0`}>
          <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">Payment</h3>
          <p className={mutedClass}>
            Choose a payment plan and confirm Payment Received at each stage.
          </p>

          <div className="mt-3 grid grid-cols-3 gap-2 rounded-md border border-border-subtle bg-surface-bg px-3 py-2.5">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Total payable
              </p>
              <p className="mt-1 text-sm font-semibold tabular-nums text-text-main">
                {form.total_payable_inr != null
                  ? `₹ ${formatMoneyInr(form.total_payable_inr)}`
                  : '—'}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Amount paid
              </p>
              <p className="mt-1 text-sm font-semibold tabular-nums text-text-main">
                {amountCollected > 0 ? `₹ ${formatMoneyInr(amountCollected)}` : '—'}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Balance
              </p>
              <p
                className={`mt-1 text-sm font-semibold tabular-nums ${
                  paymentBalance >= 0.01 ? 'text-amber-900' : 'text-text-main'
                }`}
              >
                ₹ {formatMoneyInr(paymentBalance)}
              </p>
            </div>
          </div>
          {fieldErrors.total_payable_inr || fieldErrors.invoice_id ? (
            <p className={fieldErrorClass}>
              {fieldErrors.total_payable_inr || fieldErrors.invoice_id}
            </p>
          ) : !hasBillingInvoice ? (
            <p className={mutedClass}>Create an invoice first so totals can be filled.</p>
          ) : null}

          <div className="mt-3 space-y-3">
            <div>
              <RequiredLabel>Payment plan</RequiredLabel>
              <div
                className={`grid grid-cols-2 gap-2 rounded-md border bg-card px-3 py-2 sm:grid-cols-4 ${
                  fieldErrors.payment_plan ? 'border-red-400 ring-1 ring-red-200' : 'border-border-subtle'
                }`}
              >
                {PAYMENT_PLAN_OPTIONS.map(option => (
                  <label key={option.value} className={`${radioOptionClass} whitespace-nowrap`}>
                    <input
                      type="radio"
                      name="payment_plan"
                      checked={form.payment_plan === option.value}
                      disabled={!hasBillingInvoice}
                      onChange={() => {
                        if (!billingInvoice) return;
                        const totals = invoiceTotalsFor(billingInvoice, billingTotalsSettings);
                        const payable = invoiceFinalAmount(billingInvoice, totals);
                        const amountPaid =
                          option.value === 'full'
                            ? payable
                            : option.value === 'advance'
                              ? Math.min(
                                  payable || 0,
                                  form.amount_paid_inr ?? Math.round((payable || 0) / 2)
                                )
                              : form.amount_paid_inr ?? 0;
                        const balance = Math.max(0, (payable || 0) - (amountPaid || 0));
                        const instalmentAmount =
                          option.value === 'fixed_cost'
                            ? resolveFixedPartAmount(balance, null)
                            : form.milestone_fixed_amount_inr;
                        updatePayment({
                          payment_plan: option.value as PaymentPlan,
                          total_payable_inr: payable,
                          amount_paid_inr: amountPaid,
                          invoice_id: billingInvoice.id,
                          invoice_number: billingInvoice.invoiceNumber || billingInvoice.id,
                          invoice_status: billingInvoice.status,
                          invoice_amount_inr: payable,
                          invoice_date: billingInvoice.invoiceDate || '',
                          payment_received: null,
                          payment_due_date: form.payment_due_date || todayIso,
                          payment_paid_on: '',
                          milestone_fixed_amount_inr:
                            option.value === 'fixed_cost' ? instalmentAmount : null,
                          milestone_count: option.value === 'fixed_emi' ? form.milestone_count || 2 : 2,
                          next_payment_date:
                            option.value === 'full' ? '' : form.next_payment_date || todayIso,
                        });
                      }}
                    />
                    <span className="font-semibold">{option.label}</span>
                  </label>
                ))}
              </div>
              {fieldErrors.payment_plan ? (
                <p className={fieldErrorClass}>{fieldErrors.payment_plan}</p>
              ) : null}
            </div>

            {form.payment_plan ? (
              <div className="space-y-3 rounded-md border border-emerald-200 bg-emerald-50/40 px-3 py-3">
                <div
                  className={`grid grid-cols-1 gap-3 ${
                    form.payment_plan === 'fixed_cost' || form.payment_plan === 'fixed_emi'
                      ? 'lg:grid-cols-3 xl:grid-cols-6'
                      : 'sm:grid-cols-2 lg:grid-cols-5'
                  }`}
                >
                  <div className="min-w-0">
                    <RequiredLabel htmlFor="registration-payment-mode">Payment mode</RequiredLabel>
                    <select
                      id="registration-payment-mode"
                      className={fieldClass(Boolean(fieldErrors.payment_mode))}
                      value={form.payment_mode}
                      onChange={e =>
                        updateForm({ payment_mode: e.target.value as PaymentMode | '' })
                      }
                    >
                      <option value="">Select…</option>
                      {PAYMENT_MODE_OPTIONS.map(option => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    {fieldErrors.payment_mode ? (
                      <p className={fieldErrorClass}>{fieldErrors.payment_mode}</p>
                    ) : null}
                  </div>
                  <div className="min-w-0">
                    <RequiredLabel htmlFor="registration-amount-paid">
                      {form.payment_plan === 'full'
                        ? 'Amount paid'
                        : form.payment_plan === 'advance'
                          ? 'Part payment amount'
                          : 'Amount paid now'}
                    </RequiredLabel>
                    <input
                      id="registration-amount-paid"
                      type="number"
                      min={0}
                      step="0.01"
                      readOnly={form.payment_plan === 'full'}
                      className={fieldClass(Boolean(fieldErrors.amount_paid_inr))}
                      value={form.amount_paid_inr ?? ''}
                      onChange={e => {
                        if (form.payment_plan === 'full') return;
                        const raw = e.target.value;
                        updatePayment({
                          amount_paid_inr: raw === '' ? null : Number(raw),
                          payment_due_date: form.payment_due_date || todayIso,
                          next_payment_date: form.next_payment_date || todayIso,
                        });
                      }}
                    />
                    {fieldErrors.amount_paid_inr ? (
                      <p className={fieldErrorClass}>{fieldErrors.amount_paid_inr}</p>
                    ) : null}
                  </div>
                  <div className="min-w-0">
                    <RequiredLabel htmlFor="registration-payment-due-date">Due date</RequiredLabel>
                    <DatePicker
                      id="registration-payment-due-date"
                      selected={parseLocalIsoDate(form.payment_due_date)}
                      onChange={(date: Date | null) =>
                        updateForm({ payment_due_date: formatLocalIsoDate(date) })
                      }
                      dateFormat="dd MMM yyyy"
                      className={fieldClass(Boolean(fieldErrors.payment_due_date))}
                      wrapperClassName="w-full"
                      calendarClassName="nexus-roster-datepicker"
                      placeholderText="Promised date"
                      autoComplete="off"
                      {...nexusDatePickerModalPortalProps}
                    />
                    {fieldErrors.payment_due_date ? (
                      <p className={fieldErrorClass}>{fieldErrors.payment_due_date}</p>
                    ) : null}
                  </div>
                  <div className="min-w-0">
                    <RequiredLabel htmlFor="registration-payment-paid-on">Paid Date</RequiredLabel>
                    <DatePicker
                      id="registration-payment-paid-on"
                      selected={parseLocalIsoDate(form.payment_paid_on)}
                      onChange={(date: Date | null) => {
                        const paidOn = formatLocalIsoDate(date);
                        updateForm({
                          payment_paid_on: paidOn,
                          // Paid Date rules out No — clear it so user must choose Yes.
                          ...(paidOn && form.payment_received === false
                            ? { payment_received: null }
                            : {}),
                        });
                      }}
                      dateFormat="dd MMM yyyy"
                      maxDate={new Date()}
                      className={fieldClass(Boolean(fieldErrors.payment_paid_on))}
                      wrapperClassName="w-full"
                      calendarClassName="nexus-roster-datepicker"
                      placeholderText="Actual date"
                      autoComplete="off"
                      {...nexusDatePickerModalPortalProps}
                    />
                    {fieldErrors.payment_paid_on ? (
                      <p className={fieldErrorClass}>{fieldErrors.payment_paid_on}</p>
                    ) : null}
                  </div>
                  <div className="min-w-0">
                    <RequiredLabel>Payment Received</RequiredLabel>
                    <div
                      className={`flex h-[42px] flex-wrap items-center gap-4 rounded-md border bg-card px-3 ${
                        fieldErrors.payment_received
                          ? 'border-red-400 ring-1 ring-red-200'
                          : 'border-border-subtle'
                      }`}
                    >
                      <label className={radioOptionClass}>
                        <input
                          type="radio"
                          name="payment_received_current"
                          checked={form.payment_received === true}
                          disabled={!hasBillingInvoice}
                          onChange={() =>
                            updateForm({
                              payment_received: true,
                              payment_due_date: form.payment_due_date || todayIso,
                              payment_paid_on: form.payment_paid_on || todayIso,
                              agrees_to_register: true,
                              agreement_date: form.agreement_date || todayIso,
                              agreement_method: form.agreement_method || 'in_session',
                              assigned_account_manager_id:
                                form.assigned_account_manager_id || defaultManagerId,
                            })
                          }
                        />
                        Yes
                      </label>
                      <label
                        className={`${radioOptionClass}${
                          form.payment_paid_on?.trim() ? ' opacity-50 cursor-not-allowed' : ''
                        }`}
                      >
                        <input
                          type="radio"
                          name="payment_received_current"
                          checked={form.payment_received === false}
                          disabled={!hasBillingInvoice || Boolean(form.payment_paid_on?.trim())}
                          onChange={() =>
                            updateForm({ payment_received: false, payment_paid_on: '' })
                          }
                        />
                        No
                      </label>
                    </div>
                    {fieldErrors.payment_received ? (
                      <p className={fieldErrorClass}>{fieldErrors.payment_received}</p>
                    ) : !hasIssuedInvoice && hasBillingInvoice ? (
                      <p className={mutedClass}>Issue the invoice before completing registration.</p>
                    ) : null}
                  </div>
                  {form.payment_plan === 'fixed_cost' ? (
                    <div className="min-w-0">
                      <RequiredLabel htmlFor="registration-milestone-fixed">
                        Instalment amount
                      </RequiredLabel>
                      <input
                        id="registration-milestone-fixed"
                        type="number"
                        min={0.01}
                        step="0.01"
                        className={fieldClass(Boolean(fieldErrors.milestone_fixed_amount_inr))}
                        value={form.milestone_fixed_amount_inr ?? ''}
                        onChange={e => {
                          const raw = e.target.value;
                          updatePayment({
                            milestone_fixed_amount_inr: raw === '' ? null : Number(raw),
                            next_payment_date: form.next_payment_date || todayIso,
                          });
                        }}
                      />
                      {fieldErrors.milestone_fixed_amount_inr ? (
                        <p className={fieldErrorClass}>{fieldErrors.milestone_fixed_amount_inr}</p>
                      ) : null}
                    </div>
                  ) : null}
                  {form.payment_plan === 'fixed_emi' ? (
                    <div className="min-w-0">
                      <RequiredLabel htmlFor="registration-milestone-count">
                        Number of EMIs
                      </RequiredLabel>
                      <input
                        id="registration-milestone-count"
                        type="number"
                        min={2}
                        max={3}
                        className={fieldClass(Boolean(fieldErrors.milestone_count))}
                        value={form.milestone_count}
                        onChange={e =>
                          updatePayment({
                            milestone_count: Math.min(3, Math.max(2, Number(e.target.value) || 2)),
                            next_payment_date: form.next_payment_date || todayIso,
                          })
                        }
                      />
                      {fieldErrors.milestone_count ? (
                        <p className={fieldErrorClass}>{fieldErrors.milestone_count}</p>
                      ) : null}
                    </div>
                  ) : null}
                </div>

                {form.payment_milestones.length ? (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                      Upcoming payment stages
                    </p>
                    <ul className="mt-2 space-y-2">
                      {form.payment_milestones.map((milestone, index) => (
                        <li
                          key={milestone.id}
                          className="rounded-md border border-border-subtle bg-card px-3 py-2"
                        >
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
                            <div className="min-w-0">
                              <label
                                htmlFor={`milestone-mode-${milestone.id}`}
                                className="text-xs font-semibold uppercase tracking-wide text-text-muted"
                              >
                                Payment mode
                              </label>
                              <select
                                id={`milestone-mode-${milestone.id}`}
                                className={inputClass}
                                value={milestone.payment_mode}
                                onChange={e =>
                                  updateForm({
                                    payment_milestones: form.payment_milestones.map(row =>
                                      row.id === milestone.id
                                        ? {
                                            ...row,
                                            payment_mode: e.target.value as PaymentMode | '',
                                          }
                                        : row
                                    ),
                                  })
                                }
                              >
                                <option value="">Select…</option>
                                {PAYMENT_MODE_OPTIONS.map(option => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div className="min-w-0">
                              <label className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                                Due date
                              </label>
                              <DatePicker
                                selected={parseLocalIsoDate(milestone.due_date)}
                                onChange={(date: Date | null) => {
                                  const dueDate = formatLocalIsoDate(date);
                                  const ordered = withChronologicalDueDates(
                                    form.payment_milestones,
                                    index,
                                    dueDate
                                  );
                                  updateForm({
                                    payment_milestones: ordered,
                                    next_payment_date: ordered[0]?.due_date || form.next_payment_date,
                                  });
                                }}
                                dateFormat="dd MMM yyyy"
                                minDate={
                                  index > 0
                                    ? parseLocalIsoDate(form.payment_milestones[index - 1]?.due_date) ||
                                      undefined
                                    : undefined
                                }
                                className={inputClass}
                                wrapperClassName="w-full"
                                calendarClassName="nexus-roster-datepicker"
                                placeholderText="Promised date"
                                autoComplete="off"
                                {...nexusDatePickerModalPortalProps}
                              />
                            </div>
                            <div className="min-w-0">
                              <label className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                                Paid Date
                              </label>
                              <DatePicker
                                selected={parseLocalIsoDate(milestone.paid_on)}
                                onChange={(date: Date | null) => {
                                  const paidOn = formatLocalIsoDate(date);
                                  updateForm({
                                    payment_milestones: form.payment_milestones.map(row =>
                                      row.id === milestone.id
                                        ? {
                                            ...row,
                                            paid_on: paidOn,
                                            ...(paidOn && row.payment_received === false
                                              ? { payment_received: null }
                                              : {}),
                                          }
                                        : row
                                    ),
                                  });
                                }}
                                dateFormat="dd MMM yyyy"
                                maxDate={new Date()}
                                className={inputClass}
                                wrapperClassName="w-full"
                                calendarClassName="nexus-roster-datepicker"
                                placeholderText="Actual date"
                                autoComplete="off"
                                {...nexusDatePickerModalPortalProps}
                              />
                            </div>
                            <div className="min-w-0">
                              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                                Amount
                              </p>
                              <p className="mt-2 text-sm font-semibold tabular-nums text-text-main">
                                ₹ {formatMoneyInr(milestone.amount_inr)}
                              </p>
                            </div>
                            <div className="min-w-0">
                              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                                Payment Received
                              </p>
                              <div className="mt-1 flex h-[42px] flex-wrap items-center gap-4">
                                <label className={radioOptionClass}>
                                  <input
                                    type="radio"
                                    name={`milestone_received_${milestone.id}`}
                                    checked={milestone.payment_received === true}
                                    onChange={() =>
                                      updateForm({
                                        payment_milestones: form.payment_milestones.map(row =>
                                          row.id === milestone.id
                                            ? {
                                                ...row,
                                                payment_received: true,
                                                paid_on: row.paid_on || todayIso,
                                              }
                                            : row
                                        ),
                                      })
                                    }
                                  />
                                  Yes
                                </label>
                                <label
                                  className={`${radioOptionClass}${
                                    milestone.paid_on?.trim()
                                      ? ' opacity-50 cursor-not-allowed'
                                      : ''
                                  }`}
                                >
                                  <input
                                    type="radio"
                                    name={`milestone_received_${milestone.id}`}
                                    checked={milestone.payment_received === false}
                                    disabled={Boolean(milestone.paid_on?.trim())}
                                    onChange={() =>
                                      updateForm({
                                        payment_milestones: form.payment_milestones.map(row =>
                                          row.id === milestone.id
                                            ? {
                                                ...row,
                                                payment_received: false,
                                                paid_on: '',
                                              }
                                            : row
                                        ),
                                      })
                                    }
                                  />
                                  No
                                </label>
                              </div>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                    {fieldErrors.payment_milestones ? (
                      <p className={fieldErrorClass}>{fieldErrors.payment_milestones}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>
        </div>

          <section className={sectionClass}>
            <h3 className="text-sm font-bold uppercase tracking-wide text-text-main">
              Payment confirmation
            </h3>
            <p className={mutedClass}>
              Confirm payment for{' '}
              <span className="font-mono font-semibold text-text-main">
                {billingInvoice
                  ? invoiceDisplayNumber(billingInvoice, previewInvoiceNumber)
                  : 'this invoice'}
              </span>
              . Agreement fields stay on Registration.
            </p>
          </section>
          </>
        )}
      </div>

      {!isInitialBillingTab ? (
        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border-subtle bg-card px-4 py-3">
          <button
            type="button"
            className={ghostBtnClass}
            disabled={saving}
            onClick={() => void load()}
          >
            Reset
          </button>
          <button type="submit" className={primaryBtnClass} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            {form.payment_received === true && hasIssuedInvoice
              ? 'Save payment'
              : 'Save payment draft'}
          </button>
        </div>
      ) : null}
    </form>
  );
};

export default RegistrationTab;
