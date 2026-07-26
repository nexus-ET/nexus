import type { CandidateProfile } from '../types/candidateProfile';
import { profileToForm, validateStudentMasterForm } from '../types/candidateProfile';
import {
  aspirationsToForm,
  validateAspirationsForm,
  WHY_STUDY_ABROAD_OPTIONS,
  type StudentAspirationsFormState,
} from '../types/studentAspirations';
import {
  educationToForm,
  validateCandidateEducationForm,
  type CandidateEducationRecord,
} from '../types/candidateEducation';
import {
  activityToForm,
  validateNonAcademicActivityForm,
  type NonAcademicActivityRecord,
} from '../types/nonAcademicActivity';
import type { DigitalPresenceLinkRecord } from '../types/digitalPresenceLink';
import type { CandidateTestScoresResponse } from '../types/candidateTestScores';
import type { WorkExperienceRecord } from '../types/workExperience';
import {
  projectToForm,
  validateResearchProjectForm,
  type ResearchProjectRecord,
} from '../types/researchProject';
import type { ProfilePanelTab } from '../types/profilePanel';

export type ProfileSectionStatus = 'completed' | 'in_progress' | 'action_required';

export type ProfilePulseSection = {
  key: ProfilePanelTab;
  label: string;
  status: ProfileSectionStatus;
  completionPercent: number;
  gist: string;
  actionHint?: string;
};

export type TimelineMilestoneId =
  | 'profile_setup'
  | 'university_shortlisting'
  | 'application_drafting'
  | 'submission_phase';

export type TimelineMilestone = {
  id: TimelineMilestoneId;
  label: string;
  state: 'complete' | 'current' | 'upcoming';
};

export type ProfilePulseSnapshot = {
  sections: ProfilePulseSection[];
  overallCompletionPercent: number;
  visionStatement: string;
  timeline: TimelineMilestone[];
  currentMilestoneId: TimelineMilestoneId;
};

const SECTION_ORDER: Array<{ key: ProfilePanelTab; label: string }> = [
  { key: 'aspirations', label: 'Aspirations' },
  { key: 'profile', label: 'Personal Profile' },
  { key: 'academia', label: 'Academia' },
  { key: 'non_academia', label: 'Non-Academia' },
  { key: 'digital_presence', label: 'Digital Presence' },
  { key: 'test_scores', label: 'Test Scores' },
  { key: 'work_projects', label: 'Professional' },
  { key: 'projects_research', label: 'Projects & Research' },
];

function sectionResult(
  status: ProfileSectionStatus,
  gist: string,
  actionHint?: string
): Pick<ProfilePulseSection, 'status' | 'completionPercent' | 'gist' | 'actionHint'> {
  const completionPercent =
    status === 'completed' ? 100 : status === 'in_progress' ? 55 : 0;
  return { status, completionPercent, gist, actionHint };
}

function hasAnyValue(values: Array<string | number | boolean | null | undefined>): boolean {
  return values.some(value => {
    if (typeof value === 'string') return value.trim().length > 0;
    if (typeof value === 'number') return Number.isFinite(value);
    return Boolean(value);
  });
}

function evaluateAspirations(raw: unknown): Pick<ProfilePulseSection, 'status' | 'completionPercent' | 'gist' | 'actionHint'> {
  const aspirations = (raw as { aspirations?: Record<string, unknown> })?.aspirations ?? raw;
  const form = aspirationsToForm(aspirations as Parameters<typeof aspirationsToForm>[0]);
  const errors = validateAspirationsForm(form);
  const touched = hasAnyValue([
    form.why_study_abroad.length,
    form.study_countries_iso2.length,
    form.programs.length,
    form.intake_years.length,
    form.funding_sources.length,
  ]);

  const countryLabels = form.study_countries_iso2.slice(0, 2).join(', ');
  const programLabels = form.programs.slice(0, 2).join(', ');
  const gist =
    countryLabels || programLabels
      ? [countryLabels && `Target: ${countryLabels}`, programLabels && `Programs: ${programLabels}`]
          .filter(Boolean)
          .join(' · ')
      : 'Study goals and preferences not captured yet.';

  if (errors.length === 0) {
    return sectionResult('completed', gist);
  }
  if (touched) {
    return sectionResult('in_progress', gist, 'Finish required aspiration fields to strengthen your roadmap.');
  }
  return sectionResult('action_required', gist, 'Start with why you want to study abroad and where.');
}

function evaluatePersonalProfile(profile: CandidateProfile | null | undefined) {
  if (!profile) {
    return sectionResult(
      'action_required',
      'Identity and contact details are missing.',
      'Add legal name, date of birth, and contact information.'
    );
  }

  const form = profileToForm(profile);
  const errors = validateStudentMasterForm(form);
  const gistParts = [form.city, form.country_iso2].filter(Boolean);
  const gist =
    gistParts.length > 0
      ? `Based in ${gistParts.join(', ')}`
      : form.email
        ? `Contact: ${form.email}`
        : 'Personal details incomplete.';

  if (Object.keys(errors).length === 0) {
    return sectionResult('completed', gist);
  }

  const touched = hasAnyValue([
    form.first_name,
    form.last_name,
    form.email,
    form.phone_local,
    form.address1,
    form.city,
  ]);

  if (touched) {
    return sectionResult('in_progress', gist, 'Complete all mandatory personal profile fields.');
  }
  return sectionResult('action_required', gist, 'Add your full legal name and contact details.');
}

