import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, Link, useLocation, Outlet, Navigate } from 'react-router-dom';
import {
  Bot,
  Search,
  MoreVertical,
  ArrowUpRight,
  Clock,
  Database,
  AlertTriangle,
  ShieldAlert,
  ExternalLink,
  Check,
  RefreshCw
} from 'lucide-react';
import { apiFetch, getStoredToken, clearSession } from '../utils/api';
import { isAllowedRoute, normalizePath } from '../utils/routeAccess';
import Sidebar from '../components/Sidebar';
import UserProfileMenu from '../components/UserProfileMenu';
import NotificationBell from '../components/NotificationBell';
import { usePushNotifications } from '../hooks/usePushNotifications';
import MetaLeadSyncPanel from '../components/dashboard/MetaLeadSyncPanel';

// --- SCHEMA & DATA LAYER INTERFACES ---
interface DashboardMetric {
  label: string;
  value: string | number;
  color: 'amber' | 'alert' | 'muted' | 'accent';
  icon: React.ComponentType<any>;
}

interface SystemNotification {
  id: number;
  title: string;
  message: string;
  severity: 'HIGH' | 'WARNING' | 'INFO';
  created_at?: string;
  link_path?: string;
}

interface StudentLead {
  id: number;
  full_name: string;
  status: 'QUALIFIED' | 'NEEDS_AUDIT' | 'CONVERTED';
  destination_country?: string;
}

interface CurrentUser {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  admin_role?: { name?: string | null } | null;
}

