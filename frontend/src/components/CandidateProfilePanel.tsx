import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { BookOpen, Briefcase, ClipboardList, FlaskConical, GraduationCap, Gauge, Link2, Loader2, School, Sparkles, User, X } from 'lucide-react';
import MyAspirationsTab from './MyAspirationsTab';
import ProfilePulseTab from './ProfilePulseTab';
import CandidateTestScoresTab from './CandidateTestScoresTab';
import WorkProjectsTab from './WorkProjectsTab';
import ResearchProjectsTab from './ResearchProjectsTab';
import NonAcademicActivitiesTab from './NonAcademicActivitiesTab';
import CandidateEducationsTab from './CandidateEducationsTab';
import DigitalPresenceTab from './DigitalPresenceTab';
import UniversityShortlistTab from './UniversityShortlistTab';
import { apiFetch } from '../utils/api';
import { useCountries, formatPhoneCountryLabel } from '../hooks/useCountries';
import { useStatusDefinitions } from '../hooks/useStudentStatus';
import type { CandidateProfile, StudentMasterFormState } from '../types/candidateProfile';
import {
  formToSavePayload,
  formatLocalIsoDate,
  parseLocalIsoDate,
  profileToForm,
  PROFILE_FIELD_LIMITS,
  validateStudentMasterForm,
} from '../types/candidateProfile';
import {
  PHONE_LOCAL_DRAFT_MAX_LENGTH,
  PHONE_LOCAL_PLACEHOLDER,
  sanitizePhoneLocalDraft,
  validateDateOfBirth,
} from '../utils/phoneCountry';
import {
  buildProfileFromBooking,
  loadBookingCandidateProfile,
  type BookingRowForProfile,
} from '../utils/candidateProfileLoader';
import type { ProfilePanelTab } from '../types/profilePanel';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
  studentInfoSectionClass as sectionClass,
} from './studentInfoFormStyles';
import { nexusDatePickerPortalProps } from '../utils/nexusDatePickerPortal';

interface CandidateProfilePanelProps {
  booking: BookingRowForProfile;
  dateLabel?: string;
  timeLabel?: string;
  onClose?: () => void;
  variant?: 'standalone' | 'embedded';
}

const FORM_TABS: ProfilePanelTab[] = ['profile'];

const isFormTab = (tab: ProfilePanelTab): boolean => FORM_TABS.includes(tab);

const RequiredLabel: React.FC<{ htmlFor?: string; children: React.ReactNode }> = ({
  htmlFor,
  children,
}) => (
  <label htmlFor={htmlFor} className={labelClass}>
    {children}
    <span className="text-red-600" aria-hidden="true">
      {' '}
      *
    </span>
  </label>
);

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const phoneCountrySelectClass = (hasError: boolean) =>
  `${fieldClass(hasError)} max-w-[7.5rem]`;

const phoneCountrySelectOptionalClass = `${inputClass} max-w-[7.5rem]`;

const radioGroupClass = 'flex flex-wrap items-center gap-3 min-h-[36px]';
const radioOptionClass =
  'inline-flex items-center gap-1.5 text-sm text-text-main cursor-pointer';

const radioBoxClass = (hasError: boolean) =>
  `w-full rounded-md border bg-card px-3 py-2 ${radioGroupClass}${
    hasError ? ' border-red-400 ring-1 ring-red-200' : ' border-border-subtle'
  }`;

const PlaceholderTabSection: React.FC<{ title: string; description: string }> = ({
  title,
  description,
}) => (
  <section className={sectionClass}>
    <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">{title}</h3>
    <p className="text-sm text-text-muted">{description}</p>
  </section>
);

