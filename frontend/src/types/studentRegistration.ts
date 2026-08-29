import { roundMoney } from '../utils/invoiceMoney';

export type AgreementMethod = 'in_session' | 'phone' | 'email' | 'parent_present';
export type DeclineOutcome = 'follow_up' | 'not_interested' | 'deferred';
export type PaymentMode = 'upi' | 'neft_imps' | 'rtgs' | 'card' | 'cash' | 'cheque' | 'other';
/** @deprecated kept for older saved registration JSON */
export type RemainingPaymentPlan = 'full' | 'parts';
/** @deprecated kept for older saved registration JSON */
export type MilestoneSplit = 'equal' | 'fixed';
export type PaymentPlan = 'full' | 'advance' | 'fixed_cost' | 'fixed_emi';

export const AGREEMENT_METHOD_OPTIONS: { value: AgreementMethod; label: string }[] = [
  { value: 'in_session', label: 'In session' },
  { value: 'phone', label: 'Phone' },
  { value: 'email', label: 'Email' },
  { value: 'parent_present', label: 'Parent present' },
];

export const DECLINE_OUTCOME_OPTIONS: { value: DeclineOutcome; label: string }[] = [
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'not_interested', label: 'Not interested' },
  { value: 'deferred', label: 'Deferred' },
];

export const PAYMENT_MODE_OPTIONS: { value: PaymentMode; label: string }[] = [
  { value: 'upi', label: 'UPI' },
  { value: 'neft_imps', label: 'NEFT / IMPS' },
  { value: 'rtgs', label: 'RTGS' },
  { value: 'card', label: 'Card' },
  { value: 'cash', label: 'Cash' },
  { value: 'cheque', label: 'Cheque / DD' },
  { value: 'other', label: 'Other' },
];

export const PAYMENT_PLAN_OPTIONS: {
  value: PaymentPlan;
  label: string;
  hint: string;
}[] = [
  {
    value: 'full',
    label: 'Full',
    hint: 'Collect the entire invoice amount now.',
  },
  {
    value: 'advance',
    label: 'Part Payment',
    hint: 'Collect a part now; schedule the balance as one remaining payment.',
  },
  {
    value: 'fixed_cost',
    label: 'Instalments (fixed amount)',
    hint: 'Split the balance into at most three fixed-amount part payments.',
  },
  {
    value: 'fixed_emi',
    label: 'EMI (equal)',
    hint: 'Split the balance into equal EMI instalments.',
  },
];

/** Max upcoming part payments for Instalments (fixed amount) and EMI. */
export const MAX_PART_PAYMENTS = 3;

export interface PaymentMilestone {
  id: string;
  due_date: string;
  /** Actual receipt date — may be earlier or later than due_date. */
  paid_on: string;
  amount_inr: number;
  payment_mode: PaymentMode | '';
  /** Payment Received Yes/No for this instalment stage. */
  payment_received: boolean | null;
}

export interface StudentRegistrationData {
  agrees_to_register: boolean | null;
  agreement_date: string | null;
  agreement_method: AgreementMethod | null;
  parent_consent: boolean | null;
  assigned_account_manager_id: number | null;
  package_id: string | null;
  service_ids: string[];
  bill_now: boolean;
  notes: string;
  decline_outcome: DeclineOutcome | null;
  invoice_id: string | null;
  invoice_number: string | null;
  invoice_status: string | null;
  invoice_amount_inr: number | null;
  invoice_date: string | null;
  payment_received: boolean;
  payment_confirmed_at: string | null;
  payment_mode: PaymentMode | null;
  total_payable_inr: number | null;
  amount_paid_inr: number | null;
  /** Promised / scheduled date for the current (1st) payment stage. */
  payment_due_date: string | null;
  /** Actual receipt date for the current (1st) payment stage. */
  payment_paid_on: string | null;
  next_payment_date: string | null;
  payment_plan: PaymentPlan | null;
  /** @deprecated */
  remaining_plan: RemainingPaymentPlan | null;
  /** @deprecated */
  milestone_split: MilestoneSplit | null;
  milestone_count: number | null;
  milestone_fixed_amount_inr: number | null;
  payment_milestones: PaymentMilestone[];
}

