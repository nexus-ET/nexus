import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Clock3,
  Globe2,
  GraduationCap,
  MessageCircleReply,
  Sparkles,
  UserPlus,
} from 'lucide-react';
import HeadlessScrollArea from './HeadlessScrollArea';

export interface PulseLead {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  phone_number?: string;
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  target_degree?: string | null;
  target_major?: string | null;
  current_location?: string | null;
  intake_step?: string;
  intake_step_label?: string;
  intake_complete?: boolean;
  study_interest_complete?: boolean;
  english_test_scores?: string | null;
  gre_score?: string | null;
  gmat_score?: string | null;
  test_scores?: string | null;
  wants_consultation_call?: boolean | null;
  consultation_scheduled_at?: string | null;
  consultation_session_date?: string | null;
  consultation_session_time?: string | null;
  assigned_counsellor_name?: string | null;
  appointment_status?: string | null;
  status?: string;
  updated_at?: string;
  latest_interaction_time?: string;
  unread_count?: number;
  total_messages_received?: number;
  has_ai_messages?: boolean;
  has_messages?: boolean;
  messages?: { sender?: string; created_at?: string; senderName?: string }[];
}

export type PulseBoardMode = 'ai-active' | 'handoffs' | 'prospects';

interface AiActivePulseBoardProps {
  leads: PulseLead[];
  isLoading?: boolean;
  onSelectLead: (leadId: number) => void;
  /** Defaults to AI Active copy; use `handoffs` / `prospects` for other queues. */
  mode?: PulseBoardMode;
  kicker?: string;
  title?: string;
  subtitle?: string;
  queueLabel?: string;
  emptyTitle?: string;
  emptySubtitle?: string;
  loadingLabel?: string;
}

const MODE_COPY: Record<
  PulseBoardMode,
  {
    kicker: string;
    title: string;
    subtitle: string;
    queueLabel: string;
    emptyTitle: string;
    emptySubtitle: string;
    loadingLabel: string;
  }
> = {
  'ai-active': {
    kicker: 'Live intake pulse',
    title: "Who's moving right now",
    subtitle: 'Hover a candidate for full intake details. Tap to open their AI conversation.',
    queueLabel: 'in AI Active',
    emptyTitle: 'No AI Active candidates yet',
    emptySubtitle: 'When leads enter the AI queue, living clusters will appear here.',
    loadingLabel: 'Mapping your AI Active pulse...',
  },
  handoffs: {
    kicker: 'Handoff pulse',
    title: 'Who needs a human right now',
    subtitle: 'Hover a candidate for full details. Tap to open their escalated conversation.',
    queueLabel: 'in Handoffs',
    emptyTitle: 'No handoff candidates yet',
    emptySubtitle: 'When leads escalate for human help, living clusters will appear here.',
    loadingLabel: 'Mapping your handoff pulse...',
  },
  prospects: {
    kicker: 'Prospects pulse',
    title: "Who's in the pipeline right now",
    subtitle: 'Hover a candidate for full intake details. Tap to open their prospect profile.',
    queueLabel: 'in view',
    emptyTitle: 'No prospects match this view',
    emptySubtitle: 'Adjust filters or wait for new leads — living clusters will appear here.',
    loadingLabel: 'Mapping your prospects pulse...',
  },
};

interface NamedCluster {
  key: string;
  label: string;
  leads: PulseLead[];
}

interface CountryProgramCluster {
  key: string;
  label: string;
  leads: PulseLead[];
  programs: NamedCluster[];
}

interface PreviewState {
  lead: PulseLead;
  left: number;
  top: number;
}

const COUNTRY_PALETTE = ['#322f86', '#4a47a0', '#0077b6', '#0096c7', '#00b4d8', '#48cae4'];
const PROGRAM_PALETTE = ['#386fa4', '#3d5a80', '#5c7cfa', '#748ffc', '#91a7ff', '#bac8ff'];
const TBD_ACCENT = '#64748b';
const CLUSTER_PREVIEW_LIMIT = 6;
const POPUP_WIDTH = 460;
const POPUP_MAX_HEIGHT = 640;

function timestampMs(value?: string | null): number {
  if (!value) return 0;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? 0 : ms;
}

function initials(name?: string | null): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

const TBD_COUNTRY = 'Country TBD';
const TBD_PROGRAM = 'Program TBD';

function normalizeClusterLabel(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ');
}

function isTbdClusterLabel(label: string): boolean {
  return label === TBD_COUNTRY || label === TBD_PROGRAM;
}

function programLabel(lead: PulseLead): string {
  const named =
    lead.target_program?.trim() ||
    lead.target_degree?.trim() ||
    lead.target_major?.trim() ||
    lead.preferred_course?.trim() ||
    '';
  return named ? normalizeClusterLabel(named) : TBD_PROGRAM;
}

