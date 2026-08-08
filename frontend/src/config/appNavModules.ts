import type { LucideIcon } from 'lucide-react';
import {
  Archive,
  BookOpen,
  Bot,
  Brain,
  Building2,
  Calendar,
  CalendarPlus,
  ClipboardCheck,
  ClipboardList,
  FileText,
  Gauge,
  GitCompare,
  Globe2,
  GraduationCap,
  Inbox,
  KeyRound,
  Layers,
  LayoutGrid,
  MapPin,
  Plane,
  Radio,
  Settings,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCog,
  Users,
  UserSearch,
} from 'lucide-react';
import {
  ACADEMIA_HUB_SECTIONS,
  FRAMEWORK_TABS,
  GEOGRAPHY_TABS,
} from './academiaHubNav';
import { FLOWX_NAV, FLOWX_NAV_GROUPS } from './flowxNav';
import { NEXUS_INTEL_NAV } from './nexusIntelNav';
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
  /**
   * Left-nav hierarchy (heading → links). When set, the sidebar uses this
   * instead of flattening mega-menu featured + groups.
   */
  sidebarSections?: NavMegaGroup[];
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
  const canBookAppointment =
    COUNSELLING_ADMIN_ROLES.has(ctx.roleName) &&
    (allowed('/book-appointment', ctx) || allowed('/counselling', ctx));

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
        {
          path: '/prospects',
          label: 'All Prospects',
          description: 'Full prospect list',
          icon: UserSearch,
        },
        {
          path: '/archive',
          label: 'Archive',
          description: 'Closed and archived leads',
          icon: Archive,
        },
      ],
      groups: [
        {
          title: 'Directories',
          links: [
            {
              path: '/offline-leads',
              label: 'Offline Leads',
              description: 'Imported offline leads',
              icon: Inbox,
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
      // Left nav: one continuous pipeline list under Students
      sidebarSections: [
        {
          title: 'Pipeline',
          links: STUDENT_PIPELINE_NAV.map(item => ({
            path: item.path,
            label: item.label,
            icon:
              item.slug === 'counselling'
                ? GraduationCap
                : item.slug === 'visa-services'
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
      // Left nav: each hub section heading sits directly above its own links
      sidebarSections: ACADEMIA_HUB_SECTIONS.map(section => {
        if (section.items.length > 1) {
          return {
            title: section.label,
            links: section.items.map(item => ({
              path: item.path,
              label: item.label,
              icon:
                item.key === 'summary'
                  ? Gauge
                  : item.key === 'majors' || item.key === 'courses'
                    ? BookOpen
                    : item.key === 'levels' || item.key === 'states'
                      ? Layers
                      : item.key === 'programs'
                        ? GraduationCap
                        : item.key === 'cities'
                          ? MapPin
                          : item.key === 'countries'
                            ? Globe2
                            : item.key === 'institutions'
                              ? Building2
                              : ClipboardList,
            })),
          };
        }
        return {
          title: null,
          links: [
            {
              path: section.path,
              label: section.label,
              icon:
                section.key === 'institutions'
                  ? Building2
                  : section.key === 'framework'
                    ? Layers
                    : Globe2,
            },
          ],
        };
      }),
    },
    {
      id: 'nexus-intel',
      label: 'IntelX',
      activePrefixes: ['/nexus-intel'],
      featured: NEXUS_INTEL_NAV.map(item => ({
        path: item.path,
        label: item.label,
        description: item.description,
        icon:
          item.key === 'knowledge'
            ? BookOpen
            : item.key === 'ai-assistant'
              ? Bot
              : item.key === 'workflows'
                ? GitCompare
                : item.key === 'academy'
                  ? ClipboardCheck
                  : item.key === 'controls'
                    ? Sparkles
                    : item.key === 'admin'
                      ? Settings2
                      : Brain,
      })),
      groups: [
        {
          title: 'Workspace',
          links: NEXUS_INTEL_NAV.slice(0, 3).map(item => ({
            path: item.path,
            label: item.label,
            description: item.description,
            icon: item.icon,
          })),
        },
        {
          title: 'Controls',
          links: NEXUS_INTEL_NAV.slice(3).map(item => ({
            path: item.path,
            label: item.label,
            description: item.description,
            icon: item.icon,
          })),
        },
      ],
      sidebarSections: [
        {
          title: null,
          links: NEXUS_INTEL_NAV.map(item => ({
            path: item.path,
            label: item.label,
            icon: item.icon,
          })),
        },
      ],
    },
    {
      id: 'flowx',
      label: 'FlowX',
      activePrefixes: ['/flowx'],
      featured: FLOWX_NAV.map(item => ({
        path: item.path,
        label: item.label,
        description: item.description,
        icon: item.icon,
      })),
      groups: FLOWX_NAV_GROUPS.map(group => ({
        title: group.label,
        links: group.items.map(item => ({
          path: item.path,
          label: item.label,
          description: item.description,
          icon: item.icon,
        })),
      })),
      sidebarSections: FLOWX_NAV_GROUPS.map(group => ({
        title: group.label,
        links: group.items.map(item => ({
          path: item.path,
          label: item.label,
          icon: item.icon,
        })),
      })),
    },
    {
      id: 'appointments',
      label: 'Appointments',
      activePrefixes: ['/book-appointment', '/my-bookings', '/counselling'],
      featured: [
        ...(canBookAppointment
          ? [
              {
                path: '/book-appointment',
                label: 'Book Appointment',
                description: 'Schedule a counselling session for a candidate',
                icon: CalendarPlus,
              },
            ]
          : []),
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
              path: '/reports/exceptions',
              label: 'Exception Report',
              description: 'Errors, timeouts, and omissions',
              icon: ShieldAlert,
            },
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
        return { ...module, featured: [], groups: [], sidebarSections: [] };
      }
      if (module.id === 'academia' && !allowed('/academia', ctx)) {
        return { ...module, featured: [], groups: [], sidebarSections: [] };
      }
      return {
        ...module,
        featured: filterLinks(module.featured, ctx),
        groups: filterGroups(module.groups, ctx),
        sidebarSections: module.sidebarSections
          ? filterGroups(module.sidebarSections, ctx)
          : undefined,
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

/** Left-nav sections: prefer hierarchy built for the sidebar; else mega flatten. */
export function getModuleSidebarSections(
  module: NavMegaModule
): Array<{ title: string | null; links: NavMegaLink[] }> {
  if (module.sidebarSections && module.sidebarSections.length > 0) {
    return module.sidebarSections
      .filter(group => group.links.length > 0)
      .map(group => ({ title: group.title || null, links: group.links }));
  }

  const sections: Array<{ title: string | null; links: NavMegaLink[] }> = [];
  if (module.featured.length > 0) {
    sections.push({ title: null, links: module.featured });
  }
  for (const group of module.groups) {
    if (group.links.length > 0) {
      sections.push({ title: group.title, links: group.links });
    }
  }
  return sections;
}

export function getModuleDefaultPath(module: NavMegaModule): string | null {
  const sections = getModuleSidebarSections(module);
  return sections[0]?.links[0]?.path ?? null;
}

export function findModuleById(
  modules: NavMegaModule[],
  moduleId: string | null | undefined
): NavMegaModule | null {
  if (!moduleId) return null;
  return modules.find(module => module.id === moduleId) ?? null;
}

export function findModuleForPath(
  modules: NavMegaModule[],
  pathname: string
): NavMegaModule | null {
  return modules.find(module => isModuleActive(module, pathname)) ?? null;
}
