import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  createEmptyInvoiceDraft,
  INVOICE_CANCELLATION_REASON_OTHER,
  invoiceDocumentSchema,
  issuedStorageKeyFromCancelled,
  resolveInvoiceCancellationReason,
  type InvoiceDocument,
  type InvoiceStatus,
} from '../schemas/invoiceWorkspaceSchema';
import { useAdminSettingsStore } from './adminSettingsStore';
import { stateCodeFromGstin } from '../constants/indianGstStates';
import { normalizeBankPaymentList } from '../schemas/billingSettingsSchema';
import { getCachedBusinessTimezone } from '../utils/timezone';

const FY_DEMO_SEED_PREFIX = 'seed_fy_';

function normalizeInvoiceRow(row: unknown): InvoiceDocument | null {
  if (!row || typeof row !== 'object') return null;
  const raw = { ...(row as Record<string, unknown>) };
  const legacyDest = raw.destinationCountryIso2;
  if (!Array.isArray(raw.destinationCountries)) {
    if (typeof legacyDest === 'string' && legacyDest.trim()) {
      raw.destinationCountries = [legacyDest.trim().toUpperCase()];
    } else {
      raw.destinationCountries = [];
    }
  }
  delete raw.destinationCountryIso2;
  if (typeof raw.cancellationReasonCode !== 'string') {
    raw.cancellationReasonCode = '';
  }
  if (typeof raw.cancellationReasonDetail !== 'string') {
    raw.cancellationReasonDetail = '';
  }
  if (typeof raw.cloudDownloadUrl !== 'string') {
    raw.cloudDownloadUrl = '';
  }
  if (typeof raw.issuedCloudStorageKey !== 'string') {
    raw.issuedCloudStorageKey = '';
  }
  if (typeof raw.issuedCloudDownloadUrl !== 'string') {
    raw.issuedCloudDownloadUrl = '';
  }
  if (typeof raw.cancelledCloudStorageKey !== 'string') {
    raw.cancelledCloudStorageKey = '';
  }
  if (typeof raw.cancelledCloudDownloadUrl !== 'string') {
    raw.cancelledCloudDownloadUrl = '';
  }
  const legacyKey =
    typeof raw.cloudStorageKey === 'string' ? raw.cloudStorageKey.trim() : '';
  if (legacyKey) {
    if (/_Cancelled\.pdf$/i.test(legacyKey)) {
      if (!String(raw.cancelledCloudStorageKey || '').trim()) {
        raw.cancelledCloudStorageKey = legacyKey;
      }
      if (!String(raw.issuedCloudStorageKey || '').trim()) {
        raw.issuedCloudStorageKey = issuedStorageKeyFromCancelled(legacyKey);
      }
    } else if (!String(raw.issuedCloudStorageKey || '').trim()) {
      raw.issuedCloudStorageKey = legacyKey;
    }
  }
  if (typeof raw.draftSavedAt !== 'string' || !raw.draftSavedAt.trim()) {
    raw.draftSavedAt =
      typeof raw.createdAt === 'string' && raw.createdAt.trim() ? raw.createdAt : '';
  }
  const parsed = invoiceDocumentSchema.safeParse(raw);
  if (parsed.success) return parsed.data;

  // Incomplete drafts (empty student name, invalid UPI, etc.) used to fail
  // Zod and get dropped on rehydrate — leaving /invoices looking empty.
  const fallback = createEmptyInvoiceDraft();
  const recoveredId =
    typeof raw.id === 'string' && raw.id.trim() ? raw.id.trim() : fallback.id;
  const recoveredLines = Array.isArray(raw.lines)
    ? raw.lines
        .flatMap(line => {
          if (!line || typeof line !== 'object') return [];
          const item = line as Record<string, unknown>;
          const name = String(item.name ?? '').trim() || 'Service';
          return [
            {
              id: String(item.id ?? '').trim() || `line_${recoveredId}`,
              serviceId: String(item.serviceId ?? ''),
              name,
              quantity: Number(item.quantity) || 1,
              unitPriceInr: Number(item.unitPriceInr) || 0,
            },
          ];
        })
    : [];
  const recovered = invoiceDocumentSchema.safeParse({
    ...fallback,
    ...raw,
    id: recoveredId,
    lines: recoveredLines,
    upiVpa:
      typeof raw.upiVpa === 'string' && /^[\w.\-]+@[\w.\-]+$/.test(raw.upiVpa.trim())
        ? raw.upiVpa.trim()
        : '',
    sacCode:
      typeof raw.sacCode === 'string' && raw.sacCode.trim().length >= 4
        ? raw.sacCode.trim()
        : fallback.sacCode,
    invoiceDate:
      typeof raw.invoiceDate === 'string' && raw.invoiceDate.trim()
        ? raw.invoiceDate
        : fallback.invoiceDate,
    dueDate:
      typeof raw.dueDate === 'string' && raw.dueDate.trim()
        ? raw.dueDate
        : fallback.dueDate,
  });
  return recovered.success ? recovered.data : { ...fallback, id: recoveredId };
}

