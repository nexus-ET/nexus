import { z } from 'zod';

import { emptyToNull } from './shared';

const optionalDate = z.preprocess(emptyToNull, z.string().nullable().optional());

export const wizardIntakeItemSchema = z
  .object({
    local_id: z.string().optional(),
    name: z.string().min(1, 'Intake name is required').max(255),
    intake_code: z.preprocess(emptyToNull, z.string().max(50).nullable().optional()),
    start_date: optionalDate,
    end_date: optionalDate,
    application_deadline: optionalDate,
    enrollment_cap: z
      .number({ error: 'Enrollment cap must be a number' })
      .int('Enrollment cap must be a whole number')
      .positive('Enrollment cap must be greater than zero')
      .max(100000, 'Enrollment cap is too large')
      .optional()
      .nullable(),
  })
  .superRefine((value, ctx) => {
    if (value.start_date && value.end_date && value.start_date > value.end_date) {
      ctx.addIssue({
        code: 'custom',
        message: 'Start date must be on or before end date',
        path: ['end_date'],
      });
    }
    if (
      value.application_deadline &&
      value.end_date &&
      value.application_deadline > value.end_date
    ) {
      ctx.addIssue({
        code: 'custom',
        message: 'Application deadline must be on or before intake end date',
        path: ['application_deadline'],
      });
    }
  });

export const wizardIntakesStepSchema = z.array(wizardIntakeItemSchema);

export type WizardIntakeItem = z.infer<typeof wizardIntakeItemSchema>;

export const emptyWizardIntakeDraft: WizardIntakeItem = {
  local_id: '',
  name: '',
  intake_code: null,
  start_date: null,
  end_date: null,
  application_deadline: null,
  enrollment_cap: null,
};

export function createEmptyWizardIntakeDraft(): WizardIntakeItem {
  return {
    ...emptyWizardIntakeDraft,
    local_id: crypto.randomUUID(),
  };
}

export function hydrateWizardIntake(raw: Partial<WizardIntakeItem>): WizardIntakeItem {
  return {
    ...createEmptyWizardIntakeDraft(),
    ...raw,
    local_id: raw.local_id || crypto.randomUUID(),
    name: raw.name || '',
    intake_code: raw.intake_code || null,
    start_date: raw.start_date || null,
    end_date: raw.end_date || null,
    application_deadline: raw.application_deadline || null,
    enrollment_cap: raw.enrollment_cap ?? null,
  };
}

export function intakeToApiPayload(intake: WizardIntakeItem) {
  const { local_id: _localId, ...rest } = intake;
  return {
    ...rest,
    name: intake.name.trim(),
    intake_code: intake.intake_code?.trim() || null,
    start_date: intake.start_date || null,
    end_date: intake.end_date || null,
    application_deadline: intake.application_deadline || null,
    enrollment_cap: intake.enrollment_cap ?? null,
  };
}
