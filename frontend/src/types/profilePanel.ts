export type ProfilePanelTab =
  | 'profile_pulse'
  | 'aspirations'
  | 'profile'
  | 'academia'
  | 'non_academia'
  | 'digital_presence'
  | 'test_scores'
  | 'work_projects'
  | 'projects_research'
  | 'university_shortlist';

export const PROFILE_PANEL_TAB_LABELS: Record<ProfilePanelTab, string> = {
  profile_pulse: 'PROFILE PULSE',
  aspirations: 'ASPIRATIONS',
  profile: 'PERSONAL PROFILE',
  academia: 'ACADEMIA',
  non_academia: 'NON-ACADEMIA',
  digital_presence: 'DIGITAL PRESENCE',
  test_scores: 'TEST SCORES',
  work_projects: 'PROFESSIONAL',
  projects_research: 'PROJECTS & RESEARCH',
  university_shortlist: 'SHORTLIST',
};