const CandidateProfilePanel: React.FC<CandidateProfilePanelProps> = ({
  booking,
  dateLabel,
  timeLabel,
  onClose,
  variant = 'standalone',
}) => {
  const isEmbedded = variant === 'embedded';
  const [form, setForm] = useState<StudentMasterFormState>(() =>
    profileToForm(buildProfileFromBooking(booking))
  );
  const [baseline, setBaseline] = useState<StudentMasterFormState>(() =>
    profileToForm(buildProfileFromBooking(booking))
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<ProfilePanelTab>(
    variant === 'embedded' ? 'profile_pulse' : 'aspirations'
  );
  const [leadStatusLabel, setLeadStatusLabel] = useState(booking.status_stage_name ?? '');
  const [leadStatusDefinitionId, setLeadStatusDefinitionId] = useState<number | null>(
    booking.status_definition_id ?? null
  );

  const dobDate = useMemo(() => parseLocalIsoDate(form.date_of_birth), [form.date_of_birth]);

  const profileFullName = useMemo(() => {
    const first = form.first_name.trim();
    const middle = form.middle_name.trim();
    const last = form.last_name.trim();
    if (!first || !last) return '';
    return [first, middle, last].filter(Boolean).join(' ');
  }, [form.first_name, form.middle_name, form.last_name]);

  const { countries } = useCountries();
  const { data: statusDefinitions } = useStatusDefinitions();

  const profileStatusLabel = useMemo(() => {
    if (leadStatusLabel.trim()) return leadStatusLabel.trim();
    const statusId = leadStatusDefinitionId ?? booking.status_definition_id;
    if (!statusId) return '';
    const match = statusDefinitions?.items.find(item => item.id === statusId);
    return match?.stage_name ?? '';
  }, [
    booking.status_definition_id,
    leadStatusDefinitionId,
    leadStatusLabel,
    statusDefinitions?.items,
  ]);

  const countriesByName = useMemo(
    () => [...countries].sort((a, b) => a.name.localeCompare(b.name)),
    [countries]
  );

  const countriesByCode = useMemo(
    () => [...countries].sort((a, b) => a.iso2.localeCompare(b.iso2)),
    [countries]
  );

  const applyProfile = useCallback((profile: CandidateProfile) => {
    const next = profileToForm(profile);
    setForm(next);
    setBaseline(next);
    setSavedAt(profile.saved_at || null);
    setFieldErrors({});
  }, []);

  useEffect(() => {
    setActiveTab(isEmbedded ? 'profile_pulse' : 'aspirations');
    setLeadStatusLabel(booking.status_stage_name ?? '');
    setLeadStatusDefinitionId(booking.status_definition_id ?? null);
  }, [booking.id, booking.status_definition_id, booking.status_stage_name, isEmbedded]);

  useEffect(() => {
    if (!booking.lead_id) return;

    let cancelled = false;
    apiFetch(`leads/${booking.lead_id}`)
      .then(response => {
        if (cancelled) return;
        const data = response as {
          status_stage_name?: string | null;
          status_definition_id?: number | null;
        };
        if (data.status_stage_name) {
          setLeadStatusLabel(data.status_stage_name);
        }
        if (data.status_definition_id != null) {
          setLeadStatusDefinitionId(data.status_definition_id);
        }
      })
      .catch(() => {
        /* keep booking snapshot values */
      });

    return () => {
      cancelled = true;
    };
  }, [booking.lead_id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadBookingCandidateProfile(booking, apiFetch)
      .then(result => {
        if (cancelled) return;
        applyProfile(result.profile);
      })
      .catch(err => {
        if (cancelled) return;
        applyProfile(buildProfileFromBooking(booking));
        setError(err instanceof Error ? err.message : 'Failed to load candidate profile.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [applyProfile, booking]);

  const updateForm = (patch: Partial<StudentMasterFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    const clearedKeys = Object.keys(patch);
    if (clearedKeys.length) {
      setFieldErrors(prev => {
        const next = { ...prev };
        clearedKeys.forEach(key => {
          delete next[key];
        });
        return next;
      });
    }
  };

  const handleCancel = () => {
    setForm(baseline);
    setSuccess(null);
    setError(null);
    setFieldErrors({});
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    const validationErrors = validateStudentMasterForm(form);
    const dobValidation = form.date_of_birth ? validateDateOfBirth(form.date_of_birth) : null;
    if (dobValidation) {
      validationErrors.date_of_birth = dobValidation;
    }
    if (Object.keys(validationErrors).length > 0) {
      setFieldErrors(validationErrors);
      setError('Please complete all required fields before submitting.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const response = (await apiFetch(`bookings/mine/${booking.id}/students-master`, {
        method: 'POST',
        body: JSON.stringify(formToSavePayload(form)),
      })) as { profile: CandidateProfile; saved_at?: string };
      applyProfile(response.profile);
      setSuccess('Profile saved to students master.');
      setSavedAt(response.profile.saved_at || response.saved_at || new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile.');
    } finally {
      setSaving(false);
    }
  };

  const tabButtonClass = (tab: ProfilePanelTab) =>
    `flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-md px-1.5 py-2 text-sm leading-tight text-center transition-colors ${
      activeTab === tab
        ? 'font-bold bg-sky-100 text-sky-900 border border-sky-200'
        : 'font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg border border-transparent'
    }`;

  const profileWorkspace = (
    <>
      <div
        className={`shrink-0 flex gap-1 border-b border-border-subtle bg-surface-bg/30 ${
          isEmbedded ? 'px-2 py-1.5' : 'px-2 py-1.5'
        }`}
      >
        <button
          type="button"
          className={tabButtonClass('profile_pulse')}
          onClick={() => setActiveTab('profile_pulse')}
        >
          <Gauge size={14} className="shrink-0" />
          <span>PROFILE PULSE</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('aspirations')}
          onClick={() => setActiveTab('aspirations')}
        >
          <Sparkles size={14} className="shrink-0" />
          <span>ASPIRATIONS</span>
        </button>
        <button type="button" className={tabButtonClass('profile')} onClick={() => setActiveTab('profile')}>
          <User size={14} className="shrink-0" />
          <span>PERSONAL PROFILE</span>
        </button>
        <button type="button" className={tabButtonClass('academia')} onClick={() => setActiveTab('academia')}>
          <GraduationCap size={14} className="shrink-0" />
          <span>ACADEMIA</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('non_academia')}
          onClick={() => setActiveTab('non_academia')}
        >
          <BookOpen size={14} className="shrink-0" />
          <span>NON-ACADEMIA</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('digital_presence')}
          onClick={() => setActiveTab('digital_presence')}
        >
          <Link2 size={14} className="shrink-0" />
          <span>DIGITAL PRESENCE</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('test_scores')}
          onClick={() => setActiveTab('test_scores')}
        >
          <ClipboardList size={14} className="shrink-0" />
          <span>TEST SCORES</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('work_projects')}
          onClick={() => setActiveTab('work_projects')}
        >
          <Briefcase size={14} className="shrink-0" />
          <span>PROFESSIONAL</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('projects_research')}
          onClick={() => setActiveTab('projects_research')}
        >
          <FlaskConical size={14} className="shrink-0" />
          <span>PROJECTS & RESEARCH</span>
        </button>
        <button
          type="button"
          className={tabButtonClass('university_shortlist')}
          onClick={() => setActiveTab('university_shortlist')}
        >
          <School size={14} className="shrink-0" />
          <span>SHORTLIST</span>
        </button>
      </div>

      {activeTab === 'profile_pulse' ? (
        <ProfilePulseTab
          bookingId={booking.id}
          statusCategory={booking.status_category}
          onNavigateTab={setActiveTab}
        />
      ) : activeTab === 'aspirations' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <MyAspirationsTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'academia' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <CandidateEducationsTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'non_academia' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <NonAcademicActivitiesTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'digital_presence' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <DigitalPresenceTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'test_scores' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <CandidateTestScoresTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'work_projects' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <WorkProjectsTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'projects_research' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <ResearchProjectsTab bookingId={booking.id} compact />
        </div>
      ) : activeTab === 'university_shortlist' ? (
        <div className="flex flex-1 min-h-0 flex-col px-4 py-4">
          <UniversityShortlistTab bookingId={booking.id} compact />
        </div>
      ) : isFormTab(activeTab) ? (
        loading ? (
          <div className="flex flex-1 items-center justify-center text-text-muted">
            <Loader2 size={20} className="animate-spin mr-2" />
            <span className="text-sm">Loading profile…</span>
          </div>
        ) : (
        <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col">
          <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-4 py-4 space-y-4">
            {error ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}
            {success ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                {success}
              </div>
            ) : null}

            {activeTab === 'profile' ? (
            <section className={sectionClass}>
              <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
                Personal Profile
              </h3>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <RequiredLabel htmlFor="profile-first-name">First Name</RequiredLabel>
                  <input
                    id="profile-first-name"
                    className={fieldClass(Boolean(fieldErrors.first_name))}
                    value={form.first_name}
                    onChange={e => updateForm({ first_name: e.target.value })}
                    maxLength={PROFILE_FIELD_LIMITS.name}
                    required
                  />
                  {fieldErrors.first_name ? (
                    <p className={fieldErrorClass}>{fieldErrors.first_name}</p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass}>Middle Name</label>
                  <input
                    className={inputClass}
                    value={form.middle_name}
                    onChange={e => updateForm({ middle_name: e.target.value })}
                    maxLength={PROFILE_FIELD_LIMITS.name}
                  />
                </div>
                <div>
                  <RequiredLabel htmlFor="profile-last-name">Last Name</RequiredLabel>
                  <input
                    id="profile-last-name"
                    className={fieldClass(Boolean(fieldErrors.last_name))}
                    value={form.last_name}
                    onChange={e => updateForm({ last_name: e.target.value })}
                    maxLength={PROFILE_FIELD_LIMITS.name}
                    required
                  />
                  {fieldErrors.last_name ? (
                    <p className={fieldErrorClass}>{fieldErrors.last_name}</p>
                  ) : null}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <RequiredLabel htmlFor="profile-dob">Date of Birth</RequiredLabel>
                  <DatePicker
                    id="profile-dob"
                    selected={dobDate}
                    openToDate={dobDate ?? undefined}
                    onChange={(date: Date | null) =>
                      updateForm({ date_of_birth: formatLocalIsoDate(date) })
                    }
                    dateFormat="dd MMM yyyy"
                    placeholderText="Select date of birth"
                    className={fieldClass(Boolean(fieldErrors.date_of_birth))}
                    wrapperClassName="w-full"
                    calendarClassName="nexus-roster-datepicker"
                    {...nexusDatePickerPortalProps}
                    showYearDropdown
                    scrollableYearDropdown
                    yearDropdownItemNumber={80}
                    maxDate={new Date()}
                    autoComplete="off"
                  />
                  {fieldErrors.date_of_birth ? (
                    <p className={fieldErrorClass}>{fieldErrors.date_of_birth}</p>
                  ) : null}
                </div>
                <div>
                  <RequiredLabel>Gender</RequiredLabel>
                  <div className={radioBoxClass(Boolean(fieldErrors.gender))}>
                    {(
                      [
                        { value: 'MALE', label: 'Male' },
                        { value: 'FEMALE', label: 'Female' },
                      ] as const
                    ).map(option => (
                      <label key={option.value} className={radioOptionClass}>
                        <input
                          type="radio"
                          name="profile-gender"
                          value={option.value}
                          checked={form.gender === option.value}
                          onChange={() => updateForm({ gender: option.value })}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                  {fieldErrors.gender ? <p className={fieldErrorClass}>{fieldErrors.gender}</p> : null}
                </div>
                <div>
                  <RequiredLabel>Status</RequiredLabel>
                  <div className={radioBoxClass(Boolean(fieldErrors.marital_status))}>
                    {(
                      [
                        { value: 'SINGLE', label: 'Single' },
                        { value: 'MARRIED', label: 'Married' },
                      ] as const
                    ).map(option => (
                      <label key={option.value} className={radioOptionClass}>
                        <input
                          type="radio"
                          name="profile-marital-status"
                          value={option.value}
                          checked={form.marital_status === option.value}
                          onChange={() => updateForm({ marital_status: option.value })}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                  {fieldErrors.marital_status ? (
                    <p className={fieldErrorClass}>{fieldErrors.marital_status}</p>
                  ) : null}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,2fr)_minmax(0,7.5rem)_minmax(0,1fr)_minmax(0,7.5rem)_minmax(0,1fr)] gap-2">
                <div>
                  <RequiredLabel htmlFor="profile-email">Email ID</RequiredLabel>
                  <input
                    id="profile-email"
                    type="email"
                    className={fieldClass(Boolean(fieldErrors.email))}
                    value={form.email}
                    onChange={e => updateForm({ email: e.target.value })}
                    maxLength={PROFILE_FIELD_LIMITS.email}
                    required
                  />
                  {fieldErrors.email ? <p className={fieldErrorClass}>{fieldErrors.email}</p> : null}
                </div>
                <div>
                  <RequiredLabel htmlFor="profile-phone-country">Country Code</RequiredLabel>
                  <select
                    id="profile-phone-country"
                    className={phoneCountrySelectClass(Boolean(fieldErrors.phone_country_iso2))}
                    value={form.phone_country_iso2}
                    onChange={e => updateForm({ phone_country_iso2: e.target.value })}
                    required
                  >
                    <option value="">Select</option>
                    {countriesByCode.map(country => (
                      <option key={country.iso2} value={country.iso2}>
                        {formatPhoneCountryLabel(country)}
                      </option>
                    ))}
                  </select>
                  {fieldErrors.phone_country_iso2 ? (
                    <p className={fieldErrorClass}>{fieldErrors.phone_country_iso2}</p>
                  ) : null}
                </div>
                <div>
                  <RequiredLabel htmlFor="profile-phone-local">Phone (Primary)</RequiredLabel>
                  <input
                    id="profile-phone-local"
                    className={fieldClass(Boolean(fieldErrors.phone_local))}
                    type="tel"
                    inputMode="text"
                    autoCapitalize="characters"
                    spellCheck={false}
                    value={form.phone_local}
                    onChange={e => updateForm({ phone_local: sanitizePhoneLocalDraft(e.target.value) })}
                    maxLength={PHONE_LOCAL_DRAFT_MAX_LENGTH}
                    placeholder={PHONE_LOCAL_PLACEHOLDER}
                    required
                  />
                  {fieldErrors.phone_local ? (
                    <p className={fieldErrorClass}>{fieldErrors.phone_local}</p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass}>Country Code (Secondary)</label>
                  <select
                    className={phoneCountrySelectOptionalClass}
                    value={form.phone_country_iso2_secondary}
                    onChange={e => updateForm({ phone_country_iso2_secondary: e.target.value })}
                  >
                    <option value="">Select</option>
                    {countriesByCode.map(country => (
                      <option key={`sec-${country.iso2}`} value={country.iso2}>
                        {formatPhoneCountryLabel(country)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelClass}>Phone (Secondary)</label>
                  <input
                    className={inputClass}
                    type="tel"
                    inputMode="text"
                    autoCapitalize="characters"
                    spellCheck={false}
                    value={form.phone_local_secondary}
                    onChange={e =>
                      updateForm({ phone_local_secondary: sanitizePhoneLocalDraft(e.target.value) })
                    }
                    maxLength={PHONE_LOCAL_DRAFT_MAX_LENGTH}
                    placeholder={PHONE_LOCAL_PLACEHOLDER}
                  />
                </div>
              </div>

              <div className="border-t border-border-subtle pt-3 space-y-3">
                <h4 className="text-sm font-bold uppercase tracking-wide text-text-main">
                  Location Details
                </h4>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <RequiredLabel htmlFor="profile-address1">Address 1</RequiredLabel>
                    <input
                      id="profile-address1"
                      className={fieldClass(Boolean(fieldErrors.address1))}
                      value={form.address1}
                      onChange={e => updateForm({ address1: e.target.value })}
                      maxLength={PROFILE_FIELD_LIMITS.address}
                      required
                    />
                    {fieldErrors.address1 ? (
                      <p className={fieldErrorClass}>{fieldErrors.address1}</p>
                    ) : null}
                  </div>
                  <div>
                    <RequiredLabel htmlFor="profile-address2">Address 2</RequiredLabel>
                    <input
                      id="profile-address2"
                      className={fieldClass(Boolean(fieldErrors.address2))}
                      value={form.address2}
                      onChange={e => updateForm({ address2: e.target.value })}
                      maxLength={PROFILE_FIELD_LIMITS.address}
                      required
                    />
                    {fieldErrors.address2 ? (
                      <p className={fieldErrorClass}>{fieldErrors.address2}</p>
                    ) : null}
                  </div>
                  <div>
                    <label className={labelClass}>Address 3</label>
                    <input
                      className={inputClass}
                      value={form.address3}
                      onChange={e => updateForm({ address3: e.target.value })}
                      maxLength={PROFILE_FIELD_LIMITS.address}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  <div>
                    <RequiredLabel htmlFor="profile-city">City</RequiredLabel>
                    <input
                      id="profile-city"
                      className={fieldClass(Boolean(fieldErrors.city))}
                      value={form.city}
                      onChange={e => updateForm({ city: e.target.value })}
                      maxLength={PROFILE_FIELD_LIMITS.city}
                      required
                    />
                    {fieldErrors.city ? <p className={fieldErrorClass}>{fieldErrors.city}</p> : null}
                  </div>
                  <div>
                    <RequiredLabel htmlFor="profile-state">State</RequiredLabel>
                    <input
                      id="profile-state"
                      className={fieldClass(Boolean(fieldErrors.state))}
                      value={form.state}
                      onChange={e => updateForm({ state: e.target.value })}
                      maxLength={PROFILE_FIELD_LIMITS.state}
                      required
                    />
                    {fieldErrors.state ? (
                      <p className={fieldErrorClass}>{fieldErrors.state}</p>
                    ) : null}
                  </div>
                  <div>
                    <RequiredLabel htmlFor="profile-country">Country</RequiredLabel>
                    <select
                      id="profile-country"
                      className={fieldClass(Boolean(fieldErrors.country_iso2))}
                      value={form.country_iso2}
                      onChange={e => updateForm({ country_iso2: e.target.value })}
                      required
                    >
                      <option value="">Select country</option>
                      {countriesByName.map(country => (
                        <option key={`loc-${country.iso2}`} value={country.iso2}>
                          {country.name}
                        </option>
                      ))}
                    </select>
                    {fieldErrors.country_iso2 ? (
                      <p className={fieldErrorClass}>{fieldErrors.country_iso2}</p>
                    ) : null}
                  </div>
                  <div>
                    <RequiredLabel htmlFor="profile-zipcode">Zipcode</RequiredLabel>
                    <input
                      id="profile-zipcode"
                      className={fieldClass(Boolean(fieldErrors.zipcode))}
                      value={form.zipcode}
                      onChange={e => updateForm({ zipcode: e.target.value.slice(0, PROFILE_FIELD_LIMITS.zipcode) })}
                      maxLength={PROFILE_FIELD_LIMITS.zipcode}
                      required
                    />
                    {fieldErrors.zipcode ? (
                      <p className={fieldErrorClass}>{fieldErrors.zipcode}</p>
                    ) : null}
                  </div>
                </div>
              </div>
            </section>
            ) : null}

          </div>

          <div className="shrink-0 relative z-0 flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-bg/70 px-4 py-3">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="rounded-md border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-card disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              Submit
            </button>
          </div>
        </form>
        )
      ) : null}
    </>
  );

  if (isEmbedded) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-card">{profileWorkspace}</div>
    );
  }

  return (
    <aside className="flex h-full w-full min-h-0 min-w-0 flex-col overflow-hidden bg-card">
      <div className="shrink-0 flex items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg/60 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold uppercase tracking-wide text-text-muted">View Profile</p>
          <h2 className="text-base font-bold text-text-main truncate flex items-center gap-2 mt-1">
            <User size={16} className="text-sky-700 shrink-0" />
            {profileFullName || booking.candidate_name}
          </h2>
          {dateLabel && timeLabel ? (
            <p className="text-sm text-text-muted mt-0.5">
              {dateLabel} · {timeLabel}
            </p>
          ) : null}
          {savedAt && isFormTab(activeTab) ? (
            <p className="text-sm text-emerald-700 mt-1">
              Last saved {new Date(savedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
        <div className="flex items-start gap-3 shrink-0">
          {profileStatusLabel ? (
            <p className="text-xl font-bold text-text-main leading-tight text-right max-w-[14rem]">
              {profileStatusLabel}
            </p>
          ) : null}
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border-subtle p-1.5 text-text-muted hover:bg-surface-bg hover:text-text-main shrink-0"
              aria-label="Close profile panel"
            >
              <X size={15} />
            </button>
          ) : null}
        </div>
      </div>
      {profileWorkspace}
    </aside>
  );
};

export default CandidateProfilePanel;
