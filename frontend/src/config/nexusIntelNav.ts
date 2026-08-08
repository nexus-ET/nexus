import type { LucideIcon } from 'lucide-react';
import {
  BookOpen,
  Bot,
  Brain,
  ClipboardCheck,
  GitCompare,
  Settings2,
  Sparkles,
} from 'lucide-react';

export interface NexusIntelNavItem {
  key: string;
  label: string;
  path: string;
  description: string;
  icon: LucideIcon;
}

export const NEXUS_INTEL_NAV: NexusIntelNavItem[] = [
  {
    key: 'knowledge',
    label: 'Knowledge Hub',
    path: '/nexus-intel/knowledge',
    description: 'Glossary, filters, and live terminology',
    icon: BookOpen,
  },
  {
    key: 'ai-assistant',
    label: 'AI Assistant',
    path: '/nexus-intel/ai-assistant',
    description: 'RAG chat over glossary, universities, and live policy checks',
    icon: Bot,
  },
  {
    key: 'workflows',
    label: 'Workflows',
    path: '/nexus-intel/workflows',
    description: 'Proof of funds and country comparisons',
    icon: GitCompare,
  },
  {
    key: 'academy',
    label: 'Academy',
    path: '/nexus-intel/academy',
    description: 'Micro-learning and certification quizzes',
    icon: ClipboardCheck,
  },
  {
    key: 'controls',
    label: 'Tips & Trivia',
    path: '/nexus-intel/controls',
    description: 'Daily trivia and contextual tip preferences',
    icon: Sparkles,
  },
  {
    key: 'admin',
    label: 'Scraper Admin',
    path: '/nexus-intel/admin',
    description: 'Regulatory scrape schedules and reviews',
    icon: Settings2,
  },
];

export const NEXUS_INTEL_HOME = {
  path: '/nexus-intel',
  label: 'IntelX',
  icon: Brain,
};
