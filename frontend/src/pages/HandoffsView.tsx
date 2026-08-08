import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Bot, Archive, Map } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import LeadStudyInterestPanel from '../components/LeadStudyInterestPanel';
import StudentJourneyPanel from '../components/StudentJourneyPanel';
import LeadQueueSidebarFilters from '../components/LeadQueueSidebarFilters';
import QueuePaginationControls from '../components/QueuePaginationControls';
import AiActivePulseBoard from '../components/AiActivePulseBoard';
import HeadlessScrollArea, {
  type HeadlessScrollAreaHandle,
} from '../components/HeadlessScrollArea';
import {
  buildLeadQueueQueryParams,
  DEFAULT_CONTACT_STATUS,
  DEFAULT_INTERACTION_DAYS,
  formatViewingRecordsLabel,
  HANDOFFS_PAGE_SIZE_KEY,
  interactionDaysEmptyLabel,
  persistLeadQueuePageSize,
  readLeadQueuePageSize,
  type ContactStatusFilter,
  type InteractionDaysFilter,
  type LeadQueuePageSize,
} from '../utils/leadQueueFilters';

interface MessagePayload {
  id?: number | string;
  sender: 'candidate' | 'student' | 'advisor' | 'system';
  senderName: string;
  text: string;
  created_at?: string;
  media_url?: string;
  file_name?: string;
  is_read?: boolean;
}

interface Lead {
  id: number;
  name?: string;
  full_name?: string;
  phone?: string;
  phone_number?: string;
  email: string;
  stage: string;
  is_human_locked?: boolean;
  academic_summary?: string;
  last_interaction_summary?: string;
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  target_degree?: string | null;
  target_major?: string | null;
  current_location?: string | null;
  study_interest_complete?: boolean;
  intake_step?: string;
  intake_step_label?: string;
  intake_complete?: boolean;
  wants_consultation_call?: boolean | null;
  consultation_scheduled_at?: string | null;
  consultation_session_date?: string | null;
  consultation_session_time?: string | null;
  assigned_counsellor_name?: string | null;
  appointment_status?: string | null;
  english_test_scores?: string | null;
  gre_score?: string | null;
  gmat_score?: string | null;
  test_scores?: string | null;
  messages?: MessagePayload[];
  updated_at?: string;
  latest_interaction_time?: string;
  total_messages_received: number;
  unread_count?: number;
  has_ai_messages?: boolean;
  has_messages?: boolean;
}

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

const normalizeMessage = (msg: Record<string, unknown>): MessagePayload => {
  const senderRaw = String(msg.sender || 'candidate');
  const sender =
    senderRaw === 'student' ? 'candidate' : (senderRaw as MessagePayload['sender']);
  return {
    id: msg.id as number | string | undefined,
    sender,
    senderName: String(
      msg.senderName ||
        (sender === 'advisor' ? 'Advisor' : sender === 'system' ? 'System' : 'Candidate')
    ),
    text: String(msg.text || msg.body || ''),
    created_at: msg.created_at as string | undefined,
    media_url: msg.media_url as string | undefined,
    file_name: msg.file_name as string | undefined,
    is_read: Boolean(msg.is_read),
  };
};

const mapLeadFromApi = (lead: Record<string, unknown>): Lead => {
  const rawMessages = (lead.messages || lead.chat_history || lead.history || []) as Record<
    string,
    unknown
  >[];
  return {
    id: lead.id as number,
    name: lead.name as string | undefined,
    full_name: (lead.full_name || lead.name) as string | undefined,
    phone: lead.phone as string | undefined,
    phone_number: lead.phone_number as string | undefined,
    email: (lead.email || '') as string,
    stage: (lead.stage || lead.status || 'HANDOFF') as string,
    is_human_locked: Boolean(lead.is_human_locked || lead.human_locked),
    academic_summary: lead.academic_summary as string | undefined,
    last_interaction_summary: lead.last_interaction_summary as string | undefined,
    preferred_country: (lead.preferred_country as string | null | undefined) ?? null,
    preferred_course: (lead.preferred_course as string | null | undefined) ?? null,
    target_program: (lead.target_program as string | null | undefined) ?? null,
    target_degree: (lead.target_degree as string | null | undefined) ?? null,
    target_major: (lead.target_major as string | null | undefined) ?? null,
    current_location: (lead.current_location as string | null | undefined) ?? null,
    study_interest_complete: Boolean(lead.study_interest_complete),
    intake_step: lead.intake_step as string | undefined,
    intake_step_label: lead.intake_step_label as string | undefined,
    intake_complete: Boolean(lead.intake_complete),
    wants_consultation_call: (lead.wants_consultation_call as boolean | null | undefined) ?? null,
    consultation_scheduled_at: (lead.consultation_scheduled_at as string | null | undefined) ?? null,
    consultation_session_date: (lead.consultation_session_date as string | null | undefined) ?? null,
    consultation_session_time: (lead.consultation_session_time as string | null | undefined) ?? null,
    assigned_counsellor_name: (lead.assigned_counsellor_name as string | null | undefined) ?? null,
    appointment_status: (lead.appointment_status as string | null | undefined) ?? null,
    english_test_scores: (lead.english_test_scores as string | null | undefined) ?? null,
    gre_score: (lead.gre_score as string | null | undefined) ?? null,
    gmat_score: (lead.gmat_score as string | null | undefined) ?? null,
    test_scores: (lead.test_scores as string | null | undefined) ?? null,
    messages: rawMessages.map(normalizeMessage),
    updated_at: lead.updated_at as string | undefined,
    latest_interaction_time: lead.latest_interaction_time as string | undefined,
    total_messages_received: Number(lead.total_messages_received ?? 0),
    unread_count: Number(lead.unread_count ?? 0),
    has_ai_messages: Boolean(lead.has_ai_messages),
    has_messages:
      typeof lead.has_messages === 'boolean'
        ? Boolean(lead.has_messages)
        : Boolean(lead.has_ai_messages) ||
          Number(lead.total_messages_received ?? 0) > 0 ||
          rawMessages.length > 0,
  };
};

