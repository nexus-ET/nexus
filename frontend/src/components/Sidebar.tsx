import { useEffect, useState } from 'react';
import { isAllowedRoute, isRouteActive, normalizePath } from '../utils/routeAccess';
import { STUDENT_PIPELINE_NAV, STUDENT_PIPELINE_PATHS } from '../config/studentPipelineNav';
import { ACADEMIA_HUB_SECTIONS } from '../config/academiaHubNav';
import { canAccessAcademiaHub } from '../utils/academiaAccess';
import { Link, useLocation } from 'react-router-dom';
import { useNexusSession } from '../context/NexusSessionContext';
import {
  LayoutDashboard,
  Users,
  Bot,
  Settings,
  ShieldAlert,
  Calendar,
  ChevronLeft,
  Menu,
  ChevronDown,
  UserCog,
  Radio,
  MessagesSquare,
  FileText,
  Gauge,
  GraduationCap,
  BookOpen,
} from 'lucide-react';

interface SidebarUser {
  role?: string | null;
  admin_role?: { name?: string | null } | null;
}

interface SidebarProps {
  isSidebarOpen: boolean;
  setIsSidebarOpen: (open: boolean) => void;
  allowedRoutes: string[] | null;
  currentUser: SidebarUser | null;
}

const COUNSELLING_ADMIN_ROLES = new Set(['Super Admin', 'Web Admin']);

