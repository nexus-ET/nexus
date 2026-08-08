import React, { useCallback, useEffect, useState } from 'react';
import { Eye, EyeOff, Loader2, Shield, UserCircle } from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';

interface StatusChangeReason {
  reason: string;
  description?: string;
}

interface ProfileUser {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  phone_number?: string | null;
  is_active?: boolean;
  is_superuser?: boolean;
  role?: string | null;
  admin_role?: { name?: string | null } | null;
  creation_date?: string | null;
  activation_date?: string | null;
  deactivation_date?: string | null;
  creation_reason_detail?: StatusChangeReason | null;
  activation_reason_detail?: StatusChangeReason | null;
  deactivation_reason_detail?: StatusChangeReason | null;
}

const formatDateTime = (value?: string | null): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const ReadOnlyField: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-xl border border-border-subtle bg-surface-bg/60 px-4 py-3">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{label}</p>
    <p className="text-sm font-medium text-text-main mt-1 break-words">{value || '—'}</p>
  </div>
);

const MyProfile: React.FC = () => {
  const [profile, setProfile] = useState<ProfileUser | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingPassword, setSavingPassword] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    if (!hasValidSession()) return;
    try {
      setLoading(true);
      setError(null);
      const data = (await apiFetch('users/me')) as ProfileUser;
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleChangePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.');
      return;
    }

    try {
      setSavingPassword(true);
      setError(null);
      setSuccess(null);
      await apiFetch('users/me/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setSuccess('Password updated successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password.');
    } finally {
      setSavingPassword(false);
    }
  };

  const roleLabel = profile?.admin_role?.name || profile?.role || '—';

  return (
    <div className="relative z-10 mx-auto w-full max-w-none space-y-6">
      <div>
        <h2 className="text-2xl font-extrabold text-text-main tracking-tight flex items-center gap-2">
          <UserCircle size={24} />
          My Profile
        </h2>
        <p className="text-sm text-text-muted mt-1">Manage your account details and password.</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-text-muted">
          <Loader2 size={24} className="animate-spin mr-2" />
          Loading profile...
        </div>
      ) : profile ? (
        <>
          <section className="rounded-2xl border border-border-subtle bg-card p-5 space-y-4">
            <h3 className="text-base font-semibold text-text-main">Account Information</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <ReadOnlyField label="First Name" value={profile.first_name || '—'} />
              <ReadOnlyField label="Last Name" value={profile.last_name || '—'} />
              <ReadOnlyField label="Email" value={profile.email} />
              <ReadOnlyField label="Mobile Number" value={profile.phone_number || '—'} />
              <ReadOnlyField label="Role" value={roleLabel} />
              <ReadOnlyField label="Account Status" value={profile.is_active ? 'Active' : 'Inactive'} />
              <ReadOnlyField label="Super Admin" value={profile.is_superuser ? 'Yes' : 'No'} />
              <ReadOnlyField label="Created On" value={formatDateTime(profile.creation_date)} />
              <ReadOnlyField label="Activated On" value={formatDateTime(profile.activation_date)} />
              <ReadOnlyField
                label="Deactivated On"
                value={
                  profile.is_active
                    ? 'Not applicable (account is active)'
                    : formatDateTime(profile.deactivation_date)
                }
              />
              <ReadOnlyField
                label="Creation Reason"
                value={profile.creation_reason_detail?.reason || '—'}
              />
              <ReadOnlyField
                label="Activation Reason"
                value={profile.activation_reason_detail?.reason || '—'}
              />
              <ReadOnlyField
                label="Deactivation Reason"
                value={
                  profile.is_active
                    ? 'Not applicable (account is active)'
                    : profile.deactivation_reason_detail?.reason || '—'
                }
              />
            </div>
          </section>

          <section className="rounded-2xl border border-border-subtle bg-card p-5">
            <h3 className="text-base font-semibold text-text-main mb-1 flex items-center gap-2">
              <Shield size={18} />
              Change Password
            </h3>
            <p className="text-xs text-text-muted mb-4">
              Use at least 8 characters with uppercase, lowercase, numbers, and special characters.
            </p>
            <form onSubmit={handleChangePassword} className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-text-muted mb-1.5">
                  Current Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={event => setCurrentPassword(event.target.value)}
                    className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 pr-10 text-sm text-text-main"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(prev => !prev)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-main hover:bg-card transition-colors"
                    aria-label={showPassword ? 'Hide passwords' : 'Show passwords'}
                    title={showPassword ? 'Hide passwords' : 'Show passwords'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-text-muted mb-1.5">
                  New Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={event => setNewPassword(event.target.value)}
                    className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 pr-10 text-sm text-text-main"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(prev => !prev)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-main hover:bg-card transition-colors"
                    aria-label={showPassword ? 'Hide passwords' : 'Show passwords'}
                    title={showPassword ? 'Hide passwords' : 'Show passwords'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-text-muted mb-1.5">
                  Confirm New Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={event => setConfirmPassword(event.target.value)}
                    className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 pr-10 text-sm text-text-main"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(prev => !prev)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-main hover:bg-card transition-colors"
                    aria-label={showPassword ? 'Hide passwords' : 'Show passwords'}
                    title={showPassword ? 'Hide passwords' : 'Show passwords'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div className="md:col-span-3">
                <button
                  type="submit"
                  disabled={savingPassword}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-border-subtle bg-card px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60"
                >
                  {savingPassword ? 'Updating...' : 'Update Password'}
                </button>
              </div>
            </form>
          </section>
        </>
      ) : null}
    </div>
  );
};

export default MyProfile;
