export interface AcademiaSectionTab {
  key: string;
  label: string;
  path: string;
}

export interface AcademiaNavSection {
  key: 'geography' | 'institutions' | 'framework';
  label: string;
  path: string;
  tabbed?: boolean;
  tabs?: AcademiaSectionTab[];
  items: AcademiaNavItem[];
}

export type AcademiaEntityKey =
  | 'countries'
  | 'states'
  | 'cities'
  | 'institutions'
  | 'campuses'
  | 'colleges'
  | 'levels'
  | 'programs'
  | 'majors'
  | 'courses'
  | 'summary';

export interface AcademiaNavItem {
  key: AcademiaEntityKey;
  label: string;
  path: string;
  singular: string;
  apiPath: string;
}

export const INSTITUTIONS_SECTION_PATH = '/academia/institutions';
export const GEOGRAPHY_SECTION_PATH = '/academia/geography';
export const FRAMEWORK_SECTION_PATH = '/academia/framework';

export const INSTITUTIONS_NEW_PATH = `${INSTITUTIONS_SECTION_PATH}/new`;
export const institutionEditPath = (institutionId: number | string) =>
  `${INSTITUTIONS_SECTION_PATH}/edit/${institutionId}`;
export const institutionWizardPath = (draftId: number | string) =>
  `${INSTITUTIONS_SECTION_PATH}/wizard/${draftId}`;
export const institutionHistoryPath = (institutionId: number | string) =>
  `${INSTITUTIONS_SECTION_PATH}/${institutionId}/history`;
export const institutionIntakesPath = (institutionId: number | string) =>
  `${INSTITUTIONS_SECTION_PATH}/${institutionId}/intakes`;
export const INSTITUTIONS_CALENDARS_PATH = `${INSTITUTIONS_SECTION_PATH}/calendars`;

export const INSTITUTIONS_COLLEGES_PATH = `${INSTITUTIONS_SECTION_PATH}/colleges`;

export const INSTITUTIONS_TABS: AcademiaSectionTab[] = [
  { key: 'directory', label: 'Summary', path: INSTITUTIONS_SECTION_PATH },
];

export const GEOGRAPHY_TABS: AcademiaSectionTab[] = [
  { key: 'countries', label: 'Countries', path: `${GEOGRAPHY_SECTION_PATH}/countries` },
  { key: 'states', label: 'States', path: `${GEOGRAPHY_SECTION_PATH}/states` },
  { key: 'cities', label: 'Cities', path: `${GEOGRAPHY_SECTION_PATH}/cities` },
];

export const FRAMEWORK_TABS: AcademiaSectionTab[] = [
  { key: 'summary', label: 'Summary View', path: `${FRAMEWORK_SECTION_PATH}/summary` },
  { key: 'majors', label: 'Majors', path: `${FRAMEWORK_SECTION_PATH}/majors` },
  { key: 'levels', label: 'Levels', path: `${FRAMEWORK_SECTION_PATH}/levels` },
  { key: 'programs', label: 'Programs', path: `${FRAMEWORK_SECTION_PATH}/programs` },
  { key: 'courses', label: 'Courses', path: `${FRAMEWORK_SECTION_PATH}/courses` },
];

export const ACADEMIA_HUB_SECTIONS: AcademiaNavSection[] = [
  {
    key: 'institutions',
    label: 'Institutions',
    path: INSTITUTIONS_SECTION_PATH,
    tabbed: true,
    tabs: INSTITUTIONS_TABS,
    items: [
      {
        key: 'institutions',
        label: 'Institutions',
        singular: 'Institution',
        path: INSTITUTIONS_SECTION_PATH,
        apiPath: 'academia/institutions',
      },
    ],
  },
  {
    key: 'framework',
    label: 'Academic Framework',
    path: FRAMEWORK_SECTION_PATH,
    tabbed: true,
    tabs: FRAMEWORK_TABS,
    items: [
      {
        key: 'summary',
        label: 'Summary View',
        singular: 'Hierarchy',
        path: `${FRAMEWORK_SECTION_PATH}/summary`,
        apiPath: 'academia/hierarchy',
      },
      {
        key: 'majors',
        label: 'Majors',
        singular: 'Major',
        path: `${FRAMEWORK_SECTION_PATH}/majors`,
        apiPath: 'academia/education-majors',
      },
      {
        key: 'levels',
        label: 'Levels',
        singular: 'Level',
        path: `${FRAMEWORK_SECTION_PATH}/levels`,
        apiPath: 'academia/levels',
      },
      {
        key: 'programs',
        label: 'Programs',
        singular: 'Program',
        path: `${FRAMEWORK_SECTION_PATH}/programs`,
        apiPath: 'academia/degrees',
      },
      {
        key: 'courses',
        label: 'Courses',
        singular: 'Course',
        path: `${FRAMEWORK_SECTION_PATH}/courses`,
        apiPath: 'academia/courses',
      },
    ],
  },
  {
    key: 'geography',
    label: 'Geography',
    path: GEOGRAPHY_SECTION_PATH,
    tabbed: true,
    tabs: GEOGRAPHY_TABS,
    items: [
      {
        key: 'countries',
        label: 'Countries',
        singular: 'Country',
        path: `${GEOGRAPHY_SECTION_PATH}/countries`,
        apiPath: 'academia/countries',
      },
      {
        key: 'states',
        label: 'States',
        singular: 'State',
        path: `${GEOGRAPHY_SECTION_PATH}/states`,
        apiPath: 'academia/states',
      },
      {
        key: 'cities',
        label: 'Cities',
        singular: 'City',
        path: `${GEOGRAPHY_SECTION_PATH}/cities`,
        apiPath: 'academia/cities',
      },
    ],
  },
];

export const ACADEMIA_NAV_ITEMS = ACADEMIA_HUB_SECTIONS.flatMap(section => section.items);

export const getAcademiaNavItem = (
  sectionKey: string,
  entityKey: string
): AcademiaNavItem | undefined =>
  ACADEMIA_NAV_ITEMS.find(item => item.path === `/academia/${sectionKey}/${entityKey}`);

export const getAcademiaSection = (
  sectionKey: string
): AcademiaNavSection | undefined =>
  ACADEMIA_HUB_SECTIONS.find(section => section.key === sectionKey);

export const getAcademiaSectionLabel = (sectionKey: string): string =>
  getAcademiaSection(sectionKey)?.label || sectionKey;