const Sidebar: React.FC<SidebarProps> = ({
  isSidebarOpen,
  setIsSidebarOpen,
  allowedRoutes,
  currentUser,
}) => {
  const location = useLocation();
  const { unreadMessageCount, messagingHubPulse, setMessagingHubPulse } = useNexusSession();
  const [isStudentsOpen, setIsStudentsOpen] = useState(true);
  const [isAppointmentsOpen, setIsAppointmentsOpen] = useState(true);
  const [isLeadsOpen, setIsLeadsOpen] = useState(true);
  const [isUsersOpen, setIsUsersOpen] = useState(false);
  const [isReportsOpen, setIsReportsOpen] = useState(false);
  const [isCockpitOpen, setIsCockpitOpen] = useState(false);
  const [isAcademiaOpen, setIsAcademiaOpen] = useState(false);

  const currentPath = normalizePath(location.pathname);
  const isRouteAllowed = (path: string) =>
    allowedRoutes !== null && isAllowedRoute(path, allowedRoutes);

  const resolvedRole = currentUser?.admin_role?.name || currentUser?.role || '';
  const canAccessCounselling =
    COUNSELLING_ADMIN_ROLES.has(resolvedRole) && isRouteAllowed('/counselling');
  const canAccessMessaging = isRouteAllowed('/messaging-hub');
  const canAccessMyBookings = isRouteAllowed('/my-bookings');

  const leadNavItems = [
    { path: '/ai-active', label: 'AI Active' },
    { path: '/handoffs', label: 'Handoffs' },
    { path: '/prospects', label: 'All Prospects' },
    { path: '/offline-leads', label: 'Offline Leads' },
    { path: '/archive', label: 'Archive' },
    { path: '/quarantine', label: 'Lead Quarantine' },
  ];

  const userNavItems = [
    { path: '/users', label: 'Manage Users' },
    { path: '/access-control', label: 'Access Control' },
  ];

  const reportNavItems = [
    { path: '/reports/meta-leads', label: 'Meta Leads' },
    { path: '/reports/audit-logs', label: 'Audit Logs' },
    { path: '/analytics', label: 'Analytics' },
  ];

  const appointmentNavItems = [
    ...(canAccessMyBookings ? [{ path: '/my-bookings', label: 'My Appointments' }] : []),
    ...(canAccessCounselling ? [{ path: '/counselling', label: 'Manage Appointments' }] : []),
  ];

  const studentNavItems = STUDENT_PIPELINE_NAV.filter(item => isRouteAllowed(item.path));
  const showStudentsSection = studentNavItems.length > 0;

  const visibleLeadNavItems = leadNavItems.filter(item => isRouteAllowed(item.path));
  const showLeadsSection = visibleLeadNavItems.length > 0;
  const visibleUserNavItems = userNavItems.filter(item => isRouteAllowed(item.path));
  const showUsersSection = visibleUserNavItems.length > 0;
  const visibleReportNavItems = reportNavItems.filter(item => isRouteAllowed(item.path));
  const showReportsSection = visibleReportNavItems.length > 0;
  const showAppointmentsSection = appointmentNavItems.length > 0;

  const cockpitNavItems = [
    ...(canAccessCounselling
      ? [{ path: '/command-center', label: 'Mission Control', icon: Radio }]
      : []),
    { path: '/agents', label: 'AI Agent Brain', icon: Bot },
    { path: '/security-audit', label: 'Security Audit', icon: ShieldAlert },
    { path: '/settings', label: 'Settings', icon: Settings },
  ].filter(item => isRouteAllowed(item.path));
  const showCockpitSection = cockpitNavItems.length > 0;
  const showAcademiaHubSection =
    canAccessAcademiaHub(currentUser) && isRouteAllowed('/academia');

  useEffect(() => {
    if (location.pathname.replace(/\/$/, '') === '/messaging-hub') {
      setMessagingHubPulse(false);
    } else if (unreadMessageCount > 0) {
      setMessagingHubPulse(true);
    }
  }, [location.pathname, unreadMessageCount, setMessagingHubPulse]);

  useEffect(() => {
    if (STUDENT_PIPELINE_PATHS.some(path => isRouteActive(currentPath, path))) {
      setIsStudentsOpen(true);
    }
    if (['/my-bookings', '/counselling'].some(path => isRouteActive(currentPath, path))) {
      setIsAppointmentsOpen(true);
    }
    if (['/ai-active', '/handoffs', '/prospects', '/offline-leads', '/archive', '/quarantine'].some(path => isRouteActive(currentPath, path))) {
      setIsLeadsOpen(true);
    }
    if (['/users', '/access-control'].some(path => isRouteActive(currentPath, path))) {
      setIsUsersOpen(true);
    }
    if (['/reports/meta-leads', '/reports/audit-logs', '/reports', '/analytics'].some(path => isRouteActive(currentPath, path))) {
      setIsReportsOpen(true);
    }
    if (currentPath.startsWith('/academia')) {
      setIsAcademiaOpen(true);
    }
  }, [currentPath]);

  return (
    <aside
      className={`${
        isSidebarOpen ? 'w-64' : 'w-20'
      } flex flex-col bg-canvas text-text-dark-bg transition-all duration-300 ease-in-out border-r border-border-subtle z-50`}
    >
      <div className="h-16 flex items-center justify-between px-4 border-b border-border-subtle/50">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center shrink-0 shadow-lg shadow-accent/20">
            <span className="text-text-dark-bg font-bold tracking-tighter italic">N</span>
          </div>
          {isSidebarOpen && <span className="font-bold text-lg text-white tracking-tight">NEXUS</span>}
        </div>
        <button
          type="button"
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="p-1.5 rounded-md hover:bg-card transition-colors text-text-muted hover:text-text-main"
        >
          {isSidebarOpen ? <ChevronLeft size={18} /> : <Menu size={18} />}
        </button>
      </div>

      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto custom-scrollbar">
        {allowedRoutes === null ? (
          <div className="px-3 py-4 text-xs text-text-muted italic">Loading navigation...</div>
        ) : (
          <>
            {isRouteAllowed('/') && (
              <Link
                to="/"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all ${
                  isRouteActive(currentPath, '/')
                    ? 'bg-accent text-text-dark-bg shadow-md shadow-accent/20 border-l-2 border-chart-secondary'
                    : 'hover:bg-card/40 hover:text-text-dark-bg'
                }`}
              >
                <LayoutDashboard size={20} />
                {isSidebarOpen && <span className="text-sm font-medium tracking-wide">Dashboard</span>}
              </Link>
            )}

            {canAccessMessaging && (
              <Link
                to="/messaging-hub"
                className={`relative flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all group mt-1 ${
                  messagingHubPulse && unreadMessageCount > 0 ? 'message-hub-nav-unread' : ''
                } ${
                  isRouteActive(currentPath, '/messaging-hub')
                    ? 'bg-card/60 text-text-main border-l-2 border-accent'
                    : 'hover:bg-card/40 hover:text-text-dark-bg'
                }`}
              >
                <MessagesSquare
                  size={20}
                  className={messagingHubPulse && unreadMessageCount > 0 ? 'text-primary' : 'text-text-dark-bg'}
                />
                {isSidebarOpen && (
                  <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                    <span className="text-sm font-medium tracking-wide">Chat</span>
                    {unreadMessageCount > 0 && (
                      <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
                        {unreadMessageCount > 99 ? '99+' : unreadMessageCount}
                      </span>
                    )}
                  </span>
                )}
                {!isSidebarOpen && unreadMessageCount > 0 && (
                  <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500" aria-hidden />
                )}
              </Link>
            )}

            {showAppointmentsSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsAppointmentsOpen(!isAppointmentsOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg mt-1 ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Calendar size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Appointments</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isAppointmentsOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isAppointmentsOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {appointmentNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {showLeadsSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsLeadsOpen(!isLeadsOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Users size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Manage Leads</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isLeadsOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isLeadsOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {visibleLeadNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {showStudentsSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsStudentsOpen(!isStudentsOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg mt-1 ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <GraduationCap size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Manage Students</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isStudentsOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isStudentsOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {studentNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {showUsersSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsUsersOpen(!isUsersOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg mt-1 ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <UserCog size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Users</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isUsersOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isUsersOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {visibleUserNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {showReportsSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsReportsOpen(!isReportsOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <FileText size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Reports</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isReportsOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isReportsOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {visibleReportNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {showAcademiaHubSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsAcademiaOpen(!isAcademiaOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg mt-1 ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <BookOpen size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Academia Hub</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isAcademiaOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isAcademiaOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-3">
                    {ACADEMIA_HUB_SECTIONS.map(section =>
                      section.tabbed ? (
                        <Link
                          key={section.key}
                          to={section.path}
                          className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                            isRouteActive(currentPath, section.path)
                              ? 'bg-card/60 text-text-main border-l-2 border-accent'
                              : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                          }`}
                        >
                          <span>{section.label}</span>
                        </Link>
                      ) : (
                        <div key={section.key} className="space-y-1">
                          <div className="px-3 pt-1 text-[10px] font-bold uppercase tracking-wider text-text-muted/80">
                            {section.label}
                          </div>
                          {section.items.map(item => (
                            <Link
                              key={item.path}
                              to={item.path}
                              className={`flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                                isRouteActive(currentPath, item.path)
                                  ? 'bg-card/60 text-text-main border-l-2 border-accent'
                                  : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                              }`}
                            >
                              <span>{item.label}</span>
                            </Link>
                          ))}
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            )}

            {showCockpitSection && (
              <div className="pt-2 lg:hidden">
                <button
                  type="button"
                  onClick={() => isSidebarOpen && setIsCockpitOpen(!isCockpitOpen)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all group hover:bg-card/40 hover:text-text-dark-bg mt-1 ${
                    !isSidebarOpen ? 'justify-center' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Gauge size={20} className="text-text-dark-bg" />
                    {isSidebarOpen && <span className="text-sm font-medium">Cockpit</span>}
                  </div>
                  {isSidebarOpen && (
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${isCockpitOpen ? 'rotate-180' : ''}`}
                    />
                  )}
                </button>

                {isSidebarOpen && isCockpitOpen && (
                  <div className="mt-1 ml-4 pl-4 border-l border-border-subtle space-y-1">
                    {cockpitNavItems.map(item => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-all ${
                          isRouteActive(currentPath, item.path)
                            ? 'bg-card/60 text-text-main border-l-2 border-accent'
                            : 'text-text-dark-bg hover:bg-card/40 hover:text-text-dark-bg'
                        }`}
                      >
                        <item.icon size={14} />
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

          </>
        )}
      </nav>
    </aside>
  );
};

export default Sidebar;
