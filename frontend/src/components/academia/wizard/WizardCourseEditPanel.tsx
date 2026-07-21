import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';

import RichTextEditor from '../../ui/rich-text-editor';
import InlineExpandPanel from '../form/InlineExpandPanel';
import WizardFieldError from './form/WizardFieldError';
import { emptyToNull, richTextField } from '../../../schemas/wizard/shared';
import { wizardInputClass, wizardLabelClass } from './form/wizardFormStyles';

const courseEditSchema = z.object({
  course_code: z.preprocess(
    emptyToNull,
    z
      .string()
      .max(50, 'Course code must be 50 characters or fewer')
      .regex(
        /^[A-Z0-9_-]+$/i,
        'Course code may only contain letters, numbers, dashes, and underscores'
      )
      .nullable()
      .optional()
  ),
  credits: z
    .number({ error: 'Credits must be a number' })
    .min(0, 'Credits cannot be negative')
    .max(30, 'Credits cannot exceed 30')
    .optional()
    .nullable(),
  syllabus_outline: richTextField(5000, 'Course description'),
});

export type WizardCourseEditValues = z.infer<typeof courseEditSchema>;

interface WizardCourseEditPanelProps {
  title: string;
  subtitle?: string;
  defaultValues: WizardCourseEditValues;
  onClose: () => void;
  onSave: (values: WizardCourseEditValues) => Promise<boolean> | boolean;
}

const WizardCourseEditPanel: React.FC<WizardCourseEditPanelProps> = ({
  title,
  subtitle,
  defaultValues,
  onClose,
  onSave,
}) => {
  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<WizardCourseEditValues>({
    resolver: zodResolver(courseEditSchema),
    defaultValues,
    mode: 'onSubmit',
  });

  const submit = handleSubmit(async values => {
    const saved = await onSave(values);
    if (saved) onClose();
  });

  return (
    <InlineExpandPanel
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => void submit()}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
            Save course details
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className={wizardLabelClass}>Course code</label>
          <input {...register('course_code')} className={wizardInputClass(Boolean(errors.course_code))} />
          <WizardFieldError message={errors.course_code?.message} />
        </div>
        <div>
          <label className={wizardLabelClass}>Credits</label>
          <Controller
            control={control}
            name="credits"
            render={({ field }) => (
              <input
                type="number"
                min={0}
                max={30}
                value={field.value ?? ''}
                onChange={event =>
                  field.onChange(event.target.value ? Number(event.target.value) : null)
                }
                className={wizardInputClass(Boolean(errors.credits))}
              />
            )}
          />
          <WizardFieldError message={errors.credits?.message} />
        </div>
        <div className="md:col-span-2">
          <Controller
            control={control}
            name="syllabus_outline"
            render={({ field, fieldState }) => (
              <RichTextEditor
                label="Course description"
                content={field.value || ''}
                onChange={field.onChange}
                maxLength={5000}
                error={fieldState.error?.message}
              />
            )}
          />
        </div>
      </div>
    </InlineExpandPanel>
  );
};

export default WizardCourseEditPanel;
