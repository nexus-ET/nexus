import { phoneLocalToDigits } from '../utils/phoneCountry';

export type GenderOption = 'MALE' | 'FEMALE';
export type MaritalStatusOption = 'SINGLE' | 'MARRIED';

export interface CandidateProfileLocation {
  address1?: string | null;
  address2?: string | null;
  address3?: string | null;
  city?: string | null;
  state?: string | null;
  country_iso2?: string | null;
  country?: string | null;
  zipcode?: string | null;
}

export interface CandidateProfileEducation {
  degree_code?: string | null;
  degree?: string | null;
  degree_other?: string | null;
  major?: string | null;
  university?: string | null;
  graduation_year?: number | null;
  gpa_cgpa_code?: string | null;
  gpa_cgpa?: string | null;
  gpa_cgpa_other?: string | null;
}

export interface CandidateProfileStudyInterest {
  target_destination_iso2?: string | null;
  target_destination?: string | null;
  target_program_code?: string | null;
  target_program?: string | null;
  target_course_code?: string | null;
  target_course?: string | null;
}

export interface CandidateProfileAptitude {
  english_test_scores?: string | null;
  gre_score?: string | null;
  gmat_score?: string | null;
}

export interface CandidateProfile {
  lead_id?: number | null;
  first_name?: string | null;
  middle_name?: string | null;
  last_name?: string | null;
  date_of_birth?: string | null;
  gender?: GenderOption | null;
  marital_status?: MaritalStatusOption | null;
  email?: string | null;
  phone_country_iso2?: string | null;
  phone_local?: string | null;
  phone_number?: string | null;
  phone_country_iso2_secondary?: string | null;
  phone_local_secondary?: string | null;
  phone_number_secondary?: string | null;
  location: CandidateProfileLocation;
  education: CandidateProfileEducation;
  study_interest: CandidateProfileStudyInterest;
  aptitude_scores?: CandidateProfileAptitude;
  students_master_id?: number | null;
  saved_at?: string | null;
}

export type StudentMasterSaveScope = 'profile' | 'full';

export interface StudentMasterFormState {
  first_name: string;
  middle_name: string;
  last_name: string;
  date_of_birth: string;
  gender: GenderOption | '';
  marital_status: MaritalStatusOption | '';
  email: string;
  phone_country_iso2: string;
  phone_local: string;
  phone_country_iso2_secondary: string;
  phone_local_secondary: string;
  address1: string;
  address2: string;
  address3: string;
  city: string;
  state: string;
  country_iso2: string;
  zipcode: string;
}

export interface BookingCandidateProfileResponse {
  booking_id: number;
  candidate_name: string;
  profile: CandidateProfile;
}

export interface StudentMasterSaveResponse {
  booking_id: number;
  lead_id?: number | null;
  students_master_id: number;
  saved_at: string;
  profile: CandidateProfile;
}

export type MyBookingProfileSource = 'profile_api' | 'activity_api' | 'booking_row';

export const PROFILE_FIELD_LIMITS = {
  name: 50,
  email: 50,
  address: 50,
  city: 50,
  state: 50,
  zipcode: 7,
} as const;

export const PROFILE_MAJOR_OPTIONS = [
  { value: 'Computer Science', label: 'Computer Science' },
  { value: 'Business Administration', label: 'Business Administration' },
  { value: 'Engineering', label: 'Engineering' },
  { value: 'Medicine', label: 'Medicine' },
  { value: 'Other', label: 'Other' },
] as const;

