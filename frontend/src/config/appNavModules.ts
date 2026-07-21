import type { LucideIcon } from 'lucide-react';
import {
  Archive,
  BookOpen,
  Bot,
  Building2,
  Calendar,
  ClipboardList,
  FileText,
  Gauge,
  Globe2,
  GraduationCap,
  Inbox,
  KeyRound,
  Layers,
  MapPin,
  Plane,
  Radio,
  Settings,
  ShieldAlert,
  ShieldCheck,
  UserCog,
  Users,
  UserSearch,
} from 'lucide-react';
import {
  ACADEMIA_HUB_SECTIONS,
  FRAMEWORK_TABS,
  GEOGRAPHY_TABS,
} from './academiaHubNav';
import { STUDENT_PIPELINE_NAV } from './studentPipelineNav';
import { isAllowedRoute } from '../utils/routeAccess';
import { canAccessAcademiaHub } from '../utils/academiaAccess';

/** GitHub-style mega-menu link (icon + title + optional description). */
export interface NavMegaLink {
  path: string;
  label: string;
  description?: string;
  icon?: LucideIcon;
}

export interface NavMegaGroup {
  title: string;
  links: NavMegaLink[];
}

export interface NavMegaModule {
  id: string;
  label: string;
  /** Paths that mark this module as active in the header. */
  activePrefixes: string[];
  /** Featured column (GitHub left rail style). */
  featured: NavMegaLink[];
  /** Additional grouped columns. */
  groups: NavMegaGroup[];
}

export interface NavAccessContext {
  allowedRoutes: string[] | null;
  roleName: string;
  currentUser: { role?: string | null; admin_role?: { name?: string | null } | null } | null;
}

const COUNSELLING_ADMIN_ROLES = new Set(['Super Admin', 'Web Admin']);

function allowed(path: string, ctx: NavAccessContext): boolean {
  return ctx.allowedRoutes !== null && isAllowedRoute(path, ctx.allowedRoutes);
}

function filterLinks(links: NavMegaLink[], ctx: NavAccessContext): NavMegaLink[] {
  return links.filter(link => allowed(link.path, ctx));
}

function filterGroups(groups: NavMegaGroup[], ctx: NavAccessContext): NavMegaGroup[] {
  return groups
    .map(group => ({ ...group, links: filterLinks(group.links, ctx) }))
    .filter(group => group.links.length > 0);
}

