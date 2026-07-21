export type ResearchProjectType =
  | 'BUSINESS'
  | 'CRIME_AND_LAW'
  | 'DRUGS_AND_DRUG_ABUSE'
  | 'EDUCATION'
  | 'ENVIRONMENTAL'
  | 'HEALTH'
  | 'MEDIA_AND_COMMUNICATION'
  | 'OTHERS'
  | 'POLITICAL_ISSUE'
  | 'PSYCHOLOGY'
  | 'RELIGION'
  | 'SOCIAL_ISSUES'
  | 'TECHNOLOGY'
  | 'TERRORISM'
  | 'WOMEN_AND_GENDER'
  | 'ENGINEERING_PHYSICAL_SCIENCES'
  | 'ART_HUMANITIES'
  | 'DATA_SCIENCE_AI'
  | 'ECONOMICS_FINANCE';

export interface ResearchProjectTypeOption {
  value: ResearchProjectType;
  label: string;
}

export const RESEARCH_PROJECT_TYPE_OPTIONS: ResearchProjectTypeOption[] = [
  { value: 'BUSINESS', label: 'Businesss' },
  { value: 'CRIME_AND_LAW', label: 'Crime and Law' },
  { value: 'DRUGS_AND_DRUG_ABUSE', label: 'Drugs and Drug Abuse' },
  { value: 'EDUCATION', label: 'Education' },
  { value: 'ENVIRONMENTAL', label: 'Environmental' },
  { value: 'HEALTH', label: 'Health' },
  { value: 'MEDIA_AND_COMMUNICATION', label: 'Media and Communication' },
  { value: 'OTHERS', label: 'Others' },
  { value: 'POLITICAL_ISSUE', label: 'Political Issue' },
  { value: 'PSYCHOLOGY', label: 'Psychology' },
  { value: 'RELIGION', label: 'Religion' },
  { value: 'SOCIAL_ISSUES', label: 'Social Issues' },
  { value: 'TECHNOLOGY', label: 'Technology' },
  { value: 'TERRORISM', label: 'Terrorism' },
  { value: 'WOMEN_AND_GENDER', label: 'Women and Gender' },
  { value: 'ENGINEERING_PHYSICAL_SCIENCES', label: 'Engineering & Physical Sciences' },
  { value: 'ART_HUMANITIES', label: 'Art & Humanities' },
  { value: 'DATA_SCIENCE_AI', label: 'Data Science & AI' },
  { value: 'ECONOMICS_FINANCE', label: 'Economics & Finance' },
];

export const DESCRIPTION_MAX_LENGTH = 500;
export const TITLE_MAX_LENGTH = 255;
export const ROLE_MAX_LENGTH = 100;

export interface ResearchProjectRecord {
  id: number;
  project_type: ResearchProjectType;
  project_type_label: string;
  project_title: string | null;
  project_description: string | null;
  publication_url: string | null;
  role: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ResearchProjectsResponse {
  booking_id: number;
  lead_id: number | null;
  project_types: ResearchProjectTypeOption[];
  projects: ResearchProjectRecord[];
  saved_at: string | null;
}

export interface ResearchProjectFormState {
  project_type: ResearchProjectType | '';
  project_title: string;
  project_description: string;
  publication_url: string;
  role: string;
}

export const emptyResearchProjectForm = (): ResearchProjectFormState => ({
  project_type: '',
  project_title: '',
  project_description: '',
  publication_url: '',
  role: '',
});

export function projectToForm(project: ResearchProjectRecord): ResearchProjectFormState {
  return {
    project_type: project.project_type,
    project_title: project.project_title ?? '',
    project_description: project.project_description ?? '',
    publication_url: project.publication_url ?? '',
    role: project.role ?? '',
  };
}

export function formToSavePayload(form: ResearchProjectFormState) {
  return {
    project_type: form.project_type,
    project_title: form.project_title.trim() || null,
    project_description: form.project_description.trim() || null,
    publication_url: form.publication_url.trim() || null,
    role: form.role.trim() || null,
  };
}

export function getProjectTypeLabel(
  value: ResearchProjectType | '',
  options: ResearchProjectTypeOption[] = RESEARCH_PROJECT_TYPE_OPTIONS
): string {
  if (!value) return '';
  return options.find(option => option.value === value)?.label ?? value;
}

export function filterProjectTypeOptions(
  search: string,
  options: ResearchProjectTypeOption[] = RESEARCH_PROJECT_TYPE_OPTIONS
): ResearchProjectTypeOption[] {
  const query = search.trim().toLowerCase();
  if (!query) return options;
  return options.filter(option => option.label.toLowerCase().includes(query));
}

export function validateResearchProjectForm(form: ResearchProjectFormState): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!form.project_type) {
    errors.project_type = 'Select a project type.';
  }
  if (form.project_description.length > DESCRIPTION_MAX_LENGTH) {
    errors.project_description = `Description must be ${DESCRIPTION_MAX_LENGTH} characters or fewer.`;
  }
  if (form.project_title.length > TITLE_MAX_LENGTH) {
    errors.project_title = `Title must be ${TITLE_MAX_LENGTH} characters or fewer.`;
  }
  if (form.role.length > ROLE_MAX_LENGTH) {
    errors.role = `Role must be ${ROLE_MAX_LENGTH} characters or fewer.`;
  }

  return errors;
}