function evaluateAcademia(educations: CandidateEducationRecord[]) {
  if (!educations.length) {
    return sectionResult(
      'action_required',
      'No education history added.',
      'Add at least one school or university record.'
    );
  }

  const validCount = educations.filter(record => {
    const form = educationToForm(record);
    return Object.keys(validateCandidateEducationForm(form)).length === 0;
  }).length;

  const headline = educations[0];
  const gist = headline.university_name
    ? `${headline.degree_label || 'Degree'} at ${headline.university_name}`
    : `${educations.length} education record(s) in progress`;

  if (validCount > 0 && validCount === educations.length) {
    return sectionResult('completed', gist);
  }
  if (validCount > 0 || educations.length > 0) {
    return sectionResult('in_progress', gist, 'Complete required fields for each education entry.');
  }
  return sectionResult('action_required', gist, 'Add your latest degree and graduation details.');
}

function evaluateNonAcademia(activities: NonAcademicActivityRecord[]) {
  if (!activities.length) {
    return sectionResult(
      'action_required',
      'No extracurricular activities listed.',
      'Add leadership, volunteering, or club activities.'
    );
  }

  const validCount = activities.filter(record => {
    const form = activityToForm(record);
    return Object.keys(validateNonAcademicActivityForm(form)).length === 0;
  }).length;

  const gist = activities[0].activity_name
    ? `${activities[0].activity_name}${activities.length > 1 ? ` +${activities.length - 1} more` : ''}`
    : `${activities.length} activity record(s) started`;

  if (validCount === activities.length) {
    return sectionResult('completed', gist);
  }
  if (activities.length > 0) {
    return sectionResult('in_progress', gist, 'Complete activity details and timelines.');
  }
  return sectionResult('action_required', gist, 'Capture your non-academic strengths.');
}

function evaluateDigitalPresence(links: DigitalPresenceLinkRecord[]) {
  if (!links.length) {
    return sectionResult(
      'action_required',
      'No portfolio or social links added.',
      'Add GitHub, LinkedIn, or portfolio links admissions teams expect.'
    );
  }

  const gist = links
    .slice(0, 2)
    .map(link => link.platform_name)
    .join(', ');

  return sectionResult('completed', `${links.length} link(s): ${gist}`);
}

function evaluateTestScores(data: CandidateTestScoresResponse | null | undefined) {
  const scores = data?.scores ?? [];
  if (!scores.length) {
    return sectionResult(
      'action_required',
      'Test scores not recorded.',
      'Add English proficiency and aptitude test results.'
    );
  }

  const tests = [...new Set(scores.map(item => item.test_name))];
  const gist = `${tests.length} test(s): ${tests.slice(0, 2).join(', ')}`;
  const hasScores = scores.some(
    item => item.overall_score != null || (item.score != null && item.section_name)
  );

  if (hasScores && tests.length > 0) {
    return sectionResult('completed', gist);
  }
  return sectionResult('in_progress', gist, 'Record overall and section scores for each test.');
}

function evaluateProfessional(experiences: WorkExperienceRecord[]) {
  if (!experiences.length) {
    return sectionResult(
      'action_required',
      'No work experience added.',
      'Add internships or full-time roles to strengthen your profile.'
    );
  }

  const complete = experiences.filter(
    item => (item.company_name || '').trim() && (item.job_title || '').trim()
  ).length;

  const gist = experiences[0].job_title
    ? `${experiences[0].job_title} at ${experiences[0].company_name || 'Company'}`
    : `${experiences.length} experience record(s)`;

  if (complete === experiences.length && complete > 0) {
    return sectionResult('completed', gist);
  }
  if (experiences.length > 0) {
    return sectionResult('in_progress', gist, 'Add role details and project highlights.');
  }
  return sectionResult('action_required', gist, 'Document your professional background.');
}

function evaluateResearch(projects: ResearchProjectRecord[]) {
  if (!projects.length) {
    return sectionResult(
      'action_required',
      'No research or capstone projects listed.',
      'Add thesis, publications, or major projects.'
    );
  }

  const validCount = projects.filter(record => {
    const form = projectToForm(record);
    return Object.keys(validateResearchProjectForm(form)).length === 0;
  }).length;

  const gist = projects[0].project_title
    ? projects[0].project_title
    : `${projects.length} project record(s) in progress`;

  if (validCount === projects.length) {
    return sectionResult('completed', gist);
  }
  if (projects.length > 0) {
    return sectionResult('in_progress', gist, 'Complete project descriptions and outcomes.');
  }
  return sectionResult('action_required', gist, 'Showcase research or capstone work.');
}

