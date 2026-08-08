import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface NavigationPage {
  id: number;
  name: string;
  route: string;
  icon?: string | null;
  sort_order?: number;
}

interface AdminRoleOption {
  id: number;
  name: string;
  is_superuser?: boolean;
}

interface RolePermissionItem {
  navigation_page_id: number;
  route: string;
  name: string;
  can_access: boolean;
}

interface RolePermissionsResponse {
  role: string;
  admin_role_id: number;
  permissions: RolePermissionItem[];
}

const permissionKey = (roleId: number, pageId: number) => `${roleId}:${pageId}`;

const AccessControl: React.FC = () => {
  const [pages, setPages] = useState<NavigationPage[]>([]);
  const [roles, setRoles] = useState<AdminRoleOption[]>([]);
  const [permissionMap, setPermissionMap] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);

  const loadMatrix = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setAccessDenied(false);

      const [pagesData, rolesData] = await Promise.all([
        apiFetch('pages'),
        apiFetch('users/admin-roles'),
      ]);

      const pageList = Array.isArray(pagesData) ? (pagesData as NavigationPage[]) : [];
      const roleList = Array.isArray(rolesData) ? (rolesData as AdminRoleOption[]) : [];

      const permissionResponses = await Promise.all(
        roleList.map(role =>
          apiFetch(`permissions/${encodeURIComponent(role.name)}`) as Promise<RolePermissionsResponse>
        )
      );

      const nextMap: Record<string, boolean> = {};
      permissionResponses.forEach(response => {
        response.permissions.forEach(item => {
          nextMap[permissionKey(response.admin_role_id, item.navigation_page_id)] = item.can_access;
        });
      });

      setPages(pageList);
      setRoles(roleList);
      setPermissionMap(nextMap);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load navigation permissions.';
      if (
        message.toLowerCase().includes('super admin') ||
        message.toLowerCase().includes('access denied')
      ) {
        setAccessDenied(true);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMatrix();
  }, [loadMatrix]);

  const sortedPages = useMemo(
    () => [...pages].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [pages]
  );

  const handleToggle = async (role: AdminRoleOption, page: NavigationPage, nextValue: boolean) => {
    const key = permissionKey(role.id, page.id);
    const previousValue = permissionMap[key] ?? false;

    setPermissionMap(prev => ({ ...prev, [key]: nextValue }));
    setSavingKey(key);
    setError(null);

    try {
      await apiFetch('permissions', {
        method: 'POST',
        body: JSON.stringify({
          role: role.name,
          navigation_page_id: page.id,
          can_access: nextValue,
        }),
      });
      window.dispatchEvent(new CustomEvent('nexus:nav-permissions-changed'));
    } catch (err: unknown) {
      setPermissionMap(prev => ({ ...prev, [key]: previousValue }));
      setError(err instanceof Error ? err.message : 'Failed to update permission.');
    } finally {
      setSavingKey(null);
    }
  };

  if (accessDenied) {
    return (
      <div className="relative z-10 mx-auto w-full max-w-none">
        <div className="p-8 bg-card border border-border-subtle rounded-2xl text-center">
          <ShieldCheck size={32} className="mx-auto mb-3 text-alert" />
          <h2 className="text-lg font-bold text-text-main">Super Admin Access Required</h2>
          <p className="text-sm text-text-muted mt-2">
            The Navigation Manager is restricted to Super Admin accounts.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative z-10 mx-auto w-full max-w-none space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck size={18} className="text-accent" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-text-muted">
              Security
            </span>
          </div>
          <h2 className="text-2xl font-extrabold text-text-main tracking-tight">Navigation Manager</h2>
          <p className="text-text-muted text-sm">
            Control which sidebar pages each role can access. Changes save immediately.
          </p>
        </div>

        <button
          type="button"
          onClick={loadMatrix}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
          {error}
        </div>
      )}

      <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30">
          <h3 className="text-sm font-bold text-text-main">Role Page Permissions</h3>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading navigation permissions...
          </div>
        ) : sortedPages.length === 0 || roles.length === 0 ? (
          <div className="px-6 py-16 text-center text-sm text-text-muted">
            No navigation pages or roles are configured yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left min-w-[960px]">
              <thead>
                <tr className="text-[10px] font-black text-text-muted uppercase tracking-widest border-b border-border-subtle">
                  <th className="px-6 py-4 sticky left-0 bg-card z-10">Navigation Page</th>
                  <th className="px-6 py-4">Route</th>
                  {roles.map(role => (
                    <th key={role.id} className="px-6 py-4 text-center whitespace-nowrap">
                      {role.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/50">
                {sortedPages.map(page => (
                  <tr key={page.id} className="hover:bg-surface-bg/30 transition-colors">
                    <td className="px-6 py-4 text-sm font-bold text-text-main sticky left-0 bg-card">
                      {page.name}
                    </td>
                    <td className="px-6 py-4 text-sm text-text-muted font-mono">{page.route}</td>
                    {roles.map(role => {
                      const key = permissionKey(role.id, page.id);
                      const checked = permissionMap[key] ?? false;
                      const isSaving = savingKey === key;

                      return (
                        <td key={role.id} className="px-6 py-4">
                          <div className="flex items-center justify-center">
                            <label className="inline-flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={isSaving}
                                onChange={e =>
                                  handleToggle(role, page, e.target.checked)
                                }
                                className="h-4 w-4 rounded border-border-subtle accent-accent"
                              />
                              {isSaving && <Loader2 size={12} className="animate-spin text-text-muted" />}
                            </label>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AccessControl;
