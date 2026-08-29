import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { CandidateProfile } from '../types/candidateProfile';
import type { CandidateEducationsResponse } from '../types/candidateEducation';
import type { NonAcademicActivitiesResponse } from '../types/nonAcademicActivity';
import type { DigitalPresenceLinksResponse } from '../types/digitalPresenceLink';
import type { CandidateTestScoresResponse } from '../types/candidateTestScores';
import type { WorkExperiencesResponse } from '../types/workExperience';
import type { ResearchProjectsResponse } from '../types/researchProject';
import { buildProfilePulseSnapshot, type ProfilePulseSnapshot } from '../utils/profilePulse';

interface BookingProfileResponse {
  profile: CandidateProfile;
}

export function useProfilePulse(
  bookingId: number | null | undefined,
  statusCategory?: string | null,
  enabled = true
) {
  return useQuery<ProfilePulseSnapshot>({
    queryKey: ['bookings', 'profile-pulse', bookingId, statusCategory],
    enabled: enabled && bookingId != null,
    staleTime: 30_000,
    queryFn: async () => {
      const id = bookingId as number;
      const [
        profileResponse,
        aspirations,
        registration,
        educations,
        activities,
        digitalLinks,
        testScores,
        workExperiences,
        researchProjects,
      ] = await Promise.all([
        apiFetch(`bookings/mine/${id}/profile`).catch(() => null),
        apiFetch(`bookings/mine/${id}/aspirations`).catch(() => null),
        apiFetch(`bookings/mine/${id}/registration`).catch(() => null),
        apiFetch(`bookings/mine/${id}/educations`).catch(() => null),
        apiFetch(`bookings/mine/${id}/non-academic-activities`).catch(() => null),
        apiFetch(`bookings/mine/${id}/digital-presence-links`).catch(() => null),
        apiFetch(`bookings/mine/${id}/test-scores`).catch(() => null),
        apiFetch(`bookings/mine/${id}/work-experiences`).catch(() => null),
        apiFetch(`bookings/mine/${id}/research-projects`).catch(() => null),
      ]);

      return buildProfilePulseSnapshot({
        profile: (profileResponse as BookingProfileResponse | null)?.profile,
        aspirations,
        registration,
        educations: (educations as CandidateEducationsResponse | null)?.educations,
        activities: (activities as NonAcademicActivitiesResponse | null)?.activities,
        digitalLinks: (digitalLinks as DigitalPresenceLinksResponse | null)?.links,
        testScores: testScores as CandidateTestScoresResponse | null,
        workExperiences: (workExperiences as WorkExperiencesResponse | null)?.experiences,
        researchProjects: (researchProjects as ResearchProjectsResponse | null)?.projects,
        statusCategory,
      });
    },
  });
}
