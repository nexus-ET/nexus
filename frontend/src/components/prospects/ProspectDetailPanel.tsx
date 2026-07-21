import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  ArrowLeft,
  Bot,
  Expand,
  Mail,
  MessageCircle,
  MessageSquare,
  Minimize2,
  Sparkles,
  UserPlus,
  Users,
} from 'lucide-react';
import type { ProspectDetail } from '../../types/prospect';
import type { ProspectDetailTab } from '../../utils/prospectsUrl';
import {
  ACTOR_THEME,
  buildInteractionGroups,
  formatProspectDate,
  formatProspectTime,
  platformBadgeStyle,
} from '../../utils/prospectMessages';
import { useUpdateProspectNotes, useUpdateProspectStatus, useLeadProfileBooking } from '../../hooks/useProspects';
import {
  useStatusDefinitions,
  useUpdateStudentStatus,
  useValidTransitions,
  ValidTransitionOption,
} from '../../hooks/useStudentStatus';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../utils/api';
import type { CandidateProfile } from '../../types/candidateProfile';
import { formatProfileFullName } from '../../utils/profilePulse';
import { phoneLocalToDigits } from '../../utils/phoneCountry';
import StudentJourneyPanel from '../StudentJourneyPanel';
import InteractionLogDrawer from '../InteractionLogDrawer';
import CounsellingSessionModal from '../CounsellingSessionModal';
import CandidateProfilePanel from '../CandidateProfilePanel';
import DigitalPresenceAdminSection from '../DigitalPresenceAdminSection';
import AiActivePulseBoard, { type PulseLead } from '../AiActivePulseBoard';
import { categoryBadgeClass } from '../../utils/statusBadges';

type ProspectDetailPanelProps = {
  leadId: number | null;
  detail?: ProspectDetail;
  isLoading: boolean;
  pulseLeads?: PulseLead[];
  isPulseLoading?: boolean;
  onSelectPulseLead?: (leadId: number) => void;
  activeTab: ProspectDetailTab;
  onTabChange: (tab: ProspectDetailTab) => void;
  onBack?: () => void;
  showBackButton?: boolean;
  isFocusMode?: boolean;
  onToggleFocus?: () => void;
  studentProfileTabs?: boolean;
};

const STATUS_OPTIONS = [
  { key: 'ai-active', label: 'AI Active', icon: Bot },
  { key: 'handoff', label: 'Handoff', icon: Users },
  { key: 'archive', label: 'Archive', icon: Archive },
];

const TAB_LABELS: Record<ProspectDetailTab, string> = {
  overview: 'Overview',
  history: 'History',
  notes: 'Notes',
};

function parseMetaFields(academicSummary?: string | null): Record<string, string> {
  if (!academicSummary) return {};
  const fieldsPart = academicSummary.split('Fields:').pop();
  if (!fieldsPart) return {};

  const parsed: Record<string, string> = {};
  fieldsPart.split(',').forEach(pair => {
    const [rawKey, ...rest] = pair.split('=');
    const key = rawKey?.trim().toLowerCase();
    const value = rest.join('=').trim();
    if (key && value) parsed[key] = value;
  });
  return parsed;
}

