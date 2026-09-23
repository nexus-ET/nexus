import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, MessageSquareText, X } from 'lucide-react';
import {
  useCounselorFollowupStatuses,
  useCreateLeadFollowup,
  useLeadFollowups,
  type CounselorFollowupItem,
  type CounselorFollowupSentDocument,
  type CounselorStatusMasterItem,
} from '../hooks/useCounselorFollowups';
import { useLevels } from '../hooks/useLevels';
import { apiFetch, apiFetchBlob } from '../utils/api';
import HeadlessScrollArea from './HeadlessScrollArea';

interface CounselorFollowupDrawerProps {
  open: boolean;
  leadId: number | null;
  leadName?: string | null;
  onClose: () => void;
  onFollowupSaved?: () => void;
}

type ChecklistScope = 'global' | 'country_specific';

interface ChecklistCountryOption {
  id: number;
  iso2: string;
  name: string;
}

interface MailSentConfirmation {
  emailTo: string;
  sentAt: string;
}

const formatTime = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const formatDateOnly = (value: string): string => {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
};

/** Local calendar date as YYYY-MM-DD (avoids UTC day-shift). */
function todayLocalIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Split status master templates into Points Discussed / Action Items. */
function splitTemplateDescription(raw: string): { points: string; actions: string } {
  const text = (raw || '').trim();
  if (!text) return { points: '', actions: '' };
  const match = text.match(/^(.*?)(?:\s*Action\s+Items\s*:\s*)([\s\S]*)$/i);
  if (!match) {
    const pointsOnly = text.replace(/^\s*Points\s+Discussed\s*:\s*/i, '').trim();
    return { points: pointsOnly || text, actions: '' };
  }
  const points = match[1].replace(/^\s*Points\s+Discussed\s*:\s*/i, '').trim();
  const actions = match[2].trim();
  return { points: points || text, actions };
}

function actionItemLines(raw: string): string[] {
  return raw
    .split(/\n+/)
    .map(line => line.trim())
    .filter(Boolean);
}

function isSendDocumentChecklistStatus(
  status: CounselorStatusMasterItem | null
): boolean {
  if (!status) return false;
  const key = (status.status_key || '').trim().toLowerCase();
  if (key === 'send_document_checklist') return true;
  return (status.status_heading || '').trim().toLowerCase() === 'send document checklist';
}

function hasChecklistEmailReceipt(item: CounselorFollowupItem): boolean {
  return Boolean(item.checklist_email_sent_at && (item.checklist_email_to || '').trim());
}

