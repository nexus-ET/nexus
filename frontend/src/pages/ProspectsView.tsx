import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Archive, Users } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface MessagePayload {
  id?: number | string;
  sender: string;
  text: string;
  created_at?: string;
  media_url?: string;
  file_name?: string;
  actor?: MessageActor;
}

interface Prospect {
  id: number;
  full_name?: string;
  name?: string;
  phone?: string;
  phone_number?: string;
  email: string;
  stage: string;
  status?: string;
  is_human_locked?: boolean;
  academic_summary?: string;
  last_interaction_summary?: string;
  messages?: MessagePayload[];
  updated_at?: string;
  latest_interaction_time?: string;
  total_messages_received: number;
}

const getCandidateReceivedCount = (prospect: Prospect): number => {
  if (typeof prospect.total_messages_received === 'number' && !Number.isNaN(prospect.total_messages_received)) {
    return prospect.total_messages_received;
  }
  return (prospect.messages || []).filter(
    msg => msg.sender === 'candidate' || msg.sender === 'student'
  ).length;
};

const getProspectActivityTime = (prospect: Prospect): number => {
  const latestFromMessages = (prospect.messages || []).reduce((max, msg) => {
    const time = new Date(msg.created_at || 0).getTime();
    return time > max ? time : max;
  }, 0);

  if (latestFromMessages > 0) return latestFromMessages;
  if (prospect.latest_interaction_time) {
    return new Date(prospect.latest_interaction_time).getTime();
  }
  return new Date(prospect.updated_at || 0).getTime();
};

const sortProspects = (a: Prospect, b: Prospect): number => {
  const dateDiff = getProspectActivityTime(b) - getProspectActivityTime(a);
  if (dateDiff !== 0) return dateDiff;
  return getCandidateReceivedCount(b) - getCandidateReceivedCount(a);
};

type MessageActor = 'candidate' | 'ai' | 'admin';
type StatusKey = 'ai-active' | 'handoff' | 'archive';

const AI_AUTOMATED_PATTERNS = [
  'Got it! Your update has been logged on your dashboard matrix timeline.',
  'Got it! Thank you for that update',
  'Understood completely',
  'Understood,',
  'Awesome, glad to hear that',
  'No worries at all',
  'Are you looking to start classes',
  'Thank you for reaching out',
  'Are you currently holding an official',
  'What timing are you thinking',
  'This is the Admissions Office',
  'Monitoring channel queues',
];

const normalizeStatus = (status?: string): string =>
  (status || '').toUpperCase().replace(/-/g, '_');

const formatStatusLabel = (stage?: string): string => {
  const s = normalizeStatus(stage);
  if (s.includes('HANDOFF') || s.includes('HUMAN')) return 'Handoff';
  if (s.includes('ARCHIVE')) return 'Archive';
  if (s === 'AI_ACTIVE') return 'AI Active';
  return stage || 'Unknown';
};

