import React from 'react';

interface BusinessDomainEmailFieldProps {
  id?: string;
  name?: string;
  username: string;
  businessEmailDomain: string | null;
  loading?: boolean;
  error?: string | null;
  onUsernameChange: (value: string) => void;
}

const BusinessDomainEmailField: React.FC<BusinessDomainEmailFieldProps> = ({
  id = 'admin-email-username',
  name = 'admin-email-username',
  username,
  businessEmailDomain,
  loading = false,
  error,
  onUsernameChange,
}) => {
  const domainSuffix = businessEmailDomain ? `@${businessEmailDomain}` : '@company.com';

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = event.target.value;
    if (rawValue.includes('@')) {
      onUsernameChange(rawValue.replace(/@/g, ''));
      return;
    }
    onUsernameChange(rawValue);
  };

  return (
    <div>
      <div
        className={`flex items-stretch w-full rounded-xl border bg-surface-bg overflow-hidden focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10 ${
          error ? 'border-alert/40' : 'border-border-subtle'
        }`}
      >
        <input
          id={id}
          name={name}
          type="text"
          autoComplete="off"
          required
          inputMode="email"
          value={username}
          disabled={loading || !businessEmailDomain}
          onChange={handleChange}
          className="min-w-0 flex-1 px-3 py-2 bg-transparent border-0 text-sm text-text-main focus:outline-none disabled:opacity-60"
          placeholder={businessEmailDomain ? 'username' : 'Configure domain in Settings'}
          aria-describedby={`${id}-suffix`}
        />
        <span
          id={`${id}-suffix`}
          className="inline-flex items-center px-3 border-l border-border-subtle bg-card text-sm font-medium text-text-muted whitespace-nowrap"
        >
          {loading ? 'Loading…' : domainSuffix}
        </span>
      </div>
      {!businessEmailDomain && !loading && (
        <p className="mt-1.5 text-[11px] text-amber-700">
          Set the business email domain in Application Settings before creating admin users.
        </p>
      )}
      {error && <p className="mt-1.5 text-[11px] text-alert font-medium">{error}</p>}
    </div>
  );
};

export default BusinessDomainEmailField;
