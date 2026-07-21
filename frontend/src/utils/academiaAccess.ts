const ACADEMIA_ADMIN_ROLES = new Set(['Super Admin', 'Web Admin']);

interface AcademiaAccessUser {
  role?: string | null;
  admin_role?: { name?: string | null } | null;
  is_superuser?: boolean;
}

export const canAccessAcademiaHub = (user: AcademiaAccessUser | null | undefined): boolean => {
  if (!user) return false;
  if (user.is_superuser) return true;
  const roleName = user.admin_role?.name || user.role || '';
  return ACADEMIA_ADMIN_ROLES.has(roleName);
};