const getUnreadCount = (lead: Lead): number => {
  if (typeof lead.unread_count === 'number' && !Number.isNaN(lead.unread_count)) {
    return lead.unread_count;
  }
  return (lead.messages || []).filter(
    msg => (msg.sender === 'candidate' || msg.sender === 'student') && !msg.is_read
  ).length;
};

const getLeadActivityTime = (lead: Lead): number => {
  const latestFromMessages = (lead.messages || []).reduce((max, msg) => {
    const time = new Date(msg.created_at || 0).getTime();
    return time > max ? time : max;
  }, 0);

  if (latestFromMessages > 0) return latestFromMessages;
  if (lead.latest_interaction_time) {
    return new Date(lead.latest_interaction_time).getTime();
  }
  return new Date(lead.updated_at || 0).getTime();
};

const sortHandoffLeads = (a: Lead, b: Lead): number => {
  const aContacted = Number(
    Boolean(a.has_messages ?? a.has_ai_messages ?? (a.messages?.length ?? 0) > 0)
  );
  const bContacted = Number(
    Boolean(b.has_messages ?? b.has_ai_messages ?? (b.messages?.length ?? 0) > 0)
  );
  if (bContacted !== aContacted) return bContacted - aContacted;

  const unreadDiff = getUnreadCount(b) - getUnreadCount(a);
  if (unreadDiff !== 0) return unreadDiff;
  const dateDiff = getLeadActivityTime(b) - getLeadActivityTime(a);
  if (dateDiff !== 0) return dateDiff;
  return getUnreadCount(b) - getUnreadCount(a);
};

const EMOJI_LIST = [
  '😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', 
  '😇', '🙂', '🙃', '😉', '😌', '😍', '🥰', '😘', '😗', 
  '😙', '😚', '😋', '😛', '😝', '😜', '🤪', '🤨', '🧐', 
  '🤓', '😎', '🥸', '🤩', '🥳', '😏', '😒', '😞', '😔', 
  '✍️', '👍', '👎', '🙌', '👏', '🙏', '💡', '🔥', '✅', 
  '❌', '❤️', '✨'
];

const TRANSITION_OPTIONS = [
  { key: 'ai-active', label: 'AI ACTIVE', icon: Bot },
  { key: 'archive', label: 'ARCHIVE', icon: Archive },
] as const;

const normalizeStatus = (status?: string): string =>
  (status || '').toUpperCase().replace(/-/g, '_');

const isHandoffLead = (lead: Lead): boolean => {
  const stage = normalizeStatus(lead.stage);
  return stage.includes('HANDOFF') || stage.includes('HUMAN') || lead.is_human_locked === true;
};

