import { MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import type { IntelAiThreadGroup } from '../../types/nexusIntel';
import HeadlessScrollArea from '../HeadlessScrollArea';

interface IntelAiHistorySidebarProps {
  open: boolean;
  onToggle: () => void;
  groups: IntelAiThreadGroup[];
  activeThreadId: string | null;
  isLoading?: boolean;
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
}

function formatThreadTime(iso?: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Collapsible left rail: date-bucketed chat threads for Intel AI Assistant.
 */
export default function IntelAiHistorySidebar({
  open,
  onToggle,
  groups,
  activeThreadId,
  isLoading,
  onNewChat,
  onSelectThread,
}: IntelAiHistorySidebarProps) {
  if (!open) {
    return (
      <div className="flex h-full w-11 shrink-0 flex-col items-center gap-2 rounded-2xl border border-border-subtle bg-card/90 py-3">
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-text-muted hover:bg-surface-bg hover:text-text-main"
          title="Show chat history"
          aria-label="Show chat history"
        >
          <PanelLeftOpen size={16} />
        </button>
        <button
          type="button"
          onClick={onNewChat}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-accent hover:bg-accent/10"
          title="New chat"
          aria-label="New chat"
        >
          <MessageSquarePlus size={16} />
        </button>
      </div>
    );
  }

  const hasThreads = groups.some(group => group.threads.length > 0);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card/90 backdrop-blur-sm">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-3 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">History</p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onNewChat}
            className="inline-flex items-center gap-1 rounded-lg bg-accent px-2 py-1.5 text-[11px] font-semibold text-white hover:brightness-105"
          >
            <MessageSquarePlus size={12} />
            New
          </button>
          <button
            type="button"
            onClick={onToggle}
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-text-muted hover:bg-surface-bg hover:text-text-main"
            title="Collapse history"
            aria-label="Collapse history"
          >
            <PanelLeftClose size={15} />
          </button>
        </div>
      </div>

      <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="px-2 py-2 pr-3">
        {isLoading && !hasThreads ? (
          <p className="px-2 py-6 text-center text-xs text-text-muted">Loading threads…</p>
        ) : null}

        {!isLoading && !hasThreads ? (
          <div className="space-y-2 px-2 py-6 text-center">
            <p className="text-xs font-medium text-text-main">No chats yet</p>
            <p className="text-[11px] text-text-muted">
              Start a conversation — threads appear here grouped by date.
            </p>
          </div>
        ) : null}

        <div className="space-y-4">
          {groups.map(group => (
            <section key={group.key}>
              <h3 className="sticky top-0 z-[1] bg-card/95 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-text-muted backdrop-blur-sm">
                {group.label}
              </h3>
              <ul className="mt-1 space-y-0.5">
                {group.threads.map(thread => {
                  const active = thread.thread_id === activeThreadId;
                  return (
                    <li key={thread.thread_id}>
                      <button
                        type="button"
                        onClick={() => onSelectThread(thread.thread_id)}
                        className={`w-full rounded-xl px-2.5 py-2 text-left transition ${
                          active
                            ? 'bg-accent text-white shadow-sm'
                            : 'text-text-main hover:bg-surface-bg/80'
                        }`}
                      >
                        <span className="line-clamp-2 text-xs font-medium leading-snug">
                          {thread.title}
                        </span>
                        <span
                          className={`mt-1 flex items-center justify-between text-[10px] ${
                            active ? 'text-white/75' : 'text-text-muted'
                          }`}
                        >
                          <span>
                            {thread.turn_count} turn{thread.turn_count === 1 ? '' : 's'}
                          </span>
                          <span>{formatThreadTime(thread.updated_at)}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      </HeadlessScrollArea>
    </aside>
  );
}
