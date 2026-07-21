export type ActivityCategory =
  | 'ARTS_AND_CULTURE'
  | 'EVENT_ORGANIZING'
  | 'EXTRACURRICULAR_CLUBS_TEAMS'
  | 'GOVERNMENT'
  | 'HOBBIES'
  | 'LANGUAGE_AND_LINGUISTICS'
  | 'LEADERSHIP'
  | 'MAINSTREAM_MEDIA_AND_SOCIAL_MEDIA'
  | 'MUSIC'
  | 'OTHERS'
  | 'PART_TIME_OR_SUMMER_JOBS'
  | 'PERFORMANCE_ART'
  | 'POLITICAL_CAMPAIGNS'
  | 'RELIGIOUS'
  | 'SOCIAL_ACTIVISM'
  | 'SPORTS_AND_RECREATION'
  | 'STUDENT_BODY'
  | 'TECHNOLOGY'
  | 'TRAININGS'
  | 'TRAVELING'
  | 'VOLUNTARY_WORK_COMMUNITY_SERVICE'
  | 'WORKSHOPS';

export interface ActivityCategoryOption {
  value: ActivityCategory;
  label: string;
}

export const ACTIVITY_CATEGORY_OPTIONS: ActivityCategoryOption[] = [
  { value: 'ARTS_AND_CULTURE', label: 'Arts and Culture' },
  { value: 'EVENT_ORGANIZING', label: 'Event Organizing' },
  { value: 'EXTRACURRICULAR_CLUBS_TEAMS', label: 'Extracurricular clubs/teams' },
  { value: 'GOVERNMENT', label: 'Government' },
  { value: 'HOBBIES', label: 'Hobbies' },
  { value: 'LANGUAGE_AND_LINGUISTICS', label: 'Language and Linguistics' },
  { value: 'LEADERSHIP', label: 'Leadership' },
  { value: 'MAINSTREAM_MEDIA_AND_SOCIAL_MEDIA', label: 'Mainstream Media and Social Media' },
  { value: 'MUSIC', label: 'Music' },
  { value: 'OTHERS', label: 'Others' },
  { value: 'PART_TIME_OR_SUMMER_JOBS', label: 'Part-time or summer jobs' },
  { value: 'PERFORMANCE_ART', label: 'Performance Art' },
  { value: 'POLITICAL_CAMPAIGNS', label: 'Political Campaigns' },
  { value: 'RELIGIOUS', label: 'Religious' },
  { value: 'SOCIAL_ACTIVISM', label: 'Social Activism' },
  { value: 'SPORTS_AND_RECREATION', label: 'Sports and Recreation' },
  { value: 'STUDENT_BODY', label: 'Student Body' },
  { value: 'TECHNOLOGY', label: 'Technology' },
  { value: 'TRAININGS', label: 'Trainings' },
  { value: 'TRAVELING', label: 'Traveling' },
  { value: 'VOLUNTARY_WORK_COMMUNITY_SERVICE', label: 'Voluntary Work / Community Service' },
  { value: 'WORKSHOPS', label: 'Workshops' },
];

export const DESCRIPTION_MAX_LENGTH = 500;
export const NAME_MAX_LENGTH = 255;
export const ROLE_MAX_LENGTH = 100;

export interface NonAcademicActivityRecord {
  id: number;
  activity_category: ActivityCategory | null;
  activity_category_label: string | null;
  activity_name: string | null;
  role_or_title: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface NonAcademicActivitiesResponse {
  booking_id: number;
  lead_id: number | null;
  activity_categories: ActivityCategoryOption[];
  activities: NonAcademicActivityRecord[];
  saved_at: string | null;
}

export interface NonAcademicActivityFormState {
  activity_category: ActivityCategory | '';
  activity_name: string;
  role_or_title: string;
  start_date: string;
  end_date: string;
  description: string;
}

export const emptyNonAcademicActivityForm = (): NonAcademicActivityFormState => ({
  activity_category: '',
  activity_name: '',
  role_or_title: '',
  start_date: '',
  end_date: '',
  description: '',
});

export function activityToForm(activity: NonAcademicActivityRecord): NonAcademicActivityFormState {
  return {
    activity_category: activity.activity_category ?? '',
    activity_name: activity.activity_name ?? '',
    role_or_title: activity.role_or_title ?? '',
    start_date: activity.start_date ?? '',
    end_date: activity.end_date ?? '',
    description: activity.description ?? '',
  };
}

export function formToSavePayload(form: NonAcademicActivityFormState) {
  return {
    activity_category: form.activity_category || null,
    activity_name: form.activity_name.trim() || null,
    role_or_title: form.role_or_title.trim() || null,
    start_date: form.start_date.trim() || null,
    end_date: form.end_date.trim() || null,
    description: form.description.trim() || null,
  };
}

export function getActivityCategoryLabel(
  value: ActivityCategory | '',
  options: ActivityCategoryOption[] = ACTIVITY_CATEGORY_OPTIONS
): string {
  if (!value) return '';
  return options.find(option => option.value === value)?.label ?? value;
}

export function filterActivityCategoryOptions(
  search: string,
  options: ActivityCategoryOption[] = ACTIVITY_CATEGORY_OPTIONS
): ActivityCategoryOption[] {
  const query = search.trim().toLowerCase();
  if (!query) return options;
  return options.filter(option => option.label.toLowerCase().includes(query));
}

export function validateNonAcademicActivityForm(
  form: NonAcademicActivityFormState
): Record<string, string> {
  const errors: Record<string, string> = {};

  if (
    form.start_date &&
    form.end_date &&
    form.end_date < form.start_date
  ) {
    errors.end_date = 'End date cannot be before start date.';
  }
  if (form.description.length > DESCRIPTION_MAX_LENGTH) {
    errors.description = `Description must be ${DESCRIPTION_MAX_LENGTH} characters or fewer.`;
  }
  if (form.activity_name.length > NAME_MAX_LENGTH) {
    errors.activity_name = `Activity name must be ${NAME_MAX_LENGTH} characters or fewer.`;
  }
  if (form.role_or_title.length > ROLE_MAX_LENGTH) {
    errors.role_or_title = `Role must be ${ROLE_MAX_LENGTH} characters or fewer.`;
  }

  return errors;
}

export function formatActivityDateRange(
  startDate: string | null,
  endDate: string | null
): string | null {
  if (!startDate && !endDate) return null;
  const format = (value: string) =>
    new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
      month: 'short',
      year: 'numeric',
    });
  if (startDate && endDate) return `${format(startDate)} – ${format(endDate)}`;
  if (startDate) return `${format(startDate)} – Present`;
  return `Until ${format(endDate!)}`;
}