function stripFyDemoSamples(rows: InvoiceDocument[]): InvoiceDocument[] {
  return rows.filter(row => !String(row.id || '').startsWith(FY_DEMO_SEED_PREFIX));
}

type InvoiceWorkspaceState = {
  invoices: InvoiceDocument[];
  activeInvoiceId: string | null;
  /** Prefill invoice date as “today” in the Nexus Settings business timezone. */
  createDraft: (timezone?: string) => InvoiceDocument;
  setActiveInvoiceId: (id: string | null) => void;
  upsertInvoice: (invoice: InvoiceDocument) => void;
  getInvoice: (id: string) => InvoiceDocument | undefined;
  issueInvoice: (id: string, extras: {
    orgGstin: string;
    gstPercentage: number;
    finalPayable: number;
  }) => { ok: true; invoice: InvoiceDocument } | { ok: false; error: string };
  voidInvoice: (
    id: string,
    cancellation: { code: string; detail: string }
  ) => { ok: true; invoice: InvoiceDocument } | { ok: false; error: string };
  deleteDraft: (id: string) => void;
  listByStatus: (status?: InvoiceStatus) => InvoiceDocument[];
};

function sortInvoices(rows: InvoiceDocument[]): InvoiceDocument[] {
  return [...rows].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export const useInvoiceWorkspaceStore = create<InvoiceWorkspaceState>()(
  persist(
    (set, get) => ({
      invoices: [],
      activeInvoiceId: null,

      createDraft: timezone => {
        const billing = useAdminSettingsStore.getState();
        const orgState = stateCodeFromGstin(billing.gstNumber) || '27';
        const maxAuto = Math.min(
          100,
          Math.max(0, billing.maxAutoApproveDiscountPercent ?? 20)
        );
        const maxFixed = Math.min(
          1_000_000,
          Math.max(0, billing.maxDiscountFixedAmount ?? 10_000)
        );
        const discountType = billing.discountType === 'fixed' ? 'fixed' : 'percentage';
        const policyDefault =
          discountType === 'fixed'
            ? Math.min(1_000_000, Math.max(0, billing.discountFixedAmount || 0))
            : Math.min(100, Math.max(0, billing.discountPercentage || 0));
        const discountValue =
          discountType === 'percentage'
            ? Math.min(maxAuto, Math.max(0, policyDefault))
            : Math.min(maxFixed, Math.max(0, policyDefault));
        const draft = createEmptyInvoiceDraft({
          placeOfSupplyStateCode: orgState,
          discountType,
          discountValue,
          discountReason: billing.defaultDiscountReason || '',
          timezone: timezone || getCachedBusinessTimezone(),
        });
        const banks = normalizeBankPaymentList(billing.bankPayments);
        draft.selectedBankIndex = 0;
        draft.upiVpa = banks[0]?.upiVpa?.trim() || '';
        set(state => ({
          invoices: sortInvoices([draft, ...state.invoices]),
          activeInvoiceId: draft.id,
        }));
        return draft;
      },

      setActiveInvoiceId: id => set({ activeInvoiceId: id }),

      upsertInvoice: invoice => {
        const next =
          normalizeInvoiceRow({
            ...invoice,
            updatedAt: new Date().toISOString(),
          }) || ({ ...invoice, updatedAt: new Date().toISOString() } as InvoiceDocument);
        set(state => {
          const without = state.invoices.filter(row => row.id !== next.id);
          return {
            invoices: sortInvoices([next, ...without]),
            activeInvoiceId: next.id,
          };
        });
      },

      getInvoice: id => get().invoices.find(row => row.id === id),

      issueInvoice: (id, extras) => {
        const current = get().getInvoice(id);
        if (!current) return { ok: false, error: 'Invoice not found.' };
        if (current.status !== 'draft') {
          return { ok: false, error: 'Only draft invoices can be issued.' };
        }
        if (!current.studentMasterId?.trim()) {
          return {
            ok: false,
            error:
              'Select a valid student from Find student before issuing this invoice.',
          };
        }
        if (current.billingMode === 'package' && !current.packageId?.trim()) {
          return { ok: false, error: 'Select a package before issuing this invoice.' };
        }
        if (!current.lines.length) {
          return { ok: false, error: 'Add at least one service line before issuing.' };
        }
        if (!current.counselorId?.trim()) {
          return {
            ok: false,
            error: 'Please select an Assigned counselor / account manager.',
          };
        }
        if (!current.studentFullName.trim()) {
          return { ok: false, error: 'Student full name is required.' };
        }
        if (!current.placeOfSupplyStateCode.trim()) {
          return { ok: false, error: 'Place of supply is required.' };
        }

        const invoiceNumber = useAdminSettingsStore.getState().allocateNextInvoiceId();
        const now = new Date().toISOString();
        const issued: InvoiceDocument = {
          ...current,
          status: 'issued',
          invoiceNumber,
          issuedAt: now,
          updatedAt: now,
          orgGstinSnapshot: extras.orgGstin,
          gstPercentageSnapshot: extras.gstPercentage,
          finalPayableSnapshot: extras.finalPayable,
        };
        get().upsertInvoice(issued);
        return { ok: true, invoice: issued };
      },

      voidInvoice: (id, cancellation) => {
        const current = get().getInvoice(id);
        if (!current) return { ok: false, error: 'Invoice not found.' };
        if (current.status !== 'issued') {
          return { ok: false, error: 'Only issued invoices can be cancelled.' };
        }
        const resolved = resolveInvoiceCancellationReason(
          cancellation.code,
          cancellation.detail
        );
        if (!resolved.ok) {
          return { ok: false, error: resolved.error };
        }
        const code = String(cancellation.code || '').trim();
        const detail = String(cancellation.detail || '').trim();
        const now = new Date().toISOString();
        const issuedKey = (
          current.issuedCloudStorageKey ||
          current.cloudStorageKey ||
          ''
        ).trim();
        const voided: InvoiceDocument = {
          ...current,
          cancellationReasonCode: code,
          cancellationReasonDetail:
            code === INVOICE_CANCELLATION_REASON_OTHER ? detail : '',
          issuedCloudStorageKey: issuedKey,
          issuedCloudDownloadUrl: (
            current.issuedCloudDownloadUrl ||
            current.cloudDownloadUrl ||
            ''
          ).trim(),
          status: 'void',
          voidedAt: now,
          updatedAt: now,
        };
        get().upsertInvoice(voided);
        return { ok: true, invoice: voided };
      },

      deleteDraft: id => {
        const current = get().getInvoice(id);
        if (!current || current.status !== 'draft') {
          return;
        }
        set(state => {
          const remaining = state.invoices.filter(row => row.id !== id);
          return {
            invoices: remaining,
            activeInvoiceId:
              state.activeInvoiceId === id ? remaining[0]?.id ?? null : state.activeInvoiceId,
          };
        });
      },

      listByStatus: status => {
        const rows = get().invoices;
        if (!status) return rows;
        return rows.filter(row => row.status === status);
      },
    }),
    {
      name: 'nexus.invoice-workspace',
      version: 14,
      partialize: state => ({
        invoices: state.invoices,
        activeInvoiceId: state.activeInvoiceId,
      }),
      migrate: (persisted: unknown, _fromVersion: number) => {
        const raw = (persisted || {}) as Partial<InvoiceWorkspaceState>;
        let invoices = Array.isArray(raw.invoices)
          ? (raw.invoices.map(normalizeInvoiceRow).filter(Boolean) as InvoiceDocument[])
          : [];
        invoices = stripFyDemoSamples(invoices).map(row => {
          if (row.status !== 'archived') return row;
          return {
            ...row,
            status: row.voidedAt ? ('void' as const) : ('issued' as const),
          };
        });
        invoices = sortInvoices(invoices);
        const activeStillPresent = invoices.some(row => row.id === raw.activeInvoiceId);
        return {
          invoices,
          activeInvoiceId: activeStillPresent
            ? raw.activeInvoiceId ?? null
            : invoices[0]?.id ?? null,
        };
      },
      merge: (persistedState, currentState) => {
        const raw = (persistedState || {}) as Partial<InvoiceWorkspaceState>;
        let invoices = Array.isArray(raw.invoices)
          ? (raw.invoices.map(normalizeInvoiceRow).filter(Boolean) as InvoiceDocument[])
          : currentState.invoices;
        invoices = stripFyDemoSamples(invoices);
        invoices = sortInvoices(invoices);
        const activeStillPresent = invoices.some(row => row.id === raw.activeInvoiceId);
        return {
          ...currentState,
          invoices,
          activeInvoiceId: activeStillPresent
            ? raw.activeInvoiceId ?? null
            : invoices[0]?.id ?? null,
        };
      },
    }
  )
);
