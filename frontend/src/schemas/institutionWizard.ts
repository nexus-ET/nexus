/** @deprecated Import from `schemas/wizard` instead. Re-exported for backward compatibility. */
export * from './wizard';

export type { CampusTypeRecord } from '../types/campusTypes';

export {
  wizardCampusItemSchema as wizardCampusSchema,
  emptyWizardCampusDraft as emptyWizardCampus,
  type WizardCampusItem as WizardCampus,
} from './wizard/step2-campus';

export {
  wizardCollegeItemSchema as wizardCollegeSchema,
  type WizardCollegeItem as WizardCollege,
} from './wizard/step3-colleges';

export {
  wizardCourseOfferingItemSchema as wizardCourseSchema,
  type WizardCourseOfferingItem as WizardCourse,
} from './wizard/step4-courses';

export {
  wizardIntakeItemSchema as wizardIntakeSchema,
  type WizardIntakeItem as WizardIntake,
} from './wizard/step5-intakes';

export {
  wizardPictureItemSchema as wizardPictureSchema,
  type WizardPictureItem as WizardPicture,
} from './wizard/step6-pictures';

export type { WizardInstitutionFormValues as WizardInstitution } from './wizard/step1-institution';
