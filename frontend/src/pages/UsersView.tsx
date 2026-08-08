import React, { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  ShieldCheck,
  Plus,
  Pencil,
  UserX,
  UserCheck,
  Loader2,
  RefreshCw,
  X,
  Eye,
  EyeOff,
  Trash2,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import { isSuperAdmin } from '../utils/adminAccess';
import BusinessDomainEmailField from '../components/BusinessDomainEmailField';
import StatusChangeModal from '../components/StatusChangeModal';
import UserStatusPill from '../components/UserStatusPill';
import {
  PHONE_LOCAL_DRAFT_MAX_LENGTH,
  PHONE_LOCAL_PLACEHOLDER,
  PHONE_LOCAL_REQUIREMENTS,
  formatFullPhone,
  formatPhoneCountryLabel,
  parseStoredPhone,
  sanitizePhoneLocalDraft,
  validatePhoneWithCountry,
} from '../utils/phoneCountry';
import { useCountries } from '../hooks/useCountries';
import { useConfirmation } from '../context/ConfirmationContext';
import {
  buildBusinessEmail,
  splitEmailUsername,
  validateEmailUsername,
} from '../utils/businessEmail';

interface StatusChangeReason {
  id: number;
  reason_type: string;
  reason: string;
  description: string;
}

interface AdminRoleOption {
  id: number;
  name: string;
  description?: string | null;
  is_superuser?: boolean;
  sort_order?: number;
}

interface AdminUser {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  phone_number?: string | null;
  admin_role_id?: number | null;
  admin_role?: AdminRoleOption | null;
  role?: string | null;
  is_active?: boolean;
  is_superuser?: boolean;
  creation_reason?: number | null;
  creation_date?: string | null;
  deactivation_reason?: number | null;
  deactivation_date?: string | null;
  activation_reason?: number | null;
  activation_date?: string | null;
  deactivation_reason_detail?: StatusChangeReason | null;
}

interface UserFormState {
  first_name: string;
  last_name: string;
  email_username: string;
  phone_country_iso2: string;
  phone_number: string;
  password: string;
  admin_role_id: number | '';
}

const EMPTY_FORM: UserFormState = {
  first_name: '',
  last_name: '',
  email_username: '',
  phone_country_iso2: '',
  phone_number: '',
  password: '',
  admin_role_id: '',
};

const getInactiveReasonLabel = (user: AdminUser): string | null => {
  if (user.is_active) return null;
  return user.deactivation_reason_detail?.reason || 'Inactive';
};

const formatAdminName = (user: Pick<AdminUser, 'first_name' | 'last_name' | 'email'>): string => {
  const first = user.first_name?.trim() || '';
  const last = user.last_name?.trim() || '';
  if (first && last) return `${first} ${last}`;
  return first || last || user.email;
};

const resolveAdminRoleId = (
  adminRoleId: number | null | undefined,
  roleName: string | null | undefined,
  roles: AdminRoleOption[]
): number | '' => {
  if (adminRoleId && roles.some(item => item.id === adminRoleId)) {
    return adminRoleId;
  }
  if (roleName) {
    const match = roles.find(item => item.name === roleName);
    if (match) return match.id;
  }
  return roles[0]?.id ?? '';
};

const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_REQUIREMENTS =
  'Minimum 8 characters, including uppercase, lowercase, numbers, and special characters.';

const validatePassword = (password: string): string | null => {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters long.`;
  }

  const hasLower = /[a-z]/.test(password);
  const hasUpper = /[A-Z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);

  if (!hasLower || !hasUpper || !hasDigit || !hasSpecial) {
    return 'Password must include uppercase, lowercase, numbers, and special characters.';
  }

  return null;
};

const isDuplicateEmail = (
  email: string,
  users: AdminUser[],
  excludeUserId?: number
): boolean => {
  const normalized = email.trim().toLowerCase();
  return users.some(
    user =>
      user.id !== excludeUserId && user.email.trim().toLowerCase() === normalized
  );
};

const UsersView: React.FC = () => {
  const openConfirm = useConfirmation();
  const { currentUser } = useOutletContext<{ currentUser?: AdminUser | null }>() ?? {};
  const viewerIsSuperAdmin = isSuperAdmin(currentUser);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [form, setForm] = useState<UserFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [statusChangeTarget, setStatusChangeTarget] = useState<AdminUser | null>(null);
  const [statusChangeMode, setStatusChangeMode] = useState<'activate' | 'deactivate'>('deactivate');
  const [statusChanging, setStatusChanging] = useState(false);
  const [statusChangeError, setStatusChangeError] = useState<string | null>(null);
  const [adminRoles, setAdminRoles] = useState<AdminRoleOption[]>([]);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [businessEmailDomain, setBusinessEmailDomain] = useState<string | null>(null);
  const [loadingBusinessDomain, setLoadingBusinessDomain] = useState(true);
  const [emailUsernameError, setEmailUsernameError] = useState<string | null>(null);
  const { countries } = useCountries();

  const loadBusinessEmailDomain = useCallback(async () => {
    try {
      setLoadingBusinessDomain(true);
      const data = (await apiFetch('settings/business-email-domain')) as {
        email_domain?: string | null;
      };
      const domain = data.email_domain?.trim().toLowerCase() || null;
      setBusinessEmailDomain(domain);
      return domain;
    } catch {
      setBusinessEmailDomain(null);
      return null;
    } finally {
      setLoadingBusinessDomain(false);
    }
  }, []);

  const loadAdminRoles = useCallback(async () => {
    try {
      setLoadingRoles(true);
      const data = await apiFetch('users/admin-roles');
      const roles = Array.isArray(data) ? (data as AdminRoleOption[]) : [];
      setAdminRoles(roles);
      return roles;
    } catch {
      setAdminRoles([]);
      return [];
    } finally {
      setLoadingRoles(false);
    }
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const query = showInactive ? '?include_inactive=true' : '';
      const data = await apiFetch(`users${query}`);
      setUsers(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      if (err instanceof TypeError && err.message === 'Failed to fetch') {
        setError(
          'Cannot reach the API server. Confirm the backend is running at http://localhost:8000 and restart it if you recently updated the code.'
        );
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load admin users.');
      }
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    loadUsers();
    loadAdminRoles();
    loadBusinessEmailDomain();
  }, [loadUsers, loadAdminRoles, loadBusinessEmailDomain]);

  const openCreateModal = async () => {
    setEditingUser(null);
    const [roles] = await Promise.all([
      adminRoles.length > 0 ? Promise.resolve(adminRoles) : loadAdminRoles(),
      loadBusinessEmailDomain(),
    ]);
    setForm({
      ...EMPTY_FORM,
      admin_role_id: roles[0]?.id ?? '',
    });
    setFormError(null);
    setEmailUsernameError(null);
    setShowPassword(false);
    setModalOpen(true);
  };

  const openEditModal = async (user: AdminUser) => {
    const { countryIso2, localNumber } = parseStoredPhone(user.phone_number, countries);
    const domain = businessEmailDomain ?? (await loadBusinessEmailDomain());
    setEditingUser(user);
    setForm({
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      email_username: splitEmailUsername(user.email, domain),
      phone_country_iso2: countryIso2,
      phone_number: localNumber,
      password: '',
      admin_role_id: resolveAdminRoleId(user.admin_role_id, user.role, adminRoles),
    });
    setFormError(null);
    setEmailUsernameError(null);
    setShowPassword(false);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingUser(null);
    setForm({ ...EMPTY_FORM });
    setFormError(null);
    setEmailUsernameError(null);
    setShowPassword(false);
  };

  const handleEmailUsernameChange = (value: string) => {
    if (value.includes('@')) {
      setEmailUsernameError('Enter only the username — do not include @ or the domain.');
      setForm(prev => ({ ...prev, email_username: value.replace(/@/g, '') }));
      return;
    }

    setEmailUsernameError(null);
    setForm(prev => ({ ...prev, email_username: value }));
  };

  const validateForm = (): string | null => {
    const firstName = form.first_name.trim();
    const lastName = form.last_name.trim();
    const password = form.password.trim();

    if (!firstName) return 'First name is required.';
    if (!lastName) return 'Last name is required.';

    const usernameValidationError = validateEmailUsername(form.email_username, businessEmailDomain);
    if (usernameValidationError) {
      return usernameValidationError;
    }

    const fullEmail = buildBusinessEmail(form.email_username, businessEmailDomain as string);
    if (isDuplicateEmail(fullEmail, users, editingUser?.id)) {
      return 'An admin user with this email already exists.';
    }

    if (form.admin_role_id === '') return 'Admin role is required.';

    const phoneError = validatePhoneWithCountry(
      form.phone_country_iso2,
      form.phone_number,
      countries
    );
    if (phoneError) return phoneError;

    if (editingUser) {
      if (password) {
        return validatePassword(password);
      }
      return null;
    }

    if (!password) return 'Password is required.';
    return validatePassword(password);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFormError(null);

    const validationError = validateForm();
    if (validationError) {
      const emailError = validateEmailUsername(form.email_username, businessEmailDomain);
      if (emailError) {
        setEmailUsernameError(emailError);
        setFormError(null);
      } else {
        setEmailUsernameError(null);
        setFormError(validationError);
      }
      setSaving(false);
      return;
    }

    setEmailUsernameError(null);

    try {
      const fullPhone = formatFullPhone(form.phone_country_iso2, form.phone_number, countries);
      const fullEmail = buildBusinessEmail(form.email_username, businessEmailDomain as string);

      if (editingUser) {
        const payload: Record<string, string | number> = {
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          email: fullEmail,
          phone_number: fullPhone,
          admin_role_id: form.admin_role_id as number,
        };
        if (form.password.trim()) {
          payload.password = form.password;
        }

        await apiFetch(`users/${editingUser.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('users', {
          method: 'POST',
          body: JSON.stringify({
            first_name: form.first_name.trim(),
            last_name: form.last_name.trim(),
            email: fullEmail,
            phone_number: fullPhone,
            password: form.password,
            admin_role_id: form.admin_role_id,
            is_active: true,
          }),
        });
      }

      closeModal();
      await loadUsers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save admin user.';
      setFormError(message);
    } finally {
      setSaving(false);
    }
  };

  const openStatusChangeModal = (user: AdminUser, mode: 'activate' | 'deactivate') => {
    if (mode === 'deactivate' && !user.is_active) return;
    if (mode === 'activate' && user.is_active) return;
    setStatusChangeError(null);
    setStatusChangeMode(mode);
    setStatusChangeTarget(user);
  };

  const closeStatusChangeModal = () => {
    setStatusChangeTarget(null);
    setStatusChangeError(null);
  };

  const handleStatusChange = async (statusChangeReasonId: number) => {
    if (!statusChangeTarget) return;

    const endpoint =
      statusChangeMode === 'deactivate'
        ? `users/${statusChangeTarget.id}/deactivate`
        : `users/${statusChangeTarget.id}/activate`;

    try {
      setStatusChanging(true);
      setStatusChangeError(null);
      setError(null);
      await apiFetch(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({ status_change_reason_id: statusChangeReasonId }),
      });
      closeStatusChangeModal();
      await loadUsers();
    } catch (err: unknown) {
      setStatusChangeError(
        err instanceof Error ? err.message : `Failed to ${statusChangeMode} admin user.`
      );
    } finally {
      setStatusChanging(false);
    }
  };

  const handleDeleteUser = async (user: AdminUser) => {
    if (!viewerIsSuperAdmin) return;
    if (currentUser?.id === user.id) {
      setError('You cannot delete your own account.');
      return;
    }

    const confirmed = await openConfirm({
      title: 'Permanently delete admin?',
      message: `Delete ${formatAdminName(user)} permanently?\n\nThis removes their admin account from the system. This action cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      setDeletingUserId(user.id);
      setError(null);
      await apiFetch(`users/${user.id}`, { method: 'DELETE' });
      await loadUsers();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete admin user.');
    } finally {
      setDeletingUserId(null);
    }
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-none space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck size={18} className="text-accent" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-text-muted">
              Administration
            </span>
          </div>
          <h2 className="text-2xl font-extrabold text-text-main tracking-tight">Users Module</h2>
          <p className="text-text-muted text-sm">
            Add, edit, and deactivate Nexus admin accounts.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
              className="rounded border-border-subtle"
            />
            Show Inactive
          </label>
          <button
            type="button"
            onClick={loadUsers}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            type="button"
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 transition-all"
          >
            <Plus size={16} />
            Add Admin User
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
          {error}
        </div>
      )}

      <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30">
          <h3 className="text-sm font-bold text-text-main">Admin Users</h3>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 px-6 py-12 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading admin users...
          </div>
        ) : users.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-text-muted">
            No admin users found. Create the first admin account to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-[10px] font-black text-text-muted uppercase tracking-widest border-b border-border-subtle">
                  <th className="px-6 py-4">First Name</th>
                  <th className="px-6 py-4">Last Name</th>
                  <th className="px-6 py-4">Email</th>
                  <th className="px-6 py-4">Role</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/50">
                {users.map(user => (
                  <tr
                    key={user.id}
                    className={`transition-colors ${user.is_active ? 'hover:bg-surface-bg/30' : 'opacity-60'}`}
                  >
                    <td className="px-6 py-4 text-sm font-bold text-text-main">
                      {user.first_name?.trim() || '—'}
                    </td>
                    <td className="px-6 py-4 text-sm font-bold text-text-main">
                      {user.last_name?.trim() || '—'}
                    </td>
                    <td className="px-6 py-4 text-sm text-text-muted">{user.email}</td>
                    <td className="px-6 py-4">
                      <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-accent/10 text-accent">
                        {user.admin_role?.name || user.role || '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <UserStatusPill
                        isActive={user.is_active}
                        statusReason={getInactiveReasonLabel(user)}
                      />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => openEditModal(user)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-subtle text-xs font-semibold text-text-main hover:bg-surface-bg transition-colors"
                        >
                          <Pencil size={14} />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => openStatusChangeModal(user, 'deactivate')}
                          disabled={!user.is_active}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-alert/20 text-xs font-semibold text-alert hover:bg-alert/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <UserX size={14} />
                          Deactivate
                        </button>
                        <button
                          type="button"
                          onClick={() => openStatusChangeModal(user, 'activate')}
                          disabled={user.is_active}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-accent/20 text-xs font-semibold text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <UserCheck size={14} />
                          Activate
                        </button>
                        {viewerIsSuperAdmin && currentUser?.id !== user.id && (
                          <button
                            type="button"
                            onClick={() => handleDeleteUser(user)}
                            disabled={deletingUserId === user.id}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-alert/30 text-xs font-semibold text-alert hover:bg-alert/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            {deletingUserId === user.id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Trash2 size={14} />
                            )}
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md bg-card border border-border-subtle rounded-2xl shadow-xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
              <h3 className="text-sm font-bold text-text-main">
                {editingUser ? 'Edit Admin User' : 'Add Admin User'}
              </h3>
              <button
                type="button"
                onClick={closeModal}
                className="p-1 rounded-md text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <form
              key={editingUser ? `edit-${editingUser.id}` : 'create'}
              autoComplete="off"
              noValidate
              onSubmit={handleSubmit}
              className="px-6 py-5 space-y-4"
            >
              {formError && (
                <div className="p-3 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
                  {formError}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-text-muted mb-1.5">
                    First Name <span className="text-alert">*</span>
                  </label>
                  <input
                    type="text"
                    name="admin-first-name"
                    autoComplete="off"
                    required
                    value={form.first_name}
                    onChange={e => setForm(prev => ({ ...prev, first_name: e.target.value }))}
                    className="w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    placeholder=""
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-text-muted mb-1.5">
                    Last Name <span className="text-alert">*</span>
                  </label>
                  <input
                    type="text"
                    name="admin-last-name"
                    autoComplete="off"
                    required
                    value={form.last_name}
                    onChange={e => setForm(prev => ({ ...prev, last_name: e.target.value }))}
                    className="w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    placeholder=""
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">
                  Email <span className="text-alert">*</span>
                </label>
                <BusinessDomainEmailField
                  username={form.email_username}
                  businessEmailDomain={businessEmailDomain}
                  loading={loadingBusinessDomain}
                  error={emailUsernameError}
                  onUsernameChange={handleEmailUsernameChange}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">
                  Mobile Number <span className="text-alert">*</span>
                </label>
                <div className="flex gap-2">
                  <select
                    required
                    value={form.phone_country_iso2}
                    onChange={e =>
                      setForm(prev => ({
                        ...prev,
                        phone_country_iso2: e.target.value,
                      }))
                    }
                    className="w-[11.5rem] shrink-0 px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                  >
                    <option value="">Country code</option>
                    {countries.map(country => (
                      <option key={country.iso2} value={country.iso2}>
                        {formatPhoneCountryLabel(country)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="tel"
                    name="admin-phone-number"
                    autoComplete="off"
                    required
                    inputMode="text"
                    autoCapitalize="characters"
                    spellCheck={false}
                    maxLength={PHONE_LOCAL_DRAFT_MAX_LENGTH}
                    value={form.phone_number}
                    onChange={e =>
                      setForm(prev => ({
                        ...prev,
                        phone_number: sanitizePhoneLocalDraft(e.target.value),
                      }))
                    }
                    className="min-w-0 flex-1 px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    placeholder={PHONE_LOCAL_PLACEHOLDER}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-text-muted">{PHONE_LOCAL_REQUIREMENTS}</p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">
                  Admin Role <span className="text-alert">*</span>
                </label>
                <select
                  required
                  value={form.admin_role_id === '' ? '' : String(form.admin_role_id)}
                  disabled={loadingRoles || adminRoles.length === 0}
                  onChange={e =>
                    setForm(prev => ({
                      ...prev,
                      admin_role_id: e.target.value ? Number(e.target.value) : '',
                    }))
                  }
                  className="w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10 disabled:opacity-50"
                >
                  {loadingRoles ? (
                    <option value="">Loading roles...</option>
                  ) : adminRoles.length === 0 ? (
                    <option value="">No roles configured</option>
                  ) : (
                    adminRoles.map(role => (
                      <option key={role.id} value={role.id}>
                        {role.description ? `${role.name} - ${role.description}` : role.name}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted mb-1.5">
                  Password {!editingUser && <span className="text-alert">*</span>}
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="admin-new-password"
                    autoComplete="new-password"
                    required={!editingUser}
                    value={form.password}
                    onChange={e => setForm(prev => ({ ...prev, password: e.target.value }))}
                    className="w-full px-3 py-2 pr-10 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    placeholder=""
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(prev => !prev)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {editingUser ? (
                  <p className="mt-1.5 text-[11px] text-text-muted">
                    Leave it blank if you want to keep the old password.
                  </p>
                ) : (
                  <p className="mt-1.5 text-[11px] text-text-muted">{PASSWORD_REQUIREMENTS}</p>
                )}
                {editingUser && form.password.trim() !== '' && (
                  <p className="mt-1 text-[11px] text-text-muted">{PASSWORD_REQUIREMENTS}</p>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 rounded-xl border border-border-subtle text-sm font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  {saving && <Loader2 size={14} className="animate-spin" />}
                  {editingUser ? 'Save Changes' : 'Create Admin User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <StatusChangeModal
        open={Boolean(statusChangeTarget)}
        mode={statusChangeMode}
        userName={statusChangeTarget ? formatAdminName(statusChangeTarget) : ''}
        saving={statusChanging}
        error={statusChangeError}
        onClose={closeStatusChangeModal}
        onConfirm={handleStatusChange}
      />
    </div>
  );
};

export default UsersView;
