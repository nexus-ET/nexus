export interface SuperAdminCapableUser {
  is_superuser?: boolean;
  admin_role?: { name?: string | null } | null;
  role?: string | null;
}

export function isSuperAdmin(user: SuperAdminCapableUser | null | undefined): boolean {
  if (!user) return false;
  const roleName = user.admin_role?.name || user.role || '';
  return Boolean(user.is_superuser) || roleName === 'Super Admin';
}

const LIFECYCLE_MANAGER_ROLES = new Set(['Student Manager', 'Super Admin', 'Web Admin']);

export function canUseExpressLifecycleTransitions(user: SuperAdminCapableUser | null | undefined): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  const roleName = user.admin_role?.name || user.role || '';
  return LIFECYCLE_MANAGER_ROLES.has(roleName);
}
