import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Building2, CheckCircle2, Image as ImageIcon, Loader2, RefreshCw, Save, Settings, Upload } from 'lucide-react';
import PublicHolidayCalendar from '../components/PublicHolidayCalendar';
import { apiFetch, apiUpload, getStoredToken, resolveBaseUrl } from '../utils/api';
import { clearBusinessTimezoneCache } from '../utils/timezone';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';
import { useCountries } from '../hooks/useCountries';

type SettingValueType = 'text' | 'number' | 'boolean' | 'time' | 'working_days' | 'timezone' | 'select';

interface SettingOption {
  value: string;
  label: string;
}

interface DynamicSetting {
  key: string;
  value: string;
  updated_at?: string | null;
  updated_by_first_name?: string | null;
  updated_by_last_name?: string | null;
  label: string;
  value_type: SettingValueType | string;
  description: string;
  options?: SettingOption[] | null;
}

interface SettingsResponse {
  settings: DynamicSetting[];
}

const MONITORING_SETTING_ORDER = [
  'MONITORING_STATUS',
  'UPTIME_TARGET_URL',
  'ALERT_EMAIL',
] as const;

interface BusinessProfile {
  business_id: number;
  business_name: string;
  business_domain: string | null;
  address_line1: string | null;
  address_line2: string | null;
  address_line3: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  zip_code: string | null;
  office_phone_number: string | null;
  office_mobile_number: string | null;
  web_url: string | null;
  email_domain: string | null;
  has_logo?: boolean;
  logo_url?: string | null;
  updated_at?: string | null;
}

type BusinessProfileDraft = {
  business_name: string;
  business_domain: string;
  address_line1: string;
  address_line2: string;
  address_line3: string;
  city: string;
  state: string;
  country: string;
  zip_code: string;
  office_phone_number: string;
  office_mobile_number: string;
  web_url: string;
  email_domain: string;
};

type BusinessProfileFieldErrors = Partial<Record<keyof BusinessProfileDraft, string>>;

const EMPTY_BUSINESS_PROFILE_DRAFT: BusinessProfileDraft = {
  business_name: '',
  business_domain: '',
  address_line1: '',
  address_line2: '',
  address_line3: '',
  city: '',
  state: '',
  country: '',
  zip_code: '',
  office_phone_number: '',
  office_mobile_number: '',
  web_url: '',
  email_domain: '',
};

const DOMAIN_PATTERN = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i;
const OFFICE_PHONE_PATTERN = /^\+?[0-9a-zA-Z()\-\s.]{7,50}$/;

const isValidWebUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && Boolean(parsed.hostname);
  } catch {
    return false;
  }
};

const validateBusinessProfileDraft = (draft: BusinessProfileDraft): BusinessProfileFieldErrors => {
  const errors: BusinessProfileFieldErrors = {};
  const name = draft.business_name.trim();

  if (!name) {
    errors.business_name = 'Business name is required.';
  }

  const domain = draft.business_domain.trim();
  if (domain && !DOMAIN_PATTERN.test(domain)) {
    errors.business_domain = 'Enter a valid domain (e.g. company.com).';
  }

  const webUrl = draft.web_url.trim();
  if (webUrl && !isValidWebUrl(webUrl)) {
    errors.web_url = 'Enter a valid http or https URL.';
  }

  const emailDomain = draft.email_domain.trim();
  if (emailDomain && !DOMAIN_PATTERN.test(emailDomain)) {
    errors.email_domain = 'Enter a valid email domain (e.g. company.com).';
  }

  const officePhone = draft.office_phone_number.trim();
  if (officePhone && !OFFICE_PHONE_PATTERN.test(officePhone)) {
    errors.office_phone_number = 'Enter a valid office phone number.';
  }

  const officeMobile = draft.office_mobile_number.trim();
  if (officeMobile && !OFFICE_PHONE_PATTERN.test(officeMobile)) {
    errors.office_mobile_number = 'Enter a valid office mobile number.';
  }

  return errors;
};

