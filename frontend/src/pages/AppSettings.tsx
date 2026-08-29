import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Activity,
  Archive,
  Bell,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock,
  CloudDownload,
  Image as ImageIcon,
  Loader2,
  Receipt,
  RefreshCw,
  Save,
  Settings,
  Upload,
} from 'lucide-react';
import PublicHolidayCalendar from '../components/PublicHolidayCalendar';
import MetaLeadSyncPanel from '../components/dashboard/MetaLeadSyncPanel';
import BillingSettingsSection, {
  DEFAULT_BILLING_SECTION,
  isBillingSectionId,
  type BillingSectionId,
} from '../components/settings/BillingSettingsSection';
import LabeledContactListField from '../components/academia/form/LabeledContactListField';
import { apiFetch, apiUpload, getStoredToken, resolveBaseUrl } from '../utils/api';
import { clearBusinessTimezoneCache } from '../utils/timezone';
import { PHONE_LOCAL_PLACEHOLDER } from '../utils/phoneCountry';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';
import { useCountries } from '../hooks/useCountries';
import {
  useEmailContactTypeOptions,
  usePhoneContactTypeOptions,
} from '../hooks/useContactTypeOptions';
import {
  createDefaultEmailContacts,
  createDefaultPhoneContacts,
  isValidEmailAddress,
  normalizeEmailContacts,
  normalizePhoneContacts,
  serializeContacts,
  type ContactEntry,
} from '../schemas/contactEntry';

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

type SettingsTabId = 'organization' | 'billing' | 'workspace' | 'monitoring';
type WorkspaceSectionId = 'bookings' | 'meta' | 'holidays' | 'alerts' | 'retention';

const BOOKING_SETTING_KEYS = [
  'COUNSELING_SLOT_DURATION',
  'ALLOW_BOOKINGS',
  'COUNSELING_SESSION_PURPOSES',
  'OFFICE_HOURS_START',
  'OFFICE_HOURS_END',
  'SAME_DAY_BOOKING_LEAD_MINUTES',
  'WORKING_DAYS',
  'MAX_BOOKINGS_PER_SLOT',
  'BUSINESS_TIMEZONE',
  'CALENDAR_INTAKE_ADVANCE_DAYS',
] as const;

const ALERT_SETTING_KEYS = [
  'ADMIN_SESSION_DIGEST_ENABLED',
  'ADMIN_SESSION_DIGEST_TIME',
  'ADMIN_SESSION_NUDGE_ENABLED',
  'ADMIN_SESSION_NUDGE_MINUTES',
  'ADMIN_BOOKING_ALERTS_ENABLED',
] as const;

const RETENTION_SETTING_KEYS = [
  'AUDIT_LOG_RETENTION_DAYS',
  'EXCEPTION_LOG_RETENTION_DAYS',
] as const;

/** Shown on Workspace → Meta; keep out of Bookings & Hours orphan dump. */
const META_SETTING_KEYS = [
  'META_LEAD_SYNC_MODE',
  'META_LEAD_SYNC_INTERVAL_VALUE',
  'META_LEAD_SYNC_INTERVAL_UNIT',
  'META_LEAD_SYNC_LAST_RUN_AT',
  'META_LEAD_SYNC_LAST_RUN_SUMMARY',
] as const;

const META_READONLY_SETTING_KEYS = new Set<string>([
  'META_LEAD_SYNC_LAST_RUN_AT',
  'META_LEAD_SYNC_LAST_RUN_SUMMARY',
]);

function isMetaSettingKey(key: string): boolean {
  return key.startsWith('META_') || (META_SETTING_KEYS as readonly string[]).includes(key);
}

function isMetaReadonlySettingKey(key: string): boolean {
  return META_READONLY_SETTING_KEYS.has(key);
}

