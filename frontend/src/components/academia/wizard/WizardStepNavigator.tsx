import { AlertTriangle, Check } from 'lucide-react';
import { WIZARD_STEP_LABELS } from '../../../schemas/wizard';

interface WizardStepNavigatorProps {
  currentStep: number;
  completedSteps: number[];
  stepsWithData: number[];
  onStepClick: (step: number) => void;
}

const WizardStepNavigator: React.FC<WizardStepNavigatorProps> = ({
  currentStep,
  completedSteps,
  stepsWithData,
  onStepClick,
}) => (
  <nav className="-mb-px flex flex-wrap gap-1" aria-label="Wizard steps" role="tablist">
    {WIZARD_STEP_LABELS.map((label, index) => {
      const step = index + 1;
      const isComplete = completedSteps.includes(step);
      const hasData = stepsWithData.includes(step);
      const isActive = currentStep === step;
      return (
        <button
          key={label}
          type="button"
          role="tab"
          aria-selected={isActive}
          aria-current={isActive ? 'step' : undefined}
          onClick={() => onStepClick(step)}
          className={`relative inline-flex items-center gap-2 border-b-2 px-4 py-3 text-base font-bold transition-colors ${
            isActive
              ? 'border-accent text-accent'
              : isComplete
                ? 'border-transparent text-text-main hover:border-border-subtle hover:text-accent'
                : 'border-transparent text-text-muted hover:border-border-subtle hover:text-text-main'
          }`}
        >
          {isComplete && !isActive ? (
            <Check size={16} className="shrink-0 text-emerald-600" aria-hidden="true" />
          ) : null}
          <span className="flex flex-col items-start leading-tight">
            <span>
              {step}. {label}
            </span>
            {!hasData ? (
              <span
                className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800"
                title="Data not added"
              >
                <AlertTriangle size={11} aria-hidden="true" />
                Not added
              </span>
            ) : null}
          </span>
        </button>
      );
    })}
  </nav>
);

export default WizardStepNavigator;