const businessProfileToDraft = (profile: BusinessProfile | null): BusinessProfileDraft => ({
  business_name: profile?.business_name ?? '',
  business_domain: profile?.business_domain ?? '',
  address_line1: profile?.address_line1 ?? '',
  address_line2: profile?.address_line2 ?? '',
  address_line3: profile?.address_line3 ?? '',
  city: profile?.city ?? '',
  state: profile?.state ?? '',
  country: profile?.country ?? '',
  zip_code: profile?.zip_code ?? '',
  office_phone_number: profile?.office_phone_number ?? '',
  office_mobile_number: profile?.office_mobile_number ?? '',
  web_url: profile?.web_url ?? '',
  email_domain: profile?.email_domain ?? '',
});

const draftsMatch = (left: BusinessProfileDraft, right: BusinessProfileDraft): boolean =>
  (Object.keys(left) as Array<keyof BusinessProfileDraft>).every(key => left[key] === right[key]);

const WORKING_DAY_OPTIONS = [
  { code: 'mon', label: 'Mon', fullLabel: 'Monday' },
  { code: 'tue', label: 'Tue', fullLabel: 'Tuesday' },
  { code: 'wed', label: 'Wed', fullLabel: 'Wednesday' },
  { code: 'thu', label: 'Thu', fullLabel: 'Thursday' },
  { code: 'fri', label: 'Fri', fullLabel: 'Friday' },
  { code: 'sat', label: 'Sat', fullLabel: 'Saturday' },
  { code: 'sun', label: 'Sun', fullLabel: 'Sunday' },
] as const;

const parseWorkingDayCodes = (value: string): Set<string> => {
  const allowed = new Set(WORKING_DAY_OPTIONS.map(day => day.code));
  return new Set(
    value
      .split(',')
      .map(token => token.trim().toLowerCase())
      .filter(token => allowed.has(token as (typeof WORKING_DAY_OPTIONS)[number]['code']))
  );
};

const serializeWorkingDayCodes = (selected: Set<string>): string =>
  WORKING_DAY_OPTIONS.map(day => day.code)
    .filter(code => selected.has(code))
    .join(',');

const formatModifiedBy = (setting: DynamicSetting): string => {
  const first = setting.updated_by_first_name?.trim() ?? '';
  const last = setting.updated_by_last_name?.trim() ?? '';
  const fullName = [first, last].filter(Boolean).join(' ');
  return fullName || '—';
};