function countryLabel(lead: PulseLead): string {
  // Target destination only — not current_location (home/city), which admins confuse with study country.
  const preferred = lead.preferred_country?.trim();
  return preferred ? normalizeClusterLabel(preferred) : TBD_COUNTRY;
}

function phoneOf(lead: PulseLead): string {
  return lead.phone || lead.phone_number || '';
}

function lastActivityMs(lead: PulseLead): number {
  const fromMessages = (lead.messages || [])
    .map(msg => timestampMs(msg.created_at))
    .reduce((max, value) => Math.max(max, value), 0);
  return Math.max(
    timestampMs(lead.latest_interaction_time),
    timestampMs(lead.updated_at),
    fromMessages
  );
}

/** True only when the candidate has actually replied (inbound chat), not merely updated/created. */
function hasCandidateReply(lead: PulseLead): boolean {
  if ((lead.unread_count || 0) > 0) return true;
  if ((lead.total_messages_received || 0) > 0) return true;
  return (lead.messages || []).some(msg => {
    const sender = (msg.sender || '').toLowerCase();
    return sender === 'candidate' || sender === 'student';
  });
}

function lastReplyMs(lead: PulseLead): number {
  const fromInbound = (lead.messages || [])
    .filter(msg => {
      const sender = (msg.sender || '').toLowerCase();
      return sender === 'candidate' || sender === 'student';
    })
    .map(msg => timestampMs(msg.created_at))
    .reduce((max, value) => Math.max(max, value), 0);
  if (fromInbound > 0) return fromInbound;
  if (hasCandidateReply(lead)) {
    return Math.max(timestampMs(lead.latest_interaction_time), timestampMs(lead.updated_at));
  }
  return 0;
}

function buildClusters(
  leads: PulseLead[],
  getLabel: (lead: PulseLead) => string
): NamedCluster[] {
  // key → { display label, leads }. Case-insensitive merge so "france" and "France" stay one bucket.
  const map = new Map<string, { label: string; leads: PulseLead[] }>();
  leads.forEach(lead => {
    const label = getLabel(lead);
    const key = label.toLowerCase();
    const existing = map.get(key);
    if (existing) {
      existing.leads.push(lead);
      return;
    }
    map.set(key, { label, leads: [lead] });
  });
  return Array.from(map.entries())
    .map(([key, group]) => ({
      key,
      label: group.label,
      leads: group.leads.sort((a, b) => lastActivityMs(b) - lastActivityMs(a)),
    }))
    .sort((a, b) => {
      // Keep TBD / catch-all buckets visible at the bottom so named countries aren't buried —
      // but never drop them (admins must still see every lead).
      const aTbd = isTbdClusterLabel(a.label) ? 1 : 0;
      const bTbd = isTbdClusterLabel(b.label) ? 1 : 0;
      if (aTbd !== bTbd) return aTbd - bTbd;
      return b.leads.length - a.leads.length || a.label.localeCompare(b.label);
    });
}

function clusterLeadCount(clusters: NamedCluster[]): number {
  return clusters.reduce((sum, cluster) => sum + cluster.leads.length, 0);
}

function buildCountryProgramClusters(leads: PulseLead[]): CountryProgramCluster[] {
  return buildClusters(leads, countryLabel).map(country => ({
    ...country,
    programs: buildClusters(country.leads, programLabel),
  }));
}