const getStatusBadgeStyle = (stage?: string) => {
  const s = normalizeStatus(stage);
  if (s.includes('HANDOFF') || s.includes('HUMAN')) {
    return { backgroundColor: '#fef3c7', color: '#b45309', border: '1px solid #fde68a' };
  }
  if (s.includes('ARCHIVE')) {
    return { backgroundColor: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' };
  }
  if (s === 'AI_ACTIVE') {
    return { backgroundColor: '#ecfdf5', color: '#059669', border: '1px solid #bbf7d0' };
  }
  return { backgroundColor: '#f8fafc', color: '#64748b', border: '1px solid #e2e8f0' };
};

const getTransitionOptions = (stage?: string) => {
  const s = normalizeStatus(stage);

  if (s.includes('HANDOFF') || s.includes('HUMAN')) {
    return [
      { key: 'ai-active' as StatusKey, label: 'AI ACTIVE', icon: Bot },
      { key: 'archive' as StatusKey, label: 'ARCHIVE', icon: Archive },
    ];
  }
  if (s === 'AI_ACTIVE') {
    return [
      { key: 'handoff' as StatusKey, label: 'HANDOFF', icon: Users },
      { key: 'archive' as StatusKey, label: 'ARCHIVE', icon: Archive },
    ];
  }
  if (s.includes('ARCHIVE')) {
    return [
      { key: 'ai-active' as StatusKey, label: 'AI ACTIVE', icon: Bot },
      { key: 'handoff' as StatusKey, label: 'HANDOFF', icon: Users },
    ];
  }

  return [
    { key: 'ai-active' as StatusKey, label: 'AI ACTIVE', icon: Bot },
    { key: 'handoff' as StatusKey, label: 'HANDOFF', icon: Users },
    { key: 'archive' as StatusKey, label: 'ARCHIVE', icon: Archive },
  ];
};

const classifyMessage = (msg: MessagePayload): MessageActor => {
  if (msg.sender === 'candidate' || msg.sender === 'student') return 'candidate';
  if (msg.sender === 'system') return 'admin';

  const text = msg.text || '';
  if (AI_AUTOMATED_PATTERNS.some(pattern => text.includes(pattern))) return 'ai';
  if (text.includes('human admissions advisor has just joined')) return 'admin';
  if (text.includes('Manual Advisor') || text.includes('Takeover Override')) return 'admin';

  return 'admin';
};

const mapProspectFromApi = (lead: Record<string, unknown>): Prospect => ({
  id: lead.id as number,
  full_name: (lead.full_name || lead.name) as string | undefined,
  name: lead.name as string | undefined,
  phone: lead.phone as string | undefined,
  phone_number: lead.phone_number as string | undefined,
  email: (lead.email || '') as string,
  stage: (lead.stage || lead.status || 'AI_ACTIVE') as string,
  status: (lead.status || lead.stage) as string | undefined,
  is_human_locked: Boolean(lead.is_human_locked || lead.human_locked),
  academic_summary: lead.academic_summary as string | undefined,
  last_interaction_summary: lead.last_interaction_summary as string | undefined,
  messages: (lead.messages || lead.chat_history || lead.history || []) as MessagePayload[],
  updated_at: lead.updated_at as string | undefined,
  latest_interaction_time: lead.latest_interaction_time as string | undefined,
  total_messages_received: Number(lead.total_messages_received ?? 0),
});

const formatTime = (dateStr?: string): string => {
  if (!dateStr) return '';
  try {
    const parsed = new Date(dateStr);
    if (Number.isNaN(parsed.getTime())) return '';
    return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const getDateGroupLabel = (dateStr?: string): string => {
  if (!dateStr) return 'Earlier';
  try {
    const parsed = new Date(dateStr);
    if (Number.isNaN(parsed.getTime())) return 'Earlier';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const target = new Date(parsed);
    target.setHours(0, 0, 0, 0);
    const diffDays = Math.round((today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays > 1 && diffDays < 7) {
      return target.toLocaleDateString('en-US', { weekday: 'long' });
    }
    return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Earlier';
  }
};

const ACTOR_THEME: Record<MessageActor, { bg: string; label: string; labelColor: string; textColor: string }> = {
  candidate: { bg: '#1e3a5f', label: 'Candidate', labelColor: '#93c5fd', textColor: '#f8fafc' },
  ai: { bg: '#ede9fe', label: 'AI Active', labelColor: '#6d28d9', textColor: '#111b21' },
  admin: { bg: '#dbeafe', label: 'Nexus Admin', labelColor: '#1d4ed8', textColor: '#111b21' },
};

export default function ProspectsView() {
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [selectedProspect, setSelectedProspect] = useState<Prospect | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState('All');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatingRowId, setUpdatingRowId] = useState<number | null>(null);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchProspects = async (signal?: AbortSignal) => {
    try {
      setLoadError(null);
      const data = await apiFetch('leads/all', { signal });
      const leadsData = (Array.isArray(data) ? data : (data as { leads?: unknown[] }).leads || []).map(
        mapProspectFromApi
      );
      setProspects(leadsData);

      setSelectedProspect(prev => {
        if (!prev) return null;
        return leadsData.find((p: Prospect) => p.id === prev.id) || prev;
      });
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Error loading prospects pipeline:', error);
        setLoadError(error.message || 'Failed to load prospects.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let isActive = true;

    async function executionLoop() {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      abortControllerRef.current = new AbortController();
      await fetchProspects(abortControllerRef.current.signal);
      if (isActive) pollingTimerRef.current = setTimeout(executionLoop, 5000);
    }

    executionLoop();

    return () => {
      isActive = false;
      if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  const filteredProspects = useMemo(() => {
    return prospects
      .filter(prospect => {
        const nameMatch = (prospect.full_name || prospect.name || '')
          .toLowerCase()
          .includes(searchQuery.toLowerCase());
        const emailMatch = prospect.email.toLowerCase().includes(searchQuery.toLowerCase());
        const phoneMatch = (prospect.phone || prospect.phone_number || '').includes(searchQuery);
        const matchesSearch = nameMatch || emailMatch || phoneMatch;

        if (stageFilter === 'All') return matchesSearch;

        const stage = normalizeStatus(prospect.stage);
        if (stageFilter === 'AI Active') return matchesSearch && stage === 'AI_ACTIVE';
        if (stageFilter === 'Handoff') {
          return matchesSearch && (stage.includes('HANDOFF') || stage.includes('HUMAN') || prospect.is_human_locked);
        }
        if (stageFilter === 'Archive') return matchesSearch && stage.includes('ARCHIVE');

        return matchesSearch && prospect.stage === stageFilter;
      })
      .sort(sortProspects);
  }, [prospects, searchQuery, stageFilter]);

  const groupedMessages = useMemo(() => {
    if (!selectedProspect) return {};

    const processed: MessagePayload[] = [...(selectedProspect.messages || [])]
      .filter(msg => !msg.text?.includes('Got it! Your update has been logged on your dashboard matrix timeline.'))
      .map(msg => ({ ...msg, actor: classifyMessage(msg) }));

    const rawLogs = selectedProspect.academic_summary || selectedProspect.last_interaction_summary || '';
    if (rawLogs) {
      rawLogs.split('\n').forEach((line, index) => {
        const clean = line.trim();
        if (!clean || clean.includes('Got it! Your update has been logged on your dashboard matrix timeline.')) return;

        if (clean.startsWith('Candidate:') || clean.startsWith('student:')) {
          processed.push({
            id: `log-c-${index}`,
            sender: 'candidate',
            text: clean.replace(/^(Candidate:|student:)\s*/i, ''),
            actor: 'candidate',
          });
        } else if (clean.startsWith('Advisor:')) {
          const text = clean.replace(/^Advisor:\s*/i, '');
          processed.push({
            id: `log-a-${index}`,
            sender: 'advisor',
            text,
            actor: classifyMessage({ sender: 'advisor', text }),
          });
        } else if (clean.startsWith('[')) {
          processed.push({
            id: `log-s-${index}`,
            sender: 'system',
            text: clean,
            actor: 'admin',
          });
        }
      });
    }

    const groups: Record<string, MessagePayload[]> = {};
    processed.forEach(msg => {
      const label = getDateGroupLabel(msg.created_at);
      if (!groups[label]) groups[label] = [];
      groups[label].push(msg);
    });

    return groups;
  }, [selectedProspect]);

  useEffect(() => {
    const container = chatContainerRef.current;
    if (!container || !selectedProspect) return;
    container.scrollTop = container.scrollHeight;
  }, [selectedProspect?.id, groupedMessages]);

  const handleTransitionStatus = async (
    event: React.MouseEvent,
    prospectId: number,
    targetStatus: StatusKey
  ) => {
    event.stopPropagation();
    setUpdatingRowId(prospectId);

    try {
      await apiFetch(`leads/${prospectId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: targetStatus }),
      });

      await fetchProspects();
    } catch (error) {
      console.error('Prospect status update error:', error);
    } finally {
      setUpdatingRowId(null);
    }
  };

  const handleSelectProspect = async (prospect: Prospect) => {
    setSelectedProspect(prospect);
    try {
      const detail = await apiFetch(`leads/${prospect.id}`);
      setSelectedProspect(mapProspectFromApi(detail as Record<string, unknown>));
    } catch (error) {
      console.error('Failed to load prospect detail:', error);
    }
  };

  const hasNoMessages = Object.keys(groupedMessages).length === 0;

  return (
    <div style={styles.workspaceContainer}>
      <style>{`
        .custom-scroll-region::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scroll-region::-webkit-scrollbar-track { background: transparent; }
        .custom-scroll-region::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 20px; }
        .custom-scroll-region::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        .prospect-status-btn {
          display: flex;
          align-items: center;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          padding: 4px;
          border-radius: 4px;
          width: 26px;
          height: 26px;
          overflow: hidden;
          cursor: pointer;
          transition: width 0.3s ease;
          color: #334155;
        }
        .prospect-status-btn:hover { width: 96px; }
        .prospect-status-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .prospect-status-btn-label {
          display: none;
          margin-left: 8px;
          font-size: 8px;
          font-weight: 800;
          text-transform: uppercase;
          white-space: nowrap;
        }
        .prospect-status-btn:hover .prospect-status-btn-label { display: block; }
      `}</style>

      <div style={styles.leftSidebarPanel}>
        <div style={styles.sidebarHeader}>
          <h2 style={styles.sidebarTitle}>All Prospects</h2>
          <span style={styles.activeCounterBadge}>{filteredProspects.length}</span>
        </div>

        <div style={styles.searchHeaderSection}>
          <input
            type="text"
            placeholder="Search prospects..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={styles.searchBarInput}
          />
          <select
            value={stageFilter}
            onChange={e => setStageFilter(e.target.value)}
            style={styles.filterDropdownSelector}
          >
            <option value="All">All Stages</option>
            <option value="AI Active">AI Active</option>
            <option value="Handoff">Handoff</option>
            <option value="Archive">Archive</option>
          </select>
        </div>

        <div className="custom-scroll-region" style={styles.leadScrollList}>
          {loadError ? (
            <div style={styles.emptyListPlaceholder}>{loadError}</div>
          ) : isLoading ? (
            <div style={styles.emptyListPlaceholder}>Loading prospects...</div>
          ) : filteredProspects.length === 0 ? (
            <div style={styles.emptyListPlaceholder}>No matching prospects found.</div>
          ) : (
            filteredProspects.map(prospect => {
              const isSelected = selectedProspect?.id === prospect.id;
              const transitionOptions = getTransitionOptions(prospect.stage);
              const badgeStyle = getStatusBadgeStyle(prospect.stage);

              return (
                <div
                  key={prospect.id}
                  onClick={() => handleSelectProspect(prospect)}
                  style={{
                    ...styles.leadInteractionCard,
                    backgroundColor: isSelected ? '#f0fdf4' : '#ffffff',
                    borderColor: isSelected ? '#16a34a' : '#e2e8f0',
                    cursor: 'pointer',
                  }}
                >
                  <div style={styles.cardTopRow}>
                    <div style={styles.leadCardNameRow}>
                      <h4 style={styles.leadCardName}>
                        {prospect.full_name || prospect.name || 'Unknown'}
                      </h4>
                      <span
                        style={styles.receivedCountBadge}
                        title="Messages received from candidate"
                      >
                        {getCandidateReceivedCount(prospect)}
                      </span>
                    </div>
                    <div style={styles.statusActionGroup}>
                      {transitionOptions.map(({ key, label, icon: Icon }) => (
                        <button
                          key={key}
                          type="button"
                          className="prospect-status-btn"
                          title={label}
                          disabled={updatingRowId === prospect.id}
                          onClick={event => handleTransitionStatus(event, prospect.id, key)}
                        >
                          <Icon size={14} />
                          <span className="prospect-status-btn-label">{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={styles.cardBottomRow}>
                    <p style={styles.leadCardMeta}>
                      {prospect.phone || prospect.phone_number || 'No Phone'}
                      {prospect.email ? ` · ${prospect.email}` : ''}
                    </p>
                    <button
                      type="button"
                      onClick={event => {
                        event.stopPropagation();
                        handleSelectProspect(prospect);
                      }}
                      style={{
                        ...styles.statusLabelButton,
                        ...badgeStyle,
                      }}
                      title="View full communication history"
                    >
                      {formatStatusLabel(prospect.stage)}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div style={styles.rightChatPanel}>
        {selectedProspect ? (
          <div style={styles.activeChatInterface}>
            <div style={styles.chatHeaderBar}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3 style={styles.headerProfileName}>
                  {selectedProspect.full_name || selectedProspect.name}
                </h3>
                <p style={styles.headerProfileMeta}>
                  📱 {selectedProspect.phone || selectedProspect.phone_number || 'No Phone'} | 📧{' '}
                  {selectedProspect.email}
                </p>
              </div>
              <div style={styles.legendRow}>
                {(['candidate', 'ai', 'admin'] as MessageActor[]).map(actor => (
                  <span key={actor} style={styles.legendChip(actor)}>
                    {ACTOR_THEME[actor].label}
                  </span>
                ))}
              </div>
            </div>

            <div
              ref={chatContainerRef}
              className="custom-scroll-region"
              style={styles.whatsappChatFeedSurface}
            >
              {hasNoMessages ? (
                <div style={styles.emptyConversationPrompt}>
                  <div style={{ fontSize: '32px', marginBottom: '8px' }}>💬</div>
                  <h4 style={{ margin: '0 0 4px 0', color: '#334155', fontWeight: 600 }}>
                    No Messages Available
                  </h4>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
                    No communication history is logged for this prospect yet.
                  </p>
                </div>
              ) : (
                Object.entries(groupedMessages).map(([dateLabel, messages]) => (
                  <div key={dateLabel} style={{ width: '100%' }}>
                    <div style={styles.timelineDividerCenter}>
                      <span style={styles.timelineBadgeBubble}>{dateLabel}</span>
                    </div>

                    {messages.map((msg, index) => {
                      const actor = msg.actor || classifyMessage(msg);
                      const theme = ACTOR_THEME[actor];
                      const isOutbound = actor !== 'candidate';

                      return (
                        <div
                          key={msg.id ?? `${dateLabel}-${index}`}
                          style={{
                            ...styles.messageStreamRow,
                            justifyContent: isOutbound ? 'flex-end' : 'flex-start',
                          }}
                        >
                          <div
                            style={{
                              ...styles.messageBubbleCell,
                              backgroundColor: theme.bg,
                              borderRadius: isOutbound ? '8px 8px 0px 8px' : '8px 8px 8px 0px',
                              boxShadow: '0 1px 1px rgba(0,0,0,0.12)',
                            }}
                          >
                            <span
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                color: theme.labelColor,
                                marginBottom: '4px',
                              }}
                            >
                              {theme.label}
                            </span>
                            {msg.media_url ? (
                              <a
                                href={msg.media_url}
                                target="_blank"
                                rel="noreferrer"
                                style={styles.downloadFileActionLink}
                              >
                                {msg.file_name || 'View attachment'}
                              </a>
                            ) : null}
                            {msg.text ? (
                              <p style={{ ...styles.bubbleTextString, color: theme.textColor }}>
                                {msg.text}
                              </p>
                            ) : null}
                            {msg.created_at ? (
                              <span
                                style={{
                                  ...styles.bubbleTimestampLabel,
                                  color: actor === 'candidate' ? '#93c5fd' : '#667781',
                                }}
                              >
                                {formatTime(msg.created_at)}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <div style={styles.emptyWorkspaceGrid}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '12px' }}>👥</div>
              <h3 style={{ margin: '0 0 6px 0', color: '#334155' }}>No Prospect Selected</h3>
              <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
                Select a prospect from the left panel to load their communication timeline.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  workspaceContainer: {
    display: 'flex',
    width: '100%',
    height: '100%',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#f8fafc',
    overflow: 'hidden',
    boxSizing: 'border-box',
    fontFamily: 'system-ui, -apple-system, sans-serif',
  } as React.CSSProperties,
  leftSidebarPanel: {
    width: '20%',
    minWidth: '280px',
    maxWidth: '20%',
    height: '100%',
    borderRight: '1px solid #e2e8f0',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#ffffff',
    overflow: 'hidden',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  sidebarHeader: {
    padding: '16px 20px',
    borderBottom: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexShrink: 0,
  } as React.CSSProperties,
  sidebarTitle: { margin: 0, fontSize: '16px', fontWeight: '700', color: '#0f172a' } as React.CSSProperties,
  activeCounterBadge: {
    backgroundColor: '#dbeafe',
    color: '#1d4ed8',
    padding: '2px 8px',
    borderRadius: '10px',
    fontSize: '11px',
    fontWeight: '600',
  } as React.CSSProperties,
  searchHeaderSection: {
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    borderBottom: '1px solid #e2e8f0',
    flexShrink: 0,
  } as React.CSSProperties,
  searchBarInput: {
    padding: '10px 12px',
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    color: '#0f172a',
    fontSize: '13px',
    outline: 'none',
  } as React.CSSProperties,
  filterDropdownSelector: {
    padding: '8px 12px',
    backgroundColor: '#f8fafc',
    color: '#0f172a',
    border: '1px solid #e2e8f0',
    borderRadius: '6px',
    outline: 'none',
    fontSize: '13px',
    cursor: 'pointer',
  } as React.CSSProperties,
  leadScrollList: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  } as React.CSSProperties,
  emptyListPlaceholder: {
    textAlign: 'center',
    padding: '40px 20px',
    color: '#94a3b8',
    fontSize: '13px',
  } as React.CSSProperties,
  leadInteractionCard: {
    padding: '8px 10px',
    borderRadius: '6px',
    border: '1px solid',
    transition: 'all 0.2s ease',
    flexShrink: 0,
    width: '100%',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  } as React.CSSProperties,
  cardTopRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '6px',
  } as React.CSSProperties,
  cardBottomRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '6px',
  } as React.CSSProperties,
  cardMainFrame: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '8px',
  } as React.CSSProperties,
  leadCardNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,
  leadCardName: {
    margin: 0,
    fontSize: '14px',
    fontWeight: '700',
    color: '#1e3a8a',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    minWidth: 0,
  } as React.CSSProperties,
  receivedCountBadge: {
    flexShrink: 0,
    display: 'inline-grid',
    placeItems: 'center',
    boxSizing: 'border-box',
    minWidth: '24px',
    height: '24px',
    aspectRatio: '1',
    padding: '0 5px',
    borderRadius: '9999px',
    fontSize: '12px',
    fontWeight: '500',
    color: '#ffffff',
    backgroundColor: '#25D366',
    lineHeight: 1,
    textAlign: 'center',
    fontVariantNumeric: 'tabular-nums',
  } as React.CSSProperties,
  statusActionGroup: { display: 'flex', gap: '3px', flexShrink: 0 } as React.CSSProperties,
  leadCardMeta: {
    margin: 0,
    fontSize: '10px',
    color: '#64748b',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,
  statusLabelButton: {
    flexShrink: 0,
    fontSize: '9px',
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
    padding: '2px 6px',
    borderRadius: '4px',
    cursor: 'pointer',
    lineHeight: 1.2,
  } as React.CSSProperties,
  rightChatPanel: {
    flex: '1 1 80%',
    width: '80%',
    maxWidth: '80%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#efeae2',
    overflow: 'hidden',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  activeChatInterface: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: '100%',
    overflow: 'hidden',
  } as React.CSSProperties,
  chatHeaderBar: {
    padding: '14px 24px',
    backgroundColor: '#f0f2f5',
    borderBottom: '1px solid #e3e6e9',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    flexShrink: 0,
  } as React.CSSProperties,
  headerProfileName: { margin: 0, fontSize: '16px', fontWeight: '600', color: '#111b21' } as React.CSSProperties,
  headerProfileMeta: { margin: '2px 0 0 0', fontSize: '12px', color: '#667781' } as React.CSSProperties,
  legendRow: { display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' } as React.CSSProperties,
  legendChip: (actor: MessageActor) =>
    ({
      fontSize: '10px',
      fontWeight: 700,
      padding: '4px 8px',
      borderRadius: '999px',
      backgroundColor: ACTOR_THEME[actor].bg,
      color: actor === 'candidate' ? ACTOR_THEME[actor].textColor : ACTOR_THEME[actor].labelColor,
      border: actor === 'candidate' ? '1px solid #1e40af' : '1px solid rgba(0,0,0,0.06)',
    }) as React.CSSProperties,
  whatsappChatFeedSurface: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '20px 4%',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    backgroundImage:
      'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")',
    backgroundColor: '#efeae2',
    backgroundRepeat: 'repeat',
  } as React.CSSProperties,
  timelineDividerCenter: {
    display: 'flex',
    justifyContent: 'center',
    width: '100%',
    margin: '14px 0',
  } as React.CSSProperties,
  timelineBadgeBubble: {
    backgroundColor: '#ffffff',
    color: '#54656f',
    fontSize: '12px',
    padding: '5px 12px',
    borderRadius: '7px',
    boxShadow: '0 1px 1px rgba(0,0,0,0.08)',
    textTransform: 'capitalize',
  } as React.CSSProperties,
  messageStreamRow: { display: 'flex', width: '100%', margin: '2px 0' } as React.CSSProperties,
  messageBubbleCell: {
    maxWidth: '65%',
    minWidth: 0,
    padding: '8px 12px 10px 12px',
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    wordBreak: 'break-word',
  } as React.CSSProperties,
  bubbleTextString: {
    margin: 0,
    color: '#111b21',
    whiteSpace: 'pre-wrap',
    paddingRight: '45px',
    fontSize: '14px',
    lineHeight: 1.45,
  } as React.CSSProperties,
  bubbleTimestampLabel: {
    fontSize: '10.5px',
    color: '#667781',
    position: 'absolute',
    bottom: '3px',
    right: '8px',
  } as React.CSSProperties,
  emptyConversationPrompt: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    margin: 'auto',
    padding: '32px',
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    borderRadius: '12px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
    textAlign: 'center',
    maxWidth: '420px',
  } as React.CSSProperties,
  emptyWorkspaceGrid: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f8fafc',
  } as React.CSSProperties,
  downloadFileActionLink: {
    fontSize: '12px',
    color: '#0284c7',
    textDecoration: 'none',
    fontWeight: 600,
    wordBreak: 'break-all',
  } as React.CSSProperties,
};