/** Build all header mega-menu modules, then filter by RBAC. */
export function getAppNavModules(ctx: NavAccessContext): NavMegaModule[] {
  if (ctx.allowedRoutes === null) return [];

  const canCounselling =
    COUNSELLING_ADMIN_ROLES.has(ctx.roleName) && allowed('/counselling', ctx);

  const modules: NavMegaModule[] = [
    {
      id: 'leads',
      label: 'Leads',
      activePrefixes: [
        '/ai-active',
        '/handoffs',
        '/prospects',
        '/offline-leads',
        '/archive',
        '/quarantine',
      ],
      featured: [
        {
          path: '/ai-active',
          label: 'AI Active',
          description: 'Leads currently in AI conversation',
          icon: Bot,
        },
        {
          path: '/handoffs',
          label: 'Handoffs',
          description: 'Ready for advisor follow-up',
          icon: Users,
        },
      ],
      groups: [
        {
          title: 'Directories',
          links: [
            {
              path: '/prospects',
              label: 'All Prospects',
              description: 'Full prospect list',
              icon: UserSearch,
            },
            {
              path: '/offline-leads',
              label: 'Offline Leads',
              description: 'Imported offline leads',
              icon: Inbox,
            },
            {
              path: '/archive',
              label: 'Archive',
              description: 'Closed and archived leads',
              icon: Archive,
            },
            {
              path: '/quarantine',
              label: 'Lead Quarantine',
              description: 'Held for review',
              icon: ShieldAlert,
            },
          ],
        },
      ],
    },
    {
      id: 'students',
      label: 'Students',
      activePrefixes: STUDENT_PIPELINE_NAV.map(item => item.path),
      featured: STUDENT_PIPELINE_NAV.slice(0, 3).map(item => ({
        path: item.path,
        label: item.label,
        description: `${item.category} pipeline`,
        icon: GraduationCap,
      })),
      groups: [
        {
          title: 'Pipeline stages',
          links: STUDENT_PIPELINE_NAV.slice(3).map(item => ({
            path: item.path,
            label: item.label,
            description: `${item.category} stage`,
            icon:
              item.slug === 'visa-services'
                ? ShieldCheck
                : item.slug === 'pre-departure'
                  ? Plane
                  : item.slug === 'arrivals'
                    ? MapPin
                    : item.slug === 'prospects'
                      ? UserSearch
                      : ClipboardList,
          })),
        },
      ],
    },
    {
      id: 'academia',
      label: 'Academia',
      activePrefixes: ['/academia'],
      featured: ACADEMIA_HUB_SECTIONS.map(section => ({
        path: section.path,
        label: section.label,
        description:
          section.key === 'institutions'
            ? 'Institution directory and wizard'
            : section.key === 'framework'
              ? 'Majors, levels, programs, courses'
              : 'Countries, states, and cities',
        icon:
          section.key === 'institutions'
            ? Building2
            : section.key === 'framework'
              ? Layers
              : Globe2,
      })),
      groups: [
        {
          title: 'Geography',
          links: GEOGRAPHY_TABS.map(tab => ({
            path: tab.path,
            label: tab.label,
            icon: tab.key === 'countries' ? Globe2 : tab.key === 'states' ? Layers : MapPin,
          })),
        },
        {
          title: 'Academic framework',
          links: FRAMEWORK_TABS.map(tab => ({
            path: tab.path,
            label: tab.label,
            icon:
              tab.key === 'summary'
                ? Gauge
                : tab.key === 'majors'
                  ? BookOpen
                  : tab.key === 'levels'
                    ? Layers
                    : tab.key === 'programs'
                      ? GraduationCap
                      : ClipboardList,
          })),
        },
      ],
    },
    {
      id: 'appointments',
      label: 'Appointments',
      activePrefixes: ['/my-bookings', '/counselling'],
      featured: [
        ...(allowed('/my-bookings', ctx)
          ? [
              {
                path: '/my-bookings',
                label: 'My Appointments',
                description: 'Your scheduled counselling sessions',
                icon: Calendar,
              },
            ]
          : []),
        ...(canCounselling
          ? [
              {
                path: '/counselling',
                label: 'Manage Appointments',
                description: 'Advisor booking calendar and slots',
                icon: Calendar,
              },
            ]
          : []),
      ],
      groups: [],
    },
    {
      id: 'insights',
      label: 'Insights',
      activePrefixes: ['/reports', '/analytics'],
      featured: [
        {
          path: '/reports/meta-leads',
          label: 'Meta Leads',
          description: 'Meta lead intake reporting',
          icon: FileText,
        },
        {
          path: '/analytics',
          label: 'Analytics',
          description: 'Performance and funnel insights',
          icon: Gauge,
        },
      ],
      groups: [
        {
          title: 'Audit',
          links: [
            {
              path: '/reports/audit-logs',
              label: 'Audit Logs',
              description: 'Security and admin activity',
              icon: ShieldAlert,
            },
          ],
        },
      ],
    },
    {
      id: 'admin',
      label: 'Admin',
      activePrefixes: [
        '/users',
        '/access-control',
        '/command-center',
        '/agents',
        '/security-audit',
        '/settings',
      ],
      featured: [
        {
          path: '/users',
          label: 'Manage Users',
          description: 'Team accounts and profiles',
          icon: UserCog,
        },
        {
          path: '/settings',
          label: 'Settings',
          description: 'Application and monitoring settings',
          icon: Settings,
        },
      ],
      groups: [
        {
          title: 'Access & control',
          links: [
            {
              path: '/access-control',
              label: 'Access Control',
              description: 'Roles and permissions',
              icon: KeyRound,
            },
            ...(canCounselling
              ? [
                  {
                    path: '/command-center',
                    label: 'Mission Control',
                    description: 'Live operations cockpit',
                    icon: Radio,
                  },
                ]
              : []),
            {
              path: '/agents',
              label: 'AI Agent Brain',
              description: 'Agent configuration',
              icon: Bot,
            },
            {
              path: '/security-audit',
              label: 'Security Audit',
              description: 'Security posture checks',
              icon: ShieldAlert,
            },
          ],
        },
      ],
    },
  ];

  return modules
    .map(module => {
      if (module.id === 'academia' && !canAccessAcademiaHub(ctx.currentUser)) {
        return { ...module, featured: [], groups: [] };
      }
      if (module.id === 'academia' && !allowed('/academia', ctx)) {
        return { ...module, featured: [], groups: [] };
      }
      return {
        ...module,
        featured: filterLinks(module.featured, ctx),
        groups: filterGroups(module.groups, ctx),
      };
    })
    .filter(module => module.featured.length > 0 || module.groups.some(g => g.links.length > 0));
}

export function isModuleActive(module: NavMegaModule, pathname: string): boolean {
  const path = pathname.replace(/\/$/, '') || '/';
  return module.activePrefixes.some(prefix => {
    if (prefix === '/') return path === '/';
    return path === prefix || path.startsWith(`${prefix}/`);
  });
}
