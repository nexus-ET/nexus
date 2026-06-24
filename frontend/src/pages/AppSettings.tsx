import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, CheckCircle2, CloudDownload, Loader2, RefreshCw, Save, Settings } from 'lucide-react';
import PublicHolidayCalendar from '../components/PublicHolidayCalendar';
import { apiFetch, API_SYNC_TIMEOUT_MS } from '../utils/api';
import { clearBusinessTimezoneCache } from '../utils/timezone';

type SettingValueType = 'text' | 'number' | 'boolean' | 'time' | 'working_days' | 'timezone';

interface TimezoneOption {
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
  options?: TimezoneOption[] | null;
}

interface SettingsResponse {
  settings: DynamicSetting[];
}

type LeadSyncMode = 'automated' | 'manual';
type LeadSyncIntervalUnit = 'minutes' | 'hours' | 'days' | 'weeks';

interface LeadSyncLastRunSummary {
  forms_processed?: number;
  leads_seen?: number;
  leads_created?: number;
  leads_skipped?: number;
  errors?: string[];
}

interface LeadSyncConfig {
  mode: LeadSyncMode;
  interval_value: number;
  interval_unit: LeadSyncIntervalUnit;
  interval_unit_label: string;
  last_run_at: string | null;
  last_run_summary: LeadSyncLastRunSummary | null;
  scheduler_enabled?: boolean;
  scheduler_active?: boolean;
  scheduler_is_leader?: boolean;
  configured_interval?: string | null;
  configured_schedule?: string | null;
  active_job_interval?: string | null;
  next_scheduled_run_at?: string | null;
}

const LEAD_SYNC_INTERVAL_OPTIONS: Array<{ value: LeadSyncIntervalUnit; label: string }> = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
];

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
const OFFICE_PHONE_PATTERN = /^\+?[0-9()\-\s.]{7,50}$/;