export default function HandoffsView() {
  const { formatTime, formatDateGroup } = useBusinessTimezone();
  const [leadsQueue, setLeadsQueue] = useState<Lead[]>([]);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [interactionDays, setInteractionDays] = useState<InteractionDaysFilter>(DEFAULT_INTERACTION_DAYS);
  const [contactStatus, setContactStatus] = useState<ContactStatusFilter>(DEFAULT_CONTACT_STATUS);
  const [pageSize, setPageSize] = useState<LeadQueuePageSize>(() =>
    readLeadQueuePageSize(HANDOFFS_PAGE_SIZE_KEY)
  );
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMorePages, setHasMorePages] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatingRowId, setUpdatingRowId] = useState<number | null>(null);
  const [journeyModal, setJourneyModal] = useState<{
    studentId: number;
    studentName: string;
  } | null>(null);
  
  const chatTopRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const emojiPickerRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HeadlessScrollAreaHandle | null>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);

  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const containsOnlyEmojis = (text: string): boolean => {
    if (typeof text !== 'string') return false;
    const cleanText = text.replace(/\s/g, '');
    if (!cleanText) return false;
    const emojiRegex = /^[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{2A00}-\u{2AFF}]+$/u;
    return emojiRegex.test(cleanText);
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (emojiPickerRef.current && !emojiPickerRef.current.contains(event.target as Node)) {
        setShowEmojiPicker(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    setPage(1);
    setLeadsQueue([]);
    setTotalCount(0);
  }, [pageSize, interactionDays, contactStatus, debouncedSearch]);

  const handlePageSizeChange = useCallback((next: LeadQueuePageSize) => {
    persistLeadQueuePageSize(HANDOFFS_PAGE_SIZE_KEY, next);
    setPageSize(next);
  }, []);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize) || 1);
  const rangeStart = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, totalCount);

  const emptyQueueMessage = useMemo(() => {
    if (debouncedSearch) return 'No matching candidates found.';
    if (interactionDays === 0) return 'No candidates in the handoff queue.';
    return `No candidates with activity in ${interactionDaysEmptyLabel(interactionDays)}.`;
  }, [debouncedSearch, interactionDays]);

  const fetchHandoffQueue = useCallback(async (signal?: AbortSignal) => {
    try {
      const query = new URLSearchParams(
        buildLeadQueueQueryParams(interactionDays, debouncedSearch, contactStatus)
      );
      const safePage = Math.max(1, page);
      const offset = (safePage - 1) * pageSize;
      query.set('limit', String(pageSize));
      query.set('offset', String(offset));
      const data = await apiFetch(`leads/queue?${query.toString()}`, { signal });
      if (signal?.aborted) return;

      let rows: unknown[] = [];
      let nextTotal = 0;
      let nextHasMore = false;
      if (Array.isArray(data)) {
        rows = data;
        nextTotal = data.length;
        nextHasMore = false;
      } else if (data && typeof data === 'object') {
        const payload = data as {
          items?: unknown[];
          total_count?: number;
          has_more?: boolean;
        };
        rows = Array.isArray(payload.items) ? payload.items : [];
        nextTotal = Number(payload.total_count ?? rows.length) || 0;
        nextHasMore = Boolean(payload.has_more ?? offset + rows.length < nextTotal);
      }

      const handoffOnly = rows
        .map(item => mapLeadFromApi(item as Record<string, unknown>))
        .filter(isHandoffLead)
        .sort(sortHandoffLeads);
      if (signal?.aborted) return;

      setLeadsQueue(handoffOnly);
      setTotalCount(nextTotal);
      setHasMorePages(nextHasMore);
      setLoadError(null);

      setSelectedLead(prev => {
        // Keep an explicit selection in sync; do not auto-select on first load
        // so the right panel can show the living pulse overview.
        if (!prev) return null;
        const updatedLead = handoffOnly.find((l: Lead) => l.id === prev.id);
        if (!updatedLead) return null;

        const prevCount = (prev.messages || []).length;
        const nextCount = (updatedLead.messages || []).length;
        if (nextCount >= prevCount) return updatedLead;

        return { ...updatedLead, messages: prev.messages };
      });
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Failed to fetch handoff queue:', error);
        setLoadError(error.message || 'Failed to load handoff queue.');
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, [interactionDays, contactStatus, debouncedSearch, page, pageSize]);

  useEffect(() => {
    let isActive = true;
    async function executionLoop(isFirst = false) {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      abortControllerRef.current = new AbortController();
      if (isFirst) setIsLoading(true);
      await fetchHandoffQueue(abortControllerRef.current.signal);
      if (isActive) pollingTimerRef.current = setTimeout(() => executionLoop(false), 4000);
    }
    executionLoop(true);
    return () => {
      isActive = false;
      if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [fetchHandoffQueue]);

  useEffect(() => {
    if (!selectedLead?.id) return;

    let isActive = true;

    const refreshSelectedConversation = async () => {
      try {
        const data = await apiFetch(`leads/${selectedLead.id}`);
        if (!isActive) return;

        const mapped = mapLeadFromApi(data as Record<string, unknown>);
        setSelectedLead(mapped);
        setLeadsQueue(prev =>
          prev.map(item => (item.id === mapped.id ? { ...item, ...mapped } : item))
        );
      } catch (error: unknown) {
        if (error instanceof Error && error.name !== 'AbortError') {
          console.error('Failed to refresh handoff conversation:', error);
        }
      }
    };

    refreshSelectedConversation();
    const interval = setInterval(refreshSelectedConversation, 3000);

    return () => {
      isActive = false;
      clearInterval(interval);
    };
  }, [selectedLead?.id]);

  const handleTransitionStatus = async (
    event: React.MouseEvent,
    leadId: number,
    targetStatus: 'ai-active' | 'archive'
  ) => {
    event.stopPropagation();
    setUpdatingRowId(leadId);

    try {
      await apiFetch(`leads/${leadId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: targetStatus }),
      });

      setLeadsQueue(prev => prev.filter(l => l.id !== leadId));
      setSelectedLead(prev => (prev?.id === leadId ? null : prev));
    } catch (error) {
      console.error('Handoff status update error:', error);
    } finally {
      setUpdatingRowId(null);
    }
  };

  const handleSelectLead = async (lead: Lead) => {
    setSelectedLead(lead);

    if (getUnreadCount(lead) === 0) return;

    try {
      await apiFetch(`leads/${lead.id}/mark-read`, { method: 'POST' });

      const markMessagesRead = (messages?: MessagePayload[]) =>
        (messages || []).map(message =>
          message.sender === 'candidate' || message.sender === 'student'
            ? { ...message, is_read: true }
            : message
        );

      setLeadsQueue(prev =>
        prev.map(item =>
          item.id === lead.id
            ? {
                ...item,
                unread_count: 0,
                messages: markMessagesRead(item.messages),
              }
            : item
        )
      );

      setSelectedLead(prev =>
        prev?.id === lead.id
          ? {
              ...prev,
              unread_count: 0,
              messages: markMessagesRead(prev.messages),
            }
          : prev
      );
    } catch (error) {
      console.error('Failed to mark handoff messages as read:', error);
    }
  };

  const forceScrollToAbsoluteBottom = () => {
    const container = chatContainerRef.current?.getViewport();
    if (!container) return null;

    container.scrollTop = container.scrollHeight;

    requestAnimationFrame(() => {
      if (container) container.scrollTop = container.scrollHeight;
    });

    return setTimeout(() => {
      if (container) {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: 'smooth'
        });
      }
    }, 120);
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const container = chatContainerRef.current?.getViewport();
    if (!container) return;

    let timerId = forceScrollToAbsoluteBottom();

    const ResizeObserverClass = window.ResizeObserver || (window as any).WebKitResizeObserver;
    if (!ResizeObserverClass) return;

    const observer = new ResizeObserverClass(() => {
      if (timerId) clearTimeout(timerId);
      timerId = forceScrollToAbsoluteBottom();
    });
    
    observer.observe(container);

    return () => {
      observer.disconnect();
      if (timerId) clearTimeout(timerId);
    };
  }, [selectedLead?.id, selectedLead?.messages?.length]);

  useEffect(() => {
    if (selectedLead && chatInputRef.current) {
      const timer = setTimeout(() => {
        chatInputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [selectedLead?.id]);

  const handleJumpToNewest = () => {
    forceScrollToAbsoluteBottom();
  };

  const handleSendMessage = async (e: React.FormEvent) => {
  e.preventDefault();
  const outboundText = messageText.trim();
  if (!outboundText || !selectedLead) return;

  const currentPhone = selectedLead.phone || selectedLead.phone_number || '';
  if (!currentPhone) {
    alert("Cannot send text: Missing phone assignment on profile.");
    return;
  }

  // 1. Generate an optimistic local message object instantly
  const optimisticMessage: MessagePayload = {
    id: `optimistic-${Date.now()}`,
    sender: 'advisor',
    senderName: 'Advisor',
    text: outboundText,
    created_at: new Date().toISOString()
  };

  // 2. Append to UI immediately so the user sees it vanish from the input
  setSelectedLead(prev => {
    if (!prev) return null;
    return {
      ...prev,
      messages: [...(prev.messages || []), optimisticMessage]
    };
  });

  // 3. Reset input layout fields instantly
  setMessageText('');
  chatInputRef.current?.focus();
  setTimeout(forceScrollToAbsoluteBottom, 10);

  // 4. Define the background network pipeline with automatic retry logic
  const sendWithRetry = (textToSend: string, phoneToSend: string, retriesLeft = 3, currentDelay = 1000) => {
    apiFetch('leads/webhook/social-ingress', {
      method: 'POST',
      body: JSON.stringify({
        lead_id: selectedLead.id,
        phone: phoneToSend.trim(),
        email: selectedLead.email,
        message: textToSend,
        institution: 'Manual Advisor Intervention',
      }),
    })
    .then(async (response) => {
      if (response && typeof response === 'object') {
        const mapped = mapLeadFromApi(response as Record<string, unknown>);
        setSelectedLead(mapped);
      }
      await fetchHandoffQueue();
    })
    .catch((error) => {
      // If a true network disconnect / "Failed to fetch" happens, catch and retry
      if (retriesLeft > 0) {
        console.warn(`Upstream connection dropped. Automatically re-attempting upstream connections... (${retriesLeft} retries left)`);
        setTimeout(() => sendWithRetry(textToSend, phoneToSend, retriesLeft - 1, currentDelay * 1.5), currentDelay);
      } else {
        console.error("Background transmission breakdown permanently exhausted:", error);
      }
    });
  };

  // 5. Fire off the execution chain down the background thread
  sendWithRetry(outboundText, currentPhone);
};

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedLead) return;

    const currentPhone = selectedLead.phone || selectedLead.phone_number || '';
    if (!currentPhone) {
      alert("Cannot send document: Missing phone assignment on profile.");
      return;
    }

    if (fileInputRef.current) fileInputRef.current.value = ''; 

    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const base64Data = reader.result;
      
      apiFetch('leads/webhook/social-ingress', {
        method: 'POST',
        body: JSON.stringify({
          lead_id: selectedLead.id,
          phone: currentPhone.trim(),
          email: selectedLead.email,
          institution: 'Manual Advisor Document Dispatch',
          message: `📁 Sent File: ${file.name}`,
          attachment: base64Data,
          fileName: file.name,
          fileType: file.type,
        }),
      })
        .then(async (response) => {
          if (response && typeof response === 'object') {
            const mapped = mapLeadFromApi(response as Record<string, unknown>);
            setSelectedLead(mapped);
          }
          await fetchHandoffQueue();
          setTimeout(forceScrollToAbsoluteBottom, 50);
          chatInputRef.current?.focus();
        })
        .catch((err) => {
          console.error('File pipeline execution error:', err);
          alert('Failed to deliver document package to server.');
        });
    };
  };

  const handleAppendEmoji = (emoji: string) => {
    setMessageText(prev => prev + emoji);
    setTimeout(() => {
      chatInputRef.current?.focus();
    }, 10);
  };


  const groupedMessages = useMemo(() => {
    if (!selectedLead) return {};

    const rawMessages = selectedLead.messages || [];
    const processed: MessagePayload[] = [...rawMessages].filter(msg =>
      !(msg.text || '').includes("Got it! Your update has been logged on your dashboard matrix timeline.")
    );

    const rawLogs = selectedLead.academic_summary || selectedLead.last_interaction_summary || '';
    if (rawLogs) {
      rawLogs.split('\n').forEach((line, index) => {
        const clean = line.trim();
        if (!clean || clean.includes("Got it! Your update has been logged on your dashboard matrix timeline.")) return;

        let extractedMediaUrl = undefined;
        let extractedFileName = undefined;

        if (clean.includes("http://") || clean.includes("https://")) {
          const urlMatch = clean.match(/https?:\/\/[^\s]+/);
          if (urlMatch) {
            extractedMediaUrl = urlMatch[0];
            extractedFileName = "Attached Media Document";
          }
        }

        if (clean.startsWith('Candidate:') || clean.startsWith('student:')) {
          processed.push({ 
            id: `log-${index}`, 
            sender: 'candidate', 
            senderName: selectedLead.name || 'Candidate', 
            text: clean.replace(/^(Candidate:|student:)\s*/i, ''),
            media_url: extractedMediaUrl,
            file_name: extractedFileName
          });
        } else if (clean.startsWith('Advisor:')) {
          processed.push({ 
            id: `log-${index}`, 
            sender: 'advisor', 
            senderName: 'Advisor', 
            text: clean.replace(/^Advisor:\s*/i, ''),
            media_url: extractedMediaUrl,
            file_name: extractedFileName
          });
        } else if (clean.startsWith('[')) {
          processed.push({ id: `log-${index}`, sender: 'system', senderName: 'System', text: clean });
        }
      });
    }

    const groups: { [key: string]: MessagePayload[] } = {};
    processed.forEach((msg) => {
      const label = formatDateGroup(msg.created_at);
      if (!groups[label]) groups[label] = [];
      groups[label].push(msg);
    });

    return groups;
  }, [selectedLead, formatDateGroup]);

  const hasNoMessages = useMemo(() => {
    return Object.keys(groupedMessages).length === 0;
  }, [groupedMessages]);

  const renderMessageContent = (msg: MessagePayload) => {
    const targetUrl = msg.media_url || (typeof msg.text === 'string' && msg.text.startsWith('data:') ? msg.text : null);
    const isImage = targetUrl && (targetUrl.includes('.png') || targetUrl.includes('.jpg') || targetUrl.includes('.jpeg') || targetUrl.startsWith('data:image/'));
    const resolvedFileName = msg.file_name || (typeof msg.text === 'string' && !msg.text.startsWith('data:') ? msg.text : 'Image_Attachment.jpg');

    if (targetUrl) {
      return (
        <div style={styles.mediaAttachmentBubble}>
          {isImage ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: '600', color: '#111b21' }}>
                <span>🖼️</span>
                <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: '180px' }}>
                  {resolvedFileName}
                </span>
              </div>
              <img src={targetUrl} alt={resolvedFileName} style={styles.inlineImagePreview} />
              <a href={targetUrl} target="_blank" rel="noreferrer" style={styles.downloadFileActionLink}>
                VIEW IMAGE ATTACHMENT ↗
              </a>
            </div>
          ) : (
            <div style={styles.fileDocumentCardRow}>
              <span style={{ fontSize: '28px' }}>📄</span>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <p style={styles.documentFilenameText}>{resolvedFileName}</p>
                <a href={targetUrl} target="_blank" rel="noreferrer" download style={styles.downloadFileActionLink}>
                  Download & Open File
                </a>
              </div>
            </div>
          )}
          {(!isImage && msg.text && !msg.text.startsWith('data:')) && (
            <p style={{ 
              ...styles.bubbleTextString, 
              fontSize: containsOnlyEmojis(msg.text) ? '32px' : '16px',
              marginTop: '8px', 
              paddingRight: 0 
            }}>{msg.text}</p>
          )}
        </div>
      );
    }

    const pureEmoji = containsOnlyEmojis(msg.text);
    return (
      <p style={{ 
        ...styles.bubbleTextString, 
        fontSize: pureEmoji ? '32px' : '16px',
        lineHeight: pureEmoji ? '1.2' : '1.45'
      }}>
        {msg.text}
      </p>
    );
  };

  return (
    <>
    <div style={styles.workspaceContainer}>
      
      <style>{`
        html, body, #root { overflow: hidden !important; }
        
        .emoji-grid-btn { 
          background: none; 
          border: none; 
          font-size: 34px; 
          cursor: pointer; 
          padding: 4px; 
          border-radius: 8px; 
          transition: transform 0.1s, background 0.1s;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .emoji-grid-btn:hover { 
          background: #f1f5f9; 
          transform: scale(1.15);
        }

        .large-chat-input::placeholder {
          font-size: 22px;
          color: #94a3b8;
        }

        .no-scroll-tray {
          overflow: hidden !important;
        }
        .no-scroll-tray::-webkit-scrollbar {
          display: none !important;
          width: 0 !important;
          height: 0 !important;
        }

        .handoff-status-btn {
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
        .handoff-status-btn:hover {
          width: 96px;
        }
        .handoff-status-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .handoff-status-btn-label {
          display: none;
          margin-left: 8px;
          font-size: 8px;
          font-weight: 800;
          text-transform: uppercase;
          white-space: nowrap;
        }
        .handoff-status-btn:hover .handoff-status-btn-label {
          display: block;
        }
      `}</style>
      
      <div style={styles.leftSidebarPanel}>
        <div style={styles.sidebarHeader}>
          <div style={styles.sidebarHeaderText}>
            <h2 style={styles.sidebarTitle}>Queue</h2>
            <p
              style={styles.viewingRecordsLabel}
              title={
                totalCount > 0
                  ? formatViewingRecordsLabel(rangeStart, rangeEnd, totalCount)
                  : 'No candidates in the filtered queue'
              }
            >
              {formatViewingRecordsLabel(rangeStart, rangeEnd, totalCount)}
            </p>
          </div>
          <span style={styles.activeCounterBadge}>
            {totalCount > 0 ? `${rangeStart}–${rangeEnd}/${totalCount}` : 0}
          </span>
        </div>

        {!isLoading && !loadError && (totalCount > 0 || leadsQueue.length > 0) ? (
          <QueuePaginationControls
            page={page}
            totalPages={totalPages}
            hasMorePages={hasMorePages}
            disabled={isLoading}
            onPageChange={setPage}
            style={styles.sidebarPaginationHeader}
          />
        ) : null}

        <LeadQueueSidebarFilters
          interactionDays={interactionDays}
          onInteractionDaysChange={setInteractionDays}
          contactStatus={contactStatus}
          onContactStatusChange={setContactStatus}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          pageSize={pageSize}
          onPageSizeChange={handlePageSizeChange}
        />
        
        <HeadlessScrollArea
          className="flex-1 min-h-0"
          style={styles.leadScrollList}
          viewportStyle={styles.leadScrollViewport}
        >
          {isLoading ? (
            <div style={styles.emptyListPlaceholder}>Loading handoff queue...</div>
          ) : loadError ? (
            <div style={styles.emptyListPlaceholder}>{loadError}</div>
          ) : leadsQueue.length === 0 ? (
            <div style={styles.emptyListPlaceholder}>{emptyQueueMessage}</div>
          ) : (
            <>
            {leadsQueue.map((lead) => {
              const isSelected = selectedLead?.id === lead.id;
              const badgeStyle = getStatusBadgeStyle(lead.stage);
              const unreadCount = getUnreadCount(lead);

              return (
                <div
                  key={lead.id}
                  onClick={() => handleSelectLead(lead)}
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
                        {lead.name || lead.full_name || 'Unknown'}
                      </h4>
                      {unreadCount > 0 && (
                        <span
                          style={styles.receivedCountBadge}
                          title="Unread messages from candidate"
                        >
                          {unreadCount}
                        </span>
                      )}
                    </div>
                    <div style={styles.statusActionGroup}>
                      {TRANSITION_OPTIONS.map(({ key, label, icon: Icon }) => (
                        <button
                          key={key}
                          type="button"
                          className="handoff-status-btn"
                          title={label}
                          disabled={updatingRowId === lead.id}
                          onClick={(event) => handleTransitionStatus(event, lead.id, key)}
                        >
                          <Icon size={14} />
                          <span className="handoff-status-btn-label">{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={styles.cardBottomRow}>
                    <p style={styles.leadCardMeta}>
                      {lead.phone || lead.phone_number || 'No Phone'}
                      {lead.email ? ` · ${lead.email}` : ''}
                    </p>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleSelectLead(lead);
                      }}
                      style={{
                        ...styles.statusLabelButton,
                        ...badgeStyle,
                      }}
                      title="View conversation"
                    >
                      {formatStatusLabel(lead.stage)}
                    </button>
                  </div>
                </div>
              );
            })}
            </>
          )}
        </HeadlessScrollArea>

        {!isLoading && !loadError && (totalCount > 0 || leadsQueue.length > 0) ? (
          <QueuePaginationControls
            page={page}
            totalPages={totalPages}
            hasMorePages={hasMorePages}
            disabled={isLoading}
            onPageChange={setPage}
            style={styles.sidebarPagination}
          />
        ) : null}
      </div>

      <div style={styles.rightChatPanel}>
        {selectedLead ? (
          <div style={styles.activeChatInterface}>
            
            <div style={styles.chatHeaderBar}>
              <div style={{ flex: 1 }}>
                <h3 style={styles.headerProfileName}>{selectedLead.name || selectedLead.full_name}</h3>
                <p style={styles.headerProfileMeta}>📱 {selectedLead.phone || selectedLead.phone_number} | 📧 {selectedLead.email}</p>
              </div>
              
              <div style={styles.headerActionGroup}>
              {!hasNoMessages && (
                <button type="button" onClick={handleJumpToNewest} style={styles.jumpToNewestButton}>
                  Jump to newest <span style={styles.arrowIconString}>▼▼</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedLead(null)}
                style={styles.headerOverviewButton}
                title="Back to handoff pulse overview"
              >
                Overview
              </button>
              <button
                type="button"
                onClick={() =>
                  setJourneyModal({
                    studentId: selectedLead.id,
                    studentName: selectedLead.name || selectedLead.full_name || `Lead #${selectedLead.id}`,
                  })
                }
                style={styles.headerJourneyButton}
                title="View student journey timeline"
              >
                <Map size={14} />
                Journey
              </button>
              </div>
            </div>

            <LeadStudyInterestPanel lead={selectedLead} compact />

            <HeadlessScrollArea
              ref={chatContainerRef}
              className="flex-1 min-h-0"
              style={styles.whatsappChatFeedShell}
              viewportStyle={styles.whatsappChatFeedSurface}
            >
              <div ref={chatTopRef} style={{ height: '1px', width: '100%', }} />

              {hasNoMessages ? (
                <div style={styles.emptyConversationPrompt}>
                  <div style={{ fontSize: '32px', marginBottom: '8px' }}>💬</div>
                  <h4 style={{ margin: '0 0 4px 0', color: '#334155', fontWeight: '600' }}>No Messages Available</h4>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '13px', lineHeight: '1.4' }}>
                    There is no prior WhatsApp history logged for this user profile.
                  </p>
                </div>
              ) : (
                Object.keys(groupedMessages).map((dateLabel) => (
                  <div key={dateLabel} style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
                    
                    <div style={styles.timelineDividerCenter}>
                      <span style={styles.timelineBadgeBubble}>{dateLabel}</span>
                    </div>

                    {groupedMessages[dateLabel].map((msg, index) => {
                      if (msg.sender === 'system') {
                        return (
                          <div key={msg.id || index} style={styles.systemLogCentralRow}>
                            <span>{msg.text}</span>
                          </div>
                        );
                      }

                      const isAdvisorOutbound = msg.sender === 'advisor';

                      return (
                        <div 
                          key={msg.id || index} 
                          style={{
                            ...styles.messageStreamRow,
                            justifyContent: isAdvisorOutbound ? 'flex-end' : 'flex-start'
                          }}
                        >
                          <div style={{
                            ...styles.messageBubbleCell,
                            backgroundColor: isAdvisorOutbound ? '#dcfce7' : '#ffffff',
                            borderRadius: isAdvisorOutbound ? '8px 8px 0px 8px' : '8px 8px 8px 0px',
                            boxShadow: '0 1px 1px rgba(0,0,0,0.12)'
                          }}>
                            {renderMessageContent(msg)}
                            
                            {msg.created_at && (
                              <span style={styles.bubbleTimestampLabel}>
                                {formatTime(msg.created_at)}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}

                  </div>
                ))
              )}
              <div ref={chatEndRef} style={{ height: '1px', width: '100%' }} />
            </HeadlessScrollArea>

            <form onSubmit={handleSendMessage} style={styles.footerInputFormBar}>
              
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={styles.mediaEmbedIconButton}
                title="Attach document to WhatsApp"
              >
                📎
              </button>
              <input 
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                style={{ display: 'none' }}
                accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt"
              />

              <div style={{ position: 'relative' }} ref={emojiPickerRef}>
                <button
                  type="button"
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  style={styles.mediaEmbedIconButton}
                  title="Choose Emoji"
                >
                  😃
                </button>

                {showEmojiPicker && (
                  <div className="no-scroll-tray" style={styles.emojiFloatingTray}>
                    <div className="no-scroll-tray" style={styles.emojiGridWrapper}>
                      {EMOJI_LIST.map((emoji) => (
                        <button
                          key={emoji}
                          type="button"
                          className="emoji-grid-btn"
                          onClick={() => {
                            handleAppendEmoji(emoji);
                            setShowEmojiPicker(false);
                          }}
                        >
                          {emoji}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <input
                type="text"
                id="whatsapp-message-input"
                name="messageText"
                ref={chatInputRef}
                className="large-chat-input"
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                placeholder="Type a WhatsApp message..."
                style={styles.footerTextInputField}
              />
              <button
                type="submit"
                disabled={!messageText.trim()}
                style={{
                  ...styles.actionSendButton,
                  backgroundColor: !messageText.trim() ? '#cbd5e1' : '#322f86'
                }}
              >
                Send
              </button>
            </form>

          </div>
        ) : (
          <AiActivePulseBoard
            mode="handoffs"
            leads={leadsQueue.map(lead => ({
              id: lead.id,
              name: lead.name || lead.full_name || `Lead #${lead.id}`,
              email: lead.email,
              phone: lead.phone,
              phone_number: lead.phone_number,
              preferred_country: lead.preferred_country,
              preferred_course: lead.preferred_course,
              target_program: lead.target_program,
              target_degree: lead.target_degree,
              target_major: lead.target_major,
              current_location: lead.current_location,
              study_interest_complete: lead.study_interest_complete,
              intake_step: lead.intake_step,
              intake_step_label: lead.intake_step_label,
              intake_complete: lead.intake_complete,
              wants_consultation_call: lead.wants_consultation_call,
              consultation_scheduled_at: lead.consultation_scheduled_at,
              consultation_session_date: lead.consultation_session_date,
              consultation_session_time: lead.consultation_session_time,
              assigned_counsellor_name: lead.assigned_counsellor_name,
              appointment_status: lead.appointment_status,
              english_test_scores: lead.english_test_scores,
              gre_score: lead.gre_score,
              gmat_score: lead.gmat_score,
              test_scores: lead.test_scores,
              status: lead.stage,
              updated_at: lead.updated_at,
              latest_interaction_time: lead.latest_interaction_time,
              unread_count: lead.unread_count,
              total_messages_received: lead.total_messages_received,
              has_ai_messages: lead.has_ai_messages,
              messages: lead.messages,
            }))}
            isLoading={isLoading}
            onSelectLead={leadId => {
              const lead = leadsQueue.find(item => item.id === leadId);
              if (lead) void handleSelectLead(lead);
            }}
          />
        )}
      </div>

    </div>
    <StudentJourneyPanel
      open={journeyModal !== null}
      studentId={journeyModal?.studentId ?? null}
      studentName={journeyModal?.studentName}
      onClose={() => setJourneyModal(null)}
    />
    </>
  );
}

const styles = {
  workspaceContainer: { display: 'flex', width: '100%', height: '100%', position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#f8fafc', overflow: 'hidden', boxSizing: 'border-box', fontFamily: 'system-ui, -apple-system, sans-serif' } as React.CSSProperties,
  leftSidebarPanel: { width: '20%', minWidth: '280px', maxWidth: '20%', height: '100%', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff', overflow: 'hidden', boxSizing: 'border-box' } as React.CSSProperties,
  sidebarHeader: { padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexShrink: 0, gap: '10px' } as React.CSSProperties,
  sidebarHeaderText: { display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0, flex: 1 } as React.CSSProperties,
  sidebarTitle: { margin: 0, fontSize: '16px', fontWeight: '700', color: '#0f172a' } as React.CSSProperties,
  viewingRecordsLabel: {
    margin: 0,
    fontSize: '12px',
    fontWeight: 700,
    color: '#0f172a',
    lineHeight: 1.35,
  } as React.CSSProperties,
  activeCounterBadge: { backgroundColor: '#fee2e2', color: '#dc2626', padding: '2px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: '700', flexShrink: 0 } as React.CSSProperties,
  sidebarPagination: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    margin: 0,
    padding: '10px 12px',
    borderTop: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
    flexShrink: 0,
  } as React.CSSProperties,
  sidebarPaginationHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    margin: 0,
    padding: '8px 12px',
    borderBottom: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
    flexShrink: 0,
  } as React.CSSProperties,
  searchHeaderSection: { padding: '12px', borderBottom: '1px solid #e2e8f0', flexShrink: 0 } as React.CSSProperties,
  searchBarInput: { width: '100%', boxSizing: 'border-box', padding: '10px 12px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#0f172a', fontSize: '13px', outline: 'none' } as React.CSSProperties,
  leadScrollList: { flex: 1, minHeight: 0 } as React.CSSProperties,
  leadScrollViewport: {
    padding: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  } as React.CSSProperties,
  emptyListPlaceholder: { textAlign: 'center', padding: '40px 20px', color: '#94a3b8', fontSize: '13px' } as React.CSSProperties,
  leadInteractionCard: { padding: '8px 10px', borderRadius: '6px', border: '1px solid', transition: 'all 0.2s ease', flexShrink: 0, width: '100%', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: '2px' } as React.CSSProperties,
  cardTopRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' } as React.CSSProperties,
  cardBottomRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' } as React.CSSProperties,
  cardMainFrame: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '4px' } as React.CSSProperties,
  leadCardNameRow: { display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 } as React.CSSProperties,
  leadCardName: { margin: 0, fontSize: '14px', fontWeight: '700', color: '#322f86', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 } as React.CSSProperties,
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
  leadCardMeta: { margin: 0, fontSize: '10px', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 } as React.CSSProperties,
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
  rightChatPanel: { flex: '1 1 80%', width: '80%', maxWidth: '80%', height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#efeae2', overflow: 'hidden', boxSizing: 'border-box' } as React.CSSProperties,
  activeChatInterface: { display: 'flex', flexDirection: 'column', height: '100%', width: '100%', overflow: 'hidden' } as React.CSSProperties,
  chatHeaderBar: { padding: '14px 24px', backgroundColor: '#f0f2f5', borderBottom: '1px solid #e3e6e9', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', flexShrink: 0 } as React.CSSProperties,
  headerProfileName: { margin: 0, fontSize: '16px', fontWeight: '600', color: '#111b21' } as React.CSSProperties,
  headerProfileMeta: { margin: '2px 0 0 0', fontSize: '14px', color: '#667781' } as React.CSSProperties,
  jumpToNewestButton: { background: 'none', border: 'none', color: '#0284c7', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '5px', padding: '6px 12px', borderRadius: '6px', transition: 'background-color 0.15s ease' } as React.CSSProperties,
  headerActionGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexShrink: 0,
  } as React.CSSProperties,
  headerJourneyButton: {
    backgroundColor: '#ffffff',
    border: '1px solid #cbd5e1',
    color: '#334155',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '6px',
    flexShrink: 0,
  } as React.CSSProperties,
  arrowIconString: { fontSize: '10px', color: '#0284c7' } as React.CSSProperties,
  whatsappChatFeedShell: { flex: 1, minHeight: 0 } as React.CSSProperties,
  whatsappChatFeedSurface: {
    padding: '20px 4%',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    backgroundImage:
      'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")',
    backgroundColor: '#efeae2',
    backgroundRepeat: 'repeat',
  } as React.CSSProperties,
  timelineDividerCenter: { display: 'flex', justifyContent: 'center', width: '100%', margin: '14px 0' } as React.CSSProperties,
  timelineBadgeBubble: { backgroundColor: '#ffffff', color: '#54656f', fontSize: '12px', padding: '5px 12px', borderRadius: '7px', boxShadow: '0 1px 1px rgba(0,0,0,0.08)', textTransform: 'capitalize' } as React.CSSProperties,
  systemLogCentralRow: { display: 'flex', justifyContent: 'center', width: '100%', margin: '6px 0', fontSize: '12px', color: '#54656f', fontStyle: 'italic' } as React.CSSProperties,
  messageStreamRow: { display: 'flex', width: '100%', margin: '2px 0' } as React.CSSProperties,
  messageBubbleCell: { maxWidth: '65%', padding: '8px 12px 10px 12px', position: 'relative', display: 'flex', flexDirection: 'column', gap: '2px' } as React.CSSProperties,
  bubbleTextString: { margin: 0, color: '#111b21', whiteSpace: 'pre-wrap', paddingRight: '45px' } as React.CSSProperties,
  bubbleTimestampLabel: { fontSize: '10.5px', color: '#667781', position: 'absolute', bottom: '3px', right: '8px' } as React.CSSProperties,
  emptyConversationPrompt: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', margin: 'auto', padding: '32px', backgroundColor: 'rgba(255, 255, 255, 0.9)', borderRadius: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.05)', textAlign: 'center', maxWidth: '420px' } as React.CSSProperties,
  footerInputFormBar: { padding: '12px 18px', backgroundColor: '#f0f2f5', display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, position: 'relative' } as React.CSSProperties,
  footerTextInputField: { flex: 1, padding: '14px 18px', borderRadius: '8px', border: 'none', outline: 'none', backgroundColor: '#ffffff', fontSize: '24px', color: '#111b21', lineHeight: '1.4' } as React.CSSProperties,
  actionSendButton: { border: 'none', color: '#ffffff', padding: '12px 24px', borderRadius: '8px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', transition: 'background-color 0.2s' } as React.CSSProperties,
  mediaEmbedIconButton: { background: 'none', border: 'none', fontSize: '28px', cursor: 'pointer', padding: '6px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.15s' } as React.CSSProperties,
  emojiFloatingTray: { position: 'absolute', bottom: '70px', left: '15px', backgroundColor: '#ffffff', boxShadow: '0 6px 28px rgba(0,0,0,0.18)', borderRadius: '16px', padding: '16px', width: '620px', height: '280px', zIndex: 999, overflow: 'hidden' } as React.CSSProperties,
  emojiGridWrapper: { display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gap: '12px', width: '100%', height: '100%', overflow: 'hidden' } as React.CSSProperties,
  headerOverviewButton: {
    border: '1px solid #cbd5e1',
    backgroundColor: '#ffffff',
    color: '#322f86',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  emptyWorkspaceGrid: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc' } as React.CSSProperties,
  mediaAttachmentBubble: { display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '180px' } as React.CSSProperties,
  inlineImagePreview: { width: '100%', maxHeight: '240px', borderRadius: '6px', objectFit: 'cover', marginTop: '2px' } as React.CSSProperties,
  fileDocumentCardRow: { display: 'flex', alignItems: 'center', gap: '10px', backgroundColor: 'rgba(0,0,0,0.03)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(0,0,0,0.05)' } as React.CSSProperties,
  documentFilenameText: { margin: 0, fontSize: '14px', fontWeight: '600', color: '#111b21', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' } as React.CSSProperties,
  downloadFileActionLink: { fontSize: '12px', color: '#0284c7', textDecoration: 'none', fontWeight: '600', display: 'inline-block', marginTop: '2px' } as React.CSSProperties
};