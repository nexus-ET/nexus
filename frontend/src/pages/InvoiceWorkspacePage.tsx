import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  Plus,
  Receipt,
  Save,
  Search,
  Trash2,
  Download,
  X,
} from 'lucide-react';
import { apiFetch, apiUpload } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import PhoneWithCountryCodeInput from '../components/academia/form/PhoneWithCountryCodeInput';
import SearchableMultiSelect from '../components/academia/SearchableMultiSelect';
import {
  INDIAN_GST_STATES,
  gstStateName,
  stateCodeFromGstin,
} from '../constants/indianGstStates';
import {
  INVOICE_CANCELLATION_REASON_OPTIONS,
  INVOICE_CANCELLATION_REASON_OTHER,
  INVOICE_SAC_OPTIONS,
  PAYMENT_TERMS_PRESETS,
  createInvoiceLineId,
  displayInvoiceCancellationReason,
  resolveCancelledCloudStorageKey,
  resolveIssuedCloudStorageKey,
  resolveInvoiceCancellationReason,
  shiftIsoDate,
  type InvoiceDocument,
  type InvoiceLine,
} from '../schemas/invoiceWorkspaceSchema';
import { normalizeBankPaymentList } from '../schemas/billingSettingsSchema';
import { useAdminSettingsStore } from '../stores/adminSettingsStore';
import { useInvoiceWorkspaceStore } from '../stores/invoiceWorkspaceStore';
import { FALLBACK_COUNTRIES } from '../types/country';
import { formatMoneyInr } from '../utils/invoiceMoney';
import {
  computeInvoiceWorkspaceTotals,
  resolveSupplyType,
} from '../utils/invoiceTotals';
import { formatFullPhone } from '../utils/phoneCountry';
import { normalizeTaxRegimes } from '../utils/taxRegimes';
import { businessTodayIsoDate } from '../utils/timezone';
import {
  buildInvoiceFyOptions,
  currentIndianFy,
  indianFyStartYearFromIsoDate,
  invoiceInIndianFy,
  isPriorIndianFyInvoice,
  type IndianFy,
} from '../utils/indianFinancialYear';
import { buildUpiPayUri, upiQrImageUrl } from '../utils/upiPay';
// PDF (jspdf) is loaded on demand in handlePdf — do not static-import here.

const fieldClass =
  'w-full min-w-0 rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary';

/** Dense equal-width control grid used across invoice sections. */
const formGridClass =
  'grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6';

function isoDateDayDelta(fromIso: string, toIso: string): number {
  const [fy, fm, fd] = fromIso.split('-').map(Number);
  const [ty, tm, td] = toIso.split('-').map(Number);
  const from = Date.UTC(fy, (fm || 1) - 1, fd || 1);
  const to = Date.UTC(ty, (tm || 1) - 1, td || 1);
  return Math.round((to - from) / 86_400_000);
}

/** Move a draft’s invoice date up to Settings “today”; keep the same invoice→due gap. */
function withBusinessInvoiceDate(inv: InvoiceDocument, timezone: string): InvoiceDocument {
  if (inv.status !== 'draft') return inv;
  const today = businessTodayIsoDate(timezone);
  if (!inv.invoiceDate || inv.invoiceDate >= today) return inv;
  const gapDays = Math.max(0, isoDateDayDelta(inv.invoiceDate, inv.dueDate || inv.invoiceDate));
  return {
    ...inv,
    invoiceDate: today,
    dueDate: shiftIsoDate(today, gapDays || 7),
  };
}
const fieldWrapClass = 'min-w-0 space-y-1.5';
const labelClass = 'block text-sm font-medium text-text-main';

type StudentMasterHit = {
  id: number;
  lead_id?: number | null;
  full_name?: string | null;
  first_name?: string | null;
  middle_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone_country_iso2?: string | null;
  phone_local?: string | null;
  phone_number?: string | null;
  address_street?: string | null;
  city?: string | null;
  state?: string | null;
  country_iso2?: string | null;
  zipcode?: string | null;
  target_destination_iso2?: string | null;
  assigned_advisor_id?: number | null;
  assigned_advisor_name?: string | null;
};

type CounsellorOption = {
  id: number | string;
  name?: string | null;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
};

const DESTINATION_OPTIONS = FALLBACK_COUNTRIES.map(c => ({
  value: c.iso2,
  label: c.name,
}));

function invoicesForStudentMasterId(
  rows: InvoiceDocument[],
  studentMasterId: string,
  excludeId?: string
): InvoiceDocument[] {
  const id = studentMasterId.trim();
  if (!id) return [];
  return rows.filter(
    row => row.studentMasterId?.trim() === id && row.id !== excludeId
  );
}

type StudentDuplicateWarning = {
  hit: StudentMasterHit;
  studentName: string;
  existing: InvoiceDocument[];
};

function formatStudentMasterPhone(hit: StudentMasterHit): string {
  if (hit.phone_number?.trim()) return hit.phone_number.trim();
  if (hit.phone_country_iso2 && hit.phone_local) {
    return formatFullPhone(hit.phone_country_iso2, hit.phone_local);
  }
  return hit.phone_local?.trim() || '';
}

function SectionCard({
  title,
  subtitle,
  children,
  className = '',
  compact = false,
  fillHeight = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  compact?: boolean;
  /** Stretch to match sibling height (side-by-side panels). */
  fillHeight?: boolean;
}) {
  const padding = compact ? 'p-3 md:p-3.5' : 'p-4 md:p-5';
  const gap = compact ? 'gap-2.5' : 'gap-4';
  const stack = compact ? 'space-y-2.5' : 'space-y-4';

  return (
    <section
      className={`rounded-2xl border border-border-subtle bg-card ${padding} ${
        fillHeight ? `flex h-full flex-col ${gap}` : stack
      } ${className}`}
    >
      <div className={fillHeight ? 'shrink-0' : undefined}>
        <h3 className="text-sm font-semibold text-text-main">{title}</h3>
        {subtitle ? <p className="mt-0.5 text-xs text-text-muted">{subtitle}</p> : null}
      </div>
      {fillHeight ? (
        <div className={`flex min-h-0 flex-1 flex-col ${gap}`}>{children}</div>
      ) : (
        children
      )}
    </section>
  );
}