function mediaUrlToApiEndpoint(url: string): string | null {
  const trimmed = url.trim();
  if (!trimmed) return null;
  if (/^https?:\/\//i.test(trimmed)) return null;
  const marker = 'document-requirements/media/';
  const idx = trimmed.indexOf(marker);
  if (idx >= 0) return trimmed.slice(idx);
  if (trimmed.startsWith('/api/v1/')) return trimmed.slice('/api/v1/'.length);
  return trimmed.replace(/^\//, '');
}

function ActionItemsDisplay({ followupId, text }: { followupId: number; text: string }) {
  const lines = actionItemLines(text);
  if (lines.length <= 1) {
    return (
      <p>
        <span className="font-semibold">Action Items: </span>
        {text}
      </p>
    );
  }
  return (
    <div className="space-y-1">
      <p className="font-semibold">Action Items:</p>
      {lines.map((line, index) => (
        <p key={`${followupId}-action-${index}`}>{line}</p>
      ))}
    </div>
  );
}

function ChecklistDocumentLink({
  doc,
}: {
  doc: CounselorFollowupSentDocument;
}) {
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const label = (doc.label || '').trim() || 'Document';
  const url = (doc.url || '').trim();
  const unavailable = Boolean(doc.link_unavailable) || !url;

  const openRelative = async () => {
    const endpoint = mediaUrlToApiEndpoint(url);
    if (!endpoint) {
      setOpenError('Link unavailable');
      return;
    }
    setOpening(true);
    setOpenError(null);
    try {
      const blob = await apiFetchBlob(endpoint);
      const objectUrl = URL.createObjectURL(blob);
      window.open(objectUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (err) {
      setOpenError(err instanceof Error ? err.message : 'Failed to open file');
    } finally {
      setOpening(false);
    }
  };

  if (unavailable) {
    return (
      <li className="text-sm text-text-main">
        {label}{' '}
        <span className="text-text-muted">(link unavailable)</span>
      </li>
    );
  }

  if (/^https?:\/\//i.test(url)) {
    return (
      <li className="text-sm">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent underline underline-offset-2 hover:opacity-90 break-all"
        >
          {label}
        </a>
      </li>
    );
  }

  return (
    <li className="text-sm">
      <button
        type="button"
        className="text-accent underline underline-offset-2 hover:opacity-90 disabled:opacity-50 text-left break-all"
        onClick={() => void openRelative()}
        disabled={opening}
      >
        {opening ? 'Opening…' : label}
      </button>
      {openError ? <span className="ml-2 text-xs text-red-700">{openError}</span> : null}
    </li>
  );
}

function ChecklistSentBlock({
  item,
  compact = false,
}: {
  item: CounselorFollowupItem;
  compact?: boolean;
}) {
  if (!hasChecklistEmailReceipt(item)) return null;
  const documents = item.checklist_sent_documents ?? [];
  const sentAt = item.checklist_email_sent_at
    ? formatTime(item.checklist_email_sent_at)
    : '';
  const emailTo = (item.checklist_email_to || '').trim();

  return (
    <div
      className={
        compact
          ? 'space-y-2'
          : 'rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 space-y-2'
      }
    >
      <p className="text-sm font-semibold text-text-main">Document checklist sent</p>
      {documents.length > 0 ? (
        <ul className="list-disc pl-5 space-y-1">
          {documents.map((doc, index) => (
            <ChecklistDocumentLink
              key={`${item.id}-doc-${index}-${doc.label}`}
              doc={doc}
            />
          ))}
        </ul>
      ) : (
        <p className="text-xs text-text-muted">No attachment links were recorded.</p>
      )}
      <div className="text-xs text-text-main space-y-0.5 pt-1 border-t border-emerald-200/80">
        <p>
          <span className="font-semibold">Mail sent</span>
        </p>
        {sentAt ? (
          <p>
            <span className="font-semibold">Sent: </span>
            {sentAt}
          </p>
        ) : null}
        {emailTo ? (
          <p>
            <span className="font-semibold">Email: </span>
            {emailTo}
          </p>
        ) : null}
      </div>
    </div>
  );
}

const CounselorFollowupDrawer: React.FC<CounselorFollowupDrawerProps> = ({
  open,
  leadId,
  leadName,
  onClose,
  onFollowupSaved,
}) => {
  const statusesQuery = useCounselorFollowupStatuses(open);
  const followupsQuery = useLeadFollowups(leadId, open);
  const createMutation = useCreateLeadFollowup();
  const { levels: catalogLevels } = useLevels();

  const [statusId, setStatusId] = useState<number | ''>('');
  const [pointsDiscussed, setPointsDiscussed] = useState('');
  const [actionItems, setActionItems] = useState('');
  const [nextFollowupDate, setNextFollowupDate] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [formWarning, setFormWarning] = useState<string | null>(null);
  const [mailSentConfirmation, setMailSentConfirmation] =
    useState<MailSentConfirmation | null>(null);

  const [checklistScope, setChecklistScope] = useState<ChecklistScope>('global');
  const [checklistCountryId, setChecklistCountryId] = useState('');
  const [checklistLevel, setChecklistLevel] = useState('');
  const [checklistSendEmail, setChecklistSendEmail] = useState<'yes' | 'no'>('no');
  const [checklistLevelsWithDocs, setChecklistLevelsWithDocs] = useState<string[]>([]);
  const [checklistLevelsLoading, setChecklistLevelsLoading] = useState(false);
  const [checklistCountrySpecificAvailable, setChecklistCountrySpecificAvailable] =
    useState(false);
  const [checklistMappedCountries, setChecklistMappedCountries] = useState<
    ChecklistCountryOption[]
  >([]);
  const [checklistScopeLoading, setChecklistScopeLoading] = useState(false);
  const [checklistMetaError, setChecklistMetaError] = useState<string | null>(null);

  const statuses = useMemo(() => {
    const items = statusesQuery.data?.items ?? [];
    return [...items].sort((a, b) =>
      a.status_heading.localeCompare(b.status_heading, undefined, { sensitivity: 'base' })
    );
  }, [statusesQuery.data?.items]);
  const minFollowupDate = useMemo(() => todayLocalIso(), [open]);

  const selectedStatus = useMemo(
    () => statuses.find(item => item.id === statusId) ?? null,
    [statuses, statusId]
  );
  const showChecklistPanel = isSendDocumentChecklistStatus(selectedStatus);

  const levelsWithDocsSet = useMemo(
    () => new Set(checklistLevelsWithDocs.map(name => name.trim()).filter(Boolean)),
    [checklistLevelsWithDocs]
  );

  const catalogLevelNames = useMemo(
    () =>
      catalogLevels
        .map(level => (level.name || '').trim())
        .filter(Boolean),
    [catalogLevels]
  );

  const checklistCountryOptions = useMemo(
    () =>
      checklistMappedCountries.map(country => ({
        value: String(country.id),
        label: country.name,
      })),
    [checklistMappedCountries]
  );

  const resetChecklistPanel = useCallback(() => {
    setChecklistScope('global');
    setChecklistCountryId('');
    setChecklistLevel('');
    setChecklistSendEmail('no');
    setChecklistLevelsWithDocs([]);
    setChecklistLevelsLoading(false);
    setChecklistCountrySpecificAvailable(false);
    setChecklistMappedCountries([]);
    setChecklistScopeLoading(false);
    setChecklistMetaError(null);
  }, []);

  const resetForm = () => {
    setStatusId('');
    setPointsDiscussed('');
    setActionItems('');
    setNextFollowupDate('');
    setFormError(null);
    setFormWarning(null);
    setMailSentConfirmation(null);
    resetChecklistPanel();
  };

  const loadChecklistLevels = useCallback(
    async (scope: ChecklistScope, countryId: string) => {
      if (scope === 'country_specific' && !countryId) {
        setChecklistLevelsWithDocs([]);
        setChecklistLevel('');
        setChecklistLevelsLoading(false);
        return;
      }
      setChecklistLevelsLoading(true);
      setChecklistMetaError(null);
      try {
        const params = new URLSearchParams();
        params.set('scope', scope);
        if (scope === 'country_specific' && countryId) {
          params.set('country_id', countryId);
        }
        const data = await apiFetch<{ program_levels: string[] }>(
          `leads/document-checklist/levels?${params.toString()}`
        );
        const levels = data.program_levels ?? [];
        setChecklistLevelsWithDocs(levels);
        setChecklistLevel(prev => {
          if (prev && levels.includes(prev)) return prev;
          return '';
        });
      } catch (err) {
        setChecklistLevelsWithDocs([]);
        setChecklistLevel('');
        setChecklistMetaError(
          err instanceof Error ? err.message : 'Failed to load checklist levels.'
        );
      } finally {
        setChecklistLevelsLoading(false);
      }
    },
    []
  );

  const loadChecklistScope = useCallback(async () => {
    setChecklistScopeLoading(true);
    setChecklistMetaError(null);
    try {
      const data = await apiFetch<{
        country_specific_available: boolean;
        countries: ChecklistCountryOption[];
      }>('leads/document-checklist/scope');
      const mapped = data.countries ?? [];
      setChecklistCountrySpecificAvailable(Boolean(data.country_specific_available));
      setChecklistMappedCountries(mapped);
      return Boolean(data.country_specific_available);
    } catch (err) {
      setChecklistCountrySpecificAvailable(false);
      setChecklistMappedCountries([]);
      setChecklistMetaError(
        err instanceof Error ? err.message : 'Failed to load checklist scope options.'
      );
      return false;
    } finally {
      setChecklistScopeLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      resetForm();
      return;
    }
  }, [open, leadId]);

  useEffect(() => {
    if (!open || !showChecklistPanel) {
      if (!showChecklistPanel) resetChecklistPanel();
      return;
    }
    setChecklistScope('global');
    setChecklistCountryId('');
    setChecklistLevel('');
    setChecklistSendEmail('no');
    void loadChecklistScope();
    void loadChecklistLevels('global', '');
  }, [open, showChecklistPanel, leadId, loadChecklistScope, loadChecklistLevels, resetChecklistPanel]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const handleStatusChange = (nextId: string) => {
    if (!nextId) {
      setStatusId('');
      setPointsDiscussed('');
      setActionItems('');
      resetChecklistPanel();
      return;
    }
    const id = Number(nextId);
    setStatusId(id);
    const match = statuses.find(item => item.id === id);
    if (match) {
      const split = splitTemplateDescription(match.default_description);
      setPointsDiscussed(split.points);
      setActionItems(split.actions);
    }
    setFormError(null);
    setFormWarning(null);
    setMailSentConfirmation(null);
  };

  const handleChecklistScopeChange = (nextScope: ChecklistScope) => {
    if (nextScope === 'country_specific' && !checklistCountrySpecificAvailable) return;
    setChecklistScope(nextScope);
    setFormError(null);
    if (nextScope === 'global') {
      setChecklistCountryId('');
      void loadChecklistLevels('global', '');
      return;
    }
    void loadChecklistLevels('country_specific', checklistCountryId);
  };

  const handleChecklistCountryChange = (nextCountryId: string) => {
    setChecklistCountryId(nextCountryId);
    setFormError(null);
    void loadChecklistLevels('country_specific', nextCountryId);
  };

  const handleSave = async () => {
    if (!leadId) return;
    if (!statusId) {
      setFormError('Select a follow-up status.');
      return;
    }
    const points = pointsDiscussed.trim();
    if (!points) {
      setFormError('Points Discussed cannot be empty.');
      return;
    }
    const actions = actionItems.trim();
    const followupDate = nextFollowupDate.trim();
    const today = todayLocalIso();

    if (followupDate && followupDate < today) {
      setFormError('Next Follow-up Date cannot be in the past.');
      return;
    }
    if (actions && !followupDate) {
      setFormError('Select a Next Follow-up Date (today or a future date) when Action Items are set.');
      return;
    }
    if (actions && followupDate < today) {
      setFormError('Next Follow-up Date must be today or a future date.');
      return;
    }

    const sendEmail = showChecklistPanel && checklistSendEmail === 'yes';
    if (sendEmail) {
      if (!checklistLevel || !levelsWithDocsSet.has(checklistLevel)) {
        setFormError('Select an enabled program level before sending the document checklist email.');
        return;
      }
      if (checklistScope === 'country_specific') {
        if (!checklistCountrySpecificAvailable) {
          setFormError('Country-Specific checklists are not available (no country-mapped documents).');
          return;
        }
        if (!checklistCountryId) {
          setFormError('Select a country before sending a country-specific document checklist email.');
          return;
        }
      }
    }

    setFormError(null);
    setFormWarning(null);
    setMailSentConfirmation(null);
    try {
      const created = await createMutation.mutateAsync({
        leadId,
        payload: {
          status_id: Number(statusId),
          points_discussed: points,
          action_items: actions || null,
          target_completion_date: followupDate || null,
          ...(sendEmail
            ? {
                send_document_checklist_email: true,
                checklist_program_level: checklistLevel,
                checklist_scope: checklistScope,
                checklist_country_id:
                  checklistScope === 'country_specific'
                    ? Number(checklistCountryId)
                    : null,
              }
            : { send_document_checklist_email: false }),
        },
      });
      const emailError =
        typeof created?.email_error === 'string' ? created.email_error.trim() : '';
      if (sendEmail && emailError) {
        setFormWarning(emailError);
        setMailSentConfirmation(null);
        setStatusId('');
        setPointsDiscussed('');
        setActionItems('');
        setNextFollowupDate('');
        resetChecklistPanel();
        onFollowupSaved?.();
        return;
      }
      const sentAt = (created?.checklist_email_sent_at || '').trim();
      const emailTo = (created?.checklist_email_to || '').trim();
      const mailOk =
        sendEmail &&
        created?.email_sent === true &&
        !emailError &&
        Boolean(sentAt) &&
        Boolean(emailTo);
      setStatusId('');
      setPointsDiscussed('');
      setActionItems('');
      setNextFollowupDate('');
      resetChecklistPanel();
      setFormError(null);
      setFormWarning(null);
      setMailSentConfirmation(
        mailOk ? { emailTo, sentAt } : null
      );
      onFollowupSaved?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save notes.');
    }
  };

  if (!open || !leadId) return null;

  const timeline = followupsQuery.data?.items ?? [];
  const checklistBusy =
    createMutation.isPending || checklistLevelsLoading || checklistScopeLoading;
  const canChooseLevel =
    checklistScope === 'global' ||
    (checklistScope === 'country_specific' && Boolean(checklistCountryId));

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-[60]" onClick={onClose} role="presentation" />
      <aside className="fixed top-0 right-0 h-full w-full max-w-6xl bg-card border-l border-border-subtle shadow-2xl z-[70] flex flex-col min-h-0 overflow-hidden">
        <div className="shrink-0 flex items-start justify-between gap-4 px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Counselor Notes
            </p>
            <h2 className="text-lg font-bold text-text-main truncate">
              {leadName?.trim() || `Lead #${leadId}`}
            </h2>
            <p className="text-xs text-text-muted mt-1">
              {followupsQuery.data?.total ?? 0} interaction
              {(followupsQuery.data?.total ?? 0) === 1 ? '' : 's'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-surface-bg shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="shrink-0 border-b border-border-subtle px-5 py-4 space-y-3 bg-surface-bg/30">
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1" htmlFor="followup-status">
              Follow-up Status
            </label>
            <select
              id="followup-status"
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
              value={statusId === '' ? '' : String(statusId)}
              onChange={e => handleStatusChange(e.target.value)}
              disabled={statusesQuery.isLoading || createMutation.isPending}
            >
              <option value="">Select status…</option>
              {statuses.map(status => (
                <option key={status.id} value={status.id}>
                  {status.status_heading}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              className="block text-xs font-semibold text-text-muted mb-1"
              htmlFor="followup-points"
            >
              Points Discussed
            </label>
            <textarea
              id="followup-points"
              className="w-full min-h-[96px] rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main resize-y"
              value={pointsDiscussed}
              onChange={e => setPointsDiscussed(e.target.value)}
              placeholder={
                selectedStatus
                  ? 'Edit points discussed as needed…'
                  : 'Select a status to inject a template…'
              }
              disabled={createMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3">
            <div>
              <label
                className="block text-xs font-semibold text-text-muted mb-1"
                htmlFor="followup-actions"
              >
                Action Items
              </label>
              <textarea
                id="followup-actions"
                className="w-full min-h-[96px] rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main resize-y"
                value={actionItems}
                onChange={e => setActionItems(e.target.value)}
                placeholder={
                  selectedStatus
                    ? 'Edit action items as needed…'
                    : 'Select a status to inject a template…'
                }
                disabled={createMutation.isPending}
              />
            </div>
            <div>
              <label
                className="block text-xs font-semibold text-text-muted mb-1"
                htmlFor="followup-next-date"
              >
                Next Follow-up Date
                {actionItems.trim() ? <span className="text-red-600"> *</span> : null}
              </label>
              <input
                id="followup-next-date"
                type="date"
                min={minFollowupDate}
                className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
                value={nextFollowupDate}
                onChange={e => {
                  const next = e.target.value;
                  if (next && next < todayLocalIso()) {
                    setFormError('Next Follow-up Date cannot be in the past.');
                    return;
                  }
                  setNextFollowupDate(next);
                  setFormError(null);
                }}
                required={Boolean(actionItems.trim())}
                disabled={createMutation.isPending}
              />
            </div>
          </div>

          {showChecklistPanel ? (
            <div className="rounded-xl border border-border-subtle bg-card p-4 space-y-4">
              <div>
                <p className="text-sm font-semibold text-text-main">Send Document Checklist</p>
                <p className="text-xs text-text-muted mt-0.5">
                  Choose level and scope. Email is optional and only sends when Yes is selected.
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold text-text-muted mb-2">Scope</p>
                <div className="flex flex-wrap gap-4 text-sm text-text-main">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      name="checklist-scope"
                      value="global"
                      checked={checklistScope === 'global'}
                      onChange={() => handleChecklistScopeChange('global')}
                      disabled={checklistBusy}
                    />
                    Global
                  </label>
                  <label
                    className={`inline-flex items-center gap-2 ${
                      checklistCountrySpecificAvailable ? '' : 'text-text-muted opacity-60'
                    }`}
                  >
                    <input
                      type="radio"
                      name="checklist-scope"
                      value="country_specific"
                      checked={checklistScope === 'country_specific'}
                      onChange={() => handleChecklistScopeChange('country_specific')}
                      disabled={checklistBusy || !checklistCountrySpecificAvailable}
                    />
                    {checklistCountrySpecificAvailable
                      ? 'Country-Specific'
                      : 'Country-Specific — No country-specific documents'}
                  </label>
                </div>
                {!checklistScopeLoading && !checklistCountrySpecificAvailable ? (
                  <p className="mt-1 text-xs text-text-muted">
                    No document requirements are mapped to any country.
                  </p>
                ) : null}
              </div>

              {checklistScope === 'country_specific' && checklistCountrySpecificAvailable ? (
                <div>
                  <label
                    className="block text-xs font-semibold text-text-muted mb-1"
                    htmlFor="checklist-country"
                  >
                    Country
                  </label>
                  <select
                    id="checklist-country"
                    className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm text-text-main"
                    value={checklistCountryId}
                    onChange={e => handleChecklistCountryChange(e.target.value)}
                    disabled={checklistBusy}
                  >
                    <option value="">Select a country…</option>
                    {checklistCountryOptions.map(option => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}

              <div>
                <p className="text-xs font-semibold text-text-muted mb-2">Levels</p>
                {checklistLevelsLoading || checklistScopeLoading ? (
                  <p className="text-xs text-text-muted inline-flex items-center gap-2">
                    <Loader2 size={12} className="animate-spin" />
                    Loading levels…
                  </p>
                ) : checklistScope === 'country_specific' && !checklistCountryId ? (
                  <p className="text-xs text-text-muted">
                    Select a country to see available levels.
                  </p>
                ) : catalogLevelNames.length === 0 ? (
                  <p className="text-xs text-text-muted">No program levels found.</p>
                ) : (
                  <div className="flex flex-wrap gap-x-4 gap-y-2">
                    {catalogLevelNames.map(name => {
                      const enabled = canChooseLevel && levelsWithDocsSet.has(name);
                      return (
                        <label
                          key={name}
                          className={`inline-flex items-center gap-2 text-sm ${
                            enabled ? 'text-text-main' : 'text-text-muted opacity-60'
                          }`}
                        >
                          <input
                            type="radio"
                            name="followup-checklist-level"
                            value={name}
                            checked={checklistLevel === name}
                            disabled={!enabled || checklistBusy}
                            onChange={() => {
                              setChecklistLevel(name);
                              setFormError(null);
                            }}
                          />
                          {name}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              <div>
                <p className="text-xs font-semibold text-text-muted mb-2">Send email</p>
                <div className="flex flex-wrap gap-4 text-sm text-text-main">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      name="checklist-send-email"
                      value="no"
                      checked={checklistSendEmail === 'no'}
                      onChange={() => {
                        setChecklistSendEmail('no');
                        setFormError(null);
                      }}
                      disabled={createMutation.isPending}
                    />
                    No
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      name="checklist-send-email"
                      value="yes"
                      checked={checklistSendEmail === 'yes'}
                      onChange={() => {
                        setChecklistSendEmail('yes');
                        setFormError(null);
                      }}
                      disabled={createMutation.isPending}
                    />
                    Yes
                  </label>
                </div>
                {checklistSendEmail === 'yes' ? (
                  <p className="mt-1 text-xs text-text-muted">
                    On Save Notes, the checklist PDF and any matching requirement templates are
                    emailed to this lead. A level
                    {checklistScope === 'country_specific' ? ' and country' : ''} must be selected.
                  </p>
                ) : null}
              </div>

              {checklistMetaError ? (
                <p className="text-sm text-red-700">{checklistMetaError}</p>
              ) : null}
            </div>
          ) : null}

          {formError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {formError}
            </div>
          )}
          {formWarning && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {formWarning}
            </div>
          )}
          {mailSentConfirmation && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 space-y-1">
              <p className="font-semibold">Mail sent</p>
              <p>
                <span className="font-semibold">Sent: </span>
                {formatTime(mailSentConfirmation.sentAt)}
              </p>
              <p>
                <span className="font-semibold">Email: </span>
                {mailSentConfirmation.emailTo}
              </p>
            </div>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
              onClick={() => void handleSave()}
              disabled={createMutation.isPending || !statusId}
            >
              {createMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              Save Notes
            </button>
          </div>
        </div>

        <HeadlessScrollArea className="flex-1 min-h-0 h-0" viewportClassName="px-5 py-4">
          {followupsQuery.isLoading ? (
            <div className="flex items-center justify-center py-16 text-text-muted">
              <Loader2 size={22} className="animate-spin mr-2" />
              Loading history…
            </div>
          ) : followupsQuery.isError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {followupsQuery.error instanceof Error
                ? followupsQuery.error.message
                : 'Failed to load follow-up history.'}
            </div>
          ) : timeline.length === 0 ? (
            <p className="text-sm text-text-muted italic py-8 text-center">
              No counselor notes yet. Add the first follow-up above.
            </p>
          ) : (
            <section className="space-y-3 pb-8">
              <h3 className="text-sm font-semibold text-text-main">Interaction History</h3>
              <p className="text-xs text-text-muted">Newest first</p>
              <div className="space-y-2">
                {timeline.map(item => (
                  <article
                    key={item.id}
                    className="rounded-xl border border-border-subtle bg-surface-bg/40 p-3"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-card px-2.5 py-0.5 text-[11px] font-semibold text-text-main">
                        <MessageSquareText size={12} />
                        {item.status_heading}
                      </span>
                      <span className="text-[11px] text-text-muted text-right whitespace-nowrap">
                        {formatTime(item.created_at)}
                        {item.counselor_name?.trim()
                          ? ` · ${item.counselor_name.trim()}`
                          : ''}
                      </span>
                    </div>
                    <div className="text-sm text-text-main whitespace-pre-wrap break-words space-y-2">
                      <p>
                        <span className="font-semibold">Points Discussed: </span>
                        {item.points_discussed}
                      </p>
                      {item.action_items ? (
                        <ActionItemsDisplay followupId={item.id} text={item.action_items} />
                      ) : null}
                      {item.target_completion_date ? (
                        <p>
                          <span className="font-semibold">Next Follow-up: </span>
                          {formatDateOnly(item.target_completion_date)}
                        </p>
                      ) : null}
                      {hasChecklistEmailReceipt(item) ? (
                        <ChecklistSentBlock item={item} />
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
        </HeadlessScrollArea>
      </aside>
    </>
  );
};

export default CounselorFollowupDrawer;
