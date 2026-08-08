import type { ProspectMessage } from '../types/prospect';
import {
  formatApiClockTime,
  formatApiDateOnly,
  getApiDateGroupLabel,
} from './timezone';

export type MessageActor = 'candidate' | 'ai' | 'admin';

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

export const ACTOR_THEME: Record<
  MessageActor,
  { bg: string; label: string; labelColor: string; textColor: string }
> = {
  candidate: { bg: '#1e3a5f', label: 'Candidate', labelColor: '#93c5fd', textColor: '#f8fafc' },
  ai: { bg: '#ede9fe', label: 'AI Active', labelColor: '#6d28d9', textColor: '#111b21' },
  admin: { bg: '#dbeafe', label: 'Nexus Admin', labelColor: '#322f86', textColor: '#111b21' },
};

export function classifyMessage(msg: ProspectMessage): MessageActor {
  if (msg.sender === 'candidate' || msg.sender === 'student') return 'candidate';
  if (msg.sender === 'system') return 'admin';

  const text = msg.text || '';
  if (AI_AUTOMATED_PATTERNS.some(pattern => text.includes(pattern))) return 'ai';
  if (text.includes('human admissions advisor has just joined')) return 'admin';
  if (text.includes('Manual Advisor') || text.includes('Takeover Override')) return 'admin';

  return 'admin';
}

export function formatProspectTime(dateStr?: string, businessTimezone = 'UTC'): string {
  if (!dateStr) return '';
  return formatApiClockTime(dateStr, businessTimezone);
}

export function formatProspectDate(dateStr?: string, businessTimezone = 'UTC'): string {
  if (!dateStr) return '—';
  return formatApiDateOnly(dateStr, businessTimezone);
}

export function getDateGroupLabel(dateStr?: string, businessTimezone = 'UTC'): string {
  return getApiDateGroupLabel(dateStr, businessTimezone, 'Earlier');
}

export function buildInteractionGroups(
  messages: ProspectMessage[] | undefined,
  academicSummary?: string | null,
  businessTimezone = 'UTC'
): Record<string, Array<ProspectMessage & { actor: MessageActor }>> {
  const processed: Array<ProspectMessage & { actor: MessageActor }> = [...(messages || [])]
    .filter(msg => !msg.text?.includes('Got it! Your update has been logged on your dashboard matrix timeline.'))
    .map(msg => ({ ...msg, actor: classifyMessage(msg) }));

  const rawLogs = academicSummary || '';
  if (rawLogs) {
    rawLogs.split('\n').forEach((line, index) => {
      const clean = line.trim();
      if (!clean || clean.includes('Got it! Your update has been logged on your dashboard matrix timeline.')) {
        return;
      }
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

  const groups: Record<string, Array<ProspectMessage & { actor: MessageActor }>> = {};
  processed.forEach(msg => {
    const label = getDateGroupLabel(msg.created_at, businessTimezone);
    if (!groups[label]) groups[label] = [];
    groups[label].push(msg);
  });
  return groups;
}

export function platformBadgeStyle(badge: string | null | undefined) {
  if (badge === 'IG') {
    return { background: '#fce7f3', color: '#be185d', border: '1px solid #fbcfe8' };
  }
  if (badge === 'FB') {
    return { background: '#dbeafe', color: '#322f86', border: '1px solid #bfdbfe' };
  }
  return { background: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0' };
}