const InvoiceWorkspacePage: React.FC = () => {
  const openConfirm = useConfirmation();
  const { timezone, loading: timezoneLoading, formatDateTime } = useBusinessTimezone();
  const invoices = useInvoiceWorkspaceStore(s => s.invoices);
  const activeInvoiceId = useInvoiceWorkspaceStore(s => s.activeInvoiceId);
  const createDraft = useInvoiceWorkspaceStore(s => s.createDraft);
  const setActiveInvoiceId = useInvoiceWorkspaceStore(s => s.setActiveInvoiceId);
  const upsertInvoice = useInvoiceWorkspaceStore(s => s.upsertInvoice);
  const issueInvoice = useInvoiceWorkspaceStore(s => s.issueInvoice);
  const voidInvoice = useInvoiceWorkspaceStore(s => s.voidInvoice);
  const deleteDraft = useInvoiceWorkspaceStore(s => s.deleteDraft);

  // Select stable store slices only — never return fresh objects/arrays from selectors
  // (Zustand Object.is compare → infinite re-render loop).
  const gstNumber = useAdminSettingsStore(s => s.gstNumber);
  const gstPercentageRaw = useAdminSettingsStore(s => s.gstPercentage);
  const taxRegimesRaw = useAdminSettingsStore(s => s.taxRegimes);
  const feeCatalogRaw = useAdminSettingsStore(s => s.feeCatalog);
  const discountReasonsRaw = useAdminSettingsStore(s => s.discountReasons);
  const discountPercentageRaw = useAdminSettingsStore(s => s.discountPercentage);
  const discountFixedAmountRaw = useAdminSettingsStore(s => s.discountFixedAmount);
  const maxAutoApproveRaw = useAdminSettingsStore(s => s.maxAutoApproveDiscountPercent);
  const maxDiscountFixedRaw = useAdminSettingsStore(s => s.maxDiscountFixedAmount);
  const bankPaymentsRaw = useAdminSettingsStore(s => s.bankPayments);
  const previewNextInvoiceId = useAdminSettingsStore(s => s.previewNextInvoiceId);

  const gstPercentage = useMemo(() => {
    if (!Number.isFinite(gstPercentageRaw)) return 18;
    return Math.min(100, Math.max(0, gstPercentageRaw));
  }, [gstPercentageRaw]);
  const taxRegimes = useMemo(() => normalizeTaxRegimes(taxRegimesRaw), [taxRegimesRaw]);
  const feeCatalog = feeCatalogRaw;
  const discountReasons = useMemo(
    () => (Array.isArray(discountReasonsRaw) ? discountReasonsRaw : []),
    [discountReasonsRaw]
  );
  const maxAutoApprove = useMemo(() => {
    if (!Number.isFinite(maxAutoApproveRaw)) return 20;
    return Math.min(100, Math.max(0, maxAutoApproveRaw));
  }, [maxAutoApproveRaw]);
  const maxDiscountFixed = useMemo(() => {
    if (!Number.isFinite(maxDiscountFixedRaw)) return 10_000;
    return Math.min(1_000_000, Math.max(0, maxDiscountFixedRaw));
  }, [maxDiscountFixedRaw]);
  const policyDiscountDefaultPercent = useMemo(() => {
    if (!Number.isFinite(discountPercentageRaw)) return 0;
    return Math.min(100, Math.max(0, discountPercentageRaw));
  }, [discountPercentageRaw]);
  const policyDiscountDefaultFixed = useMemo(() => {
    if (!Number.isFinite(discountFixedAmountRaw)) return 0;
    return Math.min(1_000_000, Math.max(0, discountFixedAmountRaw));
  }, [discountFixedAmountRaw]);
  const bankPayments = useMemo(
    () => normalizeBankPaymentList(bankPaymentsRaw),
    [bankPaymentsRaw]
  );

  const [draft, setDraft] = useState<InvoiceDocument | null>(null);
  const [storeReady, setStoreReady] = useState(
    () => useInvoiceWorkspaceStore.persist.hasHydrated()
  );
  const [studentQuery, setStudentQuery] = useState('');
  const [studentHits, setStudentHits] = useState<StudentMasterHit[]>([]);
  const [studentSearching, setStudentSearching] = useState(false);
  const [counsellors, setCounsellors] = useState<CounsellorOption[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cloudLinkBusy, setCloudLinkBusy] = useState<'issued' | 'cancelled' | null>(
    null
  );
  const [listFilter, setListFilter] = useState<
    'all' | 'draft' | 'issued' | 'void'
  >('all');
  const [listSearch, setListSearch] = useState('');
  const [selectedFyStartYear, setSelectedFyStartYear] = useState<number | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<StudentDuplicateWarning | null>(
    null
  );
  const duplicateWarningRef = useRef<HTMLDivElement>(null);

  const active = useMemo(
    () => invoices.find(row => row.id === activeInvoiceId) || null,
    [invoices, activeInvoiceId]
  );

  // Wait for localStorage rehydration before creating/selecting drafts.
  // Otherwise we mount on empty store → spinner → createDraft race → overwrite.
  useEffect(() => {
    if (useInvoiceWorkspaceStore.persist.hasHydrated()) {
      setStoreReady(true);
      return;
    }
    return useInvoiceWorkspaceStore.persist.onFinishHydration(() => {
      setStoreReady(true);
    });
  }, []);

  useEffect(() => {
    if (!storeReady || timezoneLoading) return;
    if (selectedFyStartYear == null) {
      setSelectedFyStartYear(currentIndianFy(businessTodayIsoDate(timezone)).startYear);
    }
  }, [storeReady, timezoneLoading, timezone, selectedFyStartYear]);

  useEffect(() => {
    setDuplicateWarning(null);
  }, [activeInvoiceId]);

  useEffect(() => {
    if (!duplicateWarning) return;
    duplicateWarningRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [duplicateWarning]);

  useEffect(() => {
    if (!storeReady || selectedFyStartYear == null) return;
    const inFy = invoices.filter(row =>
      invoiceInIndianFy(row.invoiceDate, selectedFyStartYear)
    );
    if (!inFy.length) return;
    const activeStillVisible = inFy.some(row => row.id === activeInvoiceId);
    if (!activeStillVisible) {
      setActiveInvoiceId(inFy[0].id);
    }
  }, [storeReady, selectedFyStartYear, invoices, activeInvoiceId, setActiveInvoiceId]);

  useEffect(() => {
    if (!storeReady || timezoneLoading) return;
    const state = useInvoiceWorkspaceStore.getState();

    let activeInvoice =
      state.invoices.find(row => row.id === state.activeInvoiceId) || null;

    if (!activeInvoice && state.invoices[0]) {
      state.setActiveInvoiceId(state.invoices[0].id);
      activeInvoice = state.invoices[0];
    }

    if (!activeInvoice) {
      const created = state.createDraft(timezone);
      setDraft({
        ...created,
        lines: created.lines.map(line => ({ ...line })),
      });
      return;
    }

    // Drafts may still carry yesterday’s browser/UTC date from before Settings TZ was applied.
    if (activeInvoice && !timezoneLoading) {
      const refreshed = withBusinessInvoiceDate(activeInvoice, timezone);
      if (refreshed.invoiceDate !== activeInvoice.invoiceDate) {
        state.upsertInvoice(refreshed);
        activeInvoice = refreshed;
      }
    }

    if (activeInvoice) {
      setDraft({
        ...activeInvoice,
        lines: activeInvoice.lines.map(line => ({ ...line })),
      });
    }
  }, [storeReady, timezoneLoading, timezone]);

  useEffect(() => {
    if (!storeReady) return;
    if (!active) {
      // Active cleared (e.g. last invoice deleted) — keep local draft until
      // handleDeleteInvoice / createDraft installs a replacement.
      return;
    }
    setDraft({ ...active, lines: active.lines.map(l => ({ ...l })) });
    // Sync local editor when the selected invoice identity or saved revision changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally keyed by id/updatedAt
  }, [storeReady, active?.id, active?.updatedAt]);

  useEffect(() => {
    if (!storeReady) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const data = (await apiFetch('bookings/counsellors')) as {
          counsellors?: CounsellorOption[];
        };
        if (!cancelled) setCounsellors(data.counsellors || []);
      } catch {
        if (!cancelled) setCounsellors([]);
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [storeReady]);

  useEffect(() => {
    const query = studentQuery.trim();
    if (query.length < 2) {
      setStudentHits([]);
      setStudentSearching(false);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setStudentSearching(true);
      try {
        const params = new URLSearchParams();
        params.set('q', query);
        params.set('limit', '12');
        const data = (await apiFetch(
          `students-master/search?${params.toString()}`
        )) as { items?: StudentMasterHit[] };
        if (cancelled) return;
        setStudentHits(Array.isArray(data.items) ? data.items.slice(0, 12) : []);
      } catch (err) {
        if (cancelled) return;
        setStudentHits([]);
        setError(
          err instanceof Error
            ? `Student search failed: ${err.message}`
            : 'Student search failed.'
        );
      } finally {
        if (!cancelled) setStudentSearching(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [studentQuery]);

  const todayIso = useMemo(
    () => businessTodayIsoDate(timezoneLoading ? 'UTC' : timezone),
    [timezone, timezoneLoading]
  );
  const currentFy = useMemo(() => currentIndianFy(todayIso), [todayIso]);
  const fyOptions = useMemo(
    () =>
      buildInvoiceFyOptions(
        todayIso,
        invoices.map(row => row.invoiceDate),
        3
      ),
    [todayIso, invoices]
  );
  const activeFyStartYear = selectedFyStartYear ?? currentFy.startYear;
  const activeFy: IndianFy = useMemo(
    () => fyOptions.find(fy => fy.startYear === activeFyStartYear) || currentFy,
    [fyOptions, activeFyStartYear, currentFy]
  );
  const isHistoricalFy = activeFy.startYear !== currentFy.startYear;

  const readOnly =
    !draft ||
    draft.status !== 'draft' ||
    isPriorIndianFyInvoice(draft.invoiceDate, currentFy.startYear);

  const patch = <K extends keyof InvoiceDocument>(key: K, value: InvoiceDocument[K]) => {
    setDraft(prev => (prev ? { ...prev, [key]: value } : prev));
  };

  const supplyType = useMemo(() => {
    if (!draft) return 'inter' as const;
    return resolveSupplyType({
      placeOfSupplyStateCode: draft.placeOfSupplyStateCode,
      organizationGstin: gstNumber,
      forceExempt: draft.forceExempt,
    });
  }, [draft, gstNumber]);

  const totals = useMemo(() => {
    if (!draft) {
      return null;
    }
    return computeInvoiceWorkspaceTotals({
      lines: draft.lines,
      discountType: draft.discountType,
      discountValue: draft.discountValue,
      gstPercentage,
      regimes: taxRegimes,
      supplyType,
      maxAutoApproveDiscountPercent: maxAutoApprove,
    });
  }, [draft, gstPercentage, taxRegimes, supplyType, maxAutoApprove]);

  const discountValueBounds = useMemo(() => {
    if (draft?.discountType === 'fixed') {
      return { min: 0, max: maxDiscountFixed };
    }
    return { min: 0, max: maxAutoApprove };
  }, [draft?.discountType, maxAutoApprove, maxDiscountFixed]);

  useEffect(() => {
    if (!draft || readOnly) return;
    const { min, max } = discountValueBounds;
    const capped = Math.min(max, Math.max(min, draft.discountValue));
    if (capped !== draft.discountValue) {
      setDraft(prev => (prev ? { ...prev, discountValue: capped } : prev));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- clamp only when bounds or value change
  }, [discountValueBounds, draft?.discountValue, draft?.id, readOnly]);

  const selectedBank = draft
    ? bankPayments[
        Math.min(
          Math.max(0, draft.selectedBankIndex),
          Math.max(0, bankPayments.length - 1)
        )
      ] || bankPayments[0]
    : null;

  // Prefill UPI from Bank Details when the draft VPA is empty.
  useEffect(() => {
    if (!draft || readOnly) return;
    const bankVpa = selectedBank?.upiVpa?.trim() || '';
    if (!bankVpa || draft.upiVpa.trim()) return;
    setDraft(prev => (prev ? { ...prev, upiVpa: bankVpa } : prev));
    // Intentionally omit draft.upiVpa so clearing the field does not immediately re-fill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.id, draft?.selectedBankIndex, selectedBank?.upiVpa, readOnly]);

  const effectiveUpiVpa = (draft?.upiVpa || selectedBank?.upiVpa || '').trim();

  const upiUri = useMemo(() => {
    if (!draft || !totals || !effectiveUpiVpa) return null;
    return buildUpiPayUri({
      vpa: effectiveUpiVpa,
      payeeName: selectedBank?.beneficiaryName || 'Nexus',
      amountInr: totals.finalPayableAmount,
      note: draft.invoiceNumber || draft.studentFullName || 'Invoice',
      transactionRef: draft.invoiceNumber || draft.id.slice(0, 20),
    });
  }, [draft, totals, selectedBank, effectiveUpiVpa]);

  const filteredList = useMemo(() => {
    const byFy = invoices.filter(row =>
      invoiceInIndianFy(row.invoiceDate, activeFy.startYear)
    );
    const byStatus =
      listFilter === 'all' ? byFy : byFy.filter(row => row.status === listFilter);
    const q = listSearch.trim().toLowerCase();
    if (!q) return byStatus;
    return byStatus.filter(row => {
      const haystack = [
        row.studentFullName,
        row.invoiceNumber || '',
        row.email,
        row.phone,
        row.studentMasterId,
        row.leadId != null ? String(row.leadId) : '',
        row.counselorName,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [invoices, listFilter, listSearch, activeFy.startYear]);

  const statusLabel = (
    invoice: Pick<InvoiceDocument, 'status' | 'invoiceDate' | 'voidedAt'>
  ): string => {
    // Prior FYs are “Archived records” by year — status stays issued/cancelled.
    if (isPriorIndianFyInvoice(invoice.invoiceDate, currentFy.startYear)) {
      if (invoice.status === 'draft') return 'Draft (prior FY)';
      if (invoice.status === 'void') return 'Archived record (cancelled)';
      return 'Archived record';
    }
    if (invoice.status === 'void') return 'Cancelled';
    if (invoice.status === 'draft') return 'Draft';
    if (invoice.status === 'issued') return 'Issued';
    if (invoice.status === 'archived') return 'Archived record';
    return invoice.status;
  };

  const activeServices = useMemo(
    () => feeCatalog.services.filter(s => s.active).sort((a, b) => a.sortOrder - b.sortOrder),
    [feeCatalog.services]
  );
  const activePackages = useMemo(
    () => feeCatalog.bundles.filter(b => b.active).sort((a, b) => a.sortOrder - b.sortOrder),
    [feeCatalog.bundles]
  );

  const applyStudentMaster = (hit: StudentMasterHit, continueAnyway = false) => {
    if (!draft) return;
    const name =
      (hit.full_name || '').trim() ||
      [hit.first_name, hit.middle_name, hit.last_name].filter(Boolean).join(' ').trim();
    const existing = invoicesForStudentMasterId(invoices, String(hit.id), draft.id);
    if (existing.length && !continueAnyway) {
      setDuplicateWarning({ hit, studentName: name || `Student #${hit.id}`, existing });
      setStudentHits([]);
      return;
    }
    setDuplicateWarning(null);
    setDraft({
      ...draft,
      studentFullName: name,
      studentMasterId: String(hit.id),
      leadId: hit.lead_id ?? null,
      email: hit.email || '',
      phone: formatStudentMasterPhone(hit),
      addressStreet: hit.address_street || '',
      addressCity: hit.city || '',
      addressState: hit.state || '',
      addressCountry: (hit.country_iso2 || '').trim().toUpperCase(),
      addressPincode: hit.zipcode || '',
      destinationCountries: hit.target_destination_iso2
        ? [hit.target_destination_iso2.toUpperCase()]
        : draft.destinationCountries,
      // Keep place of supply on the org GSTIN state — do not overwrite from student
      // address (that forced IGST whenever the student lived in another state).
      counselorId: hit.assigned_advisor_id ? String(hit.assigned_advisor_id) : draft.counselorId,
      counselorName: hit.assigned_advisor_name || draft.counselorName,
    });
    setStudentQuery(name || `Student #${hit.id}`);
    setStudentHits([]);
  };

  const clearSelectedStudent = () => {
    if (!draft || readOnly) return;
    setDuplicateWarning(null);
    setStudentQuery('');
    setStudentHits([]);
    if (!draft.studentMasterId?.trim()) return;
    const orgState = stateCodeFromGstin(gstNumber) || draft.placeOfSupplyStateCode || '27';
    setDraft({
      ...draft,
      studentFullName: '',
      studentMasterId: '',
      leadId: null,
      email: '',
      phone: '',
      addressStreet: '',
      addressCity: '',
      addressState: '',
      addressCountry: '',
      addressPincode: '',
      destinationCountries: [],
      placeOfSupplyStateCode: orgState,
      counselorId: '',
      counselorName: '',
    });
  };

  const clientLocked = Boolean(draft?.studentMasterId?.trim()) || readOnly;
  const searchLocked = readOnly;

  const applyPackage = (packageId: string) => {
    const bundle = activePackages.find(b => b.id === packageId);
    if (!bundle || !draft) return;
    const lines: InvoiceLine[] = bundle.serviceIds
      .map(serviceId => activeServices.find(s => s.id === serviceId))
      .filter(Boolean)
      .map(service => ({
        id: createInvoiceLineId(),
        serviceId: service!.id,
        name: service!.name,
        quantity: 1,
        unitPriceInr: service!.basePriceInr,
      }));
    setDraft({
      ...draft,
      billingMode: 'package',
      packageId: bundle.id,
      packageName: bundle.name,
      packageInvoiceDescription: (bundle.invoiceDescription || '').trim().slice(0, 75),
      lines,
    });
  };

  const syncAlacarteServices = (serviceIds: string[]) => {
    if (!draft) return;
    const existingByServiceId = new Map(
      draft.lines
        .filter(line => Boolean(line.serviceId))
        .map(line => [line.serviceId as string, line])
    );
    const lines: InvoiceLine[] = serviceIds
      .map(serviceId => {
        const existing = existingByServiceId.get(serviceId);
        if (existing) return existing;
        const service = activeServices.find(row => row.id === serviceId);
        if (!service) return null;
        return {
          id: createInvoiceLineId(),
          serviceId: service.id,
          name: service.name,
          quantity: 1,
          unitPriceInr: service.basePriceInr,
        };
      })
      .filter(Boolean) as InvoiceLine[];
    setDraft({
      ...draft,
      billingMode: 'alacarte',
      packageId: '',
      packageName: '',
      packageInvoiceDescription: '',
      lines,
    });
  };

  const updateLine = (lineId: string, patchLine: Partial<InvoiceLine>) => {
    if (!draft) return;
    setDraft({
      ...draft,
      lines: draft.lines.map(line => (line.id === lineId ? { ...line, ...patchLine } : line)),
    });
  };

  const removeLine = (lineId: string) => {
    if (!draft) return;
    setDraft({ ...draft, lines: draft.lines.filter(line => line.id !== lineId) });
  };

  const MAX_PRINTABLE_SERVICE_LINES = 20;

  const focusInvoiceField = (id: string) => {
    window.requestAnimationFrame(() => {
      document.getElementById(id)?.focus();
    });
  };

  const hasValidStudentFromSearch = (): boolean =>
    Boolean(draft?.studentMasterId?.trim());

  const hasServiceSelection = (): boolean => {
    if (!draft) return false;
    if (draft.billingMode === 'package') {
      return Boolean(draft.packageId?.trim()) && draft.lines.length > 0;
    }
    return draft.lines.length > 0;
  };

  const ensureValidStudentSelected = (action: 'save this draft' | 'issue this invoice'): boolean => {
    if (hasValidStudentFromSearch()) return true;
    setMessage(null);
    setError(
      `Select a valid student from Find student (Students Master) before you ${action}. Typed names or blank records are not enough — pick a student from the search results so a Student / CRM ID is attached.`
    );
    focusInvoiceField('invoice-student-search');
    return false;
  };

  const ensureCounselorSelected = (): boolean => {
    if (!draft?.counselorId?.trim()) {
      setMessage(null);
      setError('Please select an Assigned counselor / account manager.');
      focusInvoiceField('invoice-counselorId');
      return false;
    }
    return true;
  };

  const ensureIssueServiceSelection = (): boolean => {
    if (hasServiceSelection()) return true;
    setMessage(null);
    if (draft?.billingMode === 'package') {
      setError(
        'Select a package from the Package dropdown before issuing this invoice. Issuing with no package or services creates a blank invoice.'
      );
      focusInvoiceField('invoice-packageId');
    } else {
      setError(
        'Select at least one à la carte service before issuing this invoice. Issuing with no services creates a blank invoice.'
      );
      focusInvoiceField('invoice-alacarte-services');
    }
    return false;
  };

  const confirmServiceLineLimit = async (): Promise<boolean> => {
    if (!draft || draft.lines.length <= MAX_PRINTABLE_SERVICE_LINES) return true;
    return openConfirm({
      title: 'Service limit for printing',
      message:
        'The page can only print a maximum of twenty services and anything more will cause page breaks.',
      confirmLabel: 'Continue anyway',
      variant: 'danger',
    });
  };

  const handleSaveDraft = async () => {
    if (!draft) return;
    setError(null);
    setMessage(null);
    if (!ensureValidStudentSelected('save this draft')) return;
    if (!(await confirmServiceLineLimit())) return;
    upsertInvoice({
      ...draft,
      status: 'draft',
      draftSavedAt: new Date().toISOString(),
    });
    setMessage('Draft saved.');
  };

  const handleIssue = async () => {
    if (!draft || !totals) return;
    setError(null);
    setMessage(null);
    if (!ensureValidStudentSelected('issue this invoice')) return;
    if (!ensureIssueServiceSelection()) return;
    if (!ensureCounselorSelected()) return;
    if (totals.requiresAuthorization && !draft.approvedByStaffId.trim()) {
      setError('This discount exceeds auto-approve threshold — select Approved by.');
      return;
    }
    if (totals.tax.unavailable) {
      setError('Selected tax regime is not available for this place of supply. Check GST & Tax settings.');
      return;
    }
    if (!(await confirmServiceLineLimit())) return;
    if (!draft.email.trim()) {
      setError('Student email is required to issue and send the invoice.');
      return;
    }
    upsertInvoice(draft);
    const result = issueInvoice(draft.id, {
      orgGstin: gstNumber,
      gstPercentage,
      finalPayable: totals.finalPayableAmount,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }

    const issued = result.invoice;
    setBusy(true);
    try {
      const { exportInvoicePdf } = await import('../utils/exportInvoicePdf');
      let managerList = counsellors;
      try {
        const data = (await apiFetch('bookings/counsellors')) as {
          counsellors?: CounsellorOption[];
        };
        if (Array.isArray(data.counsellors) && data.counsellors.length) {
          managerList = data.counsellors;
          setCounsellors(data.counsellors);
        }
      } catch {
        // Use already-loaded counsellors
      }
      const manager = managerList.find(c => String(c.id) === String(issued.counselorId));
      const managerName = (
        issued.counselorName ||
        manager?.full_name ||
        manager?.name ||
        ''
      ).trim();
      const managerEmail = (manager?.email || '').trim();
      const { blob, filename } = await exportInvoicePdf({
        invoice: issued,
        totals,
        bank: selectedBank,
        orgGstin: issued.orgGstinSnapshot || gstNumber,
        gstPercentage: issued.gstPercentageSnapshot || gstPercentage,
        accountManager: {
          name: managerName,
          email: managerEmail,
        },
        download: false,
      });

      const formData = new FormData();
      formData.append('file', blob, filename);
      formData.append('invoice_date', issued.invoiceDate);
      formData.append('student_email', issued.email.trim());
      formData.append('student_name', issued.studentFullName.trim());
      formData.append(
        'package_name',
        (issued.packageName || '').trim() || 'selected services'
      );
      formData.append(
        'account_manager_name',
        managerName || 'your account manager'
      );
      formData.append('send_email', 'true');
      const upload = (await apiUpload('invoices/upload-pdf', formData)) as {
        storage_key?: string;
        financial_year?: string;
        folder_created?: boolean;
        download_url?: string;
        email_status?: string;
      };
      const storageKey = (upload.storage_key || '').trim();
      const downloadUrl = (upload.download_url || '').trim();
      if (storageKey) {
        upsertInvoice({
          ...issued,
          cloudStorageKey: storageKey,
          cloudDownloadUrl: downloadUrl,
          issuedCloudStorageKey: storageKey,
          issuedCloudDownloadUrl: downloadUrl,
        });
      }
      if (storageKey && !storageKey.startsWith('ADMIN/ACCOUNTS/INVOICES/')) {
        setError(
          `Issued as ${issued.invoiceNumber}, but cloud path looks wrong: ${storageKey}`
        );
      }
      const fy = upload.financial_year || 'FY folder';
      const folderNote = upload.folder_created ? ` (created ${fy})` : ` under ${fy}`;
      const emailStatus = (upload.email_status || 'skipped').toLowerCase();
      const emailNote =
        emailStatus === 'sent'
          ? ` Email sent to ${issued.email.trim()}.`
          : emailStatus === 'failed'
            ? ' Email could not be sent (check SMTP settings).'
            : ' Email skipped (no valid student email).';
      setMessage(
        `Issued as ${issued.invoiceNumber}. PDF uploaded to ${storageKey || `cloud${folderNote}`}.${emailNote}`
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? `Issued as ${issued.invoiceNumber}, but cloud upload failed: ${err.message}`
          : `Issued as ${issued.invoiceNumber}, but cloud upload failed.`
      );
      setMessage(`Issued as ${issued.invoiceNumber}.`);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteInvoice = async () => {
    if (!draft || draft.status !== 'draft') return;
    const label = draft.invoiceNumber || draft.studentFullName?.trim() || 'this draft';
    const confirmed = await openConfirm({
      title: 'Delete draft?',
      message: `Delete invoice draft for "${label}"? This cannot be undone.`,
      confirmLabel: 'Delete draft',
      variant: 'danger',
    });
    if (!confirmed) return;

    const deletedId = draft.id;
    deleteDraft(deletedId);

    const state = useInvoiceWorkspaceStore.getState();
    let next =
      state.invoices.find(row => row.id === state.activeInvoiceId) ||
      state.invoices[0] ||
      null;
    if (!next) {
      next = state.createDraft(timezone);
    } else if (state.activeInvoiceId !== next.id) {
      state.setActiveInvoiceId(next.id);
    }

    setDraft({
      ...next,
      lines: next.lines.map(line => ({ ...line })),
    });
    setStudentQuery('');
    setStudentHits([]);
    setError(null);
    setMessage('Draft deleted.');
  };

  const handleVoid = async () => {
    if (!draft || draft.status !== 'issued' || !totals) return;
    const resolved = resolveInvoiceCancellationReason(
      draft.cancellationReasonCode,
      draft.cancellationReasonDetail
    );
    if (!resolved.ok) {
      setError(resolved.error);
      setMessage(null);
      window.requestAnimationFrame(() => {
        document
          .getElementById(
            resolved.focus === 'detail'
              ? 'invoice-cancellationReasonDetail'
              : 'invoice-cancellationReasonCode'
          )
          ?.focus();
      });
      return;
    }
    const label = draft.invoiceNumber || draft.studentFullName?.trim() || 'this invoice';
    const confirmed = await openConfirm({
      title: 'Cancel invoice?',
      message: `Cancel "${label}"? Reason: ${resolved.reason}. The invoice number is kept, but the document is marked cancelled and cannot be edited. A cancelled PDF will be stored in cloud. This cannot be undone.`,
      confirmLabel: 'Cancel invoice',
      variant: 'danger',
    });
    if (!confirmed) return;
    const result = voidInvoice(draft.id, {
      code: draft.cancellationReasonCode,
      detail: draft.cancellationReasonDetail,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }

    const voided = result.invoice;
    setBusy(true);
    setError(null);
    try {
      const { exportInvoicePdf } = await import('../utils/exportInvoicePdf');
      let managerList = counsellors;
      try {
        const data = (await apiFetch('bookings/counsellors', {
          authRedirect: false,
        })) as {
          counsellors?: CounsellorOption[];
        };
        if (Array.isArray(data.counsellors) && data.counsellors.length) {
          managerList = data.counsellors;
          setCounsellors(data.counsellors);
        }
      } catch {
        // Use already-loaded counsellors
      }
      const manager = managerList.find(c => String(c.id) === String(voided.counselorId));
      const managerName = (
        voided.counselorName ||
        manager?.full_name ||
        manager?.name ||
        ''
      ).trim();
      const managerEmail = (manager?.email || '').trim();
      const { blob, filename } = await exportInvoicePdf({
        invoice: voided,
        totals,
        bank: selectedBank,
        orgGstin: voided.orgGstinSnapshot || gstNumber,
        gstPercentage: voided.gstPercentageSnapshot || gstPercentage,
        accountManager: {
          name: managerName,
          email: managerEmail,
        },
        download: false,
      });

      const formData = new FormData();
      formData.append('file', blob, filename);
      formData.append('invoice_date', voided.invoiceDate);
      formData.append('send_email', 'false');
      const upload = (await apiUpload('invoices/upload-pdf', formData)) as {
        storage_key?: string;
        financial_year?: string;
        folder_created?: boolean;
        download_url?: string;
      };
      const storageKey = (upload.storage_key || '').trim();
      const downloadUrl = (upload.download_url || '').trim();
      if (storageKey) {
        upsertInvoice({
          ...voided,
          cloudStorageKey: storageKey,
          cloudDownloadUrl: downloadUrl,
          cancelledCloudStorageKey: storageKey,
          cancelledCloudDownloadUrl: downloadUrl,
        });
      }
      if (storageKey && !storageKey.startsWith('ADMIN/ACCOUNTS/INVOICES/')) {
        setError(
          `Invoice cancelled, but cloud path looks wrong: ${storageKey}`
        );
      }
      const fy = upload.financial_year || 'FY folder';
      const folderNote = upload.folder_created ? ` (created ${fy})` : ` under ${fy}`;
      setMessage(
        `Invoice cancelled. PDF uploaded to ${storageKey || `cloud${folderNote}`}.`
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? `Invoice cancelled, but cloud upload failed: ${err.message}`
          : 'Invoice cancelled, but cloud upload failed.'
      );
      setMessage('Invoice cancelled.');
    } finally {
      setBusy(false);
    }
  };

  const openCloudInvoice = async (kind: 'issued' | 'cancelled') => {
    if (!draft) return;
    const storageKey =
      kind === 'cancelled'
        ? resolveCancelledCloudStorageKey(draft)
        : resolveIssuedCloudStorageKey(draft);
    const legacyUrlMatches =
      (draft.cloudStorageKey || '').trim() === storageKey
        ? (draft.cloudDownloadUrl || '').trim()
        : '';
    const fallbackUrl = (
      kind === 'cancelled'
        ? draft.cancelledCloudDownloadUrl || legacyUrlMatches
        : draft.issuedCloudDownloadUrl || legacyUrlMatches
    ).trim();
    if (!storageKey && !fallbackUrl) return;
    setCloudLinkBusy(kind);
    setError(null);
    try {
      let url = fallbackUrl;
      if (storageKey) {
        const data = (await apiFetch('invoices/download-link', {
          method: 'POST',
          body: JSON.stringify({ storage_key: storageKey }),
        })) as { download_url?: string };
        url = (data.download_url || fallbackUrl).trim();
      }
      if (!url) {
        throw new Error('Cloud download link was empty.');
      }
      const patchKeys =
        kind === 'cancelled'
          ? { cancelledCloudDownloadUrl: url, cloudDownloadUrl: url }
          : { issuedCloudDownloadUrl: url };
      upsertInvoice({ ...draft, ...patchKeys });
      setDraft(prev => (prev ? { ...prev, ...patchKeys } : prev));
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      if (fallbackUrl) {
        window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
        return;
      }
      setError(
        err instanceof Error
          ? `Could not open ${kind} invoice: ${err.message}`
          : `Could not open ${kind} invoice.`
      );
    } finally {
      setCloudLinkBusy(null);
    }
  };

  const handlePdf = async () => {
    if (!draft || !totals) return;
    setError(null);
    setMessage(null);
    if (!ensureCounselorSelected()) return;
    if (!(await confirmServiceLineLimit())) return;
    setBusy(true);
    try {
      const { exportInvoicePdf } = await import('../utils/exportInvoicePdf');
      let managerList = counsellors;
      try {
        const data = (await apiFetch('bookings/counsellors')) as {
          counsellors?: CounsellorOption[];
        };
        if (Array.isArray(data.counsellors) && data.counsellors.length) {
          managerList = data.counsellors;
          setCounsellors(data.counsellors);
        }
      } catch {
        // Use already-loaded counsellors
      }
      const manager = managerList.find(c => String(c.id) === String(draft.counselorId));
      const managerName = (
        draft.counselorName ||
        manager?.full_name ||
        manager?.name ||
        ''
      ).trim();
      const managerEmail = (manager?.email || '').trim();
      await exportInvoicePdf({
        invoice: draft,
        totals,
        bank: selectedBank,
        orgGstin: draft.orgGstinSnapshot || gstNumber,
        gstPercentage: draft.gstPercentageSnapshot || gstPercentage,
        accountManager: {
          name: managerName,
          email: managerEmail,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF export failed.');
    } finally {
      setBusy(false);
    }
  };

  const orgStateCode = stateCodeFromGstin(gstNumber);

  if (!storeReady || timezoneLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-text-muted">
        <Loader2 className="mr-2 animate-spin" size={20} />
        Loading invoice workspace…
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="w-full max-w-none space-y-4 p-6 md:p-8 pb-16">
        <div className="flex flex-col gap-3 rounded-2xl border border-border-subtle bg-card p-4 md:flex-row md:items-start md:justify-between md:p-5">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold text-text-main">
              <Receipt size={20} />
              Invoice Workspace
            </h1>
            <p className="mt-1 text-sm text-text-muted">
              No invoices yet. The next issued invoice will be{' '}
              <span className="font-mono text-text-main">{previewNextInvoiceId()}</span>.
            </p>
          </div>
          <button
            type="button"
            onClick={() => createDraft(timezone)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-sm font-medium text-text-main hover:bg-surface-bg"
          >
            <Plus size={16} />
            New draft
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-none space-y-4 p-6 md:p-8 pb-16">
      <div className="flex flex-col gap-3 rounded-2xl border border-border-subtle bg-card p-4 md:flex-row md:items-start md:justify-between md:p-5">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-text-main">
            <Receipt size={20} />
            Invoice Workspace
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            Draft and issue student invoices using Accounts catalog, GST, and bank settings.
          </p>
          <p className="mt-2 text-xs text-text-muted">
            Next number preview: <span className="font-mono text-text-main">{previewNextInvoiceId()}</span>
            {orgStateCode ? (
              <>
                {' '}
                · Org state from GSTIN: {gstStateName(orgStateCode)} ({orgStateCode})
              </>
            ) : (
              <> · Set Organization GSTIN in Accounts → GST &amp; Tax</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => createDraft(timezone)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-sm font-medium text-text-main hover:bg-surface-bg"
          >
            <Plus size={16} />
            New draft
          </button>
          {!readOnly ? (
            <button
              type="button"
              onClick={() => void handleSaveDraft()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-sm font-medium text-text-main hover:bg-surface-bg"
            >
              <Save size={16} />
              Save draft
            </button>
          ) : null}
          {!readOnly ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleIssue()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
              Issue invoice
            </button>
          ) : null}
          {draft.status === 'issued' &&
          !isPriorIndianFyInvoice(draft.invoiceDate, currentFy.startYear) ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleVoid()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-alert/40 px-3 py-2 text-sm font-medium text-alert disabled:opacity-50"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : null}
              Cancel
            </button>
          ) : null}
          <button
            type="button"
            disabled={busy || !draft.lines.length}
            onClick={() => void handlePdf()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-sm font-medium text-text-main hover:bg-surface-bg disabled:opacity-50"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            PDF
          </button>
        </div>
      </div>

      {message ? (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          <CheckCircle2 size={16} />
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <AlertTriangle size={16} />
          {error}
        </div>
      ) : null}
      {duplicateWarning ? (
        <div
          ref={duplicateWarningRef}
          role="alert"
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-700" />
            <div className="min-w-0 flex-1 space-y-2">
              <p className="font-semibold text-amber-950">
                This student already has {duplicateWarning.existing.length} invoice
                {duplicateWarning.existing.length === 1 ? '' : 's'}
              </p>
              <p>
                <strong>{duplicateWarning.studentName}</strong> (Student / CRM ID{' '}
                <span className="font-mono">{duplicateWarning.hit.id}</span>) already has
                invoice(s) in Draft, Issued, or Cancelled status. Creating another invoice for
                the same student can cause duplicate billing, mixed GST records, and confusion
                in accounts.
              </p>
              <p className="font-medium">Existing invoices:</p>
              <ul className="list-disc space-y-1 pl-5">
                {duplicateWarning.existing.map(row => (
                  <li key={row.id}>
                    <button
                      type="button"
                      className="text-left font-medium text-amber-900 underline decoration-amber-400 underline-offset-2 hover:text-amber-950"
                      onClick={() => {
                        const fyStart = indianFyStartYearFromIsoDate(row.invoiceDate);
                        setDuplicateWarning(null);
                        if (fyStart != null) setSelectedFyStartYear(fyStart);
                        setActiveInvoiceId(row.id);
                      }}
                    >
                      {row.invoiceNumber || 'Unnumbered draft'}
                    </button>
                    {' · '}
                    {statusLabel(row)}
                    {' · '}
                    {row.invoiceDate}
                    {' · '}
                    {currentIndianFy(row.invoiceDate).label}
                    {row.finalPayableSnapshot > 0
                      ? ` · ${formatMoneyInr(row.finalPayableSnapshot)}`
                      : ''}
                  </li>
                ))}
              </ul>
              <p>
                If this is intentional (for example a new service, a later intake, or a
                replacement after a cancelled invoice), you can still create another invoice.
              </p>
              <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <button
                  type="button"
                  className="font-semibold text-amber-900 underline decoration-amber-500 underline-offset-2 hover:text-amber-950"
                  onClick={() => applyStudentMaster(duplicateWarning.hit, true)}
                >
                  Continue anyway
                </button>
                <button
                  type="button"
                  className="text-amber-800 underline decoration-amber-300 underline-offset-2 hover:text-amber-950"
                  onClick={() => setDuplicateWarning(null)}
                >
                  Use a different student
                </button>
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-3 rounded-2xl border border-border-subtle bg-card p-3">
          <div>
            <label
              htmlFor="invoice-fy-select"
              className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-text-muted"
            >
              Financial year
            </label>
            <select
              id="invoice-fy-select"
              value={activeFy.startYear}
              onChange={e => setSelectedFyStartYear(Number(e.target.value))}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-2.5 py-2 text-xs text-text-main outline-none focus:border-primary"
            >
              {fyOptions.map(fy => (
                <option key={fy.folder} value={fy.startYear}>
                  {fy.label}
                  {fy.startYear === currentFy.startYear
                    ? ' (current)'
                    : ' (archived records)'}
                  {` · ${fy.startDate.slice(0, 7)} → ${fy.endDate.slice(0, 7)}`}
                </option>
              ))}
            </select>
            {isHistoricalFy ? (
              <p className="mt-1.5 text-[11px] leading-snug text-text-muted">
                {activeFy.label} invoices are archived records (closed financial year).
              </p>
            ) : (
              <p className="mt-1.5 text-[11px] leading-snug text-text-muted">
                Showing {activeFy.label}: {activeFy.startDate} → {activeFy.endDate}. From the
                next 1 Apr, this year appears under prior FYs as archived records.
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {(
              [
                { key: 'all', label: 'All' },
                { key: 'draft', label: 'Drafts' },
                { key: 'issued', label: 'Issued' },
                { key: 'void', label: 'Cancelled' },
              ] as const
            ).map(tab => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setListFilter(tab.key)}
                className={`rounded-lg px-2 py-1 text-xs font-medium ${
                  listFilter === tab.key
                    ? 'bg-accent text-white'
                    : 'text-text-muted hover:bg-surface-bg'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
            />
            <input
              type="search"
              value={listSearch}
              onChange={e => setListSearch(e.target.value)}
              placeholder="Search student, invoice #…"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg py-2 pl-8 pr-3 text-xs text-text-main outline-none focus:border-primary"
              aria-label="Search invoices"
            />
          </div>
          <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
            {filteredList.map(row => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => setActiveInvoiceId(row.id)}
                  className={`w-full rounded-xl px-2.5 py-2 text-left text-xs ${
                    row.id === draft.id
                      ? 'bg-accent/10 text-text-main ring-1 ring-accent/30'
                      : 'hover:bg-surface-bg text-text-muted'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1 font-semibold text-text-main truncate">
                      {row.invoiceNumber || 'Draft'}
                    </div>
                    <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                      {statusLabel(row)}
                    </span>
                  </div>
                  <div className="truncate">{row.studentFullName || 'Unnamed student'}</div>
                  <div className="mt-1 space-y-0.5 text-[10px] leading-snug opacity-70">
                    <div className="truncate">
                      Draft created{' '}
                      {formatDateTime(row.createdAt, {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: undefined,
                        hour12: false,
                      })}
                    </div>
                    <div className="truncate">
                      Draft last saved{' '}
                      {formatDateTime(row.draftSavedAt || row.createdAt, {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: undefined,
                        hour12: false,
                      })}
                    </div>
                    {row.issuedAt ? (
                      <div className="truncate">
                        Issued{' '}
                        {formatDateTime(row.issuedAt, {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: undefined,
                          hour12: false,
                        })}
                      </div>
                    ) : null}
                    {row.voidedAt ? (
                      <div className="truncate">
                        Cancelled{' '}
                        {formatDateTime(row.voidedAt, {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: undefined,
                          hour12: false,
                        })}
                      </div>
                    ) : null}
                  </div>
                </button>
              </li>
            ))}
            {!filteredList.length ? (
              <li className="px-2 py-6 text-center text-xs text-text-muted">
                {listSearch.trim()
                  ? 'No invoices match your search.'
                  : `No invoices in ${activeFy.label}.`}
              </li>
            ) : null}
          </ul>
          {draft.status === 'draft' ? (
            <button
              type="button"
              onClick={() => void handleDeleteInvoice()}
              className="inline-flex w-full items-center justify-center gap-1 rounded-xl border border-border-subtle px-2 py-1.5 text-xs text-alert"
            >
              <Trash2 size={12} />
              Delete draft
            </button>
          ) : null}
        </aside>

        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-bg px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <FileText size={16} className="text-text-muted" />
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-sm font-semibold text-white">
                Number:{' '}
                <span className="font-mono font-bold">
                  {draft.invoiceNumber || previewNextInvoiceId() + ' (preview)'}
                </span>
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-sm font-semibold text-white">
                Status:{' '}
                <strong className="uppercase tracking-wide font-bold">{statusLabel(draft)}</strong>
              </span>
              {draft.status === 'void' ? (
                <span className="inline-flex max-w-xl items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-sm font-semibold text-white">
                  Reason:{' '}
                  <span className="font-bold">
                    {displayInvoiceCancellationReason(
                      draft.cancellationReasonCode,
                      draft.cancellationReasonDetail
                    ) || '—'}
                  </span>
                </span>
              ) : null}
            </div>
            {draft.status === 'issued' || draft.status === 'void' ? (
              <div className="flex flex-wrap items-center gap-2">
                {resolveIssuedCloudStorageKey(draft) ? (
                  <button
                    type="button"
                    disabled={cloudLinkBusy !== null}
                    onClick={() => void openCloudInvoice('issued')}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                    title={resolveIssuedCloudStorageKey(draft)}
                  >
                    {cloudLinkBusy === 'issued' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <ExternalLink size={14} />
                    )}
                    View / download Issued PDF
                  </button>
                ) : null}
                {draft.status === 'void' && resolveCancelledCloudStorageKey(draft) ? (
                  <button
                    type="button"
                    disabled={cloudLinkBusy !== null}
                    onClick={() => void openCloudInvoice('cancelled')}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                    title={resolveCancelledCloudStorageKey(draft)}
                  >
                    {cloudLinkBusy === 'cancelled' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <ExternalLink size={14} />
                    )}
                    View / download Cancelled PDF
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <SectionCard
            title="1. Student & lead details"
            subtitle="Bill-to party — name should match passport / academic records."
          >
            <div className="relative space-y-1.5">
              <label className={labelClass} htmlFor="invoice-student-search">
                Find student (Students Master) *
              </label>
              <div className="relative">
                <Search
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                />
                <input
                  id="invoice-student-search"
                  name="studentSearch"
                  className={`${fieldClass} pl-8 ${(studentQuery.trim() || draft.studentMasterId) && !searchLocked ? 'pr-9' : ''}`}
                  disabled={searchLocked}
                  placeholder="Type at least 2 characters to search students…"
                  value={studentQuery}
                  onChange={e => setStudentQuery(e.target.value)}
                />
                {(studentQuery.trim() || draft.studentMasterId) && !searchLocked ? (
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                    aria-label="Clear selected student"
                    title="Clear selected student"
                    onClick={clearSelectedStudent}
                  >
                    <X size={14} />
                  </button>
                ) : null}
              </div>
              {studentSearching ? (
                <p className="text-xs text-text-muted">Loading students…</p>
              ) : null}
              {!studentSearching && studentQuery.trim().length >= 2 && !studentHits.length ? (
                <p className="text-xs text-text-muted">No matching students.</p>
              ) : null}
              {studentHits.length ? (
                <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-xl border border-border-subtle bg-card shadow-lg">
                  {studentHits.map(hit => (
                    <li key={hit.id}>
                      <button
                        type="button"
                        className="w-full px-3 py-2 text-left text-sm hover:bg-surface-bg"
                        onClick={() => applyStudentMaster(hit)}
                      >
                        <div className="font-medium">
                          {hit.full_name || `Student #${hit.id}`}
                        </div>
                        <div className="text-xs text-text-muted">
                          ID {hit.id}
                          {hit.lead_id ? ` · Lead #${hit.lead_id}` : ''}
                          {hit.email ? ` · ${hit.email}` : ''}
                          {hit.city ? ` · ${hit.city}` : ''}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="text-xs text-text-muted">
                Selecting a student fills details from{' '}
                <span className="font-medium text-text-main">students_master</span> and locks
                those fields. Use the clear (X) control to reset and unlock. Destination country
                stays editable.
              </p>
            </div>

            <div className="space-y-3">
              <div className={formGridClass}>
                <div className={`${fieldWrapClass} sm:col-span-2 lg:col-span-2 xl:col-span-2`}>
                  <label className={labelClass}>Student full name *</label>
                  <input
                    id="invoice-studentFullName"
                    name="studentFullName"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.studentFullName}
                    onChange={e => patch('studentFullName', e.target.value)}
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Student / CRM ID *</label>
                  <input
                    id="invoice-studentMasterId"
                    name="studentMasterId"
                    className={fieldClass}
                    disabled
                    placeholder="Filled from student search"
                    value={draft.studentMasterId}
                    readOnly
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Lead ID</label>
                  <input
                    id="invoice-leadId"
                    name="leadId"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.leadId ?? ''}
                    onChange={e =>
                      patch('leadId', e.target.value ? Number(e.target.value) || null : null)
                    }
                  />
                </div>
                <div className={`${fieldWrapClass} sm:col-span-2 lg:col-span-1 xl:col-span-1`}>
                  <label htmlFor="invoice-phone" className={labelClass}>
                    Mobile
                  </label>
                  <PhoneWithCountryCodeInput
                    id="invoice-phone"
                    label="Mobile"
                    hideLabel
                    disabled={clientLocked}
                    value={draft.phone}
                    onChange={value => patch('phone', value)}
                    className="min-w-0"
                    hint=""
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Email</label>
                  <input
                    id="invoice-email"
                    name="email"
                    type="email"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.email}
                    onChange={e => patch('email', e.target.value)}
                  />
                </div>
              </div>

              <div className={formGridClass}>
                <div className={`${fieldWrapClass} sm:col-span-2`}>
                  <label className={labelClass}>Permanent / billing address</label>
                  <input
                    id="invoice-addressStreet"
                    name="addressStreet"
                    className={fieldClass}
                    disabled={clientLocked}
                    placeholder="Street address"
                    value={draft.addressStreet}
                    onChange={e => patch('addressStreet', e.target.value)}
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>City</label>
                  <input
                    id="invoice-addressCity"
                    name="addressCity"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.addressCity}
                    onChange={e => patch('addressCity', e.target.value)}
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>State</label>
                  <input
                    id="invoice-addressState"
                    name="addressState"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.addressState}
                    onChange={e => patch('addressState', e.target.value)}
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Country</label>
                  <select
                    id="invoice-addressCountry"
                    name="addressCountry"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.addressCountry || ''}
                    onChange={e => patch('addressCountry', e.target.value.toUpperCase())}
                  >
                    <option value="">Select country…</option>
                    {draft.addressCountry &&
                    !FALLBACK_COUNTRIES.some(c => c.iso2 === draft.addressCountry) ? (
                      <option value={draft.addressCountry}>{draft.addressCountry}</option>
                    ) : null}
                    {FALLBACK_COUNTRIES.map(country => (
                      <option key={country.iso2} value={country.iso2}>
                        {country.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Pincode</label>
                  <input
                    id="invoice-addressPincode"
                    name="addressPincode"
                    className={fieldClass}
                    disabled={clientLocked}
                    value={draft.addressPincode}
                    onChange={e => patch('addressPincode', e.target.value)}
                  />
                </div>
              </div>

              <div className={formGridClass}>
                <div className={`${fieldWrapClass} sm:col-span-2 lg:col-span-2 xl:col-span-2`}>
                  <SearchableMultiSelect
                    id="invoice-destination-countries"
                    label="Destination country"
                    values={draft.destinationCountries || []}
                    options={DESTINATION_OPTIONS}
                    onChange={values => patch('destinationCountries', values)}
                    placeholder="Select one or more destinations…"
                    disabled={readOnly}
                    emptyMessage="No countries match"
                    className="min-w-0"
                  />
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="2. Compliance & tax"
            subtitle="Place of supply vs organization GSTIN state drives CGST+SGST (same state) or IGST (different state)."
          >
            <div className={formGridClass}>
              <div className={`${fieldWrapClass} sm:col-span-2`}>
                <label className={labelClass}>Place of supply (state) *</label>
                <select id="invoice-placeOfSupplyStateCode" name="placeOfSupplyStateCode"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.placeOfSupplyStateCode}
                  onChange={e => patch('placeOfSupplyStateCode', e.target.value)}
                >
                  {INDIAN_GST_STATES.map(state => (
                    <option key={state.code} value={state.code}>
                      {state.code} — {state.name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-text-muted">
                  {orgStateCode ? (
                    <>
                      Org GSTIN state: {gstStateName(orgStateCode)} ({orgStateCode}).{' '}
                      {supplyType === 'intra' ? (
                        <span className="text-emerald-700">Same state → CGST + SGST</span>
                      ) : supplyType === 'exempt' ? (
                        <span>Exempt / 0%</span>
                      ) : (
                        <span className="text-amber-700">
                          Different from place of supply → IGST.{' '}
                          {!readOnly ? (
                            <button
                              type="button"
                              className="underline"
                              onClick={() => patch('placeOfSupplyStateCode', orgStateCode)}
                            >
                              Match org state
                            </button>
                          ) : null}
                        </span>
                      )}
                    </>
                  ) : (
                    <>Set Organization GSTIN in Accounts → GST &amp; Tax to enable CGST/SGST.</>
                  )}
                </p>
              </div>
              <div className={`${fieldWrapClass} sm:col-span-2`}>
                <label className={labelClass}>SAC code</label>
                <select id="invoice-sacCode" name="sacCode"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.sacCode}
                  onChange={e => patch('sacCode', e.target.value)}
                >
                  {INVOICE_SAC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Student / parent GSTIN</label>
                <input id="invoice-buyerGstin" name="buyerGstin"
                  className={fieldClass}
                  disabled={readOnly}
                  placeholder="Optional — ITC / B2B"
                  value={draft.buyerGstin}
                  onChange={e => patch('buyerGstin', e.target.value.toUpperCase())}
                />
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>PAN</label>
                <input id="invoice-pan" name="pan"
                  className={fieldClass}
                  disabled={readOnly}
                  placeholder="Optional"
                  maxLength={10}
                  value={draft.pan}
                  onChange={e => patch('pan', e.target.value.toUpperCase())}
                />
              </div>
              <label className="flex min-w-0 items-center gap-2 text-sm text-text-main sm:col-span-2 lg:col-span-4 xl:col-span-6">
                <input id="invoice-forceExempt" name="forceExempt"
                  type="checkbox"
                  disabled={readOnly}
                  checked={draft.forceExempt}
                  onChange={e => patch('forceExempt', e.target.checked)}
                />
                Mark as GST exempt / zero-rated for this invoice
              </label>
            </div>
          </SectionCard>

          <div className="grid grid-cols-1 items-stretch gap-4 xl:grid-cols-2">
            <SectionCard
              title="3. Services & lines"
              compact
              fillHeight
              className="min-w-0"
            >
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  disabled={readOnly}
                  onClick={() => {
                    if (!draft || draft.billingMode === 'package') return;
                    setDraft({
                      ...draft,
                      billingMode: 'package',
                      packageId: '',
                      packageName: '',
                      packageInvoiceDescription: '',
                      lines: [],
                    });
                  }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                    draft.billingMode === 'package'
                      ? 'bg-accent text-white'
                      : 'border border-border-subtle text-text-main'
                  }`}
                >
                  Package
                </button>
                <button
                  type="button"
                  disabled={readOnly}
                  onClick={() => {
                    if (!draft || draft.billingMode === 'alacarte') return;
                    setDraft({
                      ...draft,
                      billingMode: 'alacarte',
                      packageId: '',
                      packageName: '',
                      packageInvoiceDescription: '',
                      lines: [],
                    });
                  }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                    draft.billingMode === 'alacarte'
                      ? 'bg-accent text-white'
                      : 'border border-border-subtle text-text-main'
                  }`}
                >
                  À la carte
                </button>
              </div>

              <div className="grid grid-cols-1 items-start gap-2 sm:grid-cols-2 xl:grid-cols-5">
                {draft.billingMode === 'package' ? (
                  <div className={fieldWrapClass}>
                    <label className={labelClass} htmlFor="invoice-packageId">
                      Package *
                    </label>
                    <select
                      id="invoice-packageId"
                      name="packageId"
                      className={fieldClass}
                      disabled={readOnly}
                      value={draft.packageId}
                      onChange={e => applyPackage(e.target.value)}
                    >
                      <option value="">Select package…</option>
                      {activePackages.map(pkg => (
                        <option key={pkg.id} value={pkg.id}>
                          {pkg.name}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className={fieldWrapClass}>
                    <SearchableMultiSelect
                      id="invoice-alacarte-services"
                      label="Select services *"
                      values={draft.lines
                        .map(line => line.serviceId)
                        .filter((id): id is string => Boolean(id))}
                      options={activeServices.map(service => ({
                        value: service.id,
                        label: `${service.name} — ₹${formatMoneyInr(service.basePriceInr)}`,
                      }))}
                      onChange={syncAlacarteServices}
                      placeholder="Select one or more services…"
                      disabled={readOnly}
                      emptyMessage="No catalog services available"
                      className="min-w-0"
                    />
                  </div>
                )}

                <div className={fieldWrapClass}>
                  <label className={labelClass}>Discount type</label>
                  <select
                    id="invoice-discountType"
                    name="discountType"
                    className={fieldClass}
                    disabled={readOnly}
                    value={draft.discountType}
                    onChange={e => {
                      const nextType = e.target.value === 'fixed' ? 'fixed' : 'percentage';
                      const nextDefault =
                        nextType === 'fixed'
                          ? policyDiscountDefaultFixed
                          : policyDiscountDefaultPercent;
                      const maxForType =
                        nextType === 'fixed' ? maxDiscountFixed : maxAutoApprove;
                      setDraft(prev =>
                        prev
                          ? {
                              ...prev,
                              discountType: nextType,
                              discountValue: Math.min(maxForType, Math.max(0, nextDefault)),
                            }
                          : prev
                      );
                    }}
                  >
                    <option value="percentage">Percentage %</option>
                    <option value="fixed">Fixed ₹</option>
                  </select>
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>
                    {draft.discountType === 'fixed'
                      ? `Discount value (₹${formatMoneyInr(discountValueBounds.min)}–₹${formatMoneyInr(discountValueBounds.max)})`
                      : `Discount value (${discountValueBounds.min}%–${discountValueBounds.max}%)`}
                  </label>
                  <input
                    key={`invoice-discount-${draft.discountType}`}
                    id="invoice-discountValue"
                    name="discountValue"
                    type="number"
                    min={discountValueBounds.min}
                    max={discountValueBounds.max}
                    step={draft.discountType === 'fixed' ? 100 : 1}
                    className={fieldClass}
                    disabled={readOnly}
                    value={draft.discountValue}
                    onChange={e => {
                      const raw = Number(e.target.value);
                      if (!Number.isFinite(raw)) {
                        patch('discountValue', discountValueBounds.min);
                        return;
                      }
                      patch(
                        'discountValue',
                        Math.min(
                          discountValueBounds.max,
                          Math.max(discountValueBounds.min, raw)
                        )
                      );
                    }}
                  />
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Discount reason</label>
                  <select
                    id="invoice-discountReason"
                    name="discountReason"
                    className={fieldClass}
                    disabled={readOnly}
                    value={draft.discountReason}
                    onChange={e => patch('discountReason', e.target.value)}
                  >
                    <option value="">Select…</option>
                    {discountReasons.map(reason => (
                      <option key={reason} value={reason}>
                        {reason}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={fieldWrapClass}>
                  <label className={labelClass}>Approved by</label>
                  <select
                    id="invoice-approvedByStaffId"
                    name="approvedByStaffId"
                    className={fieldClass}
                    disabled={readOnly}
                    value={draft.approvedByStaffId}
                    onChange={e => {
                      const id = e.target.value;
                      const person = counsellors.find(c => String(c.id) === id);
                      patch('approvedByStaffId', id);
                      patch('approvedByStaffName', person?.full_name || person?.name || '');
                    }}
                  >
                    <option value="">Not required / select…</option>
                    {counsellors.map(c => (
                      <option key={String(c.id)} value={String(c.id)}>
                        {c.full_name || c.name || `Staff #${c.id}`}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {totals?.requiresAuthorization ? (
                <p className="text-xs text-amber-700">
                  Discount is {totals.discountPercentOfSubtotal}% of subtotal (auto-approve max{' '}
                  {maxAutoApprove}%) — authorization required before issue.
                </p>
              ) : null}

              {draft.billingMode === 'package' && draft.packageName.trim() ? (
                <div className="rounded-xl border border-border-subtle bg-surface-bg/70 px-3 py-2 text-sm">
                  <p className="font-semibold uppercase tracking-wide text-text-main">
                    {draft.packageName.trim()}
                    {draft.packageInvoiceDescription?.trim() ? (
                      <span className="font-normal normal-case tracking-normal text-text-muted">
                        {' '}
                        — package services including {draft.packageInvoiceDescription.trim()}
                      </span>
                    ) : null}
                  </p>
                </div>
              ) : null}

              <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border-subtle">
                <table className="min-w-full text-left text-sm">
                  <thead className="sticky top-0 bg-surface-bg text-xs uppercase tracking-wide text-text-muted">
                    <tr>
                      <th className="px-2.5 py-1.5 font-medium">Service</th>
                      <th className="w-28 px-2.5 py-1.5 font-medium">Price ₹</th>
                      <th className="w-8 px-2.5 py-1.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {draft.lines.map(line => (
                      <tr key={line.id} className="border-t border-border-subtle">
                        <td className="px-2.5 py-1.5">
                          <input
                            id={`invoice-lineName-${line.id}`}
                            name={`lineName-${line.id}`}
                            className={fieldClass}
                            disabled={readOnly}
                            value={line.name}
                            onChange={e => updateLine(line.id, { name: e.target.value })}
                          />
                        </td>
                        <td className="px-2.5 py-1.5">
                          <input
                            id={`invoice-lineUnitPrice-${line.id}`}
                            name={`lineUnitPrice-${line.id}`}
                            type="number"
                            min={0}
                            step={1}
                            className={fieldClass}
                            disabled={readOnly}
                            value={line.unitPriceInr}
                            onChange={e =>
                              updateLine(line.id, {
                                quantity: 1,
                                unitPriceInr: Number(e.target.value) || 0,
                              })
                            }
                          />
                        </td>
                        <td className="px-2.5 py-1.5">
                          {!readOnly ? (
                            <button
                              type="button"
                              onClick={() => removeLine(line.id)}
                              className="text-alert"
                              aria-label="Remove line"
                            >
                              <Trash2 size={14} />
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                    {!draft.lines.length ? (
                      <tr>
                        <td colSpan={3} className="px-2.5 py-5 text-center text-xs text-text-muted">
                          No lines yet — pick a package or add services.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </SectionCard>

            <SectionCard
              title="4. Calculation summary"
              subtitle="Subtotal → discount → tax → payable"
              compact
              fillHeight
              className="min-w-0"
            >
              {totals ? (
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface-bg">
                  <div className="min-h-0 flex-1 divide-y divide-border-subtle/80 overflow-auto">
                    <CalcRow
                      label="Services subtotal"
                      amount={`₹ ${formatMoneyInr(totals.linesSubtotal)}`}
                    />
                    <CalcRow
                      operator="−"
                      label="Discount"
                      hint={
                        draft.discountType === 'percentage'
                          ? `${draft.discountValue}%`
                          : 'Fixed'
                      }
                      amount={`₹ ${formatMoneyInr(totals.discountAmount)}`}
                      tone="deduct"
                    />
                    <CalcRow
                      operator="="
                      label="Taxable"
                      amount={`₹ ${formatMoneyInr(totals.taxableAmount)}`}
                      tone="subtotal"
                    />
                    {totals.tax.supplyType === 'intra' ? (
                      <>
                        <CalcRow
                          operator="+"
                          label={`CGST (${totals.tax.cgstRate}%)`}
                          amount={`₹ ${formatMoneyInr(totals.tax.cgstAmount)}`}
                          tone="add"
                        />
                        <CalcRow
                          operator="+"
                          label={`SGST (${totals.tax.sgstRate}%)`}
                          amount={`₹ ${formatMoneyInr(totals.tax.sgstAmount)}`}
                          tone="add"
                        />
                      </>
                    ) : totals.tax.supplyType === 'inter' ? (
                      <CalcRow
                        operator="+"
                        label={`IGST (${totals.tax.igstRate}%)`}
                        amount={`₹ ${formatMoneyInr(totals.tax.igstAmount)}`}
                        tone="add"
                      />
                    ) : (
                      <CalcRow
                        operator="+"
                        label="GST (exempt)"
                        amount="₹ 0.00"
                        tone="muted"
                      />
                    )}
                    <CalcRow
                      operator={totals.roundOffAmount >= 0 ? '+' : '−'}
                      label="Round-off"
                      amount={`₹ ${formatMoneyInr(Math.abs(totals.roundOffAmount))}`}
                      tone="muted"
                    />
                  </div>
                  <div className="shrink-0 border-t-2 border-border-subtle bg-accent/5 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold uppercase tracking-wide text-accent">
                        Final payable
                      </p>
                      <p className="text-right text-xl font-semibold tabular-nums text-text-main">
                        ₹ {formatMoneyInr(totals.finalPayableAmount)}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex-1" />
              )}
              {totals?.tax.unavailable ? (
                <p className="text-sm text-alert">
                  Tax regime unavailable for {supplyType} supply — enable it under Accounts → GST
                  &amp; Tax.
                </p>
              ) : null}
            </SectionCard>
          </div>

          <SectionCard
            title="5. Payment & settlement"
            subtitle="Bank accounts come from Accounts → Bank Details."
          >
            <div className={formGridClass}>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Payment terms</label>
                <select id="invoice-paymentTermsPreset" name="paymentTermsPreset"
                  className={fieldClass}
                  disabled={readOnly}
                  value={
                    PAYMENT_TERMS_PRESETS.includes(
                      draft.paymentTerms as (typeof PAYMENT_TERMS_PRESETS)[number]
                    )
                      ? draft.paymentTerms
                      : '__custom__'
                  }
                  onChange={e => {
                    if (e.target.value === '__custom__') return;
                    patch('paymentTerms', e.target.value);
                  }}
                >
                  {PAYMENT_TERMS_PRESETS.map(term => (
                    <option key={term} value={term}>
                      {term}
                    </option>
                  ))}
                  <option value="__custom__">Custom…</option>
                </select>
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Custom terms (optional)</label>
                <input id="invoice-paymentTerms" name="paymentTerms"
                  className={fieldClass}
                  disabled={readOnly}
                  placeholder="Override or refine payment terms"
                  value={draft.paymentTerms}
                  onChange={e => patch('paymentTerms', e.target.value)}
                />
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Bank account</label>
                <select id="invoice-selectedBankIndex" name="selectedBankIndex"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.selectedBankIndex}
                  onChange={e => {
                    const index = Number(e.target.value) || 0;
                    const bank = bankPayments[index];
                    setDraft(prev =>
                      prev
                        ? {
                            ...prev,
                            selectedBankIndex: index,
                            upiVpa: bank?.upiVpa?.trim() || '',
                          }
                        : prev
                    );
                  }}
                >
                  {bankPayments.map((bank, index) => (
                    <option key={index} value={index}>
                      {(bank.accountNickname?.trim() ||
                        bank.bankName ||
                        `Bank account ${index + 1}`) +
                        (bank.accountNumber ? ` ···${bank.accountNumber.slice(-4)}` : '') +
                        (bank.accountType ? ` (${bank.accountType})` : '')}
                    </option>
                  ))}
                </select>
                {selectedBank ? (
                  <p className="text-xs text-text-muted">
                    {selectedBank.beneficiaryName || '—'} · IFSC {selectedBank.ifscCode || '—'}
                    {selectedBank.upiVpa ? ` · UPI ${selectedBank.upiVpa}` : ''}
                  </p>
                ) : null}
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>UPI ID (VPA)</label>
                <input id="invoice-upiVpa" name="upiVpa"
                  className={fieldClass}
                  disabled={readOnly}
                  placeholder={selectedBank?.upiVpa || 'nexus@hdfcbank'}
                  value={effectiveUpiVpa}
                  onChange={e => patch('upiVpa', e.target.value)}
                />
                <p className="text-xs text-text-muted">
                  Prefilled from the selected bank account; you can override per invoice.
                </p>
              </div>
              <div className={`${fieldWrapClass} sm:col-span-2`}>
                <label className={labelClass}>UPI QR</label>
                <div className="flex min-h-[42px] items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg px-3 py-2">
                  {upiUri ? (
                    <>
                      <img
                        src={upiQrImageUrl(upiUri)}
                        alt="UPI QR code"
                        width={72}
                        height={72}
                        className="shrink-0 rounded-lg border border-border-subtle bg-white p-1"
                      />
                      <div className="min-w-0 text-xs text-text-muted">
                        <p className="font-medium text-text-main">Scan to pay</p>
                        <p className="mt-1 break-all font-mono">{effectiveUpiVpa}</p>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-text-muted">
                      Add a UPI ID on Accounts → Bank Details (or enter one here) to generate a QR.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="6. Administrative & audit metadata">
            <div className={formGridClass}>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Invoice date</label>
                <input id="invoice-invoiceDate" name="invoiceDate"
                  type="date"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.invoiceDate}
                  onChange={e => patch('invoiceDate', e.target.value)}
                />
                <p className="mt-1 text-[11px] text-text-muted">
                  Defaults to today in Settings timezone ({timezone})
                </p>
              </div>
              <div className={fieldWrapClass}>
                <label className={labelClass}>Due date</label>
                <input id="invoice-dueDate" name="dueDate"
                  type="date"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.dueDate}
                  onChange={e => patch('dueDate', e.target.value)}
                />
              </div>
              <div className={`${fieldWrapClass} sm:col-span-2`}>
                <label className={labelClass}>Assigned counselor / account manager *</label>
                <select id="invoice-counselorId" name="counselorId"
                  className={fieldClass}
                  disabled={readOnly}
                  value={draft.counselorId}
                  onChange={e => {
                    const id = e.target.value;
                    const person = counsellors.find(c => String(c.id) === id);
                    patch('counselorId', id);
                    patch('counselorName', person?.full_name || person?.name || '');
                    if (id.trim()) setError(null);
                  }}
                >
                  <option value="">Select…</option>
                  {counsellors.map(c => (
                    <option key={String(c.id)} value={String(c.id)}>
                      {c.full_name || c.name || `Staff #${c.id}`}
                    </option>
                  ))}
                </select>
              </div>
              {(draft.status === 'issued' &&
                !isPriorIndianFyInvoice(draft.invoiceDate, currentFy.startYear)) ||
              draft.status === 'void' ? (
                <div className={`${fieldWrapClass} sm:col-span-2`}>
                  <label className={labelClass}>
                    Cancellation reason
                    {draft.status === 'issued' ? ' (required to cancel)' : ''}
                  </label>
                  {draft.status === 'void' ? (
                    <p className="rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main">
                      {displayInvoiceCancellationReason(
                        draft.cancellationReasonCode,
                        draft.cancellationReasonDetail
                      ) || '—'}
                    </p>
                  ) : (
                    <>
                      <select
                        id="invoice-cancellationReasonCode"
                        name="cancellationReasonCode"
                        className={fieldClass}
                        value={draft.cancellationReasonCode ?? ''}
                        onChange={e => {
                          const code = e.target.value;
                          const detail =
                            code === INVOICE_CANCELLATION_REASON_OTHER
                              ? draft.cancellationReasonDetail ?? ''
                              : '';
                          setDraft(prev =>
                            prev
                              ? {
                                  ...prev,
                                  cancellationReasonCode: code,
                                  cancellationReasonDetail: detail,
                                }
                              : prev
                          );
                          // Persist without bumping updatedAt so the store→draft
                          // sync effect does not wipe other local editor state.
                          upsertInvoice({
                            ...draft,
                            cancellationReasonCode: code,
                            cancellationReasonDetail: detail,
                          });
                          if (code.trim()) setError(null);
                        }}
                      >
                        <option value="">Select…</option>
                        {INVOICE_CANCELLATION_REASON_OPTIONS.map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      {(draft.cancellationReasonCode ?? '') ===
                      INVOICE_CANCELLATION_REASON_OTHER ? (
                        <input
                          id="invoice-cancellationReasonDetail"
                          name="cancellationReasonDetail"
                          type="text"
                          className={`${fieldClass} mt-2`}
                          maxLength={500}
                          placeholder="Enter custom cancellation reason"
                          value={draft.cancellationReasonDetail ?? ''}
                          onChange={e => {
                            const detail = e.target.value;
                            setDraft(prev =>
                              prev ? { ...prev, cancellationReasonDetail: detail } : prev
                            );
                            upsertInvoice({
                              ...draft,
                              cancellationReasonDetail: detail,
                            });
                            if (detail.trim()) setError(null);
                          }}
                        />
                      ) : null}
                    </>
                  )}
                </div>
              ) : null}
              <div className={`${fieldWrapClass} sm:col-span-2`}>
                <label className={labelClass}>Internal notes / remarks</label>
                <textarea
                  id="invoice-internalNotes"
                  name="internalNotes"
                  className={`${fieldClass} min-h-[42px]`}
                  disabled={readOnly}
                  placeholder="Not printed on the student-facing invoice PDF."
                  value={draft.internalNotes ?? ''}
                  onChange={e => patch('internalNotes', e.target.value)}
                />
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
};

function CalcRow({
  label,
  hint,
  amount,
  operator,
  tone = 'default',
  compact = false,
}: {
  label: string;
  hint?: string;
  amount: string;
  operator?: '−' | '+' | '=';
  tone?: 'default' | 'deduct' | 'add' | 'subtotal' | 'muted';
  compact?: boolean;
}) {
  const amountClass =
    tone === 'deduct'
      ? 'text-alert'
      : tone === 'add'
        ? 'text-text-main'
        : tone === 'subtotal'
          ? 'font-semibold text-text-main'
          : tone === 'muted'
            ? 'text-text-muted'
            : 'text-text-main';

  return (
    <div
      className={`flex items-center gap-2.5 ${compact ? 'px-3 py-1.5' : 'px-3.5 py-2.5'} ${
        tone === 'subtotal' ? 'bg-card/80' : ''
      }`}
    >
      <div
        className={`flex shrink-0 items-center justify-center rounded-full font-semibold ${
          compact ? 'h-6 w-6 text-xs' : 'h-8 w-8 text-sm'
        } ${
          operator === '−'
            ? 'bg-alert/10 text-alert'
            : operator === '+'
              ? 'bg-accent/10 text-accent'
              : operator === '='
                ? 'bg-border-subtle text-text-main'
                : 'bg-transparent text-transparent'
        }`}
        aria-hidden={operator ? undefined : true}
      >
        {operator || '·'}
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={`${compact ? 'text-xs' : 'text-sm'} ${
            tone === 'subtotal' ? 'font-semibold text-text-main' : 'font-medium text-text-main'
          }`}
        >
          {label}
          {hint ? (
            <span className={`ml-1 font-normal text-text-muted ${compact ? '' : 'text-sm'}`}>
              ({hint})
            </span>
          ) : null}
        </p>
      </div>
      <p
        className={`shrink-0 tabular-nums ${compact ? 'text-xs' : 'text-base font-medium'} ${amountClass}`}
      >
        {amount}
      </p>
    </div>
  );
}

export default InvoiceWorkspacePage;
