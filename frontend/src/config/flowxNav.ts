import type { LucideIcon } from 'lucide-react';
import {
  GitBranch,
  Globe2,
  LayoutDashboard,
  LayoutGrid,
  MapPinned,
  Waypoints,
} from 'lucide-react';

export interface FlowxNavItem {
  key: string;
  label: string;
  path: string;
  description: string;
  icon: LucideIcon;
  /** superadmin-only tab (e.g. Master Workflow) */
  superAdminOnly?: boolean;
}

export interface FlowxNavGroup {
  key: 'operate' | 'configure';
  label: string;
  items: FlowxNavItem[];
}

/** Operate = day-to-day candidate processing; Configure = template design. */
export const FLOWX_NAV_GROUPS: FlowxNavGroup[] = [
  {
    key: 'operate',
    label: 'Operate',
    items: [
      {
        key: 'ops',
        label: 'Ops Dashboard',
        path: '/flowx/ops',
        description: 'Global pipeline health, country volume, and SLA bottlenecks',
        icon: LayoutDashboard,
      },
      {
        key: 'board',
        label: 'By Country Board',
        path: '/flowx/board',
        description: 'Operational board grouped by destination and stage',
        icon: LayoutGrid,
      },
    ],
  },
  {
    key: 'configure',
    label: 'Configure',
    items: [
      {
        key: 'countries',
        label: 'Country Workflows',
        path: '/flowx/countries',
        description: 'End-to-end process templates by destination country',
        icon: Globe2,
      },
      {
        key: 'master',
        label: 'Master Workflow',
        path: '/flowx/master',
        description: 'Canonical processes & sub-processes for all countries',
        icon: Waypoints,
        superAdminOnly: true,
      },
    ],
  },
];

/** Flat list for sidebar / featured links (Operate first). */
export const FLOWX_NAV: FlowxNavItem[] = FLOWX_NAV_GROUPS.flatMap(g => g.items);

export const FLOWX_HOME = {
  path: '/flowx/ops',
  label: 'FlowX',
  icon: GitBranch,
};

/** Country hub path helper (Tier 2). */
export function flowxCountryHubPath(iso2: string) {
  return `/flowx/ops/${(iso2 || '').toUpperCase()}`;
}

export const FLOWX_COUNTRY_HUB_ICON = MapPinned;

/** Canonical end-to-end overseas education stages. */
export const FLOWX_JOURNEY_STAGES = [
  { key: 'counselling', label: 'Counselling' },
  { key: 'college_finding', label: 'College finding' },
  { key: 'document_submission', label: 'Document readiness' },
  { key: 'tests', label: 'Tests' },
  { key: 'admission_processing', label: 'Admission processing' },
  { key: 'visa_processing', label: 'Visa processing' },
  { key: 'predeparture_travel', label: 'Pre-departure & travel' },
  { key: 'landing', label: 'Landing' },
] as const;

export type FlowxJourneyStageKey = (typeof FLOWX_JOURNEY_STAGES)[number]['key'];
