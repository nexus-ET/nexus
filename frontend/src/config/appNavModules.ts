import type { LucideIcon } from 'lucide-react';
import {
  Archive,
  BookOpen,
  Bot,
  Building2,
  Calendar,
  CalendarPlus,
  ClipboardList,
  FileText,
  Gauge,
  Globe2,
  GraduationCap,
  Inbox,
  KeyRound,
  Landmark,
  Layers,
  LayoutGrid,
  ListOrdered,
  MapPin,
  Percent,
  Plane,
  Radio,
  Receipt,
  School,
  ShieldAlert,
  ShieldCheck,
  UserCog,
  Users,
  UserSearch,
  Zap,
} from 'lucide-react';
import {
  ACADEMIA_HUB_SECTIONS,
  FRAMEWORK_TABS,
  GEOGRAPHY_TABS,
} from './academiaHubNav';
import { FLOWX_NAV_GROUPS } from './flowxNav';
import { NEXUS_INTEL_NAV } from './nexusIntelNav';
import { STUDENT_PIPELINE_NAV, STUDENT_PIPELINE_NAV_GROUPS } from './studentPipelineNav';
import { isAllowedRoute } from '../utils/routeAccess';
import { canAccessAcademiaHub } from '../utils/academiaAccess';

/** GitHub-style mega-menu link (icon + title + optional description). */
export interface NavMegaLink {
  path: string;
  label: string;
  description?: string;
  icon?: LucideIcon;
  /** Indent under the previous sibling (e.g. Sub-Majors under Majors). */
  nested?: boolean;
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

function studentPipelineIcon(slug: string): LucideIcon {
  switch (slug) {
    case 'counselling':
      return GraduationCap;
    case 'college-finding':
      return School;
    case 'visa-processing':
      return ShieldCheck;
    case 'pre-departure-travel':
      return Plane;
    case 'landing':
      return MapPin;
    default:
      return ClipboardList;
  }
}

function studentPipelineLink(item: (typeof STUDENT_PIPELINE_NAV)[number]): NavMegaLink {
  return {
    path: item.path,
    label: item.label,
    description: `${item.category} stage`,
    icon: studentPipelineIcon(item.slug),
  };
}

const OFFLINE_LEADS_MEGA_GROUP: NavMegaGroup = {
  title: 'Offline Leads',
  links: [
    {
      path: '/express-leads',
      label: 'Express Leads',
      description: 'Quick capture for walk-in and phone leads',
      icon: Zap,
    },
    {
      path: '/offline-leads',
      label: 'Offline Leads',
      description: 'Imported offline leads',
      icon: Inbox,
    },
  ],
};

const LEADS_NAV_GROUPS: NavMegaGroup[] = [
  {
    title: 'Online Leads',
    links: [
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
  },
  {
    title: 'Leads Management',
    links: [
      {
        path: '/quarantine',
        label: 'Lead Quarantine',
        description: 'Review unverified lead data',
        icon: ShieldAlert,
      },
    ],
  },
];

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
      activePrefixes: ['/ai-active', '/handoffs', '/prospects', '/archive', '/quarantine'],
      featured: [],
      groups: LEADS_NAV_GROUPS,
      sidebarSections: LEADS_NAV_GROUPS,
    },
    {
      id: 'students',
      label: 'Students',
      activePrefixes: [
        ...STUDENT_PIPELINE_NAV.map(item => item.path),
        '/express-leads',
        '/offline-leads',
      ],
      featured: [],
      groups: [
        OFFLINE_LEADS_MEGA_GROUP,
        ...STUDENT_PIPELINE_NAV_GROUPS.map(group => ({
          title: group.label,
          links: group.items.map(studentPipelineLink),
        })),
      ],
      sidebarSections: [
        OFFLINE_LEADS_MEGA_GROUP,
        ...STUDENT_PIPELINE_NAV_GROUPS.map(group => ({
          title: group.label,
          links: group.items.map(studentPipelineLink),
        })),
      ],
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
      id: 'admin',
      label: 'Admin',
      activePrefixes: [
        '/users',
        '/access-control',
        '/command-center',
        '/agents',
        '/security-audit',
        '/settings',
        '/invoices',
      ],
      featured: [
        {
          path: '/users',
          label: 'Manage Users',
          description: 'Team accounts and profiles',
          icon: UserCog,
        },
      ],
      groups: [
        {
          title: '',
          links: [
            {
              path: '/settings',
              label: 'Organization',
              description: 'Business profile, logo, and contacts',
              icon: Building2,
            },
            {
              path: '/settings?tab=workspace',
              label: 'Workspace',
              description: 'Bookings, Meta sync, holidays, and alerts',
              icon: Calendar,
            },
            {
              path: '/settings?tab=monitoring',
              label: 'Monitoring',
              description: 'Uptime checks and alert recipients',
              icon: Gauge,
            },
          ],
        },
        {
          title: 'Accounts',
          links: [
            {
              path: '/invoices',
              label: 'Invoice Workspace',
              description: 'Draft and issue student invoices',
              icon: Receipt,
            },
            {
              path: '/settings?tab=billing&section=base-price-catalog',
              label: 'Base Price Catalog',
              description: 'INR list prices and packages',
              icon: ListOrdered,
            },
            {
              path: '/settings?tab=billing&section=invoice-format',
              label: 'Invoice Format',
              description: 'Number pattern and FY strategy',
              icon: FileText,
            },
            {
              path: '/settings?tab=billing&section=organization-gstin',
              label: 'GST & Tax',
              description: 'GSTIN, GST rate, and active tax regimes',
              icon: Building2,
            },
            {
              path: '/settings?tab=billing&section=discount-policy',
              label: 'Discount Policy',
              description: 'Default discount and approval rules',
              icon: Percent,
            },
            {
              path: '/settings?tab=billing&section=bank-details',
              label: 'Bank Details',
              description: 'Accounts shown on student invoices',
              icon: Landmark,
            },
          ],
        },
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
      sidebarSections: [
        {
          title: '',
          links: [
            {
              path: '/settings',
              label: 'Organization',
              description: 'Business profile, logo, and contacts',
              icon: Building2,
            },
            {
              path: '/settings?tab=workspace',
              label: 'Workspace',
              description: 'Bookings, Meta sync, holidays, and alerts',
              icon: Calendar,
            },
            {
              path: '/settings?tab=monitoring',
              label: 'Monitoring',
              description: 'Uptime checks and alert recipients',
              icon: Gauge,
            },
          ],
        },
        {
          title: 'Accounts',
          links: [
            {
              path: '/invoices',
              label: 'Invoice Workspace',
              description: 'Draft and issue student invoices',
              icon: Receipt,
            },
            {
              path: '/settings?tab=billing&section=base-price-catalog',
              label: 'Base Price Catalog',
              description: 'INR list prices and packages',
              icon: ListOrdered,
            },
            {
              path: '/settings?tab=billing&section=invoice-format',
              label: 'Invoice Format',
              description: 'Number pattern and FY strategy',
              icon: FileText,
            },
            {
              path: '/settings?tab=billing&section=organization-gstin',
              label: 'GST & Tax',
              description: 'GSTIN, GST rate, and active tax regimes',
              icon: Building2,
            },
            {
              path: '/settings?tab=billing&section=discount-policy',
              label: 'Discount Policy',
              description: 'Default discount and approval rules',
              icon: Percent,
            },
            {
              path: '/settings?tab=billing&section=bank-details',
              label: 'Bank Details',
              description: 'Accounts shown on student invoices',
              icon: Landmark,
            },
          ],
        },
        {
          title: 'Access & control',
          links: [
            {
              path: '/users',
              label: 'Manage Users',
              description: 'Team accounts and profiles',
              icon: UserCog,
            },
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
              ? 'Super-majors, majors, sub-majors, levels, programs, courses'
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
            nested: tab.nested,
            icon:
              tab.key === 'summary'
                ? Gauge
                : tab.key === 'super-majors' || tab.key === 'majors' || tab.key === 'sub-majors'
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
              nested: item.key === 'majors' || item.key === 'sub-majors',
              icon:
                item.key === 'summary'
                  ? Gauge
                  : item.key === 'super-majors' ||
                      item.key === 'majors' ||
                      item.key === 'sub-majors' ||
                      item.key === 'courses'
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
        icon: item.icon,
      })),
      groups: [
        {
          title: 'Workspace',
          links: NEXUS_INTEL_NAV.slice(0, 4).map(item => ({
            path: item.path,
            label: item.label,
            description: item.description,
            icon: item.icon,
          })),
        },
        {
          title: 'Controls',
          links: NEXUS_INTEL_NAV.slice(4).map(item => ({
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
      featured: [],
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