/** Normalize API/stored DOB values to YYYY-MM-DD for form controls. */
export function normalizeDateOfBirth(value: string | null | undefined): string {
  if (!value) return '';
  const trimmed = value.trim();
  const isoPrefix = trimmed.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoPrefix) return isoPrefix[1];
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return '';
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function parseLocalIsoDate(value: string | null | undefined): Date | null {
  const normalized = normalizeDateOfBirth(value);
  if (!normalized) return null;
  const [year, month, day] = normalized.split('-').map(Number);
  if (!year || !month || !day) return null;
  const date = new Date(year, month - 1, day);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatLocalIsoDate(value: Date | null): string {
  if (!value) return '';
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export interface StudentMasterValidationContext {}

export function validateStudentMasterForm(
  form: StudentMasterFormState,
  _ctx: StudentMasterValidationContext = {},
  scope: StudentMasterSaveScope = 'profile'
): Record<string, string> {
  const errors: Record<string, string> = {};

  const requireText = (key: keyof StudentMasterFormState, label: string) => {
    if (!(form[key] ?? '').toString().trim()) {
      errors[key] = `${label} is required.`;
    }
  };

  if (scope === 'profile' || scope === 'full') {
    requireText('first_name', 'First name');
    requireText('last_name', 'Last name');
    requireText('gender', 'Gender');
    requireText('marital_status', 'Status');
    requireText('date_of_birth', 'Date of birth');
    requireText('email', 'Email');
    requireText('phone_country_iso2', 'Primary phone country code');
    requireText('phone_local', 'Primary phone number');
    requireText('address1', 'Address 1');
    requireText('address2', 'Address 2');
    requireText('city', 'City');
    requireText('state', 'State');
    requireText('country_iso2', 'Country');
    requireText('zipcode', 'Zipcode');

    const phoneDigits = phoneLocalToDigits(form.phone_local);
    if (form.phone_local.trim() && phoneDigits.length !== 10) {
      errors.phone_local = 'Phone number must be exactly 10 digits (letters map to the keypad).';
    }

    const checkMaxLength = (
      key: keyof StudentMasterFormState,
      label: string,
      max: number
    ) => {
      const value = (form[key] ?? '').toString();
      if (value.length > max) {
        errors[key] = `${label} must be ${max} characters or fewer.`;
      }
    };

    checkMaxLength('first_name', 'First name', PROFILE_FIELD_LIMITS.name);
    checkMaxLength('middle_name', 'Middle name', PROFILE_FIELD_LIMITS.name);
    checkMaxLength('last_name', 'Last name', PROFILE_FIELD_LIMITS.name);
    checkMaxLength('email', 'Email', PROFILE_FIELD_LIMITS.email);
    checkMaxLength('address1', 'Address 1', PROFILE_FIELD_LIMITS.address);
    checkMaxLength('address2', 'Address 2', PROFILE_FIELD_LIMITS.address);
    checkMaxLength('address3', 'Address 3', PROFILE_FIELD_LIMITS.address);
    checkMaxLength('city', 'City', PROFILE_FIELD_LIMITS.city);
    checkMaxLength('state', 'State', PROFILE_FIELD_LIMITS.state);
    checkMaxLength('zipcode', 'Zipcode', PROFILE_FIELD_LIMITS.zipcode);
  }

  return errors;
}

export function profileToForm(profile: CandidateProfile): StudentMasterFormState {
  const location = profile.location ?? {};

  return {
    first_name: profile.first_name || '',
    middle_name: profile.middle_name || '',
    last_name: profile.last_name || '',
    date_of_birth: normalizeDateOfBirth(profile.date_of_birth),
    gender: profile.gender === 'MALE' || profile.gender === 'FEMALE' ? profile.gender : '',
    marital_status:
      profile.marital_status === 'SINGLE' || profile.marital_status === 'MARRIED'
        ? profile.marital_status
        : '',
    email: profile.email || '',
    phone_country_iso2: profile.phone_country_iso2 || '',
    phone_local: profile.phone_local || '',
    phone_country_iso2_secondary: profile.phone_country_iso2_secondary || '',
    phone_local_secondary: profile.phone_local_secondary || '',
    address1: location.address1 || '',
    address2: location.address2 || '',
    address3: location.address3 || '',
    city: location.city || '',
    state: location.state || '',
    country_iso2: location.country_iso2 || '',
    zipcode: location.zipcode || '',
  };
}

export function formToSavePayload(
  form: StudentMasterFormState,
  saveScope: StudentMasterSaveScope = 'profile'
) {
  return {
    save_scope: saveScope,
    first_name: form.first_name.trim() || null,
    middle_name: form.middle_name.trim() || null,
    last_name: form.last_name.trim() || null,
    date_of_birth: normalizeDateOfBirth(form.date_of_birth) || null,
    gender: form.gender || null,
    marital_status: form.marital_status || null,
    email: form.email.trim() || null,
    phone_country_iso2: form.phone_country_iso2 || null,
    phone_local: phoneLocalToDigits(form.phone_local) || null,
    phone_country_iso2_secondary: form.phone_country_iso2_secondary || null,
    phone_local_secondary: phoneLocalToDigits(form.phone_local_secondary) || null,
    location: {
      address1: form.address1.trim() || null,
      address2: form.address2.trim() || null,
      address3: form.address3.trim() || null,
      city: form.city.trim() || null,
      state: form.state.trim() || null,
      country_iso2: form.country_iso2 || null,
      zipcode: form.zipcode.trim() || null,
    },
  };
}
