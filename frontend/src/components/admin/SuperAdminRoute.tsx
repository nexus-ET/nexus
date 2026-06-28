import React from 'react';
import { useOutletContext } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { isSuperAdmin } from '../../utils/adminAccess';

interface SuperAdminUser {
  is_superuser?: boolean;
  admin_role?: { name?: string | null } | null;
}

interface DashboardOutletContext {
  currentUser?: SuperAdminUser | null;
}

interface SuperAdminRouteProps {
  children: React.ReactNode;
}

const isSuperAdminUser = isSuperAdmin;

/**
 * Restricts access to Super Admins only (is_superuser or Super Admin role).
 * Reuses the dashboard session user when available to avoid duplicate users/me calls.
 */
const SuperAdminRoute: React.FC<SuperAdminRouteProps> = ({ children }) => {
  const { currentUser: outletUser } = useOutletContext<DashboardOutletContext>() ?? {};
  const [loading, setLoading] = React.useState(() => !outletUser);
  const [allowed, setAllowed] = React.useState(() => isSuperAdminUser(outletUser));

  React.useEffect(() => {
    if (outletUser) {
      setAllowed(isSuperAdminUser(outletUser));
      setLoading(false);
      return;
    }

    let active = true;
    apiFetch('users/me')
      .then(data => {
        if (!active) return;
        setAllowed(isSuperAdminUser(data as SuperAdminUser));
      })
      .catch(() => {
        if (active) setAllowed(false);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [outletUser]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted text-sm">
        <Loader2 size={18} className="animate-spin mr-2" />
        Verifying Super Admin access...
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-6 text-sm text-amber-900">
        Audit Logs are restricted to Super Admin users.
      </div>
    );
  }

  return <>{children}</>;
};

export default SuperAdminRoute;
