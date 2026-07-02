import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  ArrowLeft,
  Bot,
  Expand,
  Mail,
  MessageCircle,
  Minimize2,
  UserPlus,
  Users,
} from 'lucide-react';
import type { ProspectDetail, ProspectsSummary } from '../../types/prospect';
import type { ProspectDetailTab } from '../../utils/prospectsUrl';
import {
  ACTOR_THEME,
  buildInteractionGroups,
  formatProspectDate,
  formatProspectTime,
  platformBadgeStyle,
} from '../../utils/prospectMessages';
import { useUpdateProspectNotes, useUpdateProspectStatus } from '../../hooks/useProspects';
import { useStatusDefinitions, useUpdateStudentStatus } from '../../hooks/useStudentStatus';
import StudentJourneyPanel from '../StudentJourneyPanel';
import { categoryBadgeClass } from '../../utils/statusBadges';

type ProspectDetailPanelProps = {
  leadId: number | null;
  detail?: ProspectDetail;
  isLoading: boolean;
  summary?: ProspectsSummary;
  activeTab: ProspectDetailTab;
  onTabChange: (tab: ProspectDetailTab) => void;
  onBack?: () => void;
  showBackButton?: boolean;
  isFocusMode?: boolean;
  onToggleFocus?: () => void;
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
  summary,
  activeTab,
  onTabChange,
  onBack,
  showBackButton = false,
  isFocusMode = false,
  onToggleFocus,
}: ProspectDetailPanelProps) {
  const [notesDraft, setNotesDraft] = useState('');
  const [pipelineStatusId, setPipelineStatusId] = useState('');
  const [pipelineComments, setPipelineComments] = useState('');
  const [journeyOpen, setJourneyOpen] = useState(false);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const statusMutation = useUpdateProspectStatus();
  const notesMutation = useUpdateProspectNotes(leadId);
  const { data: statusDefinitionsData } = useStatusDefinitions();
  const pipelineStatusMutation = useUpdateStudentStatus(leadId);

  const statusDefinitions = statusDefinitionsData?.items ?? [];
  const selectedPipelineStatus = useMemo(
    () => statusDefinitions.find(item => String(item.id) === pipelineStatusId),
    [pipelineStatusId, statusDefinitions]
  );

  useEffect(() => {
    setJourneyOpen(false);
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
  const requiresOverrideComment = useMemo(() => {
    if (!pipelineStatusId || !detail?.status_definition_id) return false;
    const selectedId = Number(pipelineStatusId);
    if (selectedId === detail.status_definition_id) return false;
    return currentPipelineDefinition?.next_stage_id !== selectedId;
  }, [pipelineStatusId, detail?.status_definition_id, currentPipelineDefinition, detail]);

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
      <section className="prospects-detail-panel prospects-detail-panel--empty">
        <div className="prospects-welcome">
          <div className="prospects-welcome__icon">👥</div>
          <h3>Select a lead to view details</h3>
          <p>Choose a prospect from the list to review their profile, messages, and notes.</p>
          {summary ? (
            <div className="prospects-welcome__stats">
              <div>
                <strong>{summary.leads_today}</strong>
                <span>Leads today</span>
              </div>
              <div>
                <strong>{summary.total_leads}</strong>
                <span>Total leads</span>
              </div>
              <div>
                <strong>{summary.pending_handoff}</strong>
                <span>Pending handoff</span>
              </div>
              <div>
                <strong>{summary.meta_leads}</strong>
                <span>Meta leads</span>
              </div>
            </div>
          ) : null}
        </div>
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

  const handlePipelineStatusSave = () => {
    if (!pipelineStatusId || !detail) return;
    if (requiresOverrideComment && !pipelineComments.trim()) {
      window.alert('Please add a comment explaining this non-standard status change.');
      return;
    }
    pipelineStatusMutation.mutate({
      status_definition_id: Number(pipelineStatusId),
      comments: pipelineComments.trim() || undefined,
    });
  };

  const handleMessage = () => {
    if (phone && phone !== '—') {
      window.open(`https://wa.me/${phone.replace(/\D/g, '')}`, '_blank', 'noopener,noreferrer');
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
            <div>
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
            </div>
          </div>

          <div className="prospects-detail-panel__actions">
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
            <button type="button" className="prospects-action-btn" onClick={handleMessage}>
              <MessageCircle size={15} />
              Message
            </button>
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
      </div>

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
            <label className="prospects-pipeline-status__label" htmlFor="pipeline-status-select">
              Update status
            </label>
            <select
              id="pipeline-status-select"
              value={pipelineStatusId}
              onChange={event => setPipelineStatusId(event.target.value)}
              disabled={pipelineStatusMutation.isPending || statusDefinitions.length === 0}
            >
              <option value="">Select pipeline status</option>
              {statusDefinitions.map(stage => (
                <option key={stage.id} value={stage.id}>
                  {stage.stage_name}
                </option>
              ))}
            </select>
            {selectedPipelineStatus?.description ? (
              <p className="prospects-pipeline-status__description">{selectedPipelineStatus.description}</p>
            ) : (
              <p className="prospects-pipeline-status__description prospects-pipeline-status__description--muted">
                Select a status to view its guidance.
              </p>
            )}
            <textarea
              value={pipelineComments}
              onChange={event => setPipelineComments(event.target.value)}
              placeholder={
                requiresOverrideComment
                  ? 'Required: explain why this status bypasses the standard workflow...'
                  : 'Optional note for this status change...'
              }
              rows={3}
            />
            <button
              type="button"
              className="prospects-action-btn prospects-action-btn--primary"
              onClick={handlePipelineStatusSave}
              disabled={!pipelineStatusId || pipelineStatusMutation.isPending}
            >
              {pipelineStatusMutation.isPending ? 'Saving...' : 'Save pipeline status'}
            </button>
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
    </section>

    <StudentJourneyPanel
      open={journeyOpen}
      studentId={leadId}
      studentName={detail.full_name || detail.name}
      onClose={() => setJourneyOpen(false)}
    />
    </>
  );
}
