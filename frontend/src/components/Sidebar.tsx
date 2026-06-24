import { useEffect, useState } from 'react';
import { isAllowedRoute, isRouteActive, normalizePath } from '../utils/routeAccess';
import { Link, useLocation } from 'react-router-dom';
import { useNexusSession } from '../context/NexusSessionContext';
import {
  LayoutDashboard,
  Users,
  Bot,
  BarChart3,
  Settings,
  ShieldAlert,
  Calendar,
  ChevronLeft,
  Menu,
  ChevronDown,
  UserCog,
  CalendarCheck,
  Radio,
  MessagesSquare,
  FileText,
  AlertTriangle,
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
  const [isLeadsOpen, setIsLeadsOpen] = useState(true);
  const [isUsersOpen, setIsUsersOpen] = useState(true);

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
    { path: '/archive', label: 'Archive' },
  ];

  const userNavItems = [
    { path: '/users', label: 'Manage Users' },
    { path: '/access-control', label: 'Access Control' },
  ];

  const visibleLeadNavItems = leadNavItems.filter(item => isRouteAllowed(item.path));
  const showLeadsSection = visibleLeadNavItems.length > 0;
  const visibleUserNavItems = userNavItems.filter(item => isRouteAllowed(item.path));
  const showUsersSection = visibleUserNavItems.length > 0;

  const navLinks = [
    { id: 'agents', icon: Bot, label: 'AI Agents', path: '/agents' },
    { id: 'analytics', icon: BarChart3, label: 'Analytics', path: '/analytics' },
    { id: 'reports', icon: FileText, label: 'Reports', path: '/reports' },
    { id: 'quarantine', icon: AlertTriangle, label: 'Lead Quarantine', path: '/quarantine' },
    ...(canAccessCounselling
      ? [
          { id: 'counselling', icon: Calendar, label: 'Counselling', path: '/counselling' },
          { id: 'command-center', icon: Radio, label: 'Command Center', path: '/command-center' },
        ]
      : []),
    ...(canAccessMessaging
      ? [{ id: 'messaging-hub', icon: MessagesSquare, label: 'Messaging Hub', path: '/messaging-hub' }]
      : []),
    { id: 'security-audit', icon: ShieldAlert, label: 'Security Audit', path: '/security-audit' },
    { id: 'settings', icon: Settings, label: 'Settings', path: '/settings' },
  ].filter(link => isRouteAllowed(link.path));

  useEffect(() => {
    if (location.pathname.replace(/\/$/, '') === '/messaging-hub') {
      setMessagingHubPulse(false);
    } else if (unreadMessageCount > 0) {
      setMessagingHubPulse(true);
    }
  }, [location.pathname, unreadMessageCount, setMessagingHubPulse]);

  useEffect(() => {
    if (['/ai-active', '/handoffs', '/prospects', '/archive'].some(path => isRouteActive(currentPath, path))) {
      setIsLeadsOpen(true);
    }
    if (['/users', '/access-control'].some(path => isRouteActive(currentPath, path))) {
      setIsUsersOpen(true);
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

            {canAccessMyBookings && (
              <Link
                to="/my-bookings"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all group ${
                  isRouteActive(currentPath, '/my-bookings')
                    ? 'bg-card/60 text-text-main border-l-2 border-accent'
                    : 'hover:bg-card/40 hover:text-text-dark-bg'
                }`}
              >
                <CalendarCheck size={20} className="text-text-dark-bg" />
                {isSidebarOpen && <span className="text-sm font-medium tracking-wide">My Bookings</span>}
              </Link>
            )}

            {showUsersSection && (
              <div className="pt-2">
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

            {showLeadsSection && (
              <div className="pt-2">
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

            {navLinks.map(link => {
              const isMessagingHub = link.id === 'messaging-hub';
              const showUnreadBadge = isMessagingHub && unreadMessageCount > 0;
              const pulseNav = isMessagingHub && messagingHubPulse && unreadMessageCount > 0;

              return (
              <Link
                key={link.id}
                to={link.path}
                className={`relative flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all group ${
                  pulseNav ? 'message-hub-nav-unread' : ''
                } ${
                  isRouteActive(currentPath, link.path)
                    ? 'bg-card/60 text-text-main border-l-2 border-accent'
                    : 'hover:bg-card/40 hover:text-text-dark-bg'
                }`}
              >
                <link.icon size={20} className={pulseNav ? 'text-primary' : 'text-text-dark-bg'} />
                {isSidebarOpen && (
                  <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                    <span className="text-sm font-medium tracking-wide">{link.label}</span>
                    {showUnreadBadge && (
                      <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
                        {unreadMessageCount > 99 ? '99+' : unreadMessageCount}
                      </span>
                    )}
                  </span>
                )}
                {!isSidebarOpen && showUnreadBadge && (
                  <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500" aria-hidden />
                )}
              </Link>
            );
            })}
          </>
        )}
      </nav>
    </aside>
  );
};

export default Sidebar;