const SETTINGS_TABS: Array<{
  id: SettingsTabId;
  label: string;
  description: string;
  icon: React.ReactNode;
  /** When false, tab is URL-driven (Accounts → Billing) but hidden from this strip. */
  showInStrip?: boolean;
}> = [
  {
    id: 'organization',
    label: 'Organization',
    description: 'Business profile, logo, and office phone/email contacts',
    icon: <Building2 size={15} strokeWidth={2.25} />,
    showInStrip: true,
  },
  {
    id: 'billing',
    label: 'Billing',
    description: 'Base price catalog, invoice format, GSTIN, discount policy, and bank details',
    icon: <Receipt size={15} strokeWidth={2.25} />,
    showInStrip: false,
  },
  {
    id: 'workspace',
    label: 'Workspace',
    description: 'Bookings, Meta lead sync, holidays, counsellor alerts, and data retention',
    icon: <CalendarDays size={15} strokeWidth={2.25} />,
    showInStrip: true,
  },
  {
    id: 'monitoring',
    label: 'Monitoring',
    description: 'Uptime checks and alert email recipients',
    icon: <Activity size={15} strokeWidth={2.25} />,
    showInStrip: true,
  },
];

const SETTINGS_STRIP_TABS = SETTINGS_TABS.filter(tab => tab.showInStrip !== false);

const WORKSPACE_SECTIONS: Array<{
  id: WorkspaceSectionId;
  label: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    id: 'bookings',
    label: 'Bookings & Hours',
    description: 'Slot duration, office hours, timezone, and booking capacity',
    icon: <Clock size={13} strokeWidth={2.25} />,
  },
  {
    id: 'meta',
    label: 'Meta',
    description: 'Facebook & Instagram Lead Ads sync mode, schedule, and manual pull',
    icon: <CloudDownload size={13} strokeWidth={2.25} />,
  },
  {
    id: 'holidays',
    label: 'Holidays',
    description: 'Public and private office holiday calendar',
    icon: <CalendarDays size={13} strokeWidth={2.25} />,
  },
  {
    id: 'alerts',
    label: 'Counsellor Alerts',
    description: 'WhatsApp digests, pre-session nudges, and booking change alerts',
    icon: <Bell size={13} strokeWidth={2.25} />,
  },
  {
    id: 'retention',
    label: 'Data Retention',
    description: 'Audit log and exception report cleanup windows',
    icon: <Archive size={13} strokeWidth={2.25} />,
  },
];

function normalizeSettingsTabId(value: string | null): SettingsTabId | null {
  if (!value) return null;
  if (value === 'operations') return 'workspace';
  return SETTINGS_TABS.some(tab => tab.id === value) ? (value as SettingsTabId) : null;
}

function isWorkspaceSectionId(value: string | null): value is WorkspaceSectionId {
  return WORKSPACE_SECTIONS.some(section => section.id === value);
}

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
  office_phone_contacts?: ContactEntry[] | null;
  office_email_contacts?: ContactEntry[] | null;
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
  office_phone_contacts: ContactEntry[];
  office_email_contacts: ContactEntry[];
  web_url: string;
  email_domain: string;
};

type BusinessProfileFieldErrors = Partial<
  Record<keyof BusinessProfileDraft | 'office_phone_contacts' | 'office_email_contacts', string>
>;

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
  office_phone_contacts: createDefaultPhoneContacts(),
  office_email_contacts: createDefaultEmailContacts(),
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

  const phones = serializeContacts(draft.office_phone_contacts);
  if (phones.some(entry => !OFFICE_PHONE_PATTERN.test(entry.value))) {
    errors.office_phone_contacts = 'Enter valid phone numbers for each filled row.';
  }

  const emails = serializeContacts(draft.office_email_contacts);
  if (emails.some(entry => !isValidEmailAddress(entry.value))) {
    errors.office_email_contacts = 'Enter valid email addresses for each filled row.';
  }

  return errors;
};

const contactsFromProfile = (profile: BusinessProfile | null): {
  phones: ContactEntry[];
  emails: ContactEntry[];
} => {
  const phonesFromApi = Array.isArray(profile?.office_phone_contacts)
    ? profile.office_phone_contacts
    : [];
  const emailsFromApi = Array.isArray(profile?.office_email_contacts)
    ? profile.office_email_contacts
    : [];
  const legacyPhones = [
    profile?.office_phone_number
      ? { type: 'Main Line', value: profile.office_phone_number }
      : null,
    profile?.office_mobile_number
      ? { type: 'WhatsApp', value: profile.office_mobile_number }
      : null,
  ].filter(Boolean) as ContactEntry[];

  return {
    phones: normalizePhoneContacts(phonesFromApi.length ? phonesFromApi : legacyPhones),
    emails: normalizeEmailContacts(emailsFromApi),
  };
};