export interface StudentRegistrationResponse {
  students_master_id: number | null;
  booking_id: number | null;
  lead_id: number | null;
  status_definition_id: number | null;
  status_stage_name: string | null;
  future_status_definition_id: number | null;
  future_status_stage_name: string | null;
  completes_as_status_definition_id: number | null;
  completes_as_status_stage_name: string | null;
  registration: StudentRegistrationData;
  saved_at: string | null;
  registration_complete: boolean;
}

export type StudentRegistrationFormState = {
  agrees_to_register: boolean | null;
  agreement_date: string;
  agreement_method: AgreementMethod | '';
  parent_consent: boolean;
  assigned_account_manager_id: string;
  package_id: string;
  service_ids: string[];
  bill_now: boolean;
  notes: string;
  decline_outcome: DeclineOutcome | '';
  invoice_id: string;
  invoice_number: string;
  invoice_status: string;
  invoice_amount_inr: number | null;
  invoice_date: string;
  /** Current-stage Payment Received Yes/No. */
  payment_received: boolean | null;
  payment_mode: PaymentMode | '';
  total_payable_inr: number | null;
  amount_paid_inr: number | null;
  /** Promised / scheduled date for the current (1st) payment stage. */
  payment_due_date: string;
  /** Actual receipt date for the current (1st) payment stage. */
  payment_paid_on: string;
  next_payment_date: string;
  payment_plan: PaymentPlan | '';
  milestone_count: number;
  milestone_fixed_amount_inr: number | null;
  payment_milestones: PaymentMilestone[];
};

function legacyPaymentPlan(data: StudentRegistrationData): PaymentPlan | '' {
  if (data.payment_plan) return data.payment_plan;
  if (data.remaining_plan === 'full') return 'advance';
  if (data.remaining_plan === 'parts') {
    return data.milestone_split === 'fixed' ? 'fixed_cost' : 'fixed_emi';
  }
  if (
    data.payment_received &&
    data.total_payable_inr != null &&
    data.amount_paid_inr != null &&
    Math.abs(data.total_payable_inr - data.amount_paid_inr) < 0.01
  ) {
    return 'full';
  }
  return '';
}