const DEFAULT_COUNTRY_OPTIONS = [
  { value: 'India', label: 'India' },
  { value: 'United States', label: 'United States' },
  { value: 'United Kingdom', label: 'United Kingdom' },
  { value: 'Canada', label: 'Canada' },
  { value: 'Australia', label: 'Australia' },
  { value: 'United Arab Emirates', label: 'United Arab Emirates' },
  { value: 'Singapore', label: 'Singapore' },
  { value: 'Germany', label: 'Germany' },
  { value: 'France', label: 'France' },
] as const;

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
  const [leadSyncConfig, setLeadSyncConfig] = useState<LeadSyncConfig | null>(null);
  const [leadSyncDraft, setLeadSyncDraft] = useState<{
    mode: LeadSyncMode;
    interval_value: number;
    interval_unit: LeadSyncIntervalUnit;
  }>({ mode: 'automated', interval_value: 1, interval_unit: 'hours' });
  const [leadSyncLoading, setLeadSyncLoading] = useState(true);
  const [leadSyncSaving, setLeadSyncSaving] = useState(false);
  const [leadSyncRunning, setLeadSyncRunning] = useState(false);
  const [leadSyncMessage, setLeadSyncMessage] = useState<string | null>(null);
  const [leadSyncError, setLeadSyncError] = useState<string | null>(null);
  const [leadSyncUnavailable, setLeadSyncUnavailable] = useState<string | null>(null);

  const loadLeadSyncSettings = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLeadSyncLoading(true);
    }
    setLeadSyncUnavailable(null);

    try {
      const leadSyncData = (await apiFetch('settings/lead-sync')) as LeadSyncConfig;
      setLeadSyncConfig(leadSyncData);
      setLeadSyncDraft({
        mode: leadSyncData.mode,
        interval_value: leadSyncData.interval_value,
        interval_unit: leadSyncData.interval_unit,
      });
      setLeadSyncError(null);
    } catch (err: unknown) {
      setLeadSyncConfig(null);
      const message = err instanceof Error ? err.message : 'Failed to load lead sync settings.';
      if (/not found/i.test(message)) {
        setLeadSyncUnavailable(
          'Meta lead sync is not available on this server. Restart the NEXUS backend to load the latest routes.'
        );
      } else {
        setLeadSyncUnavailable(message);
      }
    } finally {
      if (!options?.silent) {
        setLeadSyncLoading(false);
      }
    }
  }, []);

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

    void loadLeadSyncSettings();
  }, [loadLeadSyncSettings]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (leadSyncDraft.mode !== 'automated' || leadSyncUnavailable) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadLeadSyncSettings({ silent: true });
    }, 30_000);

    return () => window.clearInterval(timer);
  }, [leadSyncDraft.mode, leadSyncUnavailable, loadLeadSyncSettings]);

  const leadSyncScheduleHint = useMemo(() => {
    if (leadSyncDraft.mode !== 'automated' || !leadSyncConfig) {
      return null;
    }

    if (leadSyncConfig.scheduler_enabled === false) {
      return 'Automatic scheduling is disabled on the server (META_LEAD_SYNC_ENABLED=false).';
    }

    if (leadSyncConfig.scheduler_is_leader === false) {
      return 'This backend is not the scheduler leader — another NEXUS process is running automated sync. Stop duplicate backends and keep only one server on port 8002.';
    }

    if (leadSyncConfig.scheduler_active === false) {
      return 'Scheduler is not running. Keep the NEXUS backend process running and save the schedule again.';
    }

    const intervalNote = leadSyncConfig.configured_interval
      ? ` Saved: every ${leadSyncConfig.configured_interval}.`
      : leadSyncConfig.active_job_interval
        ? ` Active job: every ${leadSyncConfig.active_job_interval}.`
        : '';

    if (leadSyncConfig.next_scheduled_run_at) {
      return `Next automatic sync: ${new Date(leadSyncConfig.next_scheduled_run_at).toLocaleString()}.${intervalNote} Activity appears in Reports.`;
    }

    return `Automatic sync is armed.${intervalNote} Keep one backend running — activity appears in Reports.`;
  }, [leadSyncConfig, leadSyncDraft.mode]);

  const dirtyKeys = useMemo(
    () =>
      settings
        .filter(item => (draftValues[item.key] ?? '') !== item.value)
        .map(item => item.key),
    [draftValues, settings]
  );

  const savedBusinessProfileDraft = useMemo(
    () => businessProfileToDraft(businessProfile),
    [businessProfile]
  );

  const isBusinessProfileDirty = useMemo(
    () => !draftsMatch(businessProfileDraft, savedBusinessProfileDraft),
    [businessProfileDraft, savedBusinessProfileDraft]
  );

  const hasUnsavedChanges = dirtyKeys.length > 0 || isBusinessProfileDirty;

  const isLeadSyncDirty = useMemo(() => {
    if (!leadSyncConfig) return false;
    return (
      leadSyncDraft.mode !== leadSyncConfig.mode ||
      leadSyncDraft.interval_value !== leadSyncConfig.interval_value ||
      leadSyncDraft.interval_unit !== leadSyncConfig.interval_unit
    );
  }, [leadSyncConfig, leadSyncDraft]);

  const handleSaveLeadSyncSettings = async () => {
    setLeadSyncSaving(true);
    setLeadSyncError(null);
    setLeadSyncMessage(null);
    try {
      const updated = (await apiFetch('settings/lead-sync', {
        method: 'PUT',
        body: JSON.stringify(leadSyncDraft),
      })) as LeadSyncConfig;
      setLeadSyncConfig(updated);
      setLeadSyncDraft({
        mode: updated.mode,
        interval_value: updated.interval_value,
        interval_unit: updated.interval_unit,
      });
      setLeadSyncMessage(
        updated.mode === 'automated'
          ? `Automated sync enabled every ${updated.interval_value} ${updated.interval_unit}.`
          : 'Manual sync mode enabled. Use Sync Now to fetch leads.'
      );
    } catch (err: unknown) {
      setLeadSyncError(err instanceof Error ? err.message : 'Failed to save lead sync settings.');
    } finally {
      setLeadSyncSaving(false);
    }
  };

  const handleRunLeadSync = async () => {
    setLeadSyncRunning(true);
    setLeadSyncError(null);
    setLeadSyncMessage(null);
    try {
      const result = (await apiFetch('settings/lead-sync/run', {
        method: 'POST',
        timeoutMs: API_SYNC_TIMEOUT_MS,
      })) as LeadSyncLastRunSummary & {
        run_at: string;
        delta_since_label?: string | null;
        delta_is_initial_backfill?: boolean;
      };
      setLeadSyncConfig(prev =>
        prev
          ? {
              ...prev,
              last_run_at: result.run_at,
              last_run_summary: {
                forms_processed: result.forms_processed,
                leads_seen: result.leads_seen,
                leads_created: result.leads_created,
                leads_skipped: result.leads_skipped,
                errors: result.errors,
              },
            }
          : prev
      );
      const deltaHint =
        result.delta_since_label && result.delta_is_initial_backfill
          ? ` (initial window from ${result.delta_since_label})`
          : result.delta_since_label
            ? ` (delta since ${result.delta_since_label})`
            : '';
      setLeadSyncMessage(
        `Sync complete${deltaHint}: ${result.leads_created ?? 0} new, ${result.leads_skipped ?? 0} already in Nexus.`
      );
    } catch (err: unknown) {
      setLeadSyncError(err instanceof Error ? err.message : 'Lead sync failed.');
    } finally {
      setLeadSyncRunning(false);
    }
  };

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
    const options = DEFAULT_COUNTRY_OPTIONS.map(option => ({ ...option }));
    const savedCountry = businessProfileDraft.country.trim();
    if (
      savedCountry &&
      !options.some(option => option.value.toLowerCase() === savedCountry.toLowerCase())
    ) {
      options.push({ value: savedCountry, label: savedCountry });
    }
    return options;
  }, [businessProfileDraft.country]);

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

    return (
      <input
        type={setting.value_type === 'number' ? 'number' : 'text'}
        min={setting.value_type === 'number' ? 1 : undefined}
        value={value}
        onChange={event => handleDraftChange(setting.key, event.target.value)}
        className="w-full max-w-md rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
      />
    );
  };

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
            Manage business profile, Meta lead synchronization, counselling, bookings, office hours, business timezone, working days, and public holidays.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
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
            Save Changes
          </button>
        </div>
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
                  ? new Date(businessProfile.updated_at).toLocaleString()
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
        <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-main flex items-center gap-2">
                <CloudDownload size={18} />
                Meta Lead Sync
              </h2>
              <p className="text-xs text-text-muted mt-1 max-w-2xl">
                Pull Facebook and Instagram Lead Ads into Nexus. Use automated scheduling or run a manual sync to
                fetch leads since the last download.
              </p>
            </div>
            {leadSyncConfig?.last_run_at ? (
              <p className="text-[11px] text-text-muted md:text-right">
                Last sync: {new Date(leadSyncConfig.last_run_at).toLocaleString()}
              </p>
            ) : null}
          </div>
          {leadSyncScheduleHint ? (
            <p className="mt-2 text-[11px] text-text-muted border-t border-border-subtle pt-2">
              {leadSyncScheduleHint}
            </p>
          ) : null}
        </div>

        <div className="p-4 md:p-5 space-y-5">
          {leadSyncLoading ? (
            <div className="flex items-center justify-center py-6 text-text-muted text-sm">
              <Loader2 size={18} className="animate-spin mr-2" />
              Loading lead sync settings...
            </div>
          ) : leadSyncUnavailable ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {leadSyncUnavailable}
            </div>
          ) : (
            <>
              <div>
                <p className="text-sm font-medium text-text-main mb-2">Sync mode</p>
                <div className="inline-flex rounded-lg border border-border-subtle bg-surface-bg p-1">
                  {(['automated', 'manual'] as LeadSyncMode[]).map(mode => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => {
                        setLeadSyncDraft(prev => ({ ...prev, mode }));
                        setLeadSyncMessage(null);
                      }}
                      className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
                        leadSyncDraft.mode === mode
                          ? 'bg-accent text-text-dark-bg shadow-sm'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      {mode === 'automated' ? 'Automated' : 'Manual'}
                    </button>
                  ))}
                </div>
              </div>

              {leadSyncDraft.mode === 'automated' ? (
                <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,140px)_minmax(0,180px)_auto] gap-3 items-end">
                  <div>
                    <label htmlFor="lead-sync-interval" className="block text-sm font-medium text-text-main">
                      Run every
                    </label>
                    <input
                      id="lead-sync-interval"
                      type="number"
                      min={1}
                      value={leadSyncDraft.interval_value}
                      onChange={event =>
                        setLeadSyncDraft(prev => ({
                          ...prev,
                          interval_value: Math.max(1, Number(event.target.value) || 1),
                        }))
                      }
                      className="mt-1.5 w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    />
                  </div>
                  <div>
                    <label htmlFor="lead-sync-unit" className="block text-sm font-medium text-text-main">
                      Interval
                    </label>
                    <select
                      id="lead-sync-unit"
                      value={leadSyncDraft.interval_unit}
                      onChange={event =>
                        setLeadSyncDraft(prev => ({
                          ...prev,
                          interval_unit: event.target.value as LeadSyncIntervalUnit,
                        }))
                      }
                      className="mt-1.5 w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    >
                      {LEAD_SYNC_INTERVAL_OPTIONS.map(option => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveLeadSyncSettings}
                    disabled={leadSyncSaving || !isLeadSyncDirty}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
                  >
                    {leadSyncSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    Save Sync Schedule
                  </button>
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                  <button
                    type="button"
                    onClick={handleRunLeadSync}
                    disabled={leadSyncRunning}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
                  >
                    {leadSyncRunning ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <CloudDownload size={16} />
                    )}
                    Sync Now
                  </button>
                  <p className="text-xs text-text-muted">
                    Delta sync: fetches only leads newer than your latest imported Meta lead (or the last 30
                    days on first run). First sync after setup may take a few minutes.
                  </p>
                  {isLeadSyncDirty ? (
                    <button
                      type="button"
                      onClick={handleSaveLeadSyncSettings}
                      disabled={leadSyncSaving}
                      className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm font-semibold hover:bg-surface-bg disabled:opacity-50"
                    >
                      {leadSyncSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      Save Manual Mode
                    </button>
                  ) : null}
                </div>
              )}

              {leadSyncConfig?.last_run_summary ? (
                <div className="rounded-lg border border-border-subtle bg-surface-bg px-4 py-3 text-sm">
                  <p className="font-medium text-text-main mb-2">Last download summary</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-text-muted block">Forms checked</span>
                      <strong>{leadSyncConfig.last_run_summary.forms_processed ?? 0}</strong>
                    </div>
                    <div>
                      <span className="text-text-muted block">Leads seen</span>
                      <strong>{leadSyncConfig.last_run_summary.leads_seen ?? 0}</strong>
                    </div>
                    <div>
                      <span className="text-text-muted block">New saved</span>
                      <strong>{leadSyncConfig.last_run_summary.leads_created ?? 0}</strong>
                    </div>
                    <div>
                      <span className="text-text-muted block">Already in Nexus</span>
                      <strong>{leadSyncConfig.last_run_summary.leads_skipped ?? 0}</strong>
                    </div>
                  </div>
                  {(leadSyncConfig.last_run_summary.errors?.length ?? 0) > 0 ? (
                    <p className="mt-2 text-xs text-amber-700">
                      {leadSyncConfig.last_run_summary.errors?.length} warning(s) during the last sync.
                    </p>
                  ) : null}
                </div>
              ) : null}

              {leadSyncMessage ? (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 flex items-center gap-2">
                  <CheckCircle2 size={16} />
                  {leadSyncMessage}
                </div>
              ) : null}

              {leadSyncError ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {leadSyncError}
                </div>
              ) : null}
            </>
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
                {settings.map(setting => {
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
                        {setting.updated_at
                          ? new Date(setting.updated_at).toLocaleString()
                          : 'Not saved yet'}
                      </td>
                      <td className="px-4 py-4 align-top text-xs text-text-muted hidden lg:table-cell">
                        {formatModifiedBy(setting)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {hasUnsavedChanges && (
        <p className="text-xs text-text-muted">
          {(dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0))} unsaved change
          {dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0) === 1 ? '' : 's'}. Click Save Changes to apply.
        </p>
      )}

      <PublicHolidayCalendar />
    </div>
  );
};

export default AppSettings;