const AppSettings: React.FC = () => {
  const { formatDateTime, refreshTimezone } = useBusinessTimezone();
  const { countries } = useCountries();
  const [settings, setSettings] = useState<DynamicSetting[]>([]);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [businessProfileDraft, setBusinessProfileDraft] = useState<BusinessProfileDraft>(
    EMPTY_BUSINESS_PROFILE_DRAFT
  );
  const [businessProfileErrors, setBusinessProfileErrors] = useState<BusinessProfileFieldErrors>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);
  const [logoViewOpen, setLogoViewOpen] = useState(false);
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | null>(null);
  const [logoPreviewLoading, setLogoPreviewLoading] = useState(false);
  const [logoPreviewError, setLogoPreviewError] = useState<string | null>(null);
  const logoFileInputRef = useRef<HTMLInputElement>(null);

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setAccessDenied(false);
      setBusinessProfileErrors({});

      const [settingsData, profileData] = await Promise.all([
        apiFetch('settings') as Promise<SettingsResponse>,
        apiFetch('settings/business-profile') as Promise<BusinessProfile>,
      ]);

      const items = Array.isArray(settingsData.settings) ? settingsData.settings : [];
      setSettings(items);
      setDraftValues(Object.fromEntries(items.map(item => [item.key, item.value])));

      setBusinessProfile(profileData);
      setBusinessProfileDraft(businessProfileToDraft(profileData));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load settings.';
      if (message.toLowerCase().includes('super admin')) {
        setAccessDenied(true);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    return () => {
      if (logoPreviewUrl) URL.revokeObjectURL(logoPreviewUrl);
    };
  }, [logoPreviewUrl]);

  const dirtyKeys = useMemo(
    () =>
      settings
        .filter(item => (draftValues[item.key] ?? '') !== item.value)
        .map(item => item.key),
    [draftValues, settings]
  );

  const { generalSettings, monitoringPanelSettings } = useMemo(() => {
    const monitoringKeys = new Set<string>(MONITORING_SETTING_ORDER);
    const byKey = new Map(settings.map(item => [item.key, item]));
    return {
      generalSettings: settings.filter(item => !monitoringKeys.has(item.key)),
      monitoringPanelSettings: MONITORING_SETTING_ORDER.map(key => byKey.get(key)).filter(
        (item): item is DynamicSetting => Boolean(item)
      ),
    };
  }, [settings]);

  const savedBusinessProfileDraft = useMemo(
    () => businessProfileToDraft(businessProfile),
    [businessProfile]
  );

  const isBusinessProfileDirty = useMemo(
    () => !draftsMatch(businessProfileDraft, savedBusinessProfileDraft),
    [businessProfileDraft, savedBusinessProfileDraft]
  );

  const hasUnsavedChanges = dirtyKeys.length > 0 || isBusinessProfileDirty;
  useUnsavedChanges(hasUnsavedChanges, 'app-settings');

  const handleDraftChange = (key: string, value: string) => {
    setDraftValues(prev => ({ ...prev, [key]: value }));
    setSuccessMessage(null);
  };

  const handleBusinessProfileChange = (field: keyof BusinessProfileDraft, value: string) => {
    setBusinessProfileDraft(prev => ({ ...prev, [field]: value }));
    setBusinessProfileErrors(prev => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
    setSuccessMessage(null);
  };

  const closeLogoView = useCallback(() => {
    setLogoViewOpen(false);
    setLogoPreviewError(null);
    setLogoPreviewLoading(false);
    setLogoPreviewUrl(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  const fetchLogoPreview = useCallback(async () => {
    setLogoPreviewLoading(true);
    setLogoPreviewError(null);
    setLogoPreviewUrl(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });

    const token = getStoredToken();
    if (!token) {
      setLogoPreviewLoading(false);
      setLogoPreviewError('Session expired. Please log in again.');
      return;
    }

    try {
      const base = resolveBaseUrl().replace(/\/$/, '');
      const response = await fetch(`${base}/settings/business-profile/logo`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'ngrok-skip-browser-warning': 'true',
        },
      });
      if (!response.ok) {
        throw new Error(
          response.status === 404 ? 'Company logo not found.' : 'Failed to load company logo.'
        );
      }
      const blob = await response.blob();
      setLogoPreviewUrl(URL.createObjectURL(blob));
    } catch (err: unknown) {
      setLogoPreviewError(err instanceof Error ? err.message : 'Failed to load company logo.');
    } finally {
      setLogoPreviewLoading(false);
    }
  }, []);

  const openLogoView = useCallback(async () => {
    if (!businessProfile?.has_logo) return;
    setLogoViewOpen(true);
    await fetchLogoPreview();
  }, [businessProfile?.has_logo, fetchLogoPreview]);

  const handleLogoFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setLogoUploading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const updated = (await apiUpload(
        'settings/business-profile/logo',
        formData
      )) as BusinessProfile;
      setBusinessProfile(updated);
      setSuccessMessage('Company logo uploaded.');
      if (logoViewOpen) {
        await fetchLogoPreview();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to upload company logo.');
    } finally {
      setLogoUploading(false);
    }
  };

  const handleSave = async () => {
    if (!hasUnsavedChanges) return;

    const validationErrors = isBusinessProfileDirty
      ? validateBusinessProfileDraft(businessProfileDraft)
      : {};
    if (Object.keys(validationErrors).length > 0) {
      setBusinessProfileErrors(validationErrors);
      setError('Fix the Business Profile errors before saving.');
      return;
    }

    const previousSettings = settings;
    const previousBusinessProfile = businessProfile;
    const previousBusinessProfileDraft = businessProfileDraft;
    const optimisticSettings = settings.map(item =>
      dirtyKeys.includes(item.key) ? { ...item, value: draftValues[item.key] ?? item.value } : item
    );

    setSettings(optimisticSettings);
    setSaving(true);
    setError(null);
    setSuccessMessage(null);
    setBusinessProfileErrors({});

    try {
      const saveTasks: Promise<unknown>[] = [];

      if (dirtyKeys.length > 0) {
        saveTasks.push(
          Promise.all(
            dirtyKeys.map(key =>
              apiFetch('settings/update', {
                method: 'POST',
                body: JSON.stringify({
                  key,
                  value: draftValues[key],
                }),
              }) as Promise<DynamicSetting>
            )
          )
        );
      }

      if (isBusinessProfileDirty) {
        saveTasks.push(
          apiFetch('settings/business-profile', {
            method: 'PUT',
            body: JSON.stringify({
              business_name: businessProfileDraft.business_name.trim(),
              business_domain: businessProfileDraft.business_domain.trim() || null,
              address_line1: businessProfileDraft.address_line1.trim() || null,
              address_line2: businessProfileDraft.address_line2.trim() || null,
              address_line3: businessProfileDraft.address_line3.trim() || null,
              city: businessProfileDraft.city.trim() || null,
              state: businessProfileDraft.state.trim() || null,
              country: businessProfileDraft.country.trim() || null,
              zip_code: businessProfileDraft.zip_code.trim() || null,
              office_phone_number: businessProfileDraft.office_phone_number.trim() || null,
              office_mobile_number: businessProfileDraft.office_mobile_number.trim() || null,
              web_url: businessProfileDraft.web_url.trim() || null,
              email_domain: businessProfileDraft.email_domain.trim() || null,
            }),
          }) as Promise<BusinessProfile>
        );
      }

      const results = await Promise.all(saveTasks);
      let nextSettings = settings;
      let nextBusinessProfile = businessProfile;
      let nextDraftValues = draftValues;

      for (const result of results) {
        if (Array.isArray(result)) {
          const updatedItems = result as DynamicSetting[];
          const updatedMap = Object.fromEntries(updatedItems.map(item => [item.key, item]));
          nextSettings = nextSettings.map(item =>
            updatedMap[item.key] ? { ...item, ...updatedMap[item.key] } : item
          );
          nextDraftValues = { ...nextDraftValues };
          updatedItems.forEach(item => {
            nextDraftValues[item.key] = item.value;
          });
        } else {
          nextBusinessProfile = result as BusinessProfile;
        }
      }

      setSettings(nextSettings);
      setDraftValues(nextDraftValues);
      setBusinessProfile(nextBusinessProfile);
      setBusinessProfileDraft(businessProfileToDraft(nextBusinessProfile));
      setSuccessMessage('Settings saved successfully.');
      if (dirtyKeys.includes('BUSINESS_TIMEZONE')) {
        clearBusinessTimezoneCache();
        void refreshTimezone();
      }
    } catch (err: unknown) {
      setSettings(previousSettings);
      setDraftValues(Object.fromEntries(previousSettings.map(item => [item.key, item.value])));
      setBusinessProfile(previousBusinessProfile);
      setBusinessProfileDraft(previousBusinessProfileDraft);
      setError(err instanceof Error ? err.message : 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const renderBusinessProfileSection = (title: string, description: string, withDivider = false) => (
    <div
      className={`col-span-1 md:col-span-2 xl:col-span-3 ${
        withDivider ? 'border-t border-border-subtle/70 pt-4 mt-1' : ''
      }`}
    >
      <h3 className="text-xs font-bold uppercase tracking-widest text-text-muted">{title}</h3>
      <p className="text-[11px] text-text-muted mt-0.5">{description}</p>
    </div>
  );

  const renderBusinessProfileField = (
    id: string,
    label: string,
    field: keyof BusinessProfileDraft,
    options?: {
      type?: string;
      placeholder?: string;
      required?: boolean;
      selectOptions?: Array<{ value: string; label: string }>;
    }
  ) => {
    const fieldError = businessProfileErrors[field];
    const controlClassName = `mt-1.5 w-full rounded-lg border bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10 ${
      fieldError ? 'border-red-300' : 'border-border-subtle'
    }`;

    return (
      <div key={id} className="min-w-0 flex flex-col">
        <label htmlFor={id} className="block text-sm font-medium text-text-main leading-tight">
          {label}
          {options?.required && <span className="text-alert"> *</span>}
        </label>
        {options?.selectOptions ? (
          <select
            id={id}
            required={options?.required}
            value={businessProfileDraft[field]}
            onChange={event => handleBusinessProfileChange(field, event.target.value)}
            className={controlClassName}
          >
            <option value="">Select country</option>
            {options.selectOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={options?.type ?? 'text'}
            required={options?.required}
            value={businessProfileDraft[field]}
            onChange={event => handleBusinessProfileChange(field, event.target.value)}
            placeholder={options?.placeholder}
            className={controlClassName}
          />
        )}
        {fieldError ? (
          <p className="mt-1 text-xs text-red-600">{fieldError}</p>
        ) : (
          <span className="mt-1 block min-h-[1rem]" aria-hidden="true" />
        )}
      </div>
    );
  };

  const countrySelectOptions = useMemo(() => {
    const options = countries.map(country => ({ value: country.name, label: country.name }));
    const savedCountry = businessProfileDraft.country.trim();
    if (
      savedCountry &&
      !options.some(option => option.value.toLowerCase() === savedCountry.toLowerCase())
    ) {
      options.push({ value: savedCountry, label: savedCountry });
    }
    return options;
  }, [countries, businessProfileDraft.country]);

  const renderValueInput = (setting: DynamicSetting) => {
    const value = draftValues[setting.key] ?? '';

    if (setting.value_type === 'working_days') {
      const selected = parseWorkingDayCodes(value);
      const toggleDay = (code: string) => {
        const next = new Set(selected);
        if (next.has(code)) {
          if (next.size === 1) return;
          next.delete(code);
        } else {
          next.add(code);
        }
        handleDraftChange(setting.key, serializeWorkingDayCodes(next));
      };

      return (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {WORKING_DAY_OPTIONS.map(day => {
              const active = selected.has(day.code);
              return (
                <button
                  key={day.code}
                  type="button"
                  title={day.fullLabel}
                  aria-pressed={active}
                  onClick={() => toggleDay(day.code)}
                  className={`min-w-[3.25rem] rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                    active
                      ? 'border-accent bg-accent/15 text-text-main'
                      : 'border-border-subtle bg-surface-bg text-text-muted hover:text-text-main hover:bg-card'
                  }`}
                >
                  {day.label}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-text-muted">
            Selected:{' '}
            {WORKING_DAY_OPTIONS.filter(day => selected.has(day.code))
              .map(day => day.fullLabel)
              .join(', ') || 'None'}
          </p>
        </div>
      );
    }

    if (setting.value_type === 'timezone') {
      const options = setting.options ?? [];
      const preview = (() => {
        try {
          return new Date().toLocaleString(undefined, {
            timeZone: value || 'UTC',
            weekday: 'short',
            day: 'numeric',
            month: 'short',
            hour: 'numeric',
            minute: '2-digit',
            timeZoneName: 'short',
          });
        } catch {
          return null;
        }
      })();

      return (
        <div className="space-y-2 max-w-md">
          <select
            value={value}
            onChange={event => handleDraftChange(setting.key, event.target.value)}
            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
          >
            {options.length === 0 ? (
              <option value={value}>{value || 'UTC'}</option>
            ) : (
              options.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))
            )}
          </select>
          {preview && (
            <p className="text-xs text-text-muted">
              Current office time: <span className="font-medium text-text-main">{preview}</span>
            </p>
          )}
        </div>
      );
    }

    if (setting.value_type === 'select') {
      const options = setting.options ?? [];
      return (
        <select
          value={value}
          onChange={event => handleDraftChange(setting.key, event.target.value)}
          className="w-full max-w-md rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
          aria-label={setting.label}
        >
          {options.length === 0 ? (
            <option value={value}>{value || '—'}</option>
          ) : (
            options.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))
          )}
        </select>
      );
    }

    if (setting.value_type === 'boolean') {
      const enabled = value.toLowerCase() === 'true';
      return (
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => handleDraftChange(setting.key, enabled ? 'false' : 'true')}
          className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors ${
            enabled ? 'bg-accent' : 'bg-border-subtle'
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
              enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      );
    }

    if (setting.key === 'COUNSELING_SESSION_PURPOSES') {
      return (
        <textarea
          value={value}
          onChange={event => handleDraftChange(setting.key, event.target.value)}
          rows={6}
          placeholder={
            'General Counselling | Initial guidance and pathway overview\nVisa Application Help | Visa forms and interview prep'
          }
          className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary"
        />
      );
    }

    const inputType =
      setting.key === 'ALERT_EMAIL'
        ? 'text'
        : setting.key === 'UPTIME_TARGET_URL'
          ? 'url'
          : setting.value_type === 'number'
            ? 'number'
            : setting.value_type === 'time'
              ? 'time'
              : 'text';

    return (
      <input
        type={inputType}
        min={setting.value_type === 'number' ? 1 : undefined}
        value={value}
        onChange={event => handleDraftChange(setting.key, event.target.value)}
        placeholder={
          setting.key === 'UPTIME_TARGET_URL'
            ? 'https://example.com/health'
            : setting.key === 'ALERT_EMAIL'
              ? 'admin@example.com, ops@example.com'
              : undefined
        }
        className={`w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10 ${
          setting.key === 'ALERT_EMAIL' ? 'max-w-2xl' : 'max-w-md'
        }`}
      />
    );
  };

  const renderSettingRow = (setting: DynamicSetting) => {
    const isDirty = dirtyKeys.includes(setting.key);
    return (
      <tr
        key={setting.key}
        className={`border-b border-border-subtle/70 ${isDirty ? 'bg-accent/5' : ''}`}
      >
        <td className="px-4 py-4 align-top">
          <div className="font-medium text-text-main">{setting.label}</div>
          <div className="text-xs text-text-muted mt-1">{setting.description}</div>
          <div className="text-[11px] text-text-muted mt-1 font-mono">{setting.key}</div>
        </td>
        <td className="px-4 py-4 align-top">{renderValueInput(setting)}</td>
        <td className="px-4 py-4 align-top text-xs text-text-muted hidden lg:table-cell">
          {setting.updated_at ? formatDateTime(setting.updated_at) : 'Not saved yet'}
        </td>
        <td className="px-4 py-4 align-top text-xs text-text-muted hidden lg:table-cell">
          {formatModifiedBy(setting)}
        </td>
      </tr>
    );
  };

  const renderActionButtons = (placement: 'top' | 'bottom') => (
    <div
      className={`flex items-center gap-2 ${
        placement === 'top' ? 'self-start' : 'justify-end pt-2'
      }`}
    >
      <button
        type="button"
        onClick={loadSettings}
        disabled={loading || saving}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm hover:bg-surface-bg disabled:opacity-60"
      >
        <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        Refresh
      </button>
      <button
        type="button"
        onClick={handleSave}
        disabled={saving || !hasUnsavedChanges}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
      >
        {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
        Save Settings
      </button>
    </div>
  );

  if (accessDenied) {
    return (
      <div className="p-6 md:p-8">
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-6 text-sm text-amber-900">
          Settings are restricted to Super Admin users.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2">
            <Settings size={24} />
            Application Settings
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Manage business profile, counselling, bookings, office hours, business timezone, working days, public holidays, and uptime monitoring.
          </p>
        </div>
        {renderActionButtons('top')}
      </div>

      {successMessage && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={16} />
          {successMessage}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
        <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-main flex items-center gap-2">
                <Building2 size={18} />
                Business Profile
              </h2>
              <p className="text-xs text-text-muted mt-1 max-w-2xl">
                Configure tenant-specific business details for this account. Email domain can later be used for
                automatic signup whitelisting.
              </p>
              {businessProfile?.business_id && (
                <p className="text-[11px] text-text-muted mt-1 font-mono">
                  Tenant ID: {businessProfile.business_id}
                </p>
              )}
            </div>
            <div className="text-[11px] text-text-muted space-y-0.5 md:text-right">
              <p>
                Last updated:{' '}
                {businessProfile?.updated_at
                  ? formatDateTime(businessProfile.updated_at)
                  : 'Not saved yet'}
              </p>
            </div>
          </div>
        </div>

        <div className="p-4 md:p-5">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-text-muted text-sm">
              <Loader2 size={18} className="animate-spin mr-2" />
              Loading business profile...
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-4 items-start">
              {renderBusinessProfileSection(
                'Business identity',
                'Core name and public-facing web presence for this tenant.'
              )}
              <div className="col-span-1 md:col-span-2 xl:col-span-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-x-6 gap-y-4 items-start">
                {renderBusinessProfileField('business-name', 'Business Name', 'business_name', {
                  required: true,
                })}
                {renderBusinessProfileField('business-domain', 'Business Domain', 'business_domain', {
                  placeholder: 'company.com',
                })}
                {renderBusinessProfileField('web-url', 'Web URL', 'web_url', {
                  type: 'url',
                  placeholder: 'https://www.company.com',
                })}
                <div className="min-w-0 flex flex-col">
                  <span className="block text-sm font-medium text-text-main leading-tight">
                    Company Logo
                  </span>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <input
                      ref={logoFileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.png,.jpg,.jpeg,.gif,.webp,.svg"
                      className="hidden"
                      onChange={handleLogoFileChange}
                    />
                    <button
                      type="button"
                      disabled={logoUploading || loading}
                      onClick={() => logoFileInputRef.current?.click()}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-medium text-text-main hover:bg-card disabled:opacity-50"
                    >
                      {logoUploading ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Upload size={14} />
                      )}
                      {businessProfile?.has_logo ? 'Replace logo' : 'Upload logo'}
                    </button>
                    {businessProfile?.has_logo && (
                      <button
                        type="button"
                        disabled={logoUploading || loading}
                        onClick={() => void openLogoView()}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-sm font-medium text-accent hover:bg-accent/10 disabled:opacity-50"
                      >
                        <ImageIcon size={14} />
                        View logo
                      </button>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-text-muted">
                    PNG, JPG, GIF, WebP, or SVG up to 5 MB. New uploads overwrite the existing logo.
                  </p>
                </div>
              </div>

              {renderBusinessProfileSection(
                'Contact & email',
                'Corporate email domain, office landline, and office mobile for this business.',
                true
              )}
              {renderBusinessProfileField('email-domain', 'Email Domain Name', 'email_domain', {
                placeholder: 'company.com',
              })}
              {renderBusinessProfileField('office-phone', 'Office Phone Number', 'office_phone_number', {
                type: 'tel',
                placeholder: '+1 (555) 123-4567',
              })}
              {renderBusinessProfileField('office-mobile', 'Office Mobile Number', 'office_mobile_number', {
                type: 'tel',
                placeholder: '+91 98765 43210',
              })}

              {renderBusinessProfileSection(
                'Physical address',
                'Street lines first, then city, state, country, and postal code on one row.',
                true
              )}
              {renderBusinessProfileField('address-line1', 'Address 1', 'address_line1', {
                placeholder: 'Street address, P.O. box',
              })}
              {renderBusinessProfileField('address-line2', 'Address 2', 'address_line2', {
                placeholder: 'Apartment, suite, unit',
              })}
              {renderBusinessProfileField('address-line3', 'Address 3', 'address_line3', {
                placeholder: 'Additional address line',
              })}

              <div className="col-span-1 md:col-span-2 xl:col-span-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-x-6 gap-y-4 items-start">
                {renderBusinessProfileField('city', 'City', 'city')}
                {renderBusinessProfileField('state', 'State / Province', 'state')}
                {renderBusinessProfileField('country', 'Country', 'country', {
                  selectOptions: countrySelectOptions,
                })}
                {renderBusinessProfileField('zip-code', 'Zip / Postal Code', 'zip_code')}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-text-muted">
            <Loader2 size={24} className="animate-spin mr-2" />
            Loading settings...
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-surface-bg border-b border-border-subtle">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold text-text-muted">Setting</th>
                  <th className="text-left px-4 py-3 font-semibold text-text-muted">Value</th>
                  <th className="text-left px-4 py-3 font-semibold text-text-muted hidden lg:table-cell">
                    Last updated
                  </th>
                  <th className="text-left px-4 py-3 font-semibold text-text-muted hidden lg:table-cell">
                    Modified by
                  </th>
                </tr>
              </thead>
              <tbody>
                {generalSettings.map(setting => renderSettingRow(setting))}
                {monitoringPanelSettings.length > 0 && (
                  <>
                    <tr className="border-b border-border-subtle/70 bg-surface-bg/80">
                      <td colSpan={4} className="px-4 pt-4 pb-2">
                        <div className="text-sm font-semibold text-text-main">Monitoring</div>
                        <p className="text-xs text-text-muted mt-0.5">
                          Alert emails receive Exception Report notifications and
                          auto-resolution confirmations immediately.
                          Uptime checks run only while Monitoring status is Active.
                        </p>
                      </td>
                    </tr>
                    {monitoringPanelSettings.map(setting => renderSettingRow(setting))}
                  </>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {hasUnsavedChanges && (
        <p className="text-xs text-text-muted">
          {(dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0))} unsaved change
          {dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0) === 1 ? '' : 's'}. Click Save Settings to apply.
        </p>
      )}

      <PublicHolidayCalendar />

      {renderActionButtons('bottom')}

      {logoViewOpen && (
        <div
          className="fixed inset-0 z-[400] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="company-logo-view-title"
          onClick={closeLogoView}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-border-subtle bg-card shadow-xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
              <h2 id="company-logo-view-title" className="text-base font-semibold text-text-main">
                View logo
              </h2>
              <button
                type="button"
                onClick={closeLogoView}
                className="rounded-lg px-2 py-1 text-sm text-text-muted hover:bg-surface-bg hover:text-text-main"
              >
                Close
              </button>
            </div>
            <div className="flex min-h-[220px] items-center justify-center p-6">
              {logoPreviewLoading && (
                <div className="flex items-center gap-2 text-sm text-text-muted">
                  <Loader2 size={18} className="animate-spin" />
                  Loading logo...
                </div>
              )}
              {!logoPreviewLoading && logoPreviewError && (
                <p className="text-sm text-red-600">{logoPreviewError}</p>
              )}
              {!logoPreviewLoading && !logoPreviewError && logoPreviewUrl && (
                <img
                  src={logoPreviewUrl}
                  alt="Company logo"
                  className="max-h-72 max-w-full object-contain"
                />
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-border-subtle px-4 py-3">
              <button
                type="button"
                disabled={logoUploading}
                onClick={() => logoFileInputRef.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm font-medium text-text-main hover:bg-card disabled:opacity-50"
              >
                {logoUploading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Upload size={14} />
                )}
                Replace logo
              </button>
              <button
                type="button"
                onClick={closeLogoView}
                className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AppSettings;
