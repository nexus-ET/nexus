import React, { useState, useEffect, useMemo, useRef } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

declare global {
  interface Window {
    __HARDWARE_INPUT_PERSIST_CACHE__?: string;
  }
}

interface MessagePayload {
  id?: number | string;
  sender: 'candidate' | 'advisor' | 'system';
  senderName: string;
  text: string;
  media_url?: string; 
  created_at?: string; 
  isOptimistic?: boolean; 
}

interface ActiveLeadPayload {
  id?: string | number;
  phone_number?: string;
  phone?: string;
  email?: string;
  name?: string;
  full_name?: string;
  stage?: string;
  messages?: any[];
  chat_history?: any[];
  history?: any[];
  academic_summary?: string;
  last_interaction_summary?: string;
}

interface AdvisorChatPanelProps {
  activeLead: ActiveLeadPayload | null;
  setActiveLead: (lead: ActiveLeadPayload | null) => void;
  onRefreshQueue?: () => Promise<void> | void;
}

interface GroupedMessageSection {
  label: string;
  messages: MessagePayload[];
}

export default function AdvisorChatPanel({ activeLead, setActiveLead, onRefreshQueue }: AdvisorChatPanelProps) {
  const [chatHistory, setChatHistory] = useState<MessagePayload[]>([]);
  const [attachedFileName, setAttachedFileName] = useState<string | null>(null);
  const [attachedFileBase64, setAttachedFileBase64] = useState<string | null>(null);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const lastActiveLeadIdRef = useRef<string | number | null>(null);

  const currentPhone = activeLead?.phone_number || activeLead?.phone || '';
  const currentEmail = activeLead?.email || '';
  const currentName = activeLead?.name || activeLead?.full_name || 'Unknown Candidate';

  const parseChatHistory = useMemo((): MessagePayload[] => {
    if (!activeLead) return [];
    const structuredMessages = activeLead.messages || activeLead.chat_history || activeLead.history;
    if (Array.isArray(structuredMessages) && structuredMessages.length > 0) {
      return structuredMessages.map((msg: any, index: number) => {
        const isMsgAdvisor = msg.sender === 'advisor' || msg.sender === 'user';
        return {
          id: msg.id || `msg-${index}`,
          sender: isMsgAdvisor ? 'advisor' : 'candidate',
          senderName: isMsgAdvisor ? 'Advisor' : currentName,
          text: msg.text || msg.body || '',
          media_url: msg.media_url || undefined,
          created_at: msg.created_at
        };
      });
    }
    const rawLogs = activeLead.academic_summary || activeLead.last_interaction_summary || '';
    if (!rawLogs) return [];
    const lines = rawLogs.split('\n');
    const parsedMessages: MessagePayload[] = [];
    lines.forEach((line, index) => {
      const cleanLine = line.trim();
      if (!cleanLine) return;
      if (cleanLine.startsWith('Candidate:') || cleanLine.startsWith('student:')) {
        parsedMessages.push({ id: `log-${index}`, sender: 'candidate', senderName: currentName, text: cleanLine.replace(/^(Candidate:|student:)\s*/i, '') });
      } else if (cleanLine.startsWith('Advisor:')) {
        parsedMessages.push({ id: `log-${index}`, sender: 'advisor', senderName: 'Advisor', text: cleanLine.replace(/^Advisor:\s*/i, '') });
      } else if (cleanLine.startsWith('[')) {
        parsedMessages.push({ id: `log-${index}`, sender: 'system', text: cleanLine, senderName: 'System' });
      }
    });
    return parsedMessages;
  }, [activeLead, currentName]);

  useEffect(() => {
    setChatHistory(parseChatHistory);
  }, [parseChatHistory]);

  // ✅ FIXED: Reliable Auto-Scroll logic for headless scrollbar
  // ADD THIS HOOK
const streamRef = useRef<HTMLDivElement>(null);

// REPLACE YOUR SCROLL EFFECT WITH THIS
useEffect(() => {
  const container = streamRef.current;
  if (!container) return;

  const scrollToBottom = () => {
  // 1. Immediate attempt
  const attemptScroll = () => {
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  };

  // 2. Use requestAnimationFrame for the primary attempt
  requestAnimationFrame(() => {
    attemptScroll();
    
    // 3. Fallback: If it's the initial load, sometimes the browser 
    // needs an extra 50ms to finish rendering the complex message bubbles
    setTimeout(attemptScroll, 50);
  });
};

  // 1. Immediate trigger (for when the history is already in state)
  scrollToBottom();

  // 2. Observer: This is the critical fix.
  // It waits for the internal content to be painted. Once the browser finishes 
  // calculating the height of the message list (including images/attachments),
  // the ResizeObserver will fire and force the scroll to the bottom.
  const observer = new ResizeObserver(() => {
    scrollToBottom();
  });

  if (container.firstElementChild) {
    observer.observe(container.firstElementChild);
  }

  return () => observer.disconnect();
}, [activeLead?.id, chatHistory]);

  // ✅ FIXED: Auto-focus logic
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeLead?.id]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    window.__HARDWARE_INPUT_PERSIST_CACHE__ = e.target.value;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAttachedFileName(file.name);
      const reader = new FileReader();
      reader.onloadend = () => {
        setAttachedFileBase64(reader.result as string);
        inputRef.current?.focus();
      };
      reader.readAsDataURL(file);
    }
  };

  const clearSelectedAttachment = () => {
    setAttachedFileName(null);
    setAttachedFileBase64(null);
    inputRef.current?.focus();
  };

  // ✅ FIXED: Non-blocking send (Optimistic UI)
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const nativeInput = inputRef.current;
    if (!nativeInput || !activeLead) return;

    const preparedText = nativeInput.value.trim();
    const preparedAttachment = attachedFileBase64;
    if (!preparedText && !preparedAttachment) return;

    const optimisticMessage: MessagePayload = {
      id: `opt-${Date.now()}`,
      sender: 'advisor',
      senderName: 'Advisor',
      text: preparedText,
      media_url: preparedAttachment || undefined,
      created_at: new Date().toISOString(),
      isOptimistic: true
    };

    setChatHistory(prev => [...prev, optimisticMessage]);
    nativeInput.value = '';
    window.__HARDWARE_INPUT_PERSIST_CACHE__ = '';
    setAttachedFileName(null);
    setAttachedFileBase64(null);
    nativeInput.focus();

    fetch(`${API_BASE_URL}/api/v1/leads/webhook/social-ingress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: currentPhone.trim(),
        message: preparedText,
        attachment: preparedAttachment || undefined,
        debug_bypass_twilio: true 
      }),
    })
    .then(async (res) => {
      if (res.ok) {
        const updated = await res.json();
        setActiveLead(updated);
        if (onRefreshQueue) await onRefreshQueue();
      } else {
        setChatHistory(prev => prev.filter(m => m.id !== optimisticMessage.id));
      }
    })
    .catch(() => setChatHistory(prev => prev.filter(m => m.id !== optimisticMessage.id)));
  };

  const formatTime = (dateStr?: string): string => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch { return ''; }
  };

  const getDateGroupLabel = (dateStr?: string): string => {
    if (!dateStr) return 'System Events';
    try {
      const targetDate = new Date(dateStr);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - targetDate.getTime()) / (1000 * 60 * 60 * 24));
      if (diffDays === 0) return 'Today';
      if (diffDays === 1) return 'Yesterday';
      return targetDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return 'System Events'; }
  };

  const groupedMessages = useMemo((): GroupedMessageSection[] => {
    const sectionMap: Map<string, MessagePayload[]> = new Map();
    const orderedLabels: string[] = [];
    chatHistory.forEach((msg) => {
      const label = getDateGroupLabel(msg.created_at);
      if (!sectionMap.has(label)) { sectionMap.set(label, []); orderedLabels.push(label); }
      sectionMap.get(label)?.push(msg);
    });
    return orderedLabels.map(label => ({ label, messages: sectionMap.get(label) || [] }));
  }, [chatHistory]);

  return (
    <div style={styles.panelContainer}>
      <div style={styles.panelHeader}>
        <div>
          <h3 style={styles.headerTitle}>{currentName}</h3>
          <p style={styles.headerSubtitle}>📱 {currentPhone} | 📧 {currentEmail}</p>
        </div>
        {activeLead?.stage && <span style={styles.stageBadge}>{activeLead.stage}</span>}
      </div>

      <div 
  ref={streamRef} 
  style={{
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    height: '100%', 
    minHeight: '0', 
    position: 'relative',
    backgroundColor: '#efeae2', // Ensure background is visible
    border: '10px solid blue'    // LEAVE THIS HERE TEMPORARILY TO VERIFY
  }}
>
  <div style={{ display: 'flex', flexDirection: 'column', width: '100%', padding: '20px 4%' }}>
    {groupedMessages.map((group) => (
      <div key={group.label} style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={styles.timelineDividerCenter}>
          <span style={styles.timelineBadgeBubble}>{group.label}</span>
        </div>
        {group.messages.map((msg, index) => (
          <div key={msg.id || `msg-${index}`} style={{ ...styles.messageRow, justifyContent: msg.sender === 'advisor' ? 'flex-end' : 'flex-start' }}>
            <div style={{ ...styles.bubble, backgroundColor: msg.sender === 'advisor' ? '#dcfce7' : '#ffffff' }}>
              {msg.text && <p style={styles.bubbleTextString}>{msg.text}</p>}
              {msg.created_at && <span style={styles.bubbleTimestampLabel}>{formatTime(msg.created_at)}</span>}
            </div>
          </div>
        ))}
      </div>
    ))}
  </div>
</div>

      <form onSubmit={handleSendMessage} style={styles.inputArea}>
        <input ref={inputRef} type="text" onChange={handleInputChange} placeholder={`Message ${currentName}...`} style={styles.textInput} />
        <button type="submit" style={styles.sendButton}>Send</button>
      </form>
    </div>
  );
}

const styles = {
  panelContainer: { display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: '#efeae2', overflow: 'hidden' } as React.CSSProperties,
  panelHeader: { padding: '14px 24px', borderBottom: '1px solid #e3e6e9', backgroundColor: '#f0f2f5' } as React.CSSProperties,
  headerTitle: { margin: 0, fontSize: '16px', fontWeight: '600' } as React.CSSProperties,
  headerSubtitle: { margin: '2px 0 0 0', fontSize: '12px', color: '#667781' } as React.CSSProperties,
  stageBadge: { backgroundColor: '#e2e8f0', fontSize: '11px', padding: '4px 8px', borderRadius: '4px' } as React.CSSProperties,
  messageStream: { 
  flex: 1, 
  overflowY: 'auto', 
  display: 'flex', 
  flexDirection: 'column',
  height: '100%', 
  minHeight: '0', 
  border: '5px solid red', // ADD THIS TEMPORARILY
  backgroundColor: 'yellow' // ADD THIS TEMPORARILY
} as React.CSSProperties,
  timelineDividerCenter: { display: 'flex', justifyContent: 'center', margin: '14px 0' } as React.CSSProperties,
  timelineBadgeBubble: { backgroundColor: '#ffffff', fontSize: '12px', padding: '5px 12px', borderRadius: '7px' } as React.CSSProperties,
  messageRow: { display: 'flex', width: '100%', margin: '2px 0' } as React.CSSProperties,
  bubble: { maxWidth: '65%', padding: '6px 10px', borderRadius: '8px', boxShadow: '0 1px 1px rgba(0,0,0,0.1)' } as React.CSSProperties,
  bubbleTextString: { margin: 0, fontSize: '14px' } as React.CSSProperties,
  bubbleTimestampLabel: { fontSize: '10px', color: '#667781', display: 'block', textAlign: 'right' } as React.CSSProperties,
  inputArea: { padding: '10px 18px', backgroundColor: '#f0f2f5', display: 'flex', alignItems: 'center', gap: '12px' } as React.CSSProperties,
  textInput: { flex: 1, padding: '10px 16px', borderRadius: '8px', border: 'none', outline: 'none' } as React.CSSProperties,
  sendButton: { border: 'none', color: '#ffffff', padding: '10px 22px', borderRadius: '8px', backgroundColor: '#16a34a', cursor: 'pointer' } as React.CSSProperties
};