function relativeLabel(ms: number): string {
  if (!ms) return 'No activity';
  const delta = Date.now() - ms;
  const mins = Math.floor(delta / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function displayValue(value?: string | null | boolean): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const cleaned = (value || '').toString().trim();
  return cleaned || '—';
}

function placePopup(anchor: DOMRect): { left: number; top: number } {
  const margin = 12;
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;

  let left = anchor.right + margin;
  if (left + POPUP_WIDTH > viewportW - margin) {
    left = anchor.left - POPUP_WIDTH - margin;
  }
  if (left < margin) {
    left = Math.max(margin, Math.min(anchor.left, viewportW - POPUP_WIDTH - margin));
  }

  let top = anchor.top;
  if (top + POPUP_MAX_HEIGHT > viewportH - margin) {
    top = Math.max(margin, viewportH - POPUP_MAX_HEIGHT - margin);
  }

  return { left, top };
}

function appointmentStatusLabel(lead: PulseLead): string {
  const explicit = (lead.appointment_status || '').trim();
  if (explicit) return explicit;
  if (
    lead.consultation_scheduled_at ||
    (lead.consultation_session_date &&
      lead.consultation_session_time &&
      lead.consultation_session_time !== 'Pending selection')
  ) {
    return 'Booked';
  }
  if (lead.consultation_session_date || lead.wants_consultation_call === true) {
    return 'Pending';
  }
  if (lead.wants_consultation_call === false) {
    return 'Declined';
  }
  return 'Not booked';
}

function LeadPreviewCard({ lead }: { lead: PulseLead }) {
  const appointment = appointmentStatusLabel(lead);
  const hasIntakeAnswers = Boolean(
    lead.preferred_country ||
      lead.target_program ||
      lead.target_degree ||
      lead.target_major ||
      lead.preferred_course ||
      lead.current_location ||
      lead.english_test_scores ||
      lead.test_scores ||
      lead.gre_score ||
      lead.gmat_score ||
      lead.wants_consultation_call != null ||
      lead.consultation_session_date ||
      lead.consultation_session_time ||
      lead.consultation_scheduled_at ||
      lead.assigned_counsellor_name
  );

  const rows: Array<[string, string]> = [
    ['Email', displayValue(lead.email)],
    ['Phone', displayValue(phoneOf(lead))],
  ];

  if (hasIntakeAnswers) {
    rows.push(
      ['Current location', displayValue(lead.current_location)],
      ['Target country', displayValue(lead.preferred_country)],
      ['Target program', displayValue(lead.target_program || lead.target_degree)],
      ['Major / course', displayValue(lead.target_major || lead.preferred_course)],
      ['English scores', displayValue(lead.english_test_scores || lead.test_scores)],
      ['GRE', displayValue(lead.gre_score)],
      ['GMAT', displayValue(lead.gmat_score)],
      ['Appointment', appointment],
      ['Wants consultation', displayValue(lead.wants_consultation_call)],
      ['Consultation date', displayValue(lead.consultation_session_date)],
      ['Consultation time', displayValue(lead.consultation_session_time)],
      ['Scheduled at', displayValue(lead.consultation_scheduled_at)],
      ['Assigned counsellor', displayValue(lead.assigned_counsellor_name)]
    );
  } else {
    rows.push(['Appointment', 'Not booked']);
  }

  rows.push(
    ['Intake step', displayValue(lead.intake_step_label || lead.intake_step)],
    ['Intake complete', displayValue(lead.intake_complete)],
    ['Messages received', displayValue(String(lead.total_messages_received ?? 0))],
    ['Unread', displayValue(String(lead.unread_count ?? 0))],
    ['AI conversation', displayValue(Boolean(lead.has_ai_messages))],
    ['Last activity', relativeLabel(lastActivityMs(lead))],
    ['Updated', relativeLabel(timestampMs(lead.updated_at))]
  );

  return (
    <>
      <div className="ai-pulse-tooltip-head">
        <strong>{lead.name}</strong>
        <span>{displayValue(lead.status || 'AI_ACTIVE')}</span>
      </div>
      <div
        className={`ai-pulse-tooltip-appointment${
          appointment === 'Booked'
            ? ' is-booked'
            : appointment === 'Pending'
              ? ' is-pending'
              : ''
        }`}
      >
        <em>Appointment</em>
        <strong>{appointment}</strong>
        <span>
          {[lead.consultation_session_date, lead.consultation_session_time]
            .filter(Boolean)
            .join(' · ') ||
            (lead.consultation_scheduled_at
              ? relativeLabel(timestampMs(lead.consultation_scheduled_at))
              : 'No session scheduled')}
        </span>
      </div>
      <dl className="ai-pulse-tooltip-grid">
        {rows.map(([label, value]) => (
          <div key={label} className="ai-pulse-tooltip-row">
            <dt>{label}</dt>
            <dd title={value}>{value}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

/**
 * Living pulse mosaic shown when no conversation is selected (AI Active or Handoffs).
 */
const AiActivePulseBoard: React.FC<AiActivePulseBoardProps> = ({
  leads,
  isLoading = false,
  onSelectLead,
  mode = 'ai-active',
  kicker,
  title,
  subtitle,
  queueLabel,
  emptyTitle,
  emptySubtitle,
  loadingLabel,
}) => {
  const copy = MODE_COPY[mode] ?? MODE_COPY['ai-active'];
  const resolved = {
    kicker: kicker ?? copy.kicker,
    title: title ?? copy.title,
    subtitle: subtitle ?? copy.subtitle,
    queueLabel: queueLabel ?? copy.queueLabel,
    emptyTitle: emptyTitle ?? copy.emptyTitle,
    emptySubtitle: emptySubtitle ?? copy.emptySubtitle,
    loadingLabel: loadingLabel ?? copy.loadingLabel,
  };

  const [preview, setPreview] = useState<PreviewState | null>(null);
  const hideTimerRef = useRef<number | null>(null);

  const livePreviewLead = useMemo(() => {
    if (!preview) return null;
    return leads.find(lead => lead.id === preview.lead.id) ?? preview.lead;
  }, [preview, leads]);

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current != null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const showPreview = useCallback(
    (lead: PulseLead, anchorEl: HTMLElement) => {
      clearHideTimer();
      const rect = anchorEl.getBoundingClientRect();
      const { left, top } = placePopup(rect);
      setPreview({ lead, left, top });
    },
    [clearHideTimer]
  );

  const scheduleHidePreview = useCallback(() => {
    clearHideTimer();
    hideTimerRef.current = window.setTimeout(() => setPreview(null), 120);
  }, [clearHideTimer]);

  useEffect(() => () => clearHideTimer(), [clearHideTimer]);

  const insights = useMemo(() => {
    const byUpdated = [...leads].sort(
      (a, b) => timestampMs(b.updated_at) - timestampMs(a.updated_at)
    );

    const newlyAdded =
      mode === 'handoffs' || mode === 'prospects'
        ? byUpdated.slice(0, 12)
        : byUpdated
            .filter(lead => !lead.has_ai_messages || (lead.total_messages_received || 0) <= 2)
            .slice(0, 12);

    const recentlyReplied = [...leads]
      .filter(hasCandidateReply)
      .sort((a, b) => {
        const unreadDiff = (b.unread_count || 0) - (a.unread_count || 0);
        if (unreadDiff !== 0) return unreadDiff;
        return lastReplyMs(b) - lastReplyMs(a);
      })
      .slice(0, 12);

    // Show EVERY country/program present in the queue (plus TBD catch-alls).
    // Previously .slice(0, 8) hid France/Russia/etc. whenever more than 8 buckets existed.
    const countries = buildClusters(leads, countryLabel);
    const programs = buildClusters(leads, programLabel);
    const byCountryProgram = buildCountryProgramClusters(leads);

    return {
      newlyAdded,
      recentlyReplied,
      countries,
      programs,
      byCountryProgram,
      countryLeadCount: clusterLeadCount(countries),
      programLeadCount: clusterLeadCount(programs),
    };
  }, [leads, mode]);

  if (isLoading) {
    return (
      <div className="ai-pulse-board ai-pulse-board--loading">
        <style>{PULSE_STYLES}</style>
        <div className="ai-pulse-loading">
          <p>{resolved.loadingLabel}</p>
        </div>
      </div>
    );
  }

  if (leads.length === 0) {
    return (
      <div className="ai-pulse-board">
        <style>{PULSE_STYLES}</style>
        <div className="ai-pulse-empty">
          <Sparkles size={28} />
          <h3>{resolved.emptyTitle}</h3>
          <p>{resolved.emptySubtitle}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-pulse-board">
      <style>{PULSE_STYLES}</style>

      <header className="ai-pulse-hero">
        <div>
          <p className="ai-pulse-kicker">{resolved.kicker}</p>
          <h3>{resolved.title}</h3>
          <p className="ai-pulse-sub">{resolved.subtitle}</p>
        </div>
        <div className="ai-pulse-stat">
          <strong>{leads.length}</strong>
          <span>{resolved.queueLabel}</span>
        </div>
      </header>

      <section className="ai-pulse-section">
        <div className="ai-pulse-section-head">
          <UserPlus size={16} />
          <h4>Newly added</h4>
          <span>{insights.newlyAdded.length}</span>
        </div>
        <div className="ai-pulse-chip-row">
          {insights.newlyAdded.length === 0 ? (
            <p className="ai-pulse-muted">No brand-new candidates in this window.</p>
          ) : (
            insights.newlyAdded.map((lead, index) => (
              <LeadChip
                key={`new-${lead.id}`}
                lead={lead}
                accent={COUNTRY_PALETTE[index % COUNTRY_PALETTE.length]}
                meta={relativeLabel(timestampMs(lead.updated_at))}
                onSelect={onSelectLead}
                onPreview={showPreview}
                onPreviewLeave={scheduleHidePreview}
              />
            ))
          )}
        </div>
      </section>

      <section className="ai-pulse-section">
        <div className="ai-pulse-section-head">
          <MessageCircleReply size={16} />
          <h4>Recently replied</h4>
          <span>{insights.recentlyReplied.length}</span>
        </div>
        <div className="ai-pulse-chip-row">
          {insights.recentlyReplied.length === 0 ? (
            <p className="ai-pulse-muted">No recent replies yet — outreach may still be warming up.</p>
          ) : (
            insights.recentlyReplied.map((lead, index) => (
              <LeadChip
                key={`reply-${lead.id}`}
                lead={lead}
                accent={PROGRAM_PALETTE[index % PROGRAM_PALETTE.length]}
                meta={
                  (lead.unread_count || 0) > 0
                    ? `${lead.unread_count} unread`
                    : relativeLabel(lastActivityMs(lead))
                }
                badge={(lead.unread_count || 0) > 0 ? lead.unread_count : undefined}
                onSelect={onSelectLead}
                onPreview={showPreview}
                onPreviewLeave={scheduleHidePreview}
              />
            ))
          )}
        </div>
      </section>

      <div className="ai-pulse-grid">
        <section className="ai-pulse-section ai-pulse-section--panel">
          <div className="ai-pulse-section-head">
            <Globe2 size={16} />
            <h4>Target countries</h4>
            <span title="Every lead in this queue is in exactly one country bucket (named or Country TBD)">
              {insights.countryLeadCount}/{leads.length} · {insights.countries.length}
            </span>
          </div>
          {insights.countryLeadCount !== leads.length ? (
            <p className="ai-pulse-muted ai-pulse-coverage-warn">
              Country coverage mismatch — some leads are missing from the country list.
            </p>
          ) : null}
          <div className="ai-pulse-cluster-stack">
            <HeadlessScrollArea className="ai-pulse-cluster-stack__scroll">
              {insights.countries.map((cluster, clusterIndex) => (
              <ClusterCard
                key={`country-${cluster.key}`}
                title={cluster.label}
                accent={
                  isTbdClusterLabel(cluster.label)
                    ? TBD_ACCENT
                    : COUNTRY_PALETTE[clusterIndex % COUNTRY_PALETTE.length]
                }
                leads={cluster.leads}
                muted={isTbdClusterLabel(cluster.label)}
                onSelect={onSelectLead}
                onPreview={showPreview}
                onPreviewLeave={scheduleHidePreview}
              />
            ))}
            </HeadlessScrollArea>
          </div>
        </section>

        <section className="ai-pulse-section ai-pulse-section--panel">
          <div className="ai-pulse-section-head">
            <GraduationCap size={16} />
            <h4>Target programs</h4>
            <span title="Every lead in this queue is in exactly one program bucket (named or Program TBD)">
              {insights.programLeadCount}/{leads.length} · {insights.programs.length}
            </span>
          </div>
          {insights.programLeadCount !== leads.length ? (
            <p className="ai-pulse-muted ai-pulse-coverage-warn">
              Program coverage mismatch — some leads are missing from the program list.
            </p>
          ) : null}
          <div className="ai-pulse-cluster-stack">
            <HeadlessScrollArea className="ai-pulse-cluster-stack__scroll">
              {insights.programs.map((cluster, clusterIndex) => (
              <ClusterCard
                key={`program-${cluster.key}`}
                title={cluster.label}
                accent={
                  isTbdClusterLabel(cluster.label)
                    ? TBD_ACCENT
                    : PROGRAM_PALETTE[clusterIndex % PROGRAM_PALETTE.length]
                }
                leads={cluster.leads}
                muted={isTbdClusterLabel(cluster.label)}
                onSelect={onSelectLead}
                onPreview={showPreview}
                onPreviewLeave={scheduleHidePreview}
              />
            ))}
            </HeadlessScrollArea>
          </div>
        </section>
      </div>

      <section className="ai-pulse-section ai-pulse-section--panel ai-pulse-section--cp">
        <div className="ai-pulse-section-head">
          <Globe2 size={16} />
          <h4>By country → program</h4>
          <span>
            {leads.length} leads · {insights.byCountryProgram.length} countries
          </span>
        </div>
        <p className="ai-pulse-muted" style={{ marginBottom: 10 }}>
          Circles under each program. Hover for details, click to open.
        </p>
        <div className="ai-pulse-cp-grid">
          {insights.byCountryProgram.map((country, countryIndex) => {
            const accent = isTbdClusterLabel(country.label)
              ? TBD_ACCENT
              : COUNTRY_PALETTE[countryIndex % COUNTRY_PALETTE.length];
            return (
              <div
                key={`cp-country-${country.key}`}
                className={`ai-pulse-cp-country${
                  isTbdClusterLabel(country.label) ? ' ai-pulse-cp-country--tbd' : ''
                }`}
                style={{ '--cluster-accent': accent } as React.CSSProperties}
              >
                <div className="ai-pulse-cp-country-head">
                  <strong>
                    <Globe2 size={13} /> {country.label}
                  </strong>
                  <span>
                    {country.leads.length} · {country.programs.length} prog
                  </span>
                </div>
                <div className="ai-pulse-cp-programs">
                  {country.programs.map((program, programIndex) => {
                    const programAccent = isTbdClusterLabel(program.label)
                      ? TBD_ACCENT
                      : PROGRAM_PALETTE[programIndex % PROGRAM_PALETTE.length];
                    return (
                      <div
                        key={`cp-program-${country.key}-${program.key}`}
                        className={`ai-pulse-cp-program${
                          isTbdClusterLabel(program.label) ? ' ai-pulse-cp-program--tbd' : ''
                        }`}
                        style={
                          { '--cluster-accent': programAccent } as React.CSSProperties
                        }
                      >
                        <div className="ai-pulse-cp-program-head">
                          <strong>
                            <GraduationCap size={12} /> {program.label}
                          </strong>
                          <span>{program.leads.length}</span>
                        </div>
                        <div className="ai-pulse-cluster-dots">
                          {program.leads.map(lead => (
                            <button
                              key={lead.id}
                              type="button"
                              className="ai-pulse-dot"
                              aria-label={lead.name}
                              onClick={() => onSelectLead(lead.id)}
                              onMouseEnter={event =>
                                showPreview(lead, event.currentTarget)
                              }
                              onMouseLeave={scheduleHidePreview}
                              onFocus={event => showPreview(lead, event.currentTarget)}
                              onBlur={scheduleHidePreview}
                            >
                              {initials(lead.name)}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {preview &&
        livePreviewLead &&
        createPortal(
          <div
            className="ai-pulse-tooltip"
            style={{ left: preview.left, top: preview.top }}
            onMouseEnter={clearHideTimer}
            onMouseLeave={scheduleHidePreview}
          >
            <LeadPreviewCard lead={livePreviewLead} />
          </div>,
          document.body
        )}
    </div>
  );
};

function LeadChip({
  lead,
  accent,
  meta,
  badge,
  onSelect,
  onPreview,
  onPreviewLeave,
}: {
  lead: PulseLead;
  accent: string;
  meta: string;
  badge?: number;
  onSelect: (leadId: number) => void;
  onPreview: (lead: PulseLead, el: HTMLElement) => void;
  onPreviewLeave: () => void;
}) {
  return (
    <button
      type="button"
      className="ai-pulse-chip"
      style={{ '--chip-accent': accent } as React.CSSProperties}
      onClick={() => onSelect(lead.id)}
      onMouseEnter={event => onPreview(lead, event.currentTarget)}
      onMouseLeave={onPreviewLeave}
      onFocus={event => onPreview(lead, event.currentTarget)}
      onBlur={onPreviewLeave}
    >
      <span className="ai-pulse-chip-avatar" style={{ background: accent }}>
        {initials(lead.name)}
        {badge != null && badge > 0 ? <i>{badge > 9 ? '9+' : badge}</i> : null}
      </span>
      <span className="ai-pulse-chip-copy">
        <strong>{lead.name}</strong>
        <em>
          <Clock3 size={11} /> {meta}
        </em>
      </span>
    </button>
  );
}

function ClusterCard({
  title,
  accent,
  leads,
  muted = false,
  onSelect,
  onPreview,
  onPreviewLeave,
}: {
  title: string;
  accent: string;
  leads: PulseLead[];
  muted?: boolean;
  onSelect: (leadId: number) => void;
  onPreview: (lead: PulseLead, el: HTMLElement) => void;
  onPreviewLeave: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visibleLeads = expanded ? leads : leads.slice(0, CLUSTER_PREVIEW_LIMIT);
  const hiddenCount = Math.max(0, leads.length - CLUSTER_PREVIEW_LIMIT);

  return (
    <div
      className={`ai-pulse-cluster${muted ? ' ai-pulse-cluster--tbd' : ''}`}
      style={{ '--cluster-accent': accent } as React.CSSProperties}
    >
      <div className="ai-pulse-cluster-top">
        <strong>{title}</strong>
        <span>{leads.length}</span>
      </div>
      <div className="ai-pulse-cluster-dots">
        {visibleLeads.map(lead => (
          <button
            key={lead.id}
            type="button"
            className="ai-pulse-dot"
            onClick={() => onSelect(lead.id)}
            onMouseEnter={event => onPreview(lead, event.currentTarget)}
            onMouseLeave={onPreviewLeave}
            onFocus={event => onPreview(lead, event.currentTarget)}
            onBlur={onPreviewLeave}
          >
            {initials(lead.name)}
          </button>
        ))}
        {hiddenCount > 0 && !expanded ? (
          <button
            type="button"
            className="ai-pulse-dot ai-pulse-dot--more"
            title={`Show ${hiddenCount} more candidate${hiddenCount === 1 ? '' : 's'} in ${title}`}
            onClick={() => setExpanded(true)}
          >
            +{hiddenCount}
          </button>
        ) : null}
        {expanded && leads.length > CLUSTER_PREVIEW_LIMIT ? (
          <button
            type="button"
            className="ai-pulse-dot ai-pulse-dot--more"
            title="Show fewer candidates"
            onClick={() => setExpanded(false)}
          >
            −
          </button>
        ) : null}
      </div>
    </div>
  );
}

const PULSE_STYLES = `
  .ai-pulse-board {
    flex: 1 1 auto;
    align-self: stretch;
    width: 100%;
    min-height: 0;
    height: 100%;
    overflow: auto;
    padding: 20px 22px 28px;
    background: #F7F9F9;
    box-sizing: border-box;
  }
  .ai-pulse-hero {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-end;
    margin-bottom: 18px;
  }
  .ai-pulse-kicker {
    margin: 0 0 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #0077b6;
  }
  .ai-pulse-hero h3 {
    margin: 0;
    font-size: 22px;
    line-height: 1.2;
    color: #322f86;
  }
  .ai-pulse-sub {
    margin: 6px 0 0;
    max-width: 42rem;
    font-size: 13px;
    color: #386fa4;
  }
  .ai-pulse-stat {
    min-width: 92px;
    padding: 10px 14px;
    border-radius: 14px;
    background: rgba(50, 47, 134, 0.92);
    color: #fff;
    text-align: center;
    box-shadow: 0 10px 30px rgba(50, 47, 134, 0.22);
  }
  .ai-pulse-stat strong {
    display: block;
    font-size: 24px;
    line-height: 1;
  }
  .ai-pulse-stat span {
    font-size: 11px;
    opacity: 0.85;
  }
  .ai-pulse-section {
    margin-bottom: 16px;
  }
  .ai-pulse-section--panel {
    margin-bottom: 0;
    padding: 14px;
    border-radius: 16px;
    background: #ffffff;
    border: 1px solid #84d2f6;
  }
  .ai-pulse-section-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    color: #322f86;
  }
  .ai-pulse-section-head h4 {
    margin: 0;
    font-size: 14px;
    font-weight: 700;
  }
  .ai-pulse-section-head span {
    margin-left: auto;
    font-size: 11px;
    font-weight: 700;
    color: #0077b6;
    background: rgba(0, 180, 216, 0.12);
    border-radius: 999px;
    padding: 2px 8px;
  }
  .ai-pulse-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  .ai-pulse-chip {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 168px;
    max-width: 220px;
    padding: 8px 10px 8px 8px;
    border-radius: 14px;
    border: 1px solid color-mix(in srgb, var(--chip-accent) 28%, #fff);
    background: #ffffff;
    box-shadow: 0 4px 12px rgba(50, 47, 134, 0.05);
    cursor: pointer;
    text-align: left;
  }
  .ai-pulse-chip:hover {
    box-shadow: 0 8px 18px rgba(50, 47, 134, 0.1);
  }
  .ai-pulse-chip-avatar {
    position: relative;
    width: 34px;
    height: 34px;
    border-radius: 11px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 11px;
    font-weight: 500;
    flex-shrink: 0;
  }
  .ai-pulse-chip-avatar i {
    position: absolute;
    top: -5px;
    right: -5px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 999px;
    background: #ef4444;
    color: #fff;
    font-size: 9px;
    font-style: normal;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .ai-pulse-chip-copy {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .ai-pulse-chip-copy strong {
    font-size: 12px;
    font-weight: 600;
    color: #322f86;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ai-pulse-chip-copy em {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-style: normal;
    color: #386fa4;
  }
  .ai-pulse-tooltip {
    position: fixed;
    width: ${POPUP_WIDTH}px;
    max-height: ${POPUP_MAX_HEIGHT}px;
    padding: 16px;
    border-radius: 16px;
    background: #ffffff;
    color: #322f86;
    border: 1px solid #84d2f6;
    box-shadow: 0 18px 40px rgba(50, 47, 134, 0.18);
    z-index: 10050;
    text-align: left;
    overflow: hidden;
  }
  .ai-pulse-tooltip-head {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: baseline;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #e2e8f0;
  }
  .ai-pulse-tooltip-head strong {
    font-size: 16px;
    font-weight: 700;
    color: #322f86;
  }
  .ai-pulse-tooltip-head span {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #0077b6;
  }
  .ai-pulse-tooltip-appointment {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    margin: 0 0 12px;
    padding: 10px 12px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
  }
  .ai-pulse-tooltip-appointment.is-booked {
    background: #ecfdf5;
    border-color: #bbf7d0;
  }
  .ai-pulse-tooltip-appointment.is-pending {
    background: #fffbeb;
    border-color: #fde68a;
  }
  .ai-pulse-tooltip-appointment em {
    grid-column: 1;
    font-style: normal;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #64748b;
  }
  .ai-pulse-tooltip-appointment strong {
    grid-column: 2;
    justify-self: end;
    font-size: 12px;
    color: #0f172a;
  }
  .ai-pulse-tooltip-appointment span {
    grid-column: 1 / -1;
    font-size: 12px;
    color: #334155;
  }
  .ai-pulse-tooltip-grid {
    margin: 0;
    display: grid;
    gap: 8px;
  }
  .ai-pulse-tooltip-row {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 10px;
    font-size: 13px;
    line-height: 1.4;
  }
  .ai-pulse-tooltip-row dt {
    margin: 0;
    color: #386fa4;
  }
  .ai-pulse-tooltip-row dd {
    margin: 0;
    color: #322f86;
    word-break: break-word;
    white-space: normal;
  }
  .ai-pulse-cp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
  }
  .ai-pulse-cp-country {
    padding: 12px;
    border-radius: 12px;
    background: #ffffff;
    border: 1px solid color-mix(in srgb, var(--cluster-accent) 22%, #e2e8f0);
  }
  .ai-pulse-cp-country--tbd {
    background: #f8fafc;
    border-style: dashed;
  }
  .ai-pulse-cp-country-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }
  .ai-pulse-cp-country-head strong {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 700;
    color: #322f86;
  }
  .ai-pulse-cp-country-head span {
    font-size: 11px;
    font-weight: 700;
    color: var(--cluster-accent);
    flex-shrink: 0;
  }
  .ai-pulse-cp-programs {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ai-pulse-cp-program {
    padding: 8px 9px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid color-mix(in srgb, var(--cluster-accent) 18%, #e2e8f0);
  }
  .ai-pulse-cp-program--tbd {
    border-style: dashed;
  }
  .ai-pulse-cp-program-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .ai-pulse-cp-program-head strong {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
    font-size: 12px;
    font-weight: 700;
    color: #322f86;
  }
  .ai-pulse-cp-program-head span {
    font-size: 11px;
    font-weight: 700;
    color: var(--cluster-accent);
    flex-shrink: 0;
  }
  .ai-pulse-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 16px;
  }
  @media (max-width: 1100px) {
    .ai-pulse-grid { grid-template-columns: 1fr; }
  }
  .ai-pulse-section--cp {
    margin-top: 4px;
    margin-bottom: 0;
  }
  .ai-pulse-cluster-stack {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .ai-pulse-cluster-stack__scroll {
    max-height: min(70vh, 720px);
  }
  .ai-pulse-cluster-stack__scroll .headless-scroll-viewport {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-right: 2px;
  }
  .ai-pulse-coverage-warn {
    color: #b45309 !important;
    margin: 0 0 8px;
  }
  .ai-pulse-cluster {
    padding: 10px 12px;
    border-radius: 12px;
    background: #ffffff;
    border: 1px solid color-mix(in srgb, var(--cluster-accent) 22%, #e2e8f0);
  }
  .ai-pulse-cluster--tbd {
    background: #f8fafc;
    border-style: dashed;
  }
  .ai-pulse-cluster-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .ai-pulse-cluster-top strong {
    font-size: 13px;
    font-weight: 600;
    color: #322f86;
  }
  .ai-pulse-cluster-top span {
    font-size: 11px;
    font-weight: 700;
    color: var(--cluster-accent);
  }
  .ai-pulse-cluster-dots {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .ai-pulse-dot {
    position: relative;
    width: 30px;
    height: 30px;
    border-radius: 999px;
    border: none;
    background: var(--cluster-accent);
    color: #fff;
    font-size: 10px;
    font-weight: 500;
    cursor: pointer;
  }
  .ai-pulse-dot--more {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(50, 47, 134, 0.08);
    color: #322f86;
    min-width: 30px;
    padding: 0 6px;
    font-weight: 600;
  }
  .ai-pulse-dot--more:hover {
    background: rgba(50, 47, 134, 0.16);
  }
  .ai-pulse-muted {
    margin: 0;
    font-size: 13px;
    color: #64748b;
  }
  .ai-pulse-empty, .ai-pulse-loading {
    height: 100%;
    min-height: 280px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: #386fa4;
    text-align: center;
    background: #F7F9F9;
  }
  .ai-pulse-empty h3, .ai-pulse-loading p {
    margin: 0;
    color: #322f86;
  }
`;

export default AiActivePulseBoard;
