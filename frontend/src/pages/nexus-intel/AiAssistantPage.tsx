import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import {
  BookOpen,
  Bot,
  Building2,
  Calendar,
  ClipboardCopy,
  ExternalLink,
  Globe2,
  GraduationCap,
  Layers,
  Loader2,
  MapPin,
  Bookmark,
  Pencil,
  Save,
  Send,
  Sparkles,
  Trash2,
  Users,
} from 'lucide-react';
import {
  useCreateIntelAiPrompt,
  useDeleteIntelAiPrompt,
  useIntelAiChat,
  useIntelAiPrompts,
  useIntelAiThread,
  useIntelAiThreads,
  useUpdateIntelAiPrompt,
} from '../../hooks/useNexusIntel';
import type { IntelAiPrompt, IntelAiPromptVisibility, IntelAiSource } from '../../types/nexusIntel';
import SimpleMarkdown, { stripHtml } from '../../components/nexus-intel/SimpleMarkdown';
import IntelLoadingBubble from '../../components/nexus-intel/IntelLoadingBubble';
import IntelAiHistorySidebar from '../../components/nexus-intel/IntelAiHistorySidebar';
import HeadlessScrollArea, {
  type HeadlessScrollAreaHandle,
} from '../../components/HeadlessScrollArea';
import { displaySourceUrl, sourceHref } from '../../utils/intelSourceHref';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: IntelAiSource[];
  retrieved?: IntelAiSource[];
  pending?: boolean;
  error?: boolean;
  createdAt?: string | null;
}

const THREAD_STORAGE_KEY = 'nexus-intel-ai-thread-id';
const SIDEBAR_STORAGE_KEY = 'nexus-intel-ai-sidebar-open';

const SUGGESTIONS = [
  'Which courses and programs do we have for Medicine / MBBS?',
  'Show students aspiring to study MBBS in Russia',
  'List upcoming counselling appointments and bookings',
];