export function emptyRegistrationForm(defaults?: {
  agreementDate?: string;
  accountManagerId?: string;
}): StudentRegistrationFormState {
  return {
    agrees_to_register: null,
    agreement_date: defaults?.agreementDate ?? '',
    agreement_method: '',
    parent_consent: false,
    assigned_account_manager_id: defaults?.accountManagerId ?? '',
    package_id: '',
    service_ids: [],
    bill_now: false,
    notes: '',
    decline_outcome: '',
    invoice_id: '',
    invoice_number: '',
    invoice_status: '',
    invoice_amount_inr: null,
    invoice_date: '',
    payment_received: null,
    payment_mode: '',
    total_payable_inr: null,
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

export function registrationToForm(
  data: StudentRegistrationData | null | undefined,
  defaults?: { agreementDate?: string; accountManagerId?: string }
): StudentRegistrationFormState {
  const empty = emptyRegistrationForm(defaults);
  if (!data) return empty;
  return {
    agrees_to_register: data.agrees_to_register ?? null,
    agreement_date: data.agreement_date || empty.agreement_date,
    agreement_method: data.agreement_method || '',
    parent_consent: data.parent_consent === true,
    assigned_account_manager_id:
      data.assigned_account_manager_id != null
        ? String(data.assigned_account_manager_id)
        : empty.assigned_account_manager_id,
    package_id: data.package_id || '',
    service_ids: Array.isArray(data.service_ids) ? data.service_ids.filter(Boolean) : [],
    bill_now: Boolean(data.bill_now),
    notes: data.notes || '',
    decline_outcome: data.decline_outcome || '',
    invoice_id: data.invoice_id || '',
    invoice_number: data.invoice_number || '',
    invoice_status: data.invoice_status || '',
    invoice_amount_inr: data.invoice_amount_inr ?? null,
    invoice_date: data.invoice_date || '',
    payment_received: data.payment_received === true ? true : data.payment_received === false ? false : null,
    payment_mode: data.payment_mode || '',
    total_payable_inr: data.total_payable_inr ?? data.invoice_amount_inr ?? null,
    amount_paid_inr: data.amount_paid_inr ?? null,
    payment_due_date: data.payment_due_date || '',
    payment_paid_on: data.payment_paid_on || '',
    next_payment_date: data.next_payment_date || '',
    payment_plan: legacyPaymentPlan(data),
    milestone_count: Math.min(3, Math.max(2, data.milestone_count || 2)),
    milestone_fixed_amount_inr: data.milestone_fixed_amount_inr ?? null,
    payment_milestones: Array.isArray(data.payment_milestones)
      ? data.payment_milestones
          .filter(row => row && typeof row === 'object')
          .map((row, index) => ({
            id: String(row.id || `ms_${index + 1}`),
            due_date: String(row.due_date || ''),
            paid_on: String(row.paid_on || ''),
            amount_inr: Number(row.amount_inr) || 0,
            payment_mode: (row.payment_mode || '') as PaymentMode | '',
            payment_received:
              row.payment_received === true ? true : row.payment_received === false ? false : null,
          }))
      : [],
  };
}

export function paymentBalanceInr(
  totalPayable: number | null | undefined,
  amountPaid: number | null | undefined
): number {
  if (totalPayable == null || amountPaid == null) return 0;
  return roundMoney(Math.max(0, totalPayable - amountPaid));
}

/** Amounts marked Payment Received = Yes (current stage + upcoming stages). */
export function totalCollectedInr(form: {
  amount_paid_inr: number | null;
  payment_received: boolean | null;
  payment_milestones: PaymentMilestone[];
}): number {
  let total = 0;
  if (form.payment_received === true && form.amount_paid_inr != null) {
    total += form.amount_paid_inr;
  }
  for (const milestone of form.payment_milestones || []) {
    if (milestone.payment_received === true) {
      total += Number(milestone.amount_inr) || 0;
    }
  }
  return roundMoney(total);
}

export function remainingBalanceAfterCollectionsInr(
  totalPayable: number | null | undefined,
  form: {
    amount_paid_inr: number | null;
    payment_received: boolean | null;
    payment_milestones: PaymentMilestone[];
  }
): number {
  if (totalPayable == null || !Number.isFinite(totalPayable)) return 0;
  return roundMoney(Math.max(0, totalPayable - totalCollectedInr(form)));
}

export function addCalendarMonths(iso: string, months: number): string {
  const [yearRaw, monthRaw, dayRaw] = iso.split('-').map(Number);
  if (!yearRaw || !monthRaw || !dayRaw) return iso;
  const absolute = yearRaw * 12 + (monthRaw - 1) + months;
  const year = Math.floor(absolute / 12);
  const monthIndex = ((absolute % 12) + 12) % 12;
  const lastDay = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  const day = Math.min(dayRaw, lastDay);
  return `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function keepMilestoneFlags(
  previous: PaymentMilestone[],
  next: PaymentMilestone[]
): PaymentMilestone[] {
  const byId = new Map(previous.map(row => [row.id, row]));
  return next.map(row => {
    const prev = byId.get(row.id);
    return {
      ...row,
      due_date: prev?.due_date || row.due_date,
      paid_on: prev?.paid_on || row.paid_on || '',
      payment_mode: prev?.payment_mode ?? row.payment_mode ?? '',
      payment_received: prev?.payment_received ?? row.payment_received ?? null,
    };
  });
}

/** Keep instalment due dates non-decreasing after a date edit. */
export function withChronologicalDueDates(
  milestones: PaymentMilestone[],
  changedIndex: number,
  newDueDate: string
): PaymentMilestone[] {
  const next = milestones.map((row, index) =>
    index === changedIndex ? { ...row, due_date: newDueDate } : { ...row }
  );
  if (!newDueDate) return next;

  if (changedIndex > 0) {
    const previous = next[changedIndex - 1]?.due_date;
    if (previous && next[changedIndex].due_date < previous) {
      next[changedIndex] = { ...next[changedIndex], due_date: previous };
    }
  }

  for (let index = changedIndex + 1; index < next.length; index += 1) {
    const earlier = next[index - 1]?.due_date;
    if (earlier && (!next[index].due_date || next[index].due_date < earlier)) {
      next[index] = { ...next[index], due_date: earlier };
    }
  }
  return next;
}

export function paymentMilestonesAreChronological(milestones: PaymentMilestone[]): boolean {
  for (let index = 1; index < milestones.length; index += 1) {
    const previous = milestones[index - 1]?.due_date;
    const current = milestones[index]?.due_date;
    if (previous && current && current < previous) return false;
  }
  return true;
}

/**
 * Round INR amounts to the nearer of ₹5,000 or ₹10,000 steps for instalment / EMI planning.
 * Sub-₹2,500 values stay as exact rupees so tiny balances are not wiped to 0.
 */
export function roundMoneyToNearest5kOr10k(amount: number): number {
  if (!Number.isFinite(amount) || amount < 0.01) return 0;
  const to5k = Math.round(amount / 5000) * 5000;
  const to10k = Math.round(amount / 10000) * 10000;
  const rounded =
    Math.abs(to5k - amount) <= Math.abs(to10k - amount) ? to5k : to10k;
  if (rounded < 0.01) return roundMoney(amount);
  return rounded;
}

/** If the 3rd instalment is under this amount, fold it into the first two. */
export const MIN_THIRD_PAYMENT_INR = 5000;

/**
 * When there are three part payments and the last is under ₹5,000,
 * split that amount equally into the first and second payments and drop the third.
 */
export function absorbSmallFinalPayment(milestones: PaymentMilestone[]): PaymentMilestone[] {
  if (milestones.length !== 3) return milestones;
  const thirdAmount = roundMoney(milestones[2]?.amount_inr || 0);
  if (thirdAmount >= MIN_THIRD_PAYMENT_INR - 0.009) return milestones;
  if (thirdAmount < 0.01) {
    return [
      { ...milestones[0], id: 'ms_1' },
      { ...milestones[1], id: 'ms_2' },
    ];
  }
  const firstShare = roundMoney(Math.floor((thirdAmount / 2) * 100) / 100);
  const secondShare = roundMoney(thirdAmount - firstShare);
  return [
    {
      ...milestones[0],
      id: 'ms_1',
      amount_inr: roundMoney((milestones[0]?.amount_inr || 0) + firstShare),
    },
    {
      ...milestones[1],
      id: 'ms_2',
      amount_inr: roundMoney((milestones[1]?.amount_inr || 0) + secondShare),
    },
  ];
}

/**
 * Resolve the fixed part-payment amount so the balance fits in at most
 * MAX_PART_PAYMENTS instalments (auto-splits into thirds when unset/too small).
 * Amounts are rounded to the nearer ₹5,000 / ₹10,000 step.
 */
export function resolveFixedPartAmount(
  balance: number,
  requested: number | null | undefined
): number {
  if (balance < 0.01) return 0;
  const minToFitInMaxParts = Math.ceil(balance / MAX_PART_PAYMENTS / 5000) * 5000;
  let fixed =
    requested != null && requested >= 0.01
      ? roundMoneyToNearest5kOr10k(requested)
      : roundMoneyToNearest5kOr10k(balance / MAX_PART_PAYMENTS);
  if (fixed < 0.01) {
    fixed = roundMoney(balance);
  }
  const needed = Math.ceil(balance / fixed - 1e-9);
  if (needed > MAX_PART_PAYMENTS) {
    fixed = minToFitInMaxParts > 0 ? minToFitInMaxParts : roundMoney(balance);
  }
  return Math.min(fixed, balance);
}

export function buildPaymentMilestones(
  form: Pick<
    StudentRegistrationFormState,
    | 'total_payable_inr'
    | 'amount_paid_inr'
    | 'next_payment_date'
    | 'payment_plan'
    | 'milestone_count'
    | 'milestone_fixed_amount_inr'
    | 'payment_milestones'
  >
): PaymentMilestone[] {
  const balance = paymentBalanceInr(form.total_payable_inr, form.amount_paid_inr);
  const startDate = (form.next_payment_date || '').trim();
  const plan = form.payment_plan;
  if (!plan || plan === 'full' || balance < 0.01 || !startDate) return [];

  let built: PaymentMilestone[] = [];
  if (plan === 'advance') {
    built = [
      {
        id: 'ms_1',
        due_date: startDate,
        paid_on: '',
        amount_inr: balance,
        payment_mode: '',
        payment_received: null,
      },
    ];
  } else if (plan === 'fixed_cost') {
    const fixed = resolveFixedPartAmount(balance, form.milestone_fixed_amount_inr);
    if (fixed < 0.01) return [];
    let remaining = balance;
    let index = 0;
    while (remaining >= 0.01 && index < MAX_PART_PAYMENTS) {
      const isLastSlot = index === MAX_PART_PAYMENTS - 1;
      const amount = isLastSlot ? remaining : roundMoney(Math.min(fixed, remaining));
      built.push({
        id: `ms_${index + 1}`,
        due_date: addCalendarMonths(startDate, index),
        paid_on: '',
        amount_inr: amount,
        payment_mode: '',
        payment_received: null,
      });
      remaining = roundMoney(remaining - amount);
      index += 1;
    }
  } else if (plan === 'fixed_emi') {
    const count = Math.min(MAX_PART_PAYMENTS, Math.max(2, Math.round(form.milestone_count || 2)));
    let base = roundMoneyToNearest5kOr10k(balance / count);
    if (base < 0.01 || base * (count - 1) >= balance - 0.009) {
      base = roundMoney(Math.floor((balance / count) * 100) / 100);
    }
    let allocated = 0;
    for (let index = 0; index < count; index += 1) {
      const amount =
        index === count - 1
          ? roundMoney(balance - allocated)
          : roundMoney(Math.min(base, balance - allocated));
      built.push({
        id: `ms_${index + 1}`,
        due_date: addCalendarMonths(startDate, index),
        paid_on: '',
        amount_inr: amount,
        payment_mode: '',
        payment_received: null,
      });
      allocated = roundMoney(allocated + amount);
    }
  }
  return keepMilestoneFlags(form.payment_milestones || [], absorbSmallFinalPayment(built));
}

export function withPaymentMilestones(
  form: StudentRegistrationFormState,
  patch: Partial<StudentRegistrationFormState>
): Partial<StudentRegistrationFormState> {
  const next = { ...form, ...patch };
  const plan = next.payment_plan;
  let amountPaid = next.amount_paid_inr;
  if (plan === 'full' && next.total_payable_inr != null) {
    amountPaid = next.total_payable_inr;
  }
  let nextPaymentDate = (next.next_payment_date || '').trim();
  if (plan && plan !== 'full') {
    nextPaymentDate =
      nextPaymentDate ||
      next.payment_milestones?.[0]?.due_date ||
      patch.next_payment_date ||
      form.next_payment_date ||
      '';
  } else {
    nextPaymentDate = '';
  }
  const balance = paymentBalanceInr(next.total_payable_inr, amountPaid);
  let fixedAmount = next.milestone_fixed_amount_inr;
  if (plan === 'fixed_cost' && balance >= 0.01) {
    fixedAmount = resolveFixedPartAmount(balance, fixedAmount);
  }
  const withAmount = {
    ...next,
    amount_paid_inr: amountPaid,
    next_payment_date: nextPaymentDate,
    milestone_fixed_amount_inr: fixedAmount,
  };
  const milestones = buildPaymentMilestones(withAmount);
  return {
    ...patch,
    amount_paid_inr: amountPaid,
    next_payment_date: milestones[0]?.due_date || nextPaymentDate,
    ...(plan === 'fixed_cost' ? { milestone_fixed_amount_inr: fixedAmount } : {}),
    payment_milestones: milestones,
  };
}

function legacyRemainingFields(plan: PaymentPlan | ''): {
  remaining_plan: RemainingPaymentPlan | null;
  milestone_split: MilestoneSplit | null;
} {
  if (plan === 'full') return { remaining_plan: null, milestone_split: null };
  if (plan === 'advance') return { remaining_plan: 'full', milestone_split: null };
  if (plan === 'fixed_cost') return { remaining_plan: 'parts', milestone_split: 'fixed' };
  if (plan === 'fixed_emi') return { remaining_plan: 'parts', milestone_split: 'equal' };
  return { remaining_plan: null, milestone_split: null };
}

export function registrationToSavePayload(form: StudentRegistrationFormState): {
  registration: StudentRegistrationData;
} {
  const managerId = Number.parseInt(form.assigned_account_manager_id, 10);
  const confirmed = form.agrees_to_register === true && form.payment_received === true;
  const hasPaymentDraft =
    form.agrees_to_register === true &&
    Boolean(form.payment_plan || form.payment_mode || form.amount_paid_inr != null);
  const balance = paymentBalanceInr(form.total_payable_inr, form.amount_paid_inr);
  const milestones =
    hasPaymentDraft && balance >= 0.01 && form.payment_plan && form.payment_plan !== 'full'
      ? buildPaymentMilestones({
          ...form,
          next_payment_date:
            form.next_payment_date.trim() || form.payment_milestones[0]?.due_date || '',
        })
      : hasPaymentDraft
        ? form.payment_milestones || []
        : [];
  const legacy = legacyRemainingFields(form.payment_plan);
  return {
    registration: {
      agrees_to_register: form.agrees_to_register,
      agreement_date: form.agreement_date.trim() || null,
      agreement_method: form.agreement_method || null,
      parent_consent: form.agrees_to_register === true ? form.parent_consent : null,
      assigned_account_manager_id: Number.isFinite(managerId) && managerId > 0 ? managerId : null,
      package_id: form.package_id.trim() || null,
      service_ids: form.package_id.trim() ? [] : form.service_ids,
      bill_now: form.bill_now,
      notes: form.notes.trim(),
      decline_outcome: form.agrees_to_register === false ? form.decline_outcome || null : null,
      invoice_id: form.agrees_to_register === true ? form.invoice_id.trim() || null : null,
      invoice_number: form.agrees_to_register === true ? form.invoice_number.trim() || null : null,
      invoice_status: form.agrees_to_register === true ? form.invoice_status.trim() || null : null,
      invoice_amount_inr: form.agrees_to_register === true ? form.invoice_amount_inr : null,
      invoice_date: form.agrees_to_register === true ? form.invoice_date.trim() || null : null,
      payment_received: confirmed,
      payment_confirmed_at: null,
      payment_mode: hasPaymentDraft ? form.payment_mode || null : null,
      total_payable_inr: hasPaymentDraft ? form.total_payable_inr : null,
      amount_paid_inr: hasPaymentDraft ? form.amount_paid_inr : null,
      payment_due_date: hasPaymentDraft ? (form.payment_due_date || '').trim() || null : null,
      payment_paid_on:
        hasPaymentDraft && form.payment_received === true
          ? (form.payment_paid_on || '').trim() || null
          : null,
      next_payment_date:
        hasPaymentDraft && balance >= 0.01
          ? milestones[0]?.due_date || form.next_payment_date.trim() || null
          : null,
      payment_plan: hasPaymentDraft ? form.payment_plan || null : null,
      remaining_plan: hasPaymentDraft ? legacy.remaining_plan : null,
      milestone_split: hasPaymentDraft ? legacy.milestone_split : null,
      milestone_count:
        hasPaymentDraft && form.payment_plan === 'fixed_emi' ? form.milestone_count : null,
      milestone_fixed_amount_inr:
        hasPaymentDraft && form.payment_plan === 'fixed_cost'
          ? resolveFixedPartAmount(balance, form.milestone_fixed_amount_inr)
          : null,
      payment_milestones: milestones,
    },
  };
}

/**
 * Billing Summary save: only the agreement panel controls.
 * Invoice payment drafts are preserved as drafts and are never newly confirmed here.
 * If registration was already payment-confirmed, that confirmed state is kept.
 */
export function registrationAgreementOnlySavePayload(
  form: StudentRegistrationFormState,
  preservedPayment?: Partial<StudentRegistrationFormState> | null,
  options?: { keepPaymentConfirmed?: boolean }
): { registration: StudentRegistrationData } {
  const keepConfirmed = options?.keepPaymentConfirmed === true;
  const paymentSource: StudentRegistrationFormState = {
    ...form,
    ...(preservedPayment || {}),
    // Agreement panel fields always win.
    agrees_to_register: form.agrees_to_register,
    agreement_date: form.agreement_date,
    agreement_method: form.agreement_method,
    parent_consent: form.parent_consent,
    assigned_account_manager_id: form.assigned_account_manager_id,
    package_id: form.package_id,
    service_ids: form.service_ids,
    notes: form.notes,
    decline_outcome: form.decline_outcome,
    // Do not confirm payment from this panel unless it was already complete.
    payment_received: keepConfirmed,
  };
  return registrationToSavePayload(paymentSource);
}

export function validateRegistrationForm(
  form: StudentRegistrationFormState,
  options: {
    under18: boolean;
    hasIssuedInvoice: boolean;
    todayIso?: string;
    requirePaymentDecision?: boolean;
  }
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (form.agrees_to_register == null) {
    errors.agrees_to_register = 'Select Yes or No.';
    return errors;
  }
  if (form.agrees_to_register) {
    if (!form.agreement_date.trim()) errors.agreement_date = 'Agreement date is required.';
    if (!form.agreement_method) errors.agreement_method = 'Select how they agreed.';
    if (!form.assigned_account_manager_id.trim()) {
      errors.assigned_account_manager_id = 'Account manager is required.';
    }
    if (options.under18 && !form.parent_consent) {
      errors.parent_consent = 'Parent or guardian consent is required for students under 18.';
    }
    if (form.payment_received === true) {
      if (!options.hasIssuedInvoice) {
        errors.payment_received = 'Issue an invoice before confirming payment.';
      }
      if (!form.invoice_id.trim() && !form.invoice_number.trim()) {
        errors.invoice_id = 'Select the issued invoice to confirm payment.';
      }
      if (!form.payment_plan) {
        errors.payment_plan = 'Select a payment plan.';
      }
      if (!form.payment_mode) {
        errors.payment_mode = 'Select the payment mode.';
      }
      if (!(form.payment_due_date || '').trim()) {
        errors.payment_due_date = 'Enter the due date for this payment.';
      }
      if (!(form.payment_paid_on || '').trim()) {
        errors.payment_paid_on = 'Enter the date payment was received.';
      }
      const total = form.total_payable_inr;
      const paid = form.amount_paid_inr;
      if (total == null || !Number.isFinite(total) || total <= 0) {
        errors.total_payable_inr = 'Total payable is required.';
      }
      if (paid == null || !Number.isFinite(paid) || paid <= 0) {
        errors.amount_paid_inr = 'Enter the amount paid.';
      } else if (total != null && paid > total + 0.009) {
        errors.amount_paid_inr = 'Amount paid cannot exceed total payable.';
      }
      if (form.payment_plan === 'full' && total != null && paid != null && paid + 0.009 < total) {
        errors.amount_paid_inr = 'Full payment must cover the total payable.';
      }
      if (form.payment_plan === 'advance' && total != null && paid != null && paid + 0.009 >= total) {
        errors.amount_paid_inr = 'Part payment must be less than the total payable.';
      }
      const balance = paymentBalanceInr(total, paid);
      if (balance >= 0.01 && form.payment_plan && form.payment_plan !== 'full') {
        if (
          form.payment_plan === 'fixed_emi' &&
          (form.milestone_count < 2 || form.milestone_count > 3)
        ) {
          errors.milestone_count = 'Use between 2 and 3 EMIs.';
        }
        if (
          form.payment_plan === 'fixed_cost' &&
          (form.milestone_fixed_amount_inr == null || form.milestone_fixed_amount_inr < 0.01)
        ) {
          errors.milestone_fixed_amount_inr = 'Enter a fixed instalment amount.';
        }
        const milestones =
          form.payment_milestones.length > 0
            ? form.payment_milestones
            : buildPaymentMilestones({
                ...form,
                next_payment_date:
                  form.next_payment_date.trim() || form.payment_milestones[0]?.due_date || '',
              });
        if (!milestones.length) {
          errors.payment_milestones = 'Define the remaining payment schedule.';
        } else if (milestones.length > MAX_PART_PAYMENTS) {
          errors.payment_milestones = `Use at most ${MAX_PART_PAYMENTS} part payments.`;
        } else if (milestones.some(row => !row.due_date)) {
          errors.payment_milestones = 'Each remaining payment needs a due date.';
        } else if (
          milestones.some(row => (row.paid_on || '').trim() && row.payment_received !== true)
        ) {
          errors.payment_milestones =
            'Select Payment Received Yes for each stage that has a Paid Date (No is not allowed).';
        } else if (
          milestones.some(
            row =>
              row.payment_received === true &&
              (!row.payment_mode || !String(row.due_date || '').trim() || !String(row.paid_on || '').trim())
          )
        ) {
          errors.payment_milestones =
            'For each upcoming payment marked Received = Yes, fill Payment Mode, Due Date, and Paid Date.';
        } else if (!paymentMilestonesAreChronological(milestones)) {
          errors.payment_milestones =
            'Due dates must be in chronological order (1st, then 2nd, then 3rd).';
        }
      }
    } else if (form.payment_received === false && (form.payment_paid_on || '').trim()) {
      errors.payment_received =
        'Payment Received cannot be No when a Paid Date is set. Select Yes or clear Paid Date.';
    } else if (
      options.requirePaymentDecision !== false &&
      form.payment_received == null &&
      form.payment_plan
    ) {
      errors.payment_received = (form.payment_paid_on || '').trim()
        ? 'Select Payment Received Yes (required when Paid Date is set).'
        : 'Select Payment Received Yes or No.';
    }

    // Upcoming stages: Paid Date may only be saved with Payment Received = Yes,
    // and Yes requires Payment Mode + Due Date + Paid Date.
    if (form.payment_plan && form.payment_milestones.length) {
      if (
        form.payment_milestones.some(
          row => (row.paid_on || '').trim() && row.payment_received !== true
        )
      ) {
        errors.payment_milestones =
          'Select Payment Received Yes for each stage that has a Paid Date (No is not allowed).';
      } else if (
        form.payment_milestones.some(
          row =>
            row.payment_received === true &&
            (!row.payment_mode ||
              !String(row.due_date || '').trim() ||
              !String(row.paid_on || '').trim())
        )
      ) {
        errors.payment_milestones =
          'For each upcoming payment marked Received = Yes, fill Payment Mode, Due Date, and Paid Date.';
      }
    }
  } else if (!form.decline_outcome) {
    errors.decline_outcome = 'Select Follow-up, Not interested, or Deferred.';
  }
  if (form.notes.length > 500) {
    errors.notes = 'Note must be 500 characters or fewer.';
  }
  return errors;
}