const businessProfileToDraft = (profile: BusinessProfile | null): BusinessProfileDraft => {
  const contacts = contactsFromProfile(profile);
  return {
    business_name: profile?.business_name ?? '',
    business_domain: profile?.business_domain ?? '',
    address_line1: profile?.address_line1 ?? '',
    address_line2: profile?.address_line2 ?? '',
    address_line3: profile?.address_line3 ?? '',
    city: profile?.city ?? '',
    state: profile?.state ?? '',
    country: profile?.country ?? '',
    zip_code: profile?.zip_code ?? '',
    office_phone_contacts: contacts.phones,
    office_email_contacts: contacts.emails,
    web_url: profile?.web_url ?? '',
    email_domain: profile?.email_domain ?? '',
  };
};

const draftsMatch = (left: BusinessProfileDraft, right: BusinessProfileDraft): boolean =>
  (Object.keys(left) as Array<keyof BusinessProfileDraft>).every(key => {
    if (key === 'office_phone_contacts' || key === 'office_email_contacts') {
      return JSON.stringify(left[key]) === JSON.stringify(right[key]);
    }
    return left[key] === right[key];
  });

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
  const phoneContactTypes = usePhoneContactTypeOptions();
  const emailContactTypes = useEmailContactTypeOptions();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = normalizeSettingsTabId(searchParams.get('tab'));
  const sectionFromUrl = searchParams.get('section');
  const [activeTab, setActiveTab] = useState<SettingsTabId>(() => tabFromUrl ?? 'organization');
  const [workspaceSection, setWorkspaceSection] = useState<WorkspaceSectionId>(() =>
    isWorkspaceSectionId(sectionFromUrl) ? sectionFromUrl : 'bookings'
  );
  const [billingSection, setBillingSection] = useState<BillingSectionId>(() =>
    isBillingSectionId(sectionFromUrl) ? sectionFromUrl : DEFAULT_BILLING_SECTION
  );
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
    const nextTab = tabFromUrl ?? 'organization';
    if (nextTab !== activeTab) {
      setActiveTab(nextTab);
    }
  }, [tabFromUrl, activeTab]);

  useEffect(() => {
    if (isWorkspaceSectionId(sectionFromUrl) && sectionFromUrl !== workspaceSection) {
      setWorkspaceSection(sectionFromUrl);
    }
  }, [sectionFromUrl, workspaceSection]);

  useEffect(() => {
    if (isBillingSectionId(sectionFromUrl) && sectionFromUrl !== billingSection) {
      setBillingSection(sectionFromUrl);
    }
  }, [sectionFromUrl, billingSection]);

  const selectTab = useCallback(
    (tabId: SettingsTabId) => {
      setActiveTab(tabId);
      const next = new URLSearchParams(searchParams);
      if (tabId === 'organization') {
        next.delete('tab');
      } else {
        next.set('tab', tabId);
      }
      if (tabId === 'workspace') {
        if (!isWorkspaceSectionId(next.get('section'))) {
          next.set('section', workspaceSection);
        }
      } else if (tabId === 'billing') {
        if (!isBillingSectionId(next.get('section'))) {
          next.set('section', billingSection);
        }
      } else {
        next.delete('section');
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams, workspaceSection, billingSection]
  );

  const selectWorkspaceSection = useCallback(
    (sectionId: WorkspaceSectionId) => {
      setWorkspaceSection(sectionId);
      const next = new URLSearchParams(searchParams);
      next.set('tab', 'workspace');
      next.set('section', sectionId);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  useEffect(() => {
    return () => {
      if (logoPreviewUrl) URL.revokeObjectURL(logoPreviewUrl);
    };
  }, [logoPreviewUrl]);

  const dirtyKeys = useMemo(
    () =>
      settings
        .filter(item => !isMetaReadonlySettingKey(item.key))
        .filter(item => (draftValues[item.key] ?? '') !== item.value)
        .map(item => item.key),
    [draftValues, settings]
  );

  const {
    monitoringPanelSettings,
    bookingSettings,
    alertSettings,
    retentionSettings,
    metaSettings,
    orphanWorkspaceSettings,
  } = useMemo(() => {
    const monitoringKeys = new Set<string>(MONITORING_SETTING_ORDER);
    const bookingKeys = new Set<string>(BOOKING_SETTING_KEYS);
    const alertKeys = new Set<string>(ALERT_SETTING_KEYS);
    const retentionKeys = new Set<string>(RETENTION_SETTING_KEYS);
    const byKey = new Map(settings.map(item => [item.key, item]));
    const ordered = (keys: readonly string[]) =>
      keys.map(key => byKey.get(key)).filter((item): item is DynamicSetting => Boolean(item));

    return {
      monitoringPanelSettings: ordered(MONITORING_SETTING_ORDER),
      bookingSettings: ordered(BOOKING_SETTING_KEYS),
      alertSettings: ordered(ALERT_SETTING_KEYS),
      retentionSettings: ordered(RETENTION_SETTING_KEYS),
      metaSettings: ordered(META_SETTING_KEYS),
      orphanWorkspaceSettings: settings.filter(
        item =>
          !monitoringKeys.has(item.key) &&
          !bookingKeys.has(item.key) &&
          !alertKeys.has(item.key) &&
          !retentionKeys.has(item.key) &&
          !isMetaSettingKey(item.key)
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

  const bookingRows = useMemo(
    () => [...bookingSettings, ...orphanWorkspaceSettings],
    [bookingSettings, orphanWorkspaceSettings]
  );

  const workspaceSectionDirty: Record<WorkspaceSectionId, boolean> = useMemo(
    () => ({
      bookings: bookingRows.some(item => dirtyKeys.includes(item.key)),
      meta: metaSettings.some(item => dirtyKeys.includes(item.key)),
      holidays: false,
      alerts: alertSettings.some(item => dirtyKeys.includes(item.key)),
      retention: retentionSettings.some(item => dirtyKeys.includes(item.key)),
    }),
    [bookingRows, metaSettings, alertSettings, retentionSettings, dirtyKeys]
  );

  const tabDirty: Record<SettingsTabId, boolean> = {
    organization: isBusinessProfileDirty,
    billing: false,
    workspace: Object.values(workspaceSectionDirty).some(Boolean),
    monitoring: monitoringPanelSettings.some(item => dirtyKeys.includes(item.key)),
  };

  const showServerSaveActions = activeTab !== 'billing';

  const handleDraftChange = (key: string, value: string) => {
    setDraftValues(prev => ({ ...prev, [key]: value }));
    setSuccessMessage(null);
  };

  const handleBusinessProfileChange = (
    field: keyof BusinessProfileDraft,
    value: string | ContactEntry[]
  ) => {
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
              office_phone_contacts: serializeContacts(businessProfileDraft.office_phone_contacts),
              office_email_contacts: serializeContacts(businessProfileDraft.office_email_contacts),
              office_phone_number:
                serializeContacts(businessProfileDraft.office_phone_contacts)[0]?.value || null,
              office_mobile_number:
                serializeContacts(businessProfileDraft.office_phone_contacts)[1]?.value || null,
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

    if (isMetaReadonlySettingKey(setting.key)) {
      const display =
        setting.key === 'META_LEAD_SYNC_LAST_RUN_SUMMARY' && value
          ? value.length > 180
            ? `${value.slice(0, 180)}…`
            : value
          : value;
      return (
        <div className="max-w-xl rounded-lg border border-border-subtle bg-surface-bg/70 px-3 py-2 text-sm text-text-main font-mono break-all">
          {display || '—'}
          <p className="mt-1 text-[11px] font-sans text-text-muted">Updated automatically by sync runs.</p>
        </div>
      );
    }

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
        <div className="w-full max-w-2xl space-y-2">
          <textarea
            value={value}
            onChange={event => handleDraftChange(setting.key, event.target.value)}
            rows={8}
            spellCheck={false}
            placeholder={[
              'General Counselling | Initial study-abroad guidance and pathway overview',
              'Visa Application Help | Visa forms, evidence checklist, and interview prep',
              'Scholarship Guidance | Funding options, eligibility, and application tips',
            ].join('\n')}
            className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 font-mono text-sm text-text-main outline-none focus:border-primary"
            aria-describedby="session-purposes-example"
          />
          <div
            id="session-purposes-example"
            className="rounded-lg border border-border-subtle bg-surface-bg/70 px-3 py-2 text-xs text-text-muted"
          >
            <p className="font-semibold text-text-main">How to enter</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              <li>One purpose per line — these appear in Book Appointment.</li>
              <li>
                Format: <span className="font-mono text-text-main">Label | Short description</span>
              </li>
              <li>The label is required; text after the pipe is optional helper copy for staff.</li>
              <li>Commas inside a description are fine — do not put multiple purposes on one line.</li>
            </ul>
            <p className="mt-2 font-semibold text-text-main">Example</p>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-text-main">
              {`General Counselling | Initial study-abroad guidance and pathway overview
Visa Application Help | Visa forms, evidence checklist, and interview prep
Scholarship Guidance | Funding options, eligibility, and application tips`}
            </pre>
          </div>
        </div>
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
        <td className="w-[34%] max-w-[19.25rem] px-4 py-4 align-top">
          <div className="font-medium text-text-main">{setting.label}</div>
          <div className="mt-1 text-xs text-text-muted break-words">{setting.description}</div>
          <div className="mt-1 break-all font-mono text-[11px] text-text-muted">{setting.key}</div>
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

  const renderSettingsTable = (rows: DynamicSetting[], emptyLabel: string) => (
    <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <Loader2 size={24} className="animate-spin mr-2" />
          Loading settings...
        </div>
      ) : rows.length === 0 ? (
        <div className="px-4 py-8 text-sm text-text-muted">{emptyLabel}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full table-fixed text-sm">
            <thead className="bg-surface-bg border-b border-border-subtle">
              <tr>
                <th className="w-[34%] max-w-[19.25rem] px-4 py-3 text-left font-semibold text-text-muted">
                  Setting
                </th>
                <th className="text-left px-4 py-3 font-semibold text-text-muted">Value</th>
                <th className="w-[13.5%] text-left px-4 py-3 font-semibold text-text-muted hidden lg:table-cell">
                  Last updated
                </th>
                <th className="w-[10.5%] text-left px-4 py-3 font-semibold text-text-muted hidden lg:table-cell">
                  Modified by
                </th>
              </tr>
            </thead>
            <tbody>{rows.map(setting => renderSettingRow(setting))}</tbody>
          </table>
        </div>
      )}
    </div>
  );

  const renderActionButtons = (placement: 'top' | 'bottom') => {
    if (!showServerSaveActions) {
      return placement === 'top' ? (
        <button
          type="button"
          onClick={loadSettings}
          disabled={loading || saving}
          className="inline-flex items-center gap-2 self-start rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm hover:bg-surface-bg disabled:opacity-60"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      ) : null;
    }

    return (
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
    <div className="space-y-6 p-6 md:p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-text-main">
            <Settings size={24} />
            Application Settings
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            Configure organization, workspace, and monitoring. Billing lives under Admin → Accounts.
          </p>
        </div>
        {renderActionButtons('top')}
      </div>

      {successMessage && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <CheckCircle2 size={16} />
          {successMessage}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-border-subtle bg-card">
        {activeTab === 'billing' ? (
          <div className="border-b border-border-subtle bg-surface-bg/50 px-4 py-2.5 md:px-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              Accounts · Billing
            </p>
            <p className="mt-0.5 text-xs text-text-muted">
              {SETTINGS_TABS.find(tab => tab.id === 'billing')?.description}
            </p>
          </div>
        ) : (
          <>
            <nav
              className="flex gap-0.5 overflow-x-auto border-b border-border-subtle px-2 pt-2 custom-scrollbar"
              aria-label="Settings sections"
              role="tablist"
            >
              {SETTINGS_STRIP_TABS.map(tab => {
                const active = activeTab === tab.id;
                const dirty = tabDirty[tab.id];
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => selectTab(tab.id)}
                    className={`group relative inline-flex shrink-0 items-center gap-2 rounded-t-lg px-3.5 py-2.5 text-sm font-semibold transition-colors ${
                      active
                        ? 'bg-surface-bg text-accent'
                        : 'text-text-muted hover:bg-surface-bg/70 hover:text-text-main'
                    }`}
                  >
                    <span
                      className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
                        active
                          ? 'bg-accent text-text-dark-bg'
                          : 'bg-surface-bg text-text-muted group-hover:bg-card group-hover:text-accent'
                      }`}
                    >
                      {tab.icon}
                    </span>
                    <span className="whitespace-nowrap tracking-wide">{tab.label}</span>
                    {dirty ? (
                      <span
                        className="h-2 w-2 rounded-full bg-amber-500"
                        title="Unsaved changes"
                        aria-label="Unsaved changes"
                      />
                    ) : null}
                    <span
                      className={`pointer-events-none absolute inset-x-2 -bottom-px h-0.5 rounded-full transition-opacity ${
                        active ? 'bg-accent opacity-100' : 'opacity-0'
                      }`}
                    />
                  </button>
                );
              })}
            </nav>

            <div className="border-b border-border-subtle bg-surface-bg/50 px-4 py-2.5 md:px-5">
              <p className="text-xs text-text-muted">
                {SETTINGS_TABS.find(tab => tab.id === activeTab)?.description}
              </p>
            </div>
          </>
        )}
      </div>

      {activeTab === 'organization' ? (
        <div className="space-y-4">
        <div className="overflow-hidden rounded-2xl border border-border-subtle bg-card">
          <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="flex items-center gap-2 text-base font-semibold text-text-main">
                  <Building2 size={18} />
                  Business Profile
                </h2>
              </div>
              <div className="space-y-0.5 text-[11px] text-text-muted md:text-right">
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
              <div className="flex items-center justify-center py-8 text-sm text-text-muted">
                <Loader2 size={18} className="mr-2 animate-spin" />
                Loading business profile...
              </div>
            ) : (
              <div className="grid grid-cols-1 items-start gap-x-6 gap-y-4 md:grid-cols-2 xl:grid-cols-3">
                {renderBusinessProfileSection(
                  'Business identity',
                  'Core name and public-facing web presence for this tenant.'
                )}
                <div className="col-span-1 grid grid-cols-1 items-start gap-x-6 gap-y-4 md:col-span-2 md:grid-cols-2 xl:col-span-3 xl:grid-cols-5">
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
                  {renderBusinessProfileField('email-domain', 'Email Domain Name', 'email_domain', {
                    placeholder: 'company.com',
                  })}
                  <div className="flex min-w-0 flex-col">
                    <span className="block text-sm font-medium leading-tight text-text-main">
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
                  'Add as many typed office phones and emails as you need.',
                  true
                )}
                <div className="col-span-1 grid grid-cols-1 items-start gap-x-6 gap-y-4 md:col-span-2 md:grid-cols-2 xl:col-span-3">
                  <LabeledContactListField
                    label="Phone numbers"
                    items={businessProfileDraft.office_phone_contacts}
                    onChange={next => handleBusinessProfileChange('office_phone_contacts', next)}
                    typeOptions={phoneContactTypes}
                    valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
                    valueInputType="tel"
                    addLabel="Add phone number"
                    errors={
                      businessProfileErrors.office_phone_contacts
                        ? [businessProfileErrors.office_phone_contacts]
                        : []
                    }
                    phoneCountries={countries}
                    defaultPhoneCountryIso2="IN"
                    fullWidth={false}
                    typeSelectWidthClass="w-full sm:w-[8.5rem]"
                  />
                  <LabeledContactListField
                    label="Email addresses"
                    items={businessProfileDraft.office_email_contacts}
                    onChange={next => handleBusinessProfileChange('office_email_contacts', next)}
                    typeOptions={emailContactTypes}
                    valuePlaceholder="office@company.com"
                    valueInputType="email"
                    addLabel="Add email address"
                    errors={
                      businessProfileErrors.office_email_contacts
                        ? [businessProfileErrors.office_email_contacts]
                        : []
                    }
                    fullWidth={false}
                    typeSelectWidthClass="w-full sm:w-[9.5rem]"
                  />
                </div>

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

                <div className="col-span-1 grid grid-cols-1 items-start gap-x-6 gap-y-4 sm:grid-cols-2 md:col-span-2 xl:col-span-3 xl:grid-cols-4">
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
        </div>
      ) : null}

      {activeTab === 'billing' ? <BillingSettingsSection /> : null}

      {activeTab === 'workspace' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2.5">
            <div className="hidden items-center gap-2 sm:flex">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Workspace
              </span>
              <span className="h-3 w-px bg-border-subtle" aria-hidden />
            </div>
            <div
              className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-card p-1"
              role="tablist"
              aria-label="Workspace sections"
            >
              {WORKSPACE_SECTIONS.map(section => {
                const active = workspaceSection === section.id;
                const dirty = workspaceSectionDirty[section.id];
                return (
                  <button
                    key={section.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => selectWorkspaceSection(section.id)}
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
                      active
                        ? 'bg-accent text-text-dark-bg shadow-sm'
                        : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
                    }`}
                  >
                    {section.icon}
                    {section.label}
                    {dirty ? (
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          active ? 'bg-amber-200' : 'bg-amber-500'
                        }`}
                        title="Unsaved changes"
                        aria-label="Unsaved changes"
                      />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>

          <p className="text-xs text-text-muted">
            {WORKSPACE_SECTIONS.find(section => section.id === workspaceSection)?.description}
          </p>

          {workspaceSection === 'bookings'
            ? renderSettingsTable(
                bookingRows,
                'No booking or office-hour settings are available for this tenant.'
              )
            : null}

          {workspaceSection === 'meta' ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-border-subtle bg-surface-bg/60 px-4 py-3">
                <p className="text-sm font-semibold text-text-main">Meta Lead Ads sync</p>
                <p className="mt-0.5 text-xs text-text-muted">
                  Use the panel for Sync Now and live scheduler status. Mode, interval value, and
                  interval unit also appear in the settings table below — edit those rows and click
                  Save Settings, or save from the panel.
                </p>
              </div>
              <MetaLeadSyncPanel onConfigChanged={() => void loadSettings()} />
              {renderSettingsTable(
                metaSettings,
                'Meta lead sync settings are not available yet. Refresh after the backend has loaded.'
              )}
            </div>
          ) : null}

          {workspaceSection === 'holidays' ? <PublicHolidayCalendar /> : null}

          {workspaceSection === 'alerts'
            ? renderSettingsTable(
                alertSettings,
                'No counsellor alert settings are available for this tenant.'
              )
            : null}

          {workspaceSection === 'retention'
            ? renderSettingsTable(
                retentionSettings,
                'No data retention settings are available for this tenant.'
              )
            : null}
        </div>
      ) : null}

      {activeTab === 'monitoring' ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-border-subtle bg-surface-bg/60 px-4 py-3">
            <p className="text-sm font-semibold text-text-main">Uptime &amp; alerts</p>
            <p className="mt-0.5 text-xs text-text-muted">
              Alert emails receive Exception Report notifications and auto-resolution confirmations
              immediately. Uptime checks run only while Monitoring status is Active.
            </p>
          </div>
          {renderSettingsTable(
            monitoringPanelSettings,
            'No monitoring settings are available for this tenant.'
          )}
        </div>
      ) : null}

      {showServerSaveActions && hasUnsavedChanges ? (
        <p className="text-xs text-text-muted">
          {dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0)} unsaved change
          {dirtyKeys.length + (isBusinessProfileDirty ? 1 : 0) === 1 ? '' : 's'}. Click Save Settings
          to apply.
        </p>
      ) : null}

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
                className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-text-dark-bg"
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
