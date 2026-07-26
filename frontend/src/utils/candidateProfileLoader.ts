import type { CandidateProfile, MyBookingProfileSource } from '../types/candidateProfile';

export interface BookingRowForProfile {
  id: number;
  lead_id?: number | null;
  candidate_name: string;
  candidate_email?: string | null;
  candidate_phone?: string | null;
  current_location?: string | null;
  preferred_country?: string | null;
  course_interest?: string | null;
  status_definition_id?: number | null;
  status_stage_name?: string | null;
  status_category?: string | null;
  date_label?: string | null;
  time_label?: string | null;
  status?: string | null;
  session_status_label?: string | null;
  admin_id?: number | null;
  admin_name?: string | null;
  scheduled_time?: string | null;
}

function splitName(fullName: string): {
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
} {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return { first_name: null, middle_name: null, last_name: null };
  }
  if (parts.length === 1) {
    return { first_name: parts[0], middle_name: null, last_name: null };
  }
  if (parts.length === 2) {
    return { first_name: parts[0], middle_name: null, last_name: parts[1] };
  }
  return {
    first_name: parts[0],
    middle_name: parts.slice(1, -1).join(' '),
    last_name: parts[parts.length - 1],
  };
}

function locationFromCurrent(currentLocation?: string | null) {
  const parts = (currentLocation || '')
    .split(',')
    .map(part => part.trim())
    .filter(Boolean);
  return {
    city: parts[0] || null,
    state: parts[1] || null,
    country: parts[2] || parts[1] || null,
  };
}

export function buildProfileFromBooking(booking: BookingRowForProfile): CandidateProfile {
  const names = splitName(booking.candidate_name || '');
  const locationParts = locationFromCurrent(booking.current_location);

  return {
    lead_id: booking.lead_id ?? null,
    first_name: names.first_name,
    middle_name: names.middle_name,
    last_name: names.last_name,
    date_of_birth: null,
    email: booking.candidate_email || null,
    phone_country_iso2: null,
    phone_local: null,
    phone_number: booking.candidate_phone || null,
    phone_country_iso2_secondary: null,
    phone_local_secondary: null,
    phone_number_secondary: null,
    location: {
      address1: null,
      address2: null,
      address3: null,
      city: locationParts.city,
      state: locationParts.state,
      country_iso2: null,
      country: locationParts.country,
      zipcode: null,
    },
    education: {
      degree_code: null,
      degree: null,
      degree_other: null,
      major: null,
      university: null,
      graduation_year: null,
      gpa_cgpa_code: null,
      gpa_cgpa: null,
      gpa_cgpa_other: null,
    },
    study_interest: {
      target_destination_iso2: null,
      target_destination: booking.preferred_country || null,
      target_program_code: null,
      target_program: null,
      target_course_code: null,
      target_course: booking.course_interest || null,
    },
    aptitude_scores: {
      english_test_scores: null,
      gre_score: null,
      gmat_score: null,
    },
  };
}

export function mergeProfileWithBooking(
  profile: CandidateProfile,
  booking: BookingRowForProfile
): CandidateProfile {
  const fallback = buildProfileFromBooking(booking);
  return {
    ...fallback,
    ...profile,
    location: { ...fallback.location, ...(profile.location ?? {}) },
    education: { ...fallback.education, ...(profile.education ?? {}) },
    study_interest: { ...fallback.study_interest, ...(profile.study_interest ?? {}) },
    aptitude_scores: { ...(fallback.aptitude_scores ?? {}), ...(profile.aptitude_scores ?? {}) },
    first_name: profile.first_name || fallback.first_name,
    middle_name: profile.middle_name || fallback.middle_name,
    last_name: profile.last_name || fallback.last_name,
    email: profile.email || fallback.email,
    phone_number: profile.phone_number || fallback.phone_number,
  };
}

interface ActivityProfileResponse {
  booking?: { candidate_name?: string };
  candidate_profile?: CandidateProfile;
}

interface DirectProfileResponse {
  booking_id: number;
  candidate_name: string;
  profile: CandidateProfile;
}

export async function loadBookingCandidateProfile(
  booking: BookingRowForProfile,
  apiFetch: (endpoint: string) => Promise<unknown>
): Promise<{ profile: CandidateProfile; source: MyBookingProfileSource }> {
  const fallback = buildProfileFromBooking(booking);

  const loadDirect = async (): Promise<CandidateProfile | null> => {
    try {
      const response = (await apiFetch(
        `bookings/mine/${booking.id}/profile`
      )) as DirectProfileResponse;
      if (response?.profile) {
        return mergeProfileWithBooking(response.profile, booking);
      }
    } catch {
      /* try activity fallback */
    }
    return null;
  };

  const loadFromActivity = async (): Promise<CandidateProfile | null> => {
    try {
      const response = (await apiFetch(
        `bookings/mine/${booking.id}/activity`
      )) as ActivityProfileResponse;
      if (response?.candidate_profile) {
        return mergeProfileWithBooking(response.candidate_profile, booking);
      }
    } catch {
      /* use booking row fallback */
    }
    return null;
  };

  const direct = await loadDirect();
  if (direct) {
    return { profile: direct, source: 'profile_api' };
  }

  const fromActivity = await loadFromActivity();
  if (fromActivity) {
    return { profile: fromActivity, source: 'activity_api' };
  }

  return { profile: fallback, source: 'booking_row' };
}
