export interface WorkProjectRecord {
  id: number;
  project_name: string | null;
  project_description: string | null;
  sort_order: number;
}

export interface WorkExperienceRecord {
  id: number;
  company_name: string | null;
  job_title: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  description: string | null;
  sort_order: number;
  projects: WorkProjectRecord[];
}

export interface WorkExperiencesResponse {
  booking_id: number;
  lead_id: number | null;
  experiences: WorkExperienceRecord[];
  saved_at: string | null;
}

export interface WorkProjectFormEntry {
  clientId: string;
  id: number | null;
  project_name: string;
  project_description: string;
}

export interface WorkExperienceFormEntry {
  clientId: string;
  id: number | null;
  company_name: string;
  job_title: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  description: string;
  projects: WorkProjectFormEntry[];
  showForm: boolean;
}

export function createEmptyProject(): WorkProjectFormEntry {
  return {
    clientId: `project-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    id: null,
    project_name: '',
    project_description: '',
  };
}

export function createEmptyExperience(showForm = true): WorkExperienceFormEntry {
  return {
    clientId: `experience-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    id: null,
    company_name: '',
    job_title: '',
    start_date: '',
    end_date: '',
    is_current: false,
    description: '',
    projects: [],
    showForm,
  };
}

export function experiencesToForm(experiences: WorkExperienceRecord[]): WorkExperienceFormEntry[] {
  return experiences.map(experience => ({
    clientId: `experience-${experience.id}`,
    id: experience.id,
    company_name: experience.company_name ?? '',
    job_title: experience.job_title ?? '',
    start_date: experience.start_date ?? '',
    end_date: experience.end_date ?? '',
    is_current: experience.is_current,
    description: experience.description ?? '',
    showForm: true,
    projects: experience.projects.map(project => ({
      clientId: `project-${project.id}`,
      id: project.id,
      project_name: project.project_name ?? '',
      project_description: project.project_description ?? '',
    })),
  }));
}

export function experiencesToSavePayload(experiences: WorkExperienceFormEntry[]) {
  return {
    experiences: experiences
      .filter(experience => experience.showForm)
      .map(experience => ({
        id: experience.id,
        company_name: experience.company_name.trim() || null,
        job_title: experience.job_title.trim() || null,
        start_date: experience.start_date.trim() || null,
        end_date: experience.is_current ? null : experience.end_date.trim() || null,
        is_current: experience.is_current,
        description: experience.description.trim() || null,
        projects: experience.projects.map(project => ({
          id: project.id,
          project_name: project.project_name.trim() || null,
          project_description: project.project_description.trim() || null,
        })),
      })),
  };
}

export function validateWorkExperiences(
  experiences: WorkExperienceFormEntry[]
): Record<string, string> {
  const errors: Record<string, string> = {};

  experiences.forEach(experience => {
    if (!experience.showForm || experience.is_current) {
      return;
    }
    if (
      experience.start_date &&
      experience.end_date &&
      experience.end_date < experience.start_date
    ) {
      errors[`${experience.clientId}-end_date`] = 'End date cannot be before start date.';
    }
  });

  return errors;
}
