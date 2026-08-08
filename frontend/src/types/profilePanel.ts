export type ProfilePanelTab =
  | 'aspirations'
  | 'profile'
  | 'academia'
  | 'non_academia'
  | 'digital_presence'
  | 'test_scores'
  | 'work_projects'
  | 'projects_research'
  | 'university_shortlist'
  | 'profile_pulse';

export const PROFILE_PANEL_TAB_LABELS: Record<ProfilePanelTab, string> = {
  aspirations: 'ASPIRATIONS',
  profile: 'PERSONAL',
  academia: 'ACADEMIA',
  non_academia: 'NON-ACADEMIA',
  digital_presence: 'DIGITAL PRESENCE',
  test_scores: 'TEST SCORES',
  work_projects: 'PROFESSIONAL',
  projects_research: 'PROJECTS & RESEARCH',
  university_shortlist: 'SHORTLIST',
  profile_pulse: 'PROFILE PULSE',
};