export function buildVisionStatement(form: StudentAspirationsFormState): string {
  if (form.why_study_abroad_other.trim()) {
    return form.why_study_abroad_other.trim();
  }

  const reasons = form.why_study_abroad
    .filter(value => value !== 'OTHER')
    .map(value => WHY_STUDY_ABROAD_OPTIONS.find(option => option.value === value)?.title)
    .filter(Boolean);

  if (reasons.length) {
    const programs = form.programs.slice(0, 2).join(', ');
    const countries = form.study_countries_iso2.slice(0, 2).join(', ');
    return `I am pursuing study abroad to ${reasons.join(', ').toLowerCase()}${countries ? ` in ${countries}` : ''}${programs ? `, focusing on ${programs}` : ''}.`;
  }

  return 'Complete your aspirations to craft a personal vision statement that guides your university journey.';
}

export function resolveTimelineMilestone(
  overallCompletionPercent: number,
  statusCategory?: string | null
): TimelineMilestoneId {
  const category = (statusCategory || '').trim();

  if (overallCompletionPercent < 75) {
    return 'profile_setup';
  }
  if (category === 'Counselling' || category === 'Prospect') {
    return 'university_shortlisting';
  }
  if (category === 'Documentation' || category === 'Admission') {
    return 'application_drafting';
  }
  if (['Visa', 'Pre-Departure', 'Arrival'].includes(category)) {
    return 'submission_phase';
  }
  if (overallCompletionPercent >= 100) {
    return 'university_shortlisting';
  }
  return 'profile_setup';
}

export function buildTimeline(currentId: TimelineMilestoneId): TimelineMilestone[] {
  const order: TimelineMilestoneId[] = [
    'profile_setup',
    'university_shortlisting',
    'application_drafting',
    'submission_phase',
  ];
  const labels: Record<TimelineMilestoneId, string> = {
    profile_setup: 'Profile Setup',
    university_shortlisting: 'University Shortlisting',
    application_drafting: 'Application Drafting',
    submission_phase: 'Submission Phase',
  };

  const currentIndex = order.indexOf(currentId);

  return order.map((id, index) => ({
    id,
    label: labels[id],
    state: index < currentIndex ? 'complete' : index === currentIndex ? 'current' : 'upcoming',
  }));
}

export function buildProfilePulseSnapshot(input: {
  profile?: CandidateProfile | null;
  aspirations?: unknown;
  educations?: CandidateEducationRecord[];
  activities?: NonAcademicActivityRecord[];
  digitalLinks?: DigitalPresenceLinkRecord[];
  testScores?: CandidateTestScoresResponse | null;
  workExperiences?: WorkExperienceRecord[];
  researchProjects?: ResearchProjectRecord[];
  statusCategory?: string | null;
}): ProfilePulseSnapshot {
  const aspirationsForm = aspirationsToForm(
    ((input.aspirations as { aspirations?: unknown })?.aspirations ??
      input.aspirations) as Parameters<typeof aspirationsToForm>[0]
  );

  const evaluators: Record<ProfilePanelTab, () => ReturnType<typeof sectionResult>> = {
    profile_pulse: () => sectionResult('action_required', ''),
    aspirations: () => evaluateAspirations(input.aspirations),
    profile: () => evaluatePersonalProfile(input.profile),
    academia: () => evaluateAcademia(input.educations ?? []),
    non_academia: () => evaluateNonAcademia(input.activities ?? []),
    digital_presence: () => evaluateDigitalPresence(input.digitalLinks ?? []),
    test_scores: () => evaluateTestScores(input.testScores),
    work_projects: () => evaluateProfessional(input.workExperiences ?? []),
    projects_research: () => evaluateResearch(input.researchProjects ?? []),
    university_shortlist: () =>
      sectionResult('action_required', 'Generate a soft university shortlist when ready.'),
  };

  const sections: ProfilePulseSection[] = SECTION_ORDER.map(section => {
    const result = evaluators[section.key]();
    return {
      key: section.key,
      label: section.label,
      ...result,
    };
  });

  const overallCompletionPercent = Math.round(
    sections.reduce((sum, section) => sum + section.completionPercent, 0) / sections.length
  );

  const currentMilestoneId = resolveTimelineMilestone(
    overallCompletionPercent,
    input.statusCategory
  );

  return {
    sections,
    overallCompletionPercent,
    visionStatement: buildVisionStatement(aspirationsForm),
    currentMilestoneId,
    timeline: buildTimeline(currentMilestoneId),
  };
}

export function formatProfileFullName(profile?: CandidateProfile | null): string {
  if (!profile) return '';
  const first = (profile.first_name || '').trim();
  const last = (profile.last_name || '').trim();
  if (!first || !last) return '';
  const middle = (profile.middle_name || '').trim();
  return [first, middle, last].filter(Boolean).join(' ');
}