function humanizeFieldKey(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function resolveMetaFields(detail: ProspectDetail): Record<string, string> {
  const fromJson = detail.additional_data;
  if (fromJson && Object.keys(fromJson).length > 0) {
    return fromJson;
  }
  return parseMetaFields(detail.academic_summary);
}

export default function ProspectDetailPanel({
  leadId,
  detail,
  isLoading,
  pulseLeads = [],
  isPulseLoading = false,
  onSelectPulseLead,
  activeTab,
  onTabChange,
  onBack,
  showBackButton = false,
  isFocusMode = false,
  onToggleFocus,
  studentProfileTabs = false,
}: ProspectDetailPanelProps) {
  const [notesDraft, setNotesDraft] = useState('');
  const [pipelineStatusId, setPipelineStatusId] = useState('');
  const [pipelineComments, setPipelineComments] = useState('');
  const [expressTargetId, setExpressTargetId] = useState('');
  const [revertTargetId, setRevertTargetId] = useState('');
  const [journeyOpen, setJourneyOpen] = useState(false);
  const [interactionBookingId, setInteractionBookingId] = useState<number | null>(null);
  const [sessionOpen, setSessionOpen] = useState(false);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const statusMutation = useUpdateProspectStatus();
  const notesMutation = useUpdateProspectNotes(leadId);
  const { data: statusDefinitionsData } = useStatusDefinitions();
  const { data: validTransitions } = useValidTransitions(leadId);
  const pipelineStatusMutation = useUpdateStudentStatus(leadId);
  const profileBookingQuery = useLeadProfileBooking(leadId, studentProfileTabs);
  const candidateProfileQuery = useQuery({
    queryKey: ['bookings', 'candidate-profile-header', profileBookingQuery.data?.id],
    queryFn: () =>
      apiFetch(`bookings/mine/${profileBookingQuery.data!.id}/profile`) as Promise<{
        profile: CandidateProfile;
      }>,
    enabled: studentProfileTabs && Boolean(profileBookingQuery.data?.id),
    staleTime: 60_000,
  });

  const profileFullName = useMemo(
    () => formatProfileFullName(candidateProfileQuery.data?.profile),
    [candidateProfileQuery.data?.profile]
  );
  const metaReceivedName = useMemo(() => {
    if (!detail) return '';
    return (detail.full_name || detail.name || '').trim();
  }, [detail]);
  const counsellingDisplayName = profileFullName || metaReceivedName || 'Student';

  const statusDefinitions = statusDefinitionsData?.items ?? [];
  const forwardTransitions = validTransitions?.forward ?? [];
  const expressTransitions = useMemo(
    () => (validTransitions?.express ?? []).filter(item => item.can_trigger),
    [validTransitions?.express]
  );
  const backwardTransitions = useMemo(
    () => (validTransitions?.backward ?? []).filter(item => item.can_trigger),
    [validTransitions?.backward]
  );
  const relaunchTransitions = useMemo(
    () => (validTransitions?.relaunch ?? []).filter(item => item.can_trigger),
    [validTransitions?.relaunch]
  );
  const revertTransitions = useMemo(
    () => [...backwardTransitions, ...relaunchTransitions],
    [backwardTransitions, relaunchTransitions]
  );
  const nextForward = forwardTransitions[0] ?? null;

  useEffect(() => {
    setJourneyOpen(false);
    setInteractionBookingId(null);
    setSessionOpen(false);
  }, [leadId]);

  useEffect(() => {
    setNotesDraft(detail?.intake_context || '');
  }, [leadId, detail?.intake_context]);

  const interactionGroups = useMemo(
    () => buildInteractionGroups(detail?.messages || detail?.chat_history, detail?.academic_summary),
    [detail]
  );

  const currentPipelineDefinition = useMemo(
    () => statusDefinitions.find(item => item.id === detail?.status_definition_id),
    [detail?.status_definition_id, statusDefinitions]
  );
  const selectedRevertTransition = useMemo(
    () => revertTransitions.find(item => String(item.to_status_id) === revertTargetId),
    [revertTargetId, revertTransitions]
  );
  const selectedExpressTransition = useMemo(
    () => expressTransitions.find(item => String(item.to_status_id) === expressTargetId),
    [expressTargetId, expressTransitions]
  );
  const requiresRevertComment = Boolean(selectedRevertTransition?.requires_comment);

  useEffect(() => {
    setExpressTargetId('');
    setRevertTargetId('');
    setPipelineComments('');
  }, [leadId, detail?.status_definition_id]);

  useEffect(() => {
    if (detail?.status_definition_id) {
      setPipelineStatusId(String(detail.status_definition_id));
    }
  }, [leadId, detail?.status_definition_id]);

  useEffect(() => {
    if (activeTab !== 'history' || !historyRef.current) return;
    historyRef.current.scrollTop = historyRef.current.scrollHeight;
  }, [activeTab, interactionGroups, leadId]);

  if (!leadId) {
    return (
      <section className="prospects-detail-panel prospects-detail-panel--pulse">
        <AiActivePulseBoard
          mode="prospects"
          leads={pulseLeads}
          isLoading={isPulseLoading}
          onSelectLead={leadId => onSelectPulseLead?.(leadId)}
        />
      </section>
    );
  }

  if (isLoading && !detail) {
    return (
      <section className="prospects-detail-panel prospects-detail-panel--empty">
        <div className="prospects-empty">Loading lead details...</div>
      </section>
    );
  }

  if (!detail) {
    return (
      <section className="prospects-detail-panel prospects-detail-panel--empty">
        <div className="prospects-empty">Unable to load this lead.</div>
      </section>
    );
  }

  const metaFields = resolveMetaFields(detail);
  const additionalFieldEntries = Object.entries(metaFields);
  const phone = detail.phone_number || detail.phone || '—';
  const badgeStyle = platformBadgeStyle(detail.platform_badge);

  const handleStatus = (status: string) => {
    statusMutation.mutate({ leadId: detail.id, status });
  };

  const handleSaveNotes = () => {
    notesMutation.mutate(notesDraft);
  };

  const applyPipelineTransition = (
    option: ValidTransitionOption,
    comments?: string
  ) => {
    pipelineStatusMutation.mutate(
      {
        status_definition_id: option.to_status_id,
        transition_type: option.transition_type,
        comments: comments?.trim() || undefined,
      },
      {
        onSuccess: () => {
          setPipelineComments('');
          setExpressTargetId('');
          setRevertTargetId('');
        },
      }
    );
  };

  const handleForwardStep = () => {
    if (!nextForward) return;
    applyPipelineTransition(nextForward, pipelineComments);
  };

  const handleExpressJump = () => {
    if (!selectedExpressTransition) return;
    applyPipelineTransition(selectedExpressTransition, pipelineComments);
  };

  const handleRevertUpdate = () => {
    if (!selectedRevertTransition) return;
    if (requiresRevertComment && !pipelineComments.trim()) {
      window.alert('Please add a comment explaining this revert or relaunch.');
      return;
    }
    applyPipelineTransition(selectedRevertTransition, pipelineComments);
  };

  const handleMessage = () => {
    if (phone && phone !== '—') {
      window.open(`https://wa.me/${phoneLocalToDigits(phone)}`, '_blank', 'noopener,noreferrer');
      return;
    }
    if (detail.email) {
      window.location.href = `mailto:${detail.email}`;
    }
  };

  return (
    <>
    <section className={`prospects-detail-panel${isFocusMode ? ' prospects-detail-panel--focus' : ''}`}>
      <div className="prospects-detail-panel__sticky">
        <div className="prospects-detail-panel__action-bar">
          <div className="prospects-detail-panel__identity">
            {showBackButton ? (
              <button type="button" className="prospects-back-btn" onClick={onBack}>
                <ArrowLeft size={16} />
                Back
              </button>
            ) : null}
            <div className={studentProfileTabs ? 'min-w-0 flex-1' : undefined}>
              {studentProfileTabs ? (
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="text-xl font-bold text-text-main leading-tight">
                      {counsellingDisplayName}
                    </h3>
                    {!profileFullName && metaReceivedName ? (
                      <p className="text-[11px] text-text-muted mt-0.5">Meta received name</p>
                    ) : null}
                    <div className="prospects-detail-panel__chips mt-1.5">
                      {detail.platform_badge ? (
                        <span className="prospects-chip" style={badgeStyle}>
                          {detail.platform_badge}
                        </span>
                      ) : null}
                      <span className="prospects-chip prospects-chip--muted">
                        {detail.stage || detail.status}
                      </span>
                    </div>
                  </div>
                  {detail.status_stage_name ? (
                    <span
                      className={`inline-flex shrink-0 items-center rounded-full border px-3 py-1.5 text-sm font-bold leading-tight text-right ${categoryBadgeClass(
                        detail.status_category
                      )}`}
                    >
                      {detail.status_stage_name}
                    </span>
                  ) : null}
                </div>
              ) : (
                <>
                  <h3>{detail.full_name || detail.name}</h3>
                  <div className="prospects-detail-panel__chips">
                    {detail.platform_badge ? (
                      <span className="prospects-chip" style={badgeStyle}>
                        {detail.platform_badge}
                      </span>
                    ) : null}
                    <span className="prospects-chip prospects-chip--muted">
                      {detail.stage || detail.status}
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="prospects-detail-panel__actions">
            {onBack ? (
              <button
                type="button"
                className="prospects-action-btn"
                onClick={onBack}
                title="Back to prospects pulse overview"
              >
                Overview
              </button>
            ) : null}
            {onToggleFocus ? (
              <button
                type="button"
                className="prospects-action-btn prospects-action-btn--icon"
                onClick={onToggleFocus}
                title={isFocusMode ? 'Show list' : 'Focus view'}
              >
                {isFocusMode ? <Minimize2 size={15} /> : <Expand size={15} />}
              </button>
            ) : null}
            {studentProfileTabs ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    const bookingId = profileBookingQuery.data?.id;
                    if (bookingId) setInteractionBookingId(bookingId);
                  }}
                  disabled={!profileBookingQuery.data?.id || profileBookingQuery.isLoading}
                  className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-accent/20 disabled:opacity-60"
                >
                  <MessageSquare size={14} />
                  View Interaction
                </button>
                <button
                  type="button"
                  onClick={() => setSessionOpen(true)}
                  disabled={!profileBookingQuery.data?.id || profileBookingQuery.isLoading}
                  className="inline-flex items-center gap-1 rounded-lg border border-violet-300 bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-900 hover:bg-violet-100 disabled:opacity-60"
                >
                  <Sparkles size={14} />
                  Session
                </button>
              </>
            ) : (
              <button
                type="button"
                className="prospects-action-btn"
                onClick={handleMessage}
              >
                <MessageCircle size={15} />
                Message
              </button>
            )}
            <button type="button" className="prospects-action-btn" onClick={() => setJourneyOpen(true)}>
              View Journey
            </button>
            <button type="button" className="prospects-action-btn" onClick={() => handleStatus('handoff')}>
              <UserPlus size={15} />
              Assign
            </button>
            <div className="prospects-action-dropdown">
              <span>Update Status</span>
              <div className="prospects-action-dropdown__menu">
                {STATUS_OPTIONS.map(option => {
                  const Icon = option.icon;
                  return (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => handleStatus(option.key)}
                      disabled={statusMutation.isPending}
                    >
                      <Icon size={14} />
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {!studentProfileTabs ? (
          <div className="prospects-detail-panel__tabs">
            {(Object.keys(TAB_LABELS) as ProspectDetailTab[]).map(tab => (
              <button
                key={tab}
                type="button"
                className={activeTab === tab ? 'is-active' : ''}
                onClick={() => onTabChange(tab)}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {studentProfileTabs ? (
        profileBookingQuery.isLoading ? (
          <div className="prospects-empty flex-1">Loading student profile...</div>
        ) : profileBookingQuery.data ? (
          <CandidateProfilePanel
            key={profileBookingQuery.data.id}
            booking={profileBookingQuery.data}
            variant="embedded"
          />
        ) : (
          <div className="prospects-empty flex-1">
            {profileBookingQuery.error instanceof Error
              ? profileBookingQuery.error.message
              : 'No counselling booking is available for this student on your account.'}
          </div>
        )
      ) : (
      <div className="prospects-detail-panel__body custom-scroll-region">
        <div className={`prospects-tab-pane${activeTab === 'overview' ? ' is-active' : ''}`}>
          <div className="prospects-pipeline-status">
            <div className="prospects-pipeline-status__header">
              <h4>Pipeline status</h4>
              {detail.status_stage_name ? (
                <span
                  className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${categoryBadgeClass(
                    detail.status_category
                  )}`}
                >
                  {detail.status_stage_name}
                </span>
              ) : null}
            </div>

            {nextForward ? (
              <div className="prospects-pipeline-status__section">
                <p className="prospects-pipeline-status__label">Next step</p>
                <p className="prospects-pipeline-status__description">
                  {nextForward.description || `Advance to ${nextForward.stage_name}.`}
                </p>
                <button
                  type="button"
                  className="prospects-action-btn prospects-action-btn--primary"
                  onClick={handleForwardStep}
                  disabled={pipelineStatusMutation.isPending}
                >
                  {pipelineStatusMutation.isPending ? 'Saving...' : `Next: ${nextForward.stage_name}`}
                </button>
              </div>
            ) : (
              <p className="prospects-pipeline-status__description prospects-pipeline-status__description--muted">
                No standard forward step is configured from this stage.
              </p>
            )}

            {(validTransitions?.express ?? []).length > 0 ? (
              <div className="prospects-pipeline-status__section">
                <label className="prospects-pipeline-status__label" htmlFor="express-status-select">
                  Jump to…
                </label>
                <select
                  id="express-status-select"
                  value={expressTargetId}
                  onChange={event => setExpressTargetId(event.target.value)}
                  disabled={pipelineStatusMutation.isPending || expressTransitions.length === 0}
                >
                  <option value="">
                    {expressTransitions.length === 0
                      ? 'Express jumps require Student Manager access'
                      : 'Select express destination'}
                  </option>
                  {expressTransitions.map(option => (
                    <option key={`express-${option.to_status_id}`} value={option.to_status_id}>
                      {option.stage_name}
                    </option>
                  ))}
                </select>
                {selectedExpressTransition?.description ? (
                  <p className="prospects-pipeline-status__description">
                    {selectedExpressTransition.description}
                  </p>
                ) : null}
                <button
                  type="button"
                  className="prospects-action-btn"
                  onClick={handleExpressJump}
                  disabled={!expressTargetId || pipelineStatusMutation.isPending}
                >
                  Express jump
                </button>
              </div>
            ) : null}

            {revertTransitions.length === 0 ? (
              <textarea
                value={pipelineComments}
                onChange={event => setPipelineComments(event.target.value)}
                placeholder="Optional note for the next forward or express step..."
                rows={2}
              />
            ) : null}

            {revertTransitions.length > 0 ? (
              <details className="prospects-pipeline-status__revert">
                <summary>Revert / update</summary>
                <label className="prospects-pipeline-status__label" htmlFor="revert-status-select">
                  Choose target stage
                </label>
                <select
                  id="revert-status-select"
                  value={revertTargetId}
                  onChange={event => setRevertTargetId(event.target.value)}
                  disabled={pipelineStatusMutation.isPending}
                >
                  <option value="">Select stage</option>
                  {revertTransitions.map(option => (
                    <option key={`${option.transition_type}-${option.to_status_id}`} value={option.to_status_id}>
                      {option.stage_name}
                    </option>
                  ))}
                </select>
                <textarea
                  value={pipelineComments}
                  onChange={event => setPipelineComments(event.target.value)}
                  placeholder={
                    requiresRevertComment
                      ? 'Required: explain why you are reverting or relaunching this student...'
                      : 'Optional note for this status change...'
                  }
                  rows={3}
                />
                <button
                  type="button"
                  className="prospects-action-btn"
                  onClick={handleRevertUpdate}
                  disabled={!revertTargetId || pipelineStatusMutation.isPending}
                >
                  {pipelineStatusMutation.isPending ? 'Saving...' : 'Apply revert / update'}
                </button>
              </details>
            ) : null}

            {currentPipelineDefinition?.description ? (
              <p className="prospects-pipeline-status__description prospects-pipeline-status__description--muted">
                Current stage guidance: {currentPipelineDefinition.description}
              </p>
            ) : null}
          </div>

          <div className="prospects-profile-grid">
            <div>
              <span>Name</span>
              <strong>{detail.full_name || detail.name || '—'}</strong>
            </div>
            <div>
              <span>Email</span>
              <strong>{detail.email || '—'}</strong>
            </div>
            <div>
              <span>Phone</span>
              <strong>{phone}</strong>
            </div>
            <div>
              <span>Location</span>
              <strong>{detail.current_location || metaFields.city || metaFields.country || '—'}</strong>
            </div>
            <div>
              <span>Preferred country</span>
              <strong>{detail.preferred_country || metaFields.preferred_country || '—'}</strong>
            </div>
            <div>
              <span>Received</span>
              <strong>{formatProspectDate(detail.created_at || detail.updated_at)}</strong>
            </div>
            {detail.meta_campaign_name ? (
              <div className="prospects-profile-grid__wide">
                <span>Campaign</span>
                <strong>{detail.meta_campaign_name}</strong>
              </div>
            ) : null}
            {detail.meta_form_id ? (
              <div>
                <span>Form ID</span>
                <strong className="font-mono text-sm">{detail.meta_form_id}</strong>
              </div>
            ) : null}
            {additionalFieldEntries.length > 0 ? (
              <div className="prospects-profile-grid__wide">
                <span>Form responses</span>
                <div className="prospects-profile-grid prospects-profile-grid--nested">
                  {additionalFieldEntries.map(([key, value]) => (
                    <div key={key}>
                      <span>{humanizeFieldKey(key)}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {detail.academic_summary ? (
              <div className="prospects-profile-grid__wide">
                <span>Lead summary</span>
                <p>{detail.academic_summary}</p>
              </div>
            ) : null}
            {leadId ? <DigitalPresenceAdminSection leadId={leadId} /> : null}
          </div>
        </div>

        <div
          ref={historyRef}
          className={`prospects-tab-pane prospects-history prospects-history--chat${
            activeTab === 'history' ? ' is-active' : ''
          }`}
        >
          {Object.keys(interactionGroups).length === 0 ? (
            <div className="prospects-empty">
              <Mail size={18} />
              <p>No WhatsApp/Twilio messages logged yet.</p>
            </div>
          ) : (
            Object.entries(interactionGroups).map(([label, messages]) => (
              <div key={label} className="prospects-history__group">
                <div className="prospects-history__divider">
                  <span>{label}</span>
                </div>
                {messages.map((msg, index) => {
                  const theme = ACTOR_THEME[msg.actor];
                  const outbound = msg.actor !== 'candidate';
                  return (
                    <div
                      key={String(msg.id ?? `${label}-${index}`)}
                      className={`prospects-history__bubble-row${outbound ? ' is-outbound' : ''}`}
                    >
                      <div
                        className="prospects-history__bubble"
                        style={{ backgroundColor: theme.bg, color: theme.textColor }}
                      >
                        <span style={{ color: theme.labelColor }}>{theme.label}</span>
                        <p>{msg.text}</p>
                        {msg.created_at ? <small>{formatProspectTime(msg.created_at)}</small> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className={`prospects-tab-pane${activeTab === 'notes' ? ' is-active' : ''}`}>
          <div className="prospects-notes">
            <p className="prospects-notes__hint">
              Internal team notes for this lead. Saved to Nexus and visible to your counselling team.
            </p>
            <textarea
              value={notesDraft}
              onChange={event => setNotesDraft(event.target.value)}
              placeholder="Add follow-up notes, call outcomes, or next steps..."
              rows={12}
            />
            <button
              type="button"
              className="prospects-action-btn prospects-action-btn--primary"
              onClick={handleSaveNotes}
              disabled={notesMutation.isPending}
            >
              {notesMutation.isPending ? 'Saving...' : 'Save notes'}
            </button>
          </div>
        </div>
      </div>
      )}
    </section>

    <StudentJourneyPanel
      open={journeyOpen}
      studentId={leadId}
      studentName={detail.full_name || detail.name}
      onClose={() => setJourneyOpen(false)}
    />

    <InteractionLogDrawer
      open={interactionBookingId !== null}
      bookingId={interactionBookingId}
      onClose={() => setInteractionBookingId(null)}
    />

    {studentProfileTabs && profileBookingQuery.data ? (
      <CounsellingSessionModal
        open={sessionOpen}
        bookingId={profileBookingQuery.data.id}
        candidateName={profileBookingQuery.data.candidate_name}
        dateLabel={profileBookingQuery.data.date_label}
        timeLabel={profileBookingQuery.data.time_label}
        onClose={() => setSessionOpen(false)}
        onStatusUpdated={() => {
          void profileBookingQuery.refetch();
        }}
      />
    ) : null}
    </>
  );
}