function formatMessageTime(iso?: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

function readStoredThreadId(): string | null {
  try {
    const value = sessionStorage.getItem(THREAD_STORAGE_KEY);
    return value && value.length > 8 ? value : null;
  } catch {
    return null;
  }
}

function writeStoredThreadId(threadId: string | null) {
  try {
    if (threadId) sessionStorage.setItem(THREAD_STORAGE_KEY, threadId);
    else sessionStorage.removeItem(THREAD_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function readSidebarOpen(): boolean {
  try {
    const raw = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (raw === null) return true;
    return raw !== '0';
  } catch {
    return true;
  }
}

function sourceIcon(type: string) {
  switch (type) {
    case 'glossary':
      return BookOpen;
    case 'university':
      return Building2;
    case 'program':
    case 'course':
      return GraduationCap;
    case 'major':
    case 'sub_major':
    case 'super_major':
    case 'level':
      return Layers;
    case 'country':
    case 'state':
    case 'city':
      return MapPin;
    case 'lead':
      return Users;
    case 'booking':
    case 'appointment':
      return Calendar;
    case 'web':
      return Globe2;
    default:
      return Sparkles;
  }
}

function sourceLabel(type: string) {
  switch (type) {
    case 'glossary':
      return 'Glossary';
    case 'university':
      return 'University';
    case 'program':
      return 'Program';
    case 'course':
      return 'Course';
    case 'major':
      return 'Major';
    case 'sub_major':
      return 'Sub-major';
    case 'super_major':
      return 'Super-major';
    case 'level':
      return 'Level';
    case 'country':
      return 'Country';
    case 'state':
      return 'State';
    case 'city':
      return 'City';
    case 'lead':
      return 'Lead';
    case 'booking':
      return 'Booking';
    case 'appointment':
      return 'Appointment';
    case 'web':
      return 'Web';
    default:
      return type;
  }
}

const AiAssistantPage: React.FC = () => {
  const [input, setInput] = useState('');
  const [activeThreadId, setActiveThreadId] = useState<string | null>(() => readStoredThreadId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSources, setActiveSources] = useState<IntelAiSource[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => readSidebarOpen());
  const [selectedPromptId, setSelectedPromptId] = useState('');
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveVisibility, setSaveVisibility] = useState<IntelAiPromptVisibility>('private');
  const [editingPrompt, setEditingPrompt] = useState<IntelAiPrompt | null>(null);
  const [promptError, setPromptError] = useState<string | null>(null);
  const chatScrollRef = useRef<HeadlessScrollAreaHandle | null>(null);
  // Blocks thread-hydration from wiping the optimistic user bubble mid-request.
  const suppressHydrateRef = useRef(false);

  const threadsQuery = useIntelAiThreads();
  const threadQuery = useIntelAiThread(activeThreadId, Boolean(activeThreadId));
  const chatMutation = useIntelAiChat();
  const promptsQuery = useIntelAiPrompts();
  const createPromptMutation = useCreateIntelAiPrompt();
  const updatePromptMutation = useUpdateIntelAiPrompt();
  const deletePromptMutation = useDeleteIntelAiPrompt();

  const savedPrompts = promptsQuery.data?.items || [];
  const selectedPrompt = savedPrompts.find(p => p.id === selectedPromptId) || null;
  const promptBusy =
    createPromptMutation.isPending ||
    updatePromptMutation.isPending ||
    deletePromptMutation.isPending;

  useEffect(() => {
    writeStoredThreadId(activeThreadId);
  }, [activeThreadId]);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarOpen ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [sidebarOpen]);

  // Hydrate center panel from the selected thread (reset cleanly on switch).
  useEffect(() => {
    if (!activeThreadId) return;
    // Never replace the live composer state while a send is in flight.
    if (suppressHydrateRef.current || chatMutation.isPending) return;
    if (!threadQuery.isFetched || threadQuery.isFetching) return;
    const detail = threadQuery.data;
    if (!detail || detail.thread_id !== activeThreadId) return;

    const restored: ChatMessage[] = (detail.messages || []).map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      sources: msg.sources,
      retrieved: msg.retrieved_sources,
      createdAt: msg.created_at,
    }));
    setMessages(restored);
    const lastAssistant = [...restored].reverse().find(m => m.role === 'assistant');
    setActiveSources(
      lastAssistant?.retrieved?.length
        ? lastAssistant.retrieved
        : lastAssistant?.sources || []
    );
  }, [
    activeThreadId,
    threadQuery.isFetched,
    threadQuery.isFetching,
    threadQuery.data,
    chatMutation.isPending,
  ]);

  useEffect(() => {
    const scrollLatestIntoView = () => {
      chatScrollRef.current?.scrollToBottom('auto');
    };

    let timeoutId = 0;
    let raf2 = 0;
    const raf1 = window.requestAnimationFrame(() => {
      scrollLatestIntoView();
      raf2 = window.requestAnimationFrame(scrollLatestIntoView);
      timeoutId = window.setTimeout(scrollLatestIntoView, 100);
    });
    return () => {
      window.cancelAnimationFrame(raf1);
      window.cancelAnimationFrame(raf2);
      window.clearTimeout(timeoutId);
    };
  }, [messages, chatMutation.isPending]);

  const startNewChat = () => {
    suppressHydrateRef.current = false;
    setActiveThreadId(null);
    writeStoredThreadId(null);
    setMessages([]);
    setActiveSources([]);
    setInput('');
  };

  const selectThread = (threadId: string) => {
    if (threadId === activeThreadId) return;
    if (chatMutation.isPending) return;
    suppressHydrateRef.current = false;
    setMessages([]);
    setActiveSources([]);
    setActiveThreadId(threadId);
  };

  const sendPrompt = async (raw: string) => {
    const prompt = raw.trim();
    if (!prompt || chatMutation.isPending) return;

    const userId = `u-${Date.now()}`;
    const pendingId = `a-${Date.now()}`;
    const sentAt = new Date().toISOString();

    // Paint the user prompt + loading bubble before the network call starts.
    suppressHydrateRef.current = true;
    flushSync(() => {
      setMessages(prev => [
        ...prev,
        { id: userId, role: 'user', content: prompt, createdAt: sentAt },
        {
          id: pendingId,
          role: 'assistant',
          content: 'Nexus Intel is analyzing policies and university data…',
          pending: true,
          createdAt: sentAt,
        },
      ]);
      setInput('');
    });
    chatScrollRef.current?.scrollToBottom('auto');

    try {
      const result = await chatMutation.mutateAsync({
        prompt,
        thread_id: activeThreadId,
      });
      flushSync(() => {
        setMessages(prev =>
          prev.map(m =>
            m.id === pendingId
              ? {
                  id: result.id,
                  role: 'assistant',
                  content: result.response_text,
                  sources: result.sources,
                  retrieved: result.retrieved_sources,
                  createdAt: result.created_at || m.createdAt,
                }
              : m
          )
        );
        setActiveSources(
          result.retrieved_sources?.length ? result.retrieved_sources : result.sources || []
        );
        if (result.thread_id && result.thread_id !== activeThreadId) {
          setActiveThreadId(result.thread_id);
        }
      });
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : 'Request failed. Please try again.';
      setMessages(prev =>
        prev.map(m =>
          m.id === pendingId
            ? {
                id: pendingId,
                role: 'assistant',
                content: `Sorry — I could not complete that request. ${detail}`,
                error: true,
              }
            : m
        )
      );
    } finally {
      // Allow hydration only after the optimistic turn is committed to local state.
      window.requestAnimationFrame(() => {
        suppressHydrateRef.current = false;
      });
    }
  };

  const copyAnswer = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId(null), 2000);
    } catch {
      /* ignore */
    }
  };

  const openSaveForm = (prompt?: IntelAiPrompt | null) => {
    setPromptError(null);
    if (prompt) {
      setEditingPrompt(prompt);
      setSaveTitle(prompt.title);
      setSaveVisibility(prompt.visibility);
      setInput(prompt.prompt_text);
    } else {
      setEditingPrompt(null);
      setSaveTitle('');
      setSaveVisibility('private');
    }
    setSaveOpen(true);
  };

  const closeSaveForm = () => {
    setSaveOpen(false);
    setEditingPrompt(null);
    setPromptError(null);
  };

  const handleSavePrompt = async () => {
    const title = saveTitle.trim();
    const promptText = input.trim() || editingPrompt?.prompt_text || '';
    if (!title) {
      setPromptError('Title is required.');
      return;
    }
    if (promptText.length < 2) {
      setPromptError('Prompt text is required (type it in the box below first).');
      return;
    }
    setPromptError(null);
    try {
      if (editingPrompt) {
        const updated = await updatePromptMutation.mutateAsync({
          id: editingPrompt.id,
          title,
          prompt_text: promptText,
          visibility: saveVisibility,
        });
        setSelectedPromptId(updated.id);
      } else {
        const created = await createPromptMutation.mutateAsync({
          title,
          prompt_text: promptText,
          visibility: saveVisibility,
        });
        setSelectedPromptId(created.id);
      }
      closeSaveForm();
    } catch (err) {
      setPromptError(err instanceof Error ? err.message : 'Could not save prompt.');
    }
  };

  const handleDeletePrompt = async (prompt: IntelAiPrompt) => {
    if (!prompt.is_owner) return;
    if (!window.confirm(`Delete saved prompt “${prompt.title}”?`)) return;
    setPromptError(null);
    try {
      await deletePromptMutation.mutateAsync(prompt.id);
      if (selectedPromptId === prompt.id) setSelectedPromptId('');
      if (editingPrompt?.id === prompt.id) closeSaveForm();
    } catch (err) {
      setPromptError(err instanceof Error ? err.message : 'Could not delete prompt.');
    }
  };

  const threadLoading =
    Boolean(activeThreadId) && threadQuery.isLoading && messages.length === 0;

  return (
    <div className="flex h-full min-h-0 gap-3 overflow-hidden">
      <IntelAiHistorySidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(prev => !prev)}
        groups={threadsQuery.data?.groups || []}
        activeThreadId={activeThreadId}
        isLoading={threadsQuery.isLoading}
        onNewChat={startNewChat}
        onSelectThread={selectThread}
      />

      <section className="grid min-h-0 min-w-0 flex-1 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-border-subtle bg-card">
        <header className="flex items-start justify-between gap-3 border-b border-border-subtle px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-accent/10 p-2 text-accent">
              <Bot size={18} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-text-main">Intel AI Assistant</h2>
              <p className="text-xs text-text-muted">
                {activeThreadId
                  ? 'Active thread loaded from history. Follow-ups stay in this session.'
                  : 'Start a new chat or pick a thread from the left history panel.'}
              </p>
            </div>
          </div>
        </header>

        <HeadlessScrollArea
          ref={chatScrollRef}
          className="min-h-0 h-full"
          viewportClassName="space-y-4 px-4 py-4 pr-3 pb-3"
        >
          {threadLoading ? (
            <p className="inline-flex items-center gap-2 text-sm text-text-muted">
              <Loader2 size={14} className="animate-spin" />
              Loading conversation…
            </p>
          ) : null}

          {messages.length === 0 && !threadLoading ? (
            <div className="space-y-3 rounded-2xl border border-dashed border-border-subtle bg-surface-bg/60 p-5">
              <p className="text-sm font-medium text-text-main">Ask a counseling question</p>
              <p className="text-xs text-text-muted">
                Follow-ups stay in this thread. The server keeps only the last 3 turns when talking
                to Ollama.
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map(text => (
                  <button
                    key={text}
                    type="button"
                    onClick={() => void sendPrompt(text)}
                    className="rounded-xl border border-border-subtle bg-card px-3 py-2 text-left text-sm text-text-main transition hover:border-accent/40 hover:bg-accent/5"
                  >
                    {text}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((message, index) => {
            const timeLabel = formatMessageTime(message.createdAt);
            const isLatestUserPrompt =
              message.role === 'user' &&
              !messages.slice(index + 1).some(m => m.role === 'user');
            return (
            <div
              key={message.id}
              data-chat-prompt={isLatestUserPrompt ? '1' : undefined}
              data-chat-tail={index === messages.length - 1 ? '1' : undefined}
              className={`flex flex-col gap-1 ${
                message.role === 'user' ? 'items-end' : 'items-start'
              }`}
            >
              {message.role === 'user' && timeLabel ? (
                <span className="px-1 text-[10px] leading-none text-text-muted/80">
                  {timeLabel}
                </span>
              ) : null}
              <div
                className={`max-w-[92%] ${
                  message.role === 'user'
                    ? 'rounded-2xl bg-accent px-3.5 py-2.5 text-white'
                    : message.pending
                      ? ''
                      : message.error
                        ? 'rounded-2xl border border-alert/30 bg-alert/10 px-3.5 py-2.5 text-alert'
                        : 'rounded-2xl border border-border-subtle bg-surface-bg px-3.5 py-2.5 text-text-main'
                }`}
              >
                {message.role === 'assistant' ? (
                  message.pending ? (
                    <IntelLoadingBubble />
                  ) : (
                    <div className="space-y-2">
                      <SimpleMarkdown content={message.content} />
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => void copyAnswer(message.id, message.content)}
                          className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-card px-2 py-1 text-[11px] text-text-muted hover:text-text-main"
                        >
                          <ClipboardCopy size={12} />
                          {copiedId === message.id ? 'Copied' : 'Copy'}
                        </button>
                        {message.retrieved?.length || message.sources?.length ? (
                          <button
                            type="button"
                            onClick={() =>
                              setActiveSources(
                                message.retrieved?.length
                                  ? message.retrieved
                                  : message.sources || []
                              )
                            }
                            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-card px-2 py-1 text-[11px] text-text-muted hover:text-text-main"
                          >
                            <Sparkles size={12} />
                            Show sources
                          </button>
                        ) : null}
                      </div>
                    </div>
                  )
                ) : (
                  <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                )}
              </div>
            </div>
            );
          })}
          <div aria-hidden className="h-6 shrink-0" data-chat-end="1" />
        </HeadlessScrollArea>

        <form
          className="border-t border-border-subtle bg-card p-3"
          onSubmit={e => {
            e.preventDefault();
            void sendPrompt(input);
          }}
        >
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="intel-ai-saved-prompt">
              Saved prompts
            </label>
            <select
              id="intel-ai-saved-prompt"
              value={selectedPromptId}
              onChange={e => {
                const id = e.target.value;
                setSelectedPromptId(id);
                const found = savedPrompts.find(p => p.id === id);
                if (found) setInput(found.prompt_text);
              }}
              className="min-w-[12rem] flex-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-text-main outline-none focus:border-accent"
            >
              <option value="">Saved prompts…</option>
              {savedPrompts.map(p => (
                <option key={p.id} value={p.id}>
                  {p.visibility === 'shared' ? '[Shared] ' : '[Private] '}
                  {p.title}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!selectedPrompt || chatMutation.isPending}
              onClick={() => {
                if (selectedPrompt) void sendPrompt(selectedPrompt.prompt_text);
              }}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-text-main hover:border-accent/40 disabled:opacity-40"
            >
              <Bookmark size={12} />
              Run
            </button>
            <button
              type="button"
              disabled={!selectedPrompt}
              onClick={() => {
                if (selectedPrompt) setInput(selectedPrompt.prompt_text);
              }}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-text-muted hover:text-text-main disabled:opacity-40"
            >
              Load
            </button>
            {selectedPrompt?.is_owner ? (
              <>
                <button
                  type="button"
                  onClick={() => openSaveForm(selectedPrompt)}
                  className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-text-muted hover:text-text-main"
                >
                  <Pencil size={12} />
                  Edit
                </button>
                <button
                  type="button"
                  disabled={promptBusy}
                  onClick={() => void handleDeletePrompt(selectedPrompt)}
                  className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-alert hover:bg-alert/5 disabled:opacity-40"
                >
                  <Trash2 size={12} />
                  Delete
                </button>
              </>
            ) : null}
            <button
              type="button"
              disabled={!input.trim()}
              onClick={() => openSaveForm(null)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-xs text-text-main hover:border-accent/40 disabled:opacity-40"
            >
              <Save size={12} />
              Save current
            </button>
          </div>

          {saveOpen ? (
            <div className="mb-2 space-y-2 rounded-xl border border-border-subtle bg-surface-bg/80 p-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-[10rem] flex-1">
                  <label className="mb-1 block text-[11px] text-text-muted" htmlFor="intel-ai-prompt-title">
                    {editingPrompt ? 'Update prompt title' : 'Save as'}
                  </label>
                  <input
                    id="intel-ai-prompt-title"
                    value={saveTitle}
                    onChange={e => setSaveTitle(e.target.value)}
                    placeholder="e.g. MBBS Russia counselling"
                    className="w-full rounded-lg border border-border-subtle bg-card px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                  />
                </div>
                <div className="flex items-center gap-1 rounded-lg border border-border-subtle bg-card p-0.5">
                  {(['private', 'shared'] as const).map(vis => (
                    <button
                      key={vis}
                      type="button"
                      onClick={() => setSaveVisibility(vis)}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-medium capitalize ${
                        saveVisibility === vis
                          ? 'bg-accent text-white'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      {vis}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  disabled={promptBusy}
                  onClick={() => void handleSavePrompt()}
                  className="inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                >
                  {promptBusy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  {editingPrompt ? 'Update' : 'Save'}
                </button>
                <button
                  type="button"
                  onClick={closeSaveForm}
                  className="rounded-lg px-2 py-1.5 text-xs text-text-muted hover:text-text-main"
                >
                  Cancel
                </button>
              </div>
              <p className="text-[11px] text-text-muted">
                {editingPrompt
                  ? 'Updates title, visibility, and the prompt text currently in the box below.'
                  : 'Saves the text currently in the prompt box. Shared prompts are visible to all signed-in users.'}
              </p>
            </div>
          ) : null}

          {promptError ? (
            <p className="mb-2 text-xs text-alert">{promptError}</p>
          ) : null}

          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              rows={2}
              placeholder="Ask a follow-up or start a new counseling question…"
              className="min-h-[64px] max-h-32 flex-1 resize-y rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void sendPrompt(input);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || chatMutation.isPending}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-accent px-3 text-sm font-medium text-white disabled:opacity-40"
            >
              {chatMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
              Send
            </button>
          </div>
        </form>
      </section>

      <aside className="hidden h-full w-72 shrink-0 flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card lg:flex">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-text-main">Sources</h3>
            <p className="text-xs text-text-muted">Retrieved context for the latest answer</p>
          </div>
          {activeSources.length > 0 ? (
            <button
              type="button"
              onClick={() => setActiveSources([])}
              className="text-[11px] text-text-muted hover:text-text-main"
            >
              Clear
            </button>
          ) : null}
        </div>
        <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="space-y-2 p-3 pr-3">
          {!activeSources.length ? (
            <p className="px-1 py-8 text-center text-xs text-text-muted">
              Sources appear here after you ask a question or click “Show sources”.
            </p>
          ) : (
            activeSources.map((source, index) => {
              const Icon = sourceIcon(source.type);
              const href = sourceHref(source.url);
              return (
                <article
                  key={`${source.type}-${source.id || source.title}-${index}`}
                  className="rounded-xl border border-border-subtle bg-surface-bg/70 p-3"
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-md bg-card px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                      <Icon size={11} />
                      {sourceLabel(source.type)}
                    </span>
                    {source.country_code ? (
                      <span className="text-[10px] text-text-muted">{source.country_code}</span>
                    ) : null}
                  </div>
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-accent hover:underline"
                    >
                      {source.title}
                    </a>
                  ) : (
                    <p className="text-sm font-medium text-text-main">{source.title}</p>
                  )}
                  {source.summary ? (
                    <p className="mt-1 line-clamp-4 text-xs text-text-muted">
                      {stripHtml(source.summary)}
                    </p>
                  ) : null}
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex max-w-full items-center gap-1 text-xs text-accent hover:underline"
                      title={href}
                    >
                      <ExternalLink size={11} className="shrink-0" />
                      <span className="truncate">{displaySourceUrl(href)}</span>
                    </a>
                  ) : source.slug ? (
                    <p className="mt-2 text-[11px] text-text-muted">Glossary slug: {source.slug}</p>
                  ) : null}
                </article>
              );
            })
          )}
        </HeadlessScrollArea>
      </aside>
    </div>
  );
};

export default AiAssistantPage;