const parseUserDisplay = (user: CurrentUser | null) => {
  if (!user) {
    return {
      firstName: 'Guest',
      lastName: 'User',
      role: '—',
      initials: 'GU',
    };
  }

  const fallbackName = user.email.split('@')[0] || 'User';
  const firstName = (user.first_name || '').trim() || fallbackName;
  const lastName = (user.last_name || '').trim() || '';
  const initials = lastName
    ? `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase()
    : firstName.slice(0, 2).toUpperCase();

  return {
    firstName,
    lastName,
    role: user.role || 'Admin',
    initials,
  };
};

interface DashboardSummary {
  awaiting_consultation: number;
  escalation_queue: number;
  missing_post_audit: number;
  missing_audit_count: number;
  active_ai_chats: number;
  notifications: SystemNotification[];
  leads: StudentLead[];
}

const INITIAL_DASHBOARD: DashboardSummary = {
  awaiting_consultation: 0,
  escalation_queue: 0,
  missing_post_audit: 0,
  missing_audit_count: 0,
  active_ai_chats: 0,
  notifications: [],
  leads: [],
};

const DASHBOARD_POLL_INTERVAL_MS = 30_000;

const NexusDashboard: React.FC = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [aiEngineActive, setAiEngineActive] = useState(true);

  const [dashboard, setDashboard] = useState<DashboardSummary>(INITIAL_DASHBOARD);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [allowedRoutes, setAllowedRoutes] = useState<string[]>(['/']);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const location = useLocation();
  const isInitialMount = useRef(true);
  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const userDisplay = parseUserDisplay(currentUser);
  usePushNotifications();

  const currentPath = normalizePath(location.pathname);
  const isMessagingHub = currentPath === '/messaging-hub';
  const canAccessCurrentRoute = isAllowedRoute(currentPath, allowedRoutes);

  const loadAllowedRoutes = useCallback(async () => {
    if (!getStoredToken()) {
      setAllowedRoutes(['/']);
      return;
    }

    try {
      const data = await apiFetch('permissions/my-role');
      const payload = data as { allowed_routes?: string[] };
      setAllowedRoutes(payload.allowed_routes?.length ? payload.allowed_routes : ['/']);
    } catch {
      setAllowedRoutes(['/']);
    }
  }, []);

  useEffect(() => {
    if (!getStoredToken()) return;

    apiFetch('users/me')
      .then(data => setCurrentUser(data as CurrentUser))
      .catch(() => setCurrentUser(null));

    loadAllowedRoutes();
  }, [loadAllowedRoutes]);

  useEffect(() => {
    const handlePermissionsChanged = () => {
      loadAllowedRoutes();
    };

    window.addEventListener('nexus:nav-permissions-changed', handlePermissionsChanged);
    return () => {
      window.removeEventListener('nexus:nav-permissions-changed', handlePermissionsChanged);
    };
  }, [loadAllowedRoutes]);

  const metrics: DashboardMetric[] = [
    { label: 'Awaiting Consultation', value: dashboard.awaiting_consultation, color: 'amber', icon: Clock },
    { label: 'Escalation Queue', value: dashboard.escalation_queue, color: 'alert', icon: AlertTriangle },
    { label: 'Missing Post-Audit', value: dashboard.missing_post_audit, color: 'muted', icon: ShieldAlert },
    { label: 'Active AI Chats', value: dashboard.active_ai_chats.toLocaleString(), color: 'accent', icon: Bot },
  ];

  // Fetch dashboard summary from a single API endpoint
  async function fetchDashboardSummary(signal?: AbortSignal, showLoading = true) {
    try {
      if (showLoading) setLoading(true);
      setError(null);

      const data = await apiFetch('dashboard/summary', { signal }) as DashboardSummary;

      if (signal?.aborted) return;

      setDashboard({
        awaiting_consultation: data.awaiting_consultation ?? 0,
        escalation_queue: data.escalation_queue ?? 0,
        missing_post_audit: data.missing_post_audit ?? data.missing_audit_count ?? 0,
        missing_audit_count: data.missing_audit_count ?? data.missing_post_audit ?? 0,
        active_ai_chats: data.active_ai_chats ?? 0,
        notifications: data.notifications ?? [],
        leads: data.leads ?? [],
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      console.error('Dashboard failed to synchronize:', err);

      const message = err instanceof Error ? err.message : 'Failed to synchronize matrix parameters.';
      if (message.toLowerCase().includes('access denied')) {
        setError('Dashboard access is disabled for your role. Re-enable it in Access Control.');
        return;
      }

      setError(message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    if (location.pathname !== '/') return;
    if (!getStoredToken()) {
      navigate('/login');
      return;
    }

    let isActive = true;

    async function loadDashboard(showLoading: boolean) {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      abortControllerRef.current = new AbortController();

      await fetchDashboardSummary(abortControllerRef.current.signal, showLoading);

      if (isActive && location.pathname === '/') {
        pollingTimerRef.current = setTimeout(() => loadDashboard(false), DASHBOARD_POLL_INTERVAL_MS);
      }
    }

    const showLoading = isInitialMount.current || dashboard.leads.length === 0;
    loadDashboard(showLoading);
    isInitialMount.current = false;

    return () => {
      isActive = false;
      if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [location.pathname]);

  // Action mutation handler
  async function handleResolveAlert(id: number) {
    try {
      await apiFetch(`notifications/${id}/resolve`, { method: 'POST' });
      setDashboard(prev => ({
        ...prev,
        notifications: prev.notifications.filter(n => n.id !== id),
      }));
    } catch (err: unknown) {
      alert(`Could not clear alert node: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }

  const handleLogout = () => {
    clearSession();
    navigate('/login');
  };

  return (
    <div className="flex h-screen w-full bg-surface-bg overflow-hidden font-sans text-text-main">
      <Sidebar
        isSidebarOpen={isSidebarOpen}
        setIsSidebarOpen={setIsSidebarOpen}
        allowedRoutes={allowedRoutes}
        currentUser={currentUser}
      />

      {/* --- TOP HEADER AND CONTAINER WORKSPACE --- */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        <header className="sticky top-0 h-16 bg-card/80 backdrop-blur-md border-b border-border-subtle flex items-center justify-between px-8 z-40">
          <div className="flex items-center gap-6 shrink-0">
            <div className="flex items-center gap-2 px-3 py-1 bg-card border border-border-subtle rounded-full">
              <Bot size={14} className="text-success" />
              <span className={`w-2 h-2 rounded-full bg-success ${aiEngineActive ? 'animate-pulse' : ''}`} />
              <span className="text-[11px] font-bold text-success tracking-wider uppercase">AI Engine: Active</span>
            </div>
          </div>

          <div className="flex-1 max-w-2xl px-8">
            <div className="relative group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted group-focus-within:text-accent transition-colors" size={18} />
              <input 
                type="text"
                placeholder="Search leads, countries, scores..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-surface-bg border border-transparent rounded-xl text-sm focus:outline-none focus:bg-card focus:border-accent focus:ring-4 focus:ring-accent/10 transition-all text-text-main placeholder:text-text-muted/60"
              />
            </div>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <NotificationBell />
            <div className="h-8 w-px bg-border-subtle mx-2" />
            <UserProfileMenu
              firstName={userDisplay.firstName}
              lastName={userDisplay.lastName}
              role={userDisplay.role}
              initials={userDisplay.initials}
              onLogout={handleLogout}
            />
          </div>
        </header>

        {/* --- MAIN PAGE CONTENT OUTLET --- */}
        <main
          className={`relative flex-1 ${
            isMessagingHub ? 'flex min-h-0 flex-col overflow-hidden p-4 md:p-6' : 'overflow-y-auto p-8'
          }`}
        >
          <div className="absolute inset-0 z-0 pointer-events-none opacity-15" style={{ backgroundImage: 'radial-gradient(var(--color-text-muted) 1px, transparent 1px)', backgroundSize: '24px 24px' }} />

          {location.pathname === '/' ? (
            <div className="relative z-10 max-w-7xl mx-auto space-y-8">
              
              {error && (
                <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
                  {error} - Automatically re-attempting upstream connections...
                </div>
              )}

              <div className="flex items-end justify-between">
                <div>
                  <h2 className="text-2xl font-extrabold text-text-main tracking-tight">Education Intelligence</h2>
                  <p className="text-text-muted text-sm">Managing the automated intake pipeline for university success.</p>
                </div>
                <button 
                  onClick={() => fetchDashboardSummary(undefined, true)}
                  disabled={loading}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all disabled:opacity-50"
                >
                  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                  Sync Pipeline
                </button>
              </div>

              <MetaLeadSyncPanel />

              {/* --- 4-CARD DATA HERO ROW --- */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {loading && dashboard.leads.length === 0 ? (
                  Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="bg-card border border-border-subtle p-5 h-32 rounded-2xl animate-pulse" />
                  ))
                ) : (
                  metrics.map((metric) => (
                    <Link 
                      key={metric.label} 
                      to={metric.label === 'Awaiting Consultation' ? '/handoffs' : metric.label === 'Active AI Chats' ? '/ai-active' : '#'}
                      className="bg-card border border-border-subtle p-5 rounded-2xl shadow-sm hover:shadow-md transition-all group block"
                    >
                      <div className="flex justify-between items-start mb-4">
                        <div className={`p-2.5 rounded-xl ${
                          metric.color === 'amber' ? 'bg-amber-50 text-amber-600' :
                          metric.color === 'alert' ? 'bg-alert/10 text-alert' :
                          metric.color === 'muted' ? 'bg-surface-bg text-text-muted' : 'bg-accent/10 text-accent'
                        }`}>
                          <metric.icon size={20} />
                        </div>
                        <ArrowUpRight size={16} className="text-text-muted/40 group-hover:text-text-muted transition-colors" />
                      </div>
                      <p className="text-text-muted text-[11px] font-bold uppercase tracking-widest mb-1">{metric.label}</p>
                      <h3 className="text-2xl font-black text-text-main">{metric.value}</h3>
                    </Link>
                  ))
                )}
              </div>

              {/* --- ACTION FEED AND QUALIFICATION PIPELINE --- */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pb-12">
                
                {/* Left Column: Action Feed */}
                <div className="lg:col-span-1 space-y-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-black text-text-main uppercase tracking-tighter">Actionable Feed</h4>
                    <span className="text-[10px] font-bold text-accent bg-accent/10 px-2 py-0.5 rounded-full uppercase">Real-time</span>
                  </div>
                  <div className="space-y-4 max-h-[600px] overflow-y-auto custom-scrollbar pr-2">
                    {loading && dashboard.notifications.length === 0 ? (
                      <div className="text-xs text-text-muted italic">Polling infrastructure stream layers...</div>
                    ) : dashboard.notifications.length === 0 ? (
                      <div className="p-8 text-center text-xs text-text-muted border border-dashed border-border-subtle rounded-xl bg-card">
                        All clear. No exceptional log items require handling.
                      </div>
                    ) : (
                      dashboard.notifications.map((n) => (
                        <div key={n.id} className={`p-4 rounded-xl border-l-4 shadow-sm space-y-3 bg-card ${
                          n.severity === 'HIGH' ? 'border-alert' : n.severity === 'WARNING' ? 'border-amber-500' : 'border-accent'
                        }`}>
                          <div className="flex justify-between items-start">
                            <h5 className="text-sm font-bold text-text-main">{n.title}</h5>
                            <span className="text-[10px] text-text-muted font-medium">
                              {n.created_at ? new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Just now'}
                            </span>
                          </div>
                          <p className="text-xs text-text-muted leading-relaxed">{n.message}</p>
                          <div className="flex gap-2">
                            <Link to={n.link_path || "/handoffs"} className="flex-1 px-3 py-1.5 bg-surface-bg border border-border-subtle rounded-lg text-[10px] font-bold text-text-main hover:bg-border-subtle/40 transition-colors flex items-center justify-center gap-1.5">
                              <ExternalLink size={12} /> Inspect
                            </Link>
                            <button onClick={() => handleResolveAlert(n.id)} className="flex-1 px-3 py-1.5 bg-text-main rounded-lg text-[10px] font-bold text-text-dark-bg hover:opacity-90 transition-all flex items-center justify-center gap-1.5">
                              <Check size={12} /> Resolve
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Right Column: Dynamic Pipeline Tracker */}
                <div className="lg:col-span-2">
                  <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
                    <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30 flex items-center justify-between">
                      <h4 className="text-sm font-bold text-text-main">Student Qualification Pipeline</h4>
                      <button className="text-text-muted hover:text-text-main"><MoreVertical size={16} /></button>
                    </div>
                    <table className="w-full text-left">
                      <thead>
                        <tr className="text-[10px] font-black text-text-muted uppercase tracking-widest border-b border-border-subtle">
                          <th className="px-6 py-4">Student Lead</th>
                          <th className="px-6 py-4">AI status</th>
                          <th className="px-6 py-4">Destination</th>
                          <th className="px-6 py-4 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle/50">
                        {loading && dashboard.leads.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="px-6 py-8 text-center text-xs text-text-muted italic">Polling qualification datasets...</td>
                          </tr>
                        ) : dashboard.leads.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="px-6 py-8 text-center text-xs text-text-muted italic">No leads detected in current active pipelines.</td>
                          </tr>
                        ) : (
                          dashboard.leads.map((lead) => (
                            <tr key={lead.id} className="group hover:bg-surface-bg/30 transition-colors">
                              <td className="px-6 py-4 text-sm font-bold text-text-main">{lead.full_name}</td>
                              <td className="px-6 py-4">
                                <span className={`px-2.5 py-1 rounded-full text-[10px] font-black uppercase ${
                                  lead.status === 'QUALIFIED' ? 'text-success bg-accent/10' :
                                  lead.status === 'NEEDS_AUDIT' ? 'text-amber-600 bg-amber-50' : 'text-accent bg-accent/10'
                                }`}>
                                  {lead.status?.replace('_', ' ')}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-sm text-text-muted font-medium">{lead.destination_country || 'Unassigned'}</td>
                              <td className="px-6 py-4 text-right">
                                <Link 
                                  to={lead.status === 'QUALIFIED' ? '/handoffs' : '/ai-active'} 
                                  className="p-1.5 text-text-muted hover:text-accent transition-colors inline-block"
                                >
                                  <ExternalLink size={16} />
                                </Link>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

              </div>
            </div>
          ) : !canAccessCurrentRoute ? (
            <Navigate to={allowedRoutes[0] || '/'} replace />
          ) : (
            <div
              className={`relative z-10 w-full animate-in fade-in slide-in-from-bottom-2 duration-300 ${
                isMessagingHub ? 'flex min-h-0 flex-1 flex-col' : 'h-full'
              }`}
            >
              <Outlet />
            </div>
          )}
        </main>

        {/* --- GLOBAL PERSISTENT FOOTER --- */}
        <footer className="sticky bottom-0 w-full h-10 bg-card border-t border-border-subtle flex items-center justify-between px-8 z-40">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Database size={14} className="text-accent" />
              <span className="text-[10px] font-bold text-text-muted">
                CRM Database: <span className="text-success uppercase tracking-tighter">In Sync</span>
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-[10px] font-mono text-text-muted/50">v1.2.4-STABLE</span>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default NexusDashboard